"""AstroDash — Astrophotography Imaging Dashboard."""
import os
import json
import csv
import io
import asyncio
import logging
from datetime import datetime, date, timedelta
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .models.database import (
    Base, get_engine, get_session, create_tables,
    UserSettings, Mount, Telescope, Camera, Filter, Accessory,
    UserEquipment, DSOTarget, ImagingProject, SessionLog, ForecastCache
)
from .models.equipment_seed import CAMERAS, MOUNTS, TELESCOPES, FILTERS, ACCESSORIES
from .models.dso_catalog import DSO_CATALOG
from .models.expanded_catalog import EXPANDED_CATALOG
from .services.astrospheric import (
    fetch_forecast, fetch_sky, compute_tonight_forecast, poll_and_cache
)
from .services.astronomy import (
    get_twilight_times, compute_target_position, compute_target_visibility,
    get_moon_info, moon_separation
)
from .services.notifications import send_imaging_alert

logger = logging.getLogger(__name__)


def get_filter_channels(filter_type: str, bandpass: str, camera_color_type: str = "Color (OSC)") -> list:
    """Determine which imaging channels a filter contributes to.
    
    Returns a list of channel strings: "l", "r", "g", "b", "ha", "oiii", "sii"
    Based on filter_type, bandpass text, and camera type (OSC vs Mono).
    
    For OSC cameras:
      - Broadband/LP filters → l, r, g, b (Bayer captures all)
      - Duo-band (e.g. L-eXtreme Hα+OIII) → ha, oiii only
      - Quad-band LP (e.g. L-Quad) → l, r, g, b, ha, oiii
    For Mono cameras:
      - L filter → l
      - R filter → r, G filter → g, B filter → b
      - Narrowband → ha, oiii, sii as appropriate
    """
    if not filter_type:
        # No filter info: assume broadband
        if camera_color_type == "Mono":
            return ["l"]  # mono with no filter = luminance
        return ["l", "r", "g", "b"]
    
    ft = filter_type.lower()
    bp = (bandpass or "").lower()
    is_mono = (camera_color_type == "Mono")
    
    # Mono-specific single-channel filters
    if is_mono:
        if "luminance" in ft or ft == "l":
            return ["l"]
        if ft in ("red", "r"):
            return ["r"]
        if ft in ("green", "g"):
            return ["g"]
        if ft in ("blue", "b"):
            return ["b"]
    
    # Single-channel narrowband filters (both OSC and mono)
    if "hydrogen" in ft or ft == "hydrogen-alpha":
        return ["ha"]
    if "oxygen" in ft or ft == "oxygen-iii":
        return ["oiii"]
    if "sulfur" in ft or ft == "sulfur-ii":
        return ["sii"]
    
    # Broadband / light pollution / UV-IR cut
    if any(x in ft for x in ["broadband", "uv/ir", "uv-ir"]):
        if is_mono:
            return ["l"]  # mono + broadband = luminance
        return ["l", "r", "g", "b"]
    
    # Duo-band, tri-band, quad-band — parse bandpass text
    channels = []
    if "ha" in bp or "h-alpha" in bp or "hα" in bp or "hydrogen" in bp:
        channels.append("ha")
    if "oiii" in bp or "o-iii" in bp or "oxygen" in bp:
        channels.append("oiii")
    if "sii" in bp or "s-ii" in bp or "sulfur" in bp:
        channels.append("sii")
    # Quad-band LP filters like L-Quad Enhance also contribute LRGB
    if "quad" in ft and "lp" in ft:
        if not is_mono:
            channels.extend(["l", "r", "g", "b"])
    
    if channels:
        return list(dict.fromkeys(channels))  # deduplicate, preserve order
    
    # Fallback
    if is_mono:
        return ["l"]
    return ["l", "r", "g", "b"]


def compute_channel_integration(filter_name: str, total_min: float, db, camera_name: str = None) -> dict:
    """Given a filter name, total integration, and optional camera, return per-channel minutes.
    
    Each channel gets the full integration time (dual-band filters capture
    both channels simultaneously; OSC cameras capture L/R/G/B simultaneously).
    """
    result = {"l": 0.0, "r": 0.0, "g": 0.0, "b": 0.0, "ha": 0.0, "oiii": 0.0, "sii": 0.0}
    if not total_min:
        return result
    
    # Determine camera type
    camera_color_type = "Color (OSC)"
    if camera_name:
        cam = db.query(Camera).filter(Camera.name == camera_name).first()
        if cam and cam.color_type:
            camera_color_type = cam.color_type
    
    if not filter_name:
        # No filter = broadband
        channels = ["l", "r", "g", "b"] if camera_color_type != "Mono" else ["l"]
    else:
        # Look up filter in catalog
        f = db.query(Filter).filter(Filter.name == filter_name).first()
        if f:
            channels = get_filter_channels(f.filter_type, f.bandpass, camera_color_type)
            logger.info(f"Channel mapping: filter='{filter_name}' camera='{camera_name}' type='{camera_color_type}' -> {channels}")
        else:
            channels = ["l", "r", "g", "b"] if camera_color_type != "Mono" else ["l"]
            logger.warning(f"Channel mapping: filter='{filter_name}' NOT FOUND, defaulting to {channels}")
    
    for ch in channels:
        if ch in result:
            result[ch] = total_min
    
    return result


def _get_utc_offset(timezone_str: str = None, longitude: float = None) -> float:
    """Get UTC offset in hours for astronomical display purposes.
    
    For astronomical computations (twilight, target visibility), the UTC offset
    must correspond to the LOCATION, not necessarily the user's wall-clock timezone.
    
    When longitude is provided, we validate the timezone against it and fall back
    to a longitude-based approximation if they disagree by more than 2 hours.
    This handles the case where a user changes their lat/lon without updating timezone.
    """
    tz_offset = None
    if timezone_str:
        try:
            import zoneinfo
            zone = zoneinfo.ZoneInfo(timezone_str)
            now = datetime.now(zone)
            offset_seconds = now.utcoffset().total_seconds()
            tz_offset = offset_seconds / 3600.0
        except Exception:
            fallbacks = {
                "America/New_York": -5, "America/Chicago": -6,
                "America/Denver": -7, "America/Los_Angeles": -8,
                "America/Phoenix": -7, "America/Anchorage": -9,
                "Pacific/Honolulu": -10, "America/Halifax": -4,
                "America/St_Johns": -3.5, "America/Edmonton": -7,
                "America/Winnipeg": -6, "America/Toronto": -5,
                "America/Vancouver": -8, "Europe/London": 0,
                "Europe/Paris": 1, "Europe/Berlin": 1,
                "Australia/Sydney": 11, "Asia/Tokyo": 9,
            }
            if timezone_str in fallbacks:
                tz_offset = fallbacks[timezone_str]
    
    # Approximate UTC offset from longitude (every 15° ≈ 1 hour)
    lon_offset = round(longitude / 15.0) if longitude is not None else None
    
    if tz_offset is not None and lon_offset is not None:
        # If timezone and longitude agree (within 2h), trust the timezone (it handles DST)
        if abs(tz_offset - lon_offset) <= 2:
            return tz_offset
        # They disagree — location and timezone are mismatched.
        # Use longitude-based offset for correct astronomical display.
        logger.warning(f"Timezone '{timezone_str}' (UTC{tz_offset:+.1f}) doesn't match "
                      f"longitude {longitude:.1f} (expected ~UTC{lon_offset:+.0f}). "
                      f"Using longitude-based offset for astronomical calculations.")
        return float(lon_offset)
    
    if tz_offset is not None:
        return tz_offset
    if lon_offset is not None:
        return float(lon_offset)
    
    return 0.0

logging.basicConfig(level=logging.INFO)

DB_PATH = os.environ.get("ASTRODASH_DB", "data/astrodash.db")
scheduler = AsyncIOScheduler()


def _auto_migrate(engine):
    """Add any missing columns to existing tables (lightweight schema migration)."""
    import sqlalchemy
    inspector = sqlalchemy.inspect(engine)
    
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing_cols:
                col_type = col.type.compile(engine.dialect)
                default = "DEFAULT 0.0" if "FLOAT" in str(col_type).upper() else ""
                sql = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type} {default}'
                try:
                    with engine.connect() as conn:
                        conn.execute(sqlalchemy.text(sql))
                        conn.commit()
                    logger.info(f"Migration: added column {table.name}.{col.name} ({col_type})")
                except Exception as e:
                    logger.debug(f"Migration skip {table.name}.{col.name}: {e}")


_init_status = {"state": "starting", "message": "Initializing...", "progress": 0}

def init_database():
    """Initialize database and seed catalog data if empty."""
    global _init_status
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    engine = get_engine(DB_PATH)
    create_tables(engine)
    
    # Auto-migrate: add any missing columns to existing tables
    _auto_migrate(engine)
    
    session = get_session(engine)
    
    try:
        steps = 7
        step = 0
        
        # Seed equipment if empty
        if session.query(Camera).count() == 0:
            _init_status = {"state": "seeding", "message": "Seeding camera catalog...", "progress": int(step/steps*100)}
            logger.info("Seeding camera catalog...")
            for cam_data in CAMERAS:
                session.add(Camera(**cam_data))
        step += 1
        
        if session.query(Mount).count() == 0:
            _init_status = {"state": "seeding", "message": "Seeding mount catalog...", "progress": int(step/steps*100)}
            logger.info("Seeding mount catalog...")
            for m_data in MOUNTS:
                session.add(Mount(**m_data))
        step += 1
        
        if session.query(Telescope).count() == 0:
            _init_status = {"state": "seeding", "message": "Seeding telescope catalog...", "progress": int(step/steps*100)}
            logger.info("Seeding telescope catalog...")
            for t_data in TELESCOPES:
                session.add(Telescope(**t_data))
        step += 1
        
        if session.query(Filter).count() == 0:
            _init_status = {"state": "seeding", "message": "Seeding filter catalog...", "progress": int(step/steps*100)}
            logger.info("Seeding filter catalog...")
            for f_data in FILTERS:
                session.add(Filter(**f_data))
        else:
            # Update bandpass info for existing catalog filters
            for f_data in FILTERS:
                existing = session.query(Filter).filter(
                    Filter.name == f_data["name"],
                    Filter.manufacturer == f_data["manufacturer"],
                    Filter.is_catalog == True
                ).first()
                if existing and existing.bandpass != f_data.get("bandpass"):
                    existing.bandpass = f_data.get("bandpass")
                    existing.filter_type = f_data.get("filter_type", existing.filter_type)
                    existing.broadband_friendly = f_data.get("broadband_friendly", existing.broadband_friendly)
                    existing.narrowband_friendly = f_data.get("narrowband_friendly", existing.narrowband_friendly)
        step += 1
        
        if session.query(Accessory).count() == 0:
            _init_status = {"state": "seeding", "message": "Seeding accessory catalog...", "progress": int(step/steps*100)}
            logger.info("Seeding accessory catalog...")
            for a_data in ACCESSORIES:
                session.add(Accessory(**a_data))
        step += 1
        
        # Build combined catalog: base + expanded, deduped by catalog_id
        _seen_ids = set()
        FULL_CATALOG = []
        for dso_data in DSO_CATALOG + EXPANDED_CATALOG:
            cid = dso_data.get("catalog_id", "")
            if cid and cid not in _seen_ids:
                _seen_ids.add(cid)
                FULL_CATALOG.append(dso_data)
        
        if session.query(DSOTarget).count() == 0:
            _init_status = {"state": "seeding", "message": "Seeding target catalog...", "progress": int(step/steps*100)}
            logger.info(f"Seeding DSO catalog ({len(FULL_CATALOG)} targets)...")
            for i, dso_data in enumerate(FULL_CATALOG):
                session.add(DSOTarget(**dso_data))
                if i % 100 == 0 and len(FULL_CATALOG) > 100:
                    pct = int((step + i/len(FULL_CATALOG)) / steps * 100)
                    _init_status = {"state": "seeding", "message": f"Seeding targets... ({i}/{len(FULL_CATALOG)})", "progress": pct}
        else:
            # Migrate: insert any new catalog targets missing from existing database
            existing_ids = {r[0] for r in session.query(DSOTarget.catalog_id).all() if r[0]}
            added = 0
            for dso_data in FULL_CATALOG:
                if dso_data.get("catalog_id") and dso_data["catalog_id"] not in existing_ids:
                    session.add(DSOTarget(**dso_data))
                    added += 1
            if added:
                logger.info(f"Added {added} new catalog targets to existing database")
        step += 1
        
        # Ensure settings row exists
        if session.query(UserSettings).count() == 0:
            session.add(UserSettings(id=1))
        
        _init_status = {"state": "seeding", "message": "Committing to database...", "progress": 95}
        session.commit()
        _init_status = {"state": "ready", "message": "Ready", "progress": 100}
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database init error: {e}")
        _init_status = {"state": "error", "message": str(e), "progress": 0}
        session.rollback()
    finally:
        session.close()


async def scheduled_poll():
    """Scheduled forecast polling — runs every 6 hours (matching Astrospheric update cadence)."""
    await poll_and_cache(DB_PATH)


async def check_notifications():
    """Check if it's time to send an imaging notification. Runs every 10 minutes."""
    from .models.database import UserSettings
    import time
    
    try:
        session = get_db()
        settings = session.query(UserSettings).first()
        if not settings or not settings.notify_enabled:
            return
        if not settings.latitude or not settings.longitude:
            return
        
        now_utc = datetime.utcnow()
        
        # Compute tonight's astronomical dusk (returned in local time)
        utc_offset_hours = _get_utc_offset(settings.timezone, settings.longitude)
        
        # Convert 'now' to the user's local time to compare with local dusk time
        now = now_utc + timedelta(hours=utc_offset_hours)
        today_str = now.strftime("%Y-%m-%d")
        now_ts = time.time()
        try:
            from .services.astronomy import get_twilight_times
            twilight = get_twilight_times(settings.latitude, settings.longitude,
                                          utc_offset_hours=utc_offset_hours)
        except Exception as e:
            logger.warning(f"Notification check: twilight calc failed: {e}")
            return
        
        # Parse astronomical dusk time string back to a datetime for comparison
        astro_dusk_str = twilight.get("astronomical_dusk")
        if not astro_dusk_str:
            return
        
        # Convert dusk string (e.g. "8:42 PM") to today's datetime
        try:
            dusk_time = datetime.strptime(astro_dusk_str, "%I:%M %p").replace(
                year=now.year, month=now.month, day=now.day)
        except ValueError:
            logger.warning(f"Notification check: could not parse dusk time '{astro_dusk_str}'")
            return
        
        hours_before = settings.notify_hours_before_dark or 6
        interval_hours = settings.notify_interval_hours or 24
        quiet_start = settings.notify_quiet_start  # None means no quiet hours
        
        # First notification time: dusk minus hours_before_dark
        first_notify_time = dusk_time - timedelta(hours=hours_before)
        
        logger.debug(f"Notification check: local_now={now.strftime('%I:%M %p')}, "
                     f"dusk={astro_dusk_str}, first_alert={first_notify_time.strftime('%I:%M %p')}, "
                     f"utc_offset={utc_offset_hours}h")
        
        # Check quiet hours — don't notify before this local hour
        if quiet_start is not None and now.hour < quiet_start:
            return
        
        # Are we past the first notification time?
        if now < first_notify_time:
            return
        
        # Are we past dusk? Stop sending for tonight.
        if now > dusk_time:
            return
        
        # Check if we already sent today and whether it's time for a repeat
        if settings.notify_last_sent_date == today_str and settings.notify_last_sent_ts:
            # Already sent today — check repeat interval
            if interval_hours >= 24:
                # Once per night, already sent
                return
            elapsed_hours = (now_ts - settings.notify_last_sent_ts) / 3600.0
            if elapsed_hours < interval_hours:
                return
        
        # Time to potentially send! Get the current forecast.
        cache = session.query(ForecastCache).order_by(ForecastCache.fetched_at.desc()).first()
        if not cache:
            # No API key or no forecast data — can't send
            return
        
        # Reconstruct forecast
        cloud_data = cache.cloud_data or []
        all_hours = {
            "cloud": cloud_data,
            "transparency": cache.transparency_data or [],
            "seeing": cache.seeing_data or [],
            "wind": cache.wind_data or [],
            "temperature": cache.temperature_data or [],
            "dewpoint": cache.dewpoint_data or [],
            "hours": [entry.get("hour", 0) if isinstance(entry, dict) else 0 for entry in cloud_data],
        }
        img_start = twilight.get("imaging_start_hour")
        img_end = settings.imaging_end_hour if settings.imaging_end_hour is not None else 1
        moon_ill = cache.moon_illumination or 0
        
        forecast = compute_tonight_forecast(all_hours, img_start, img_end,
                                             moon_illumination=moon_ill)
        
        score = forecast.get("score", 0)
        threshold = settings.notify_go_threshold or 70
        
        # Decide whether to send
        if score >= threshold:
            # GO — send notification
            pass
        elif settings.notify_nogo:
            # NO-GO notification enabled — send only once (at first_notify_time), no repeats
            if settings.notify_last_sent_date == today_str:
                return  # Already sent the NO-GO today
        else:
            # Below threshold, NO-GO notifications disabled
            return
        
        # Send the notification
        from .services.notifications import build_variables, render_template, send_notification, DEFAULT_TEMPLATE
        variables = build_variables(forecast)
        template = settings.notify_template or DEFAULT_TEMPLATE
        message = render_template(template, variables)
        
        verdict = variables.get("verdict", "?")
        if score >= threshold:
            title = f"🔭 {verdict} for Imaging Tonight!"
        else:
            title = f"🌧️ NO-GO Tonight (Score: {score})"
        
        result = await send_notification(settings, title, message, variables)
        
        if result.get("ok"):
            logger.info(f"Notification sent: {title}")
            # Update tracking fields
            settings.notify_last_sent_date = today_str
            settings.notify_last_sent_ts = now_ts
            session.commit()
        else:
            logger.warning(f"Notification failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"Notification check error: {e}")
    finally:
        try:
            session.close()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    init_database()
    
    # Start scheduler
    # Forecast poll: every 6 hours (matching Astrospheric's CMC data update cadence)
    scheduler.add_job(scheduled_poll, 'interval', hours=6, id='forecast_poll',
                      next_run_time=datetime.now())  # run immediately on startup
    # Notification check: every 10 minutes (lightweight — just time comparisons)
    scheduler.add_job(check_notifications, 'interval', minutes=10, id='notification_check')
    scheduler.start()
    logger.info("Scheduler started — forecast poll every 6h, notification check every 10min")
    
    yield
    
    scheduler.shutdown()
    logger.info("Scheduler stopped")


APP_VERSION = "0.1.0"
app = FastAPI(title="AstroDash", version=APP_VERSION, lifespan=lifespan)

# Static files and templates
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def get_db():
    engine = get_engine(DB_PATH)
    return get_session(engine)


@app.get("/api/status")
async def get_status():
    """Return initialization status for startup progress display."""
    return _init_status


@app.get("/api/version")
async def get_version():
    return {"version": APP_VERSION}


# ═══════════════════════════════════════════════════════════════
# Pages
# ═══════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db = get_db()
    try:
        settings = db.query(UserSettings).first()
        if not settings or not settings.setup_complete:
            return templates.TemplateResponse("setup.html", {"request": request})
        return templates.TemplateResponse("dashboard.html", {"request": request})
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# API: Settings
# ═══════════════════════════════════════════════════════════════

class SettingsUpdate(BaseModel):
    astrospheric_api_key: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    timezone: Optional[str] = None
    bortle_zone: Optional[int] = None
    horizon_north: Optional[int] = None
    horizon_east: Optional[int] = None
    horizon_south: Optional[int] = None
    horizon_west: Optional[int] = None
    preferred_targets: Optional[list] = None
    imaging_end_hour: Optional[int] = None
    notify_enabled: Optional[bool] = None
    notify_method: Optional[str] = None  # "ntfy", "discord", "webhook"
    notify_webhook_url: Optional[str] = None
    notify_discord_url: Optional[str] = None
    notify_ntfy_server: Optional[str] = None
    notify_ntfy_topic: Optional[str] = None
    notify_go_threshold: Optional[int] = None
    notify_hours_before_dark: Optional[int] = None
    notify_interval_hours: Optional[int] = None
    notify_template: Optional[str] = None
    notify_nogo: Optional[bool] = None
    notify_quiet_start: Optional[int] = None
    dark_last_date: Optional[str] = None
    dark_temp_c: Optional[float] = None
    dark_gain: Optional[int] = None
    dark_reminder_months: Optional[int] = None
    setup_complete: Optional[bool] = None


@app.get("/api/settings")
async def get_settings():
    db = get_db()
    try:
        s = db.query(UserSettings).first()
        if not s:
            return {"setup_complete": False}
        return {
            "astrospheric_api_key": s.astrospheric_api_key,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "location_name": s.location_name,
            "timezone": s.timezone,
            "bortle_zone": s.bortle_zone,
            "horizon_north": s.horizon_north,
            "horizon_east": s.horizon_east,
            "horizon_south": s.horizon_south,
            "horizon_west": s.horizon_west,
            "preferred_targets": s.preferred_targets or [],
            "imaging_end_hour": s.imaging_end_hour,
            "notify_enabled": s.notify_enabled,
            "notify_method": s.notify_method,
            "notify_webhook_url": s.notify_webhook_url,
            "notify_discord_url": s.notify_discord_url,
            "notify_ntfy_server": s.notify_ntfy_server,
            "notify_ntfy_topic": s.notify_ntfy_topic,
            "notify_go_threshold": s.notify_go_threshold,
            "notify_hours_before_dark": s.notify_hours_before_dark,
            "notify_interval_hours": s.notify_interval_hours,
            "notify_template": s.notify_template,
            "notify_nogo": s.notify_nogo,
            "notify_quiet_start": s.notify_quiet_start,
            "dark_last_date": str(s.dark_last_date) if s.dark_last_date else None,
            "dark_temp_c": s.dark_temp_c,
            "dark_gain": s.dark_gain,
            "dark_reminder_months": s.dark_reminder_months,
            "setup_complete": s.setup_complete,
        }
    finally:
        db.close()


@app.put("/api/settings")
async def update_settings(data: SettingsUpdate):
    db = get_db()
    try:
        s = db.query(UserSettings).first()
        if not s:
            s = UserSettings(id=1)
            db.add(s)
        
        for field, value in data.dict(exclude_unset=True).items():
            if field == "dark_last_date" and value:
                value = date.fromisoformat(value)
            setattr(s, field, value)
        
        s.updated_at = datetime.utcnow()
        db.commit()
        
        # Trigger immediate forecast poll if API key was just set
        if data.astrospheric_api_key:
            asyncio.create_task(poll_and_cache(DB_PATH))
        
        return {"status": "ok"}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# API: Forecast
# ═══════════════════════════════════════════════════════════════

@app.get("/api/forecast")
async def get_forecast():
    db = get_db()
    try:
        settings = db.query(UserSettings).first()
        if not settings or not settings.latitude:
            return {"error": "Location not configured. Check Settings."}
        
        # Always compute twilight and imaging window (no API key needed)
        utc_offset_hours = _get_utc_offset(settings.timezone, settings.longitude)
        logger.info(f"UTC offset from timezone '{settings.timezone}' / lon={settings.longitude}: {utc_offset_hours}h")
        try:
            twilight = get_twilight_times(settings.latitude, settings.longitude,
                                          utc_offset_hours=utc_offset_hours)
            img_start = twilight.get("imaging_start_hour")
            if img_start is None:
                return {"error": "Could not compute twilight for this location."}
        except Exception as e:
            logger.warning(f"Twilight calculation failed: {e}")
            return {"error": f"Could not compute twilight: {e}"}
        img_end = settings.imaging_end_hour if settings.imaging_end_hour is not None else 1
        
        # Compute moon info for imaging window (not just current time)
        try:
            from .services.astronomy import get_moon_window_info
            moon_window = get_moon_window_info(
                settings.latitude, settings.longitude,
                img_start, img_end,
                utc_offset_hours=utc_offset_hours)
        except Exception as e:
            logger.warning(f"Moon window calc failed: {e}")
            moon_window = None
        
        # Fallback: current moon info
        try:
            moon_info = get_moon_info(settings.latitude, settings.longitude)
        except Exception:
            moon_info = {"illumination": 0, "altitude": 0, "phase": "Unknown"}
        
        # Base response with twilight + imaging window (always available)
        moon_data = {
            "illumination": moon_window["illumination"] if moon_window else moon_info.get("illumination", 0),
            "altitude": moon_info.get("altitude", 0),
            "phase": moon_info.get("phase_name", moon_info.get("phase", "Unknown")),
        }
        if moon_window:
            moon_data["window_alt_min"] = moon_window["alt_min"]
            moon_data["window_alt_max"] = moon_window["alt_max"]
            moon_data["window_up"] = moon_window["up_during_window"]
            moon_data["window_hours_up"] = moon_window["hours_above_horizon"]
            moon_data["window_total_hours"] = moon_window["total_window_hours"]
            moon_data["window_rises_at"] = moon_window["rises_at"]
            moon_data["window_sets_at"] = moon_window["sets_at"]
        
        base = {
            "twilight": twilight,
            "imaging_window_start": img_start,
            "imaging_window_end": img_end,
            "moon": moon_data,
        }
        
        # If no API key, return base data with no_api_key flag
        if not settings.astrospheric_api_key:
            base["no_api_key"] = True
            return base
        
        # Get latest cache
        cache = db.query(ForecastCache).order_by(ForecastCache.fetched_at.desc()).first()
        if not cache:
            base["error"] = "No forecast data yet. Waiting for first poll..."
            return base
        
        # Reconstruct all_hours from cached data
        cloud_data = cache.cloud_data or []
        all_hours = {
            "cloud": cloud_data,
            "transparency": cache.transparency_data or [],
            "seeing": cache.seeing_data or [],
            "wind": cache.wind_data or [],
            "temperature": cache.temperature_data or [],
            "dewpoint": cache.dewpoint_data or [],
            "hours": [entry.get("hour", 0) if isinstance(entry, dict) else 0 for entry in cloud_data],
        }
        
        moon_ill = cache.moon_illumination or 0
        
        # Compute forecast for imaging window
        forecast = compute_tonight_forecast(
            all_hours, img_start, img_end,
            moon_illumination=moon_ill
        )
        
        # Merge base data into forecast
        forecast["twilight"] = twilight
        forecast["imaging_window_start"] = img_start
        forecast["imaging_window_end"] = img_end
        forecast["fetched_at"] = cache.fetched_at.isoformat() if cache.fetched_at else None
        forecast["model_time"] = cache.model_time
        forecast["credits_used"] = cache.credits_used
        forecast["moon"] = {
            "illumination": moon_ill,
            "altitude": cache.moon_altitude,
            "phase": cache.moon_phase,
        }
        
        return forecast
    finally:
        db.close()


@app.post("/api/forecast/refresh")
async def refresh_forecast():
    """Force an immediate forecast refresh."""
    asyncio.create_task(poll_and_cache(DB_PATH))
    return {"status": "refreshing"}


@app.get("/api/forecast/tomorrow")
async def get_tomorrow_forecast():
    """Get preliminary forecast for tomorrow night's imaging window."""
    from .services.astrospheric import filter_tomorrow_window
    db = get_db()
    try:
        settings = db.query(UserSettings).first()
        if not settings or not settings.latitude:
            return {"error": "Location not configured."}
        
        # Always compute twilight for tomorrow (no API key needed)
        utc_offset_hours = _get_utc_offset(settings.timezone, settings.longitude)
        
        tomorrow = datetime.utcnow() + timedelta(days=1)
        try:
            twilight = get_twilight_times(settings.latitude, settings.longitude,
                                          dt=tomorrow, utc_offset_hours=utc_offset_hours)
            img_start = twilight.get("imaging_start_hour")
            if img_start is None:
                return {"error": "Could not compute twilight for this location."}
        except Exception as e:
            logger.warning(f"Tomorrow twilight calc failed: {e}")
            return {"error": f"Could not compute twilight: {e}"}
        img_end = settings.imaging_end_hour if settings.imaging_end_hour is not None else 1
        
        base = {
            "imaging_window_start": img_start,
            "imaging_window_end": img_end,
            "num_hours": (img_end + 24 - img_start) % 24 if img_start != img_end else 0,
        }
        
        if not settings.astrospheric_api_key:
            base["no_api_key"] = True
            return base
        
        cache = db.query(ForecastCache).order_by(ForecastCache.fetched_at.desc()).first()
        if not cache:
            base["error"] = "No forecast data yet"
            return base
        
        logger.info(f"Tomorrow forecast: img_start={img_start}, img_end={img_end}")
        
        # Reconstruct all_hours from cache
        cloud_data = cache.cloud_data or []
        all_hours = {
            "cloud": cloud_data,
            "transparency": cache.transparency_data or [],
            "seeing": cache.seeing_data or [],
            "wind": cache.wind_data or [],
            "temperature": cache.temperature_data or [],
            "dewpoint": cache.dewpoint_data or [],
            "hours": [entry.get("hour", 0) if isinstance(entry, dict) else 0 for entry in cloud_data],
        }
        
        logger.info(f"Tomorrow forecast: {len(all_hours['hours'])} total hours in cache, "
                     f"first few: {all_hours['hours'][:5]}")
        
        # Filter to tomorrow's window
        window = filter_tomorrow_window(all_hours, img_start, img_end)
        
        if not window.get("hours"):
            return {"error": "Tomorrow's imaging window is not covered by the current forecast."}
        
        # Score each hour
        from .services.astrospheric import score_hour, kelvin_to_f, transparency_label, seeing_label, format_hour
        
        hours = []
        scores = []
        max_cloud = 0
        max_wind = 0
        max_transp = 0
        
        for i, local_h in enumerate(window.get("hours", [])):
            c = window["cloud"][i]["value"] if i < len(window["cloud"]) else 0
            t = window["transparency"][i]["value"] if i < len(window["transparency"]) else 10
            s = window["seeing"][i]["value"] if i < len(window["seeing"]) else 3
            w = window["wind"][i]["value"] if i < len(window["wind"]) else 0
            temp_k = window["temperature"][i]["value"] if i < len(window["temperature"]) else 273
            dew_k = window["dewpoint"][i]["value"] if i < len(window["dewpoint"]) else 273
            
            hour_score = score_hour(c, t, s, w)
            scores.append(hour_score)
            
            if c > max_cloud: max_cloud = c
            if w > max_wind: max_wind = w
            if t > max_transp: max_transp = t
            
            temp_f = kelvin_to_f(temp_k) if temp_k > 100 else 0
            dew_f = kelvin_to_f(dew_k) if dew_k > 100 else 0
            wind_mph = round(w * 2.237)
            
            hours.append({
                "hour": local_h,
                "time": format_hour(local_h),
                "score": hour_score,
                "cloud_pct": round(c, 1),
                "transparency": transparency_label(t),
                "seeing": seeing_label(s),
                "wind_mph": wind_mph,
                "temp_f": temp_f,
                "dew_point_f": dew_f,
                "dew_depression_f": temp_f - dew_f,
            })
        
        avg_score = round(sum(scores) / len(scores)) if scores else 0
        
        if avg_score >= 70: verdict = "GO"
        elif avg_score >= 45: verdict = "MAYBE"
        else: verdict = "NO-GO"
        
        if max_cloud > 30:
            worst = f"Clouds ({round(max_cloud)}%)"
        elif max_wind > 8.9:
            worst = f"Wind ({round(max_wind * 2.237)} mph)"
        elif max_transp > 14:
            worst = "Poor transparency"
        else:
            worst = "All clear"
        
        return {
            "score": avg_score,
            "verdict": verdict,
            "hours": hours,
            "num_hours": len(hours),
            "worst_issue": worst,
            "imaging_window_start": img_start,
            "imaging_window_end": img_end,
            "twilight": twilight,
        }
    except Exception as e:
        logger.error(f"Tomorrow forecast error: {type(e).__name__}: {e}", exc_info=True)
        return {"error": f"Failed to compute tomorrow's forecast: {type(e).__name__}: {e}"}
    finally:
        db.close()


@app.get("/api/debug/raw-forecast")
async def debug_raw_forecast():
    """Debug endpoint: show raw cached forecast data structure."""
    db = get_db()
    try:
        cache = db.query(ForecastCache).order_by(ForecastCache.fetched_at.desc()).first()
        if not cache:
            return {"error": "No cached data"}
        cloud = cache.cloud_data or []
        return {
            "fetched_at": cache.fetched_at.isoformat() if cache.fetched_at else None,
            "model_time": cache.model_time,
            "local_start_time": cache.local_start_time,
            "num_cloud_hours": len(cloud),
            "first_3_cloud": cloud[:3] if cloud else [],
            "first_3_temp": (cache.temperature_data or [])[:3],
            "first_3_wind": (cache.wind_data or [])[:3],
            "moon_illumination": cache.moon_illumination,
            "moon_altitude": cache.moon_altitude,
        }
    finally:
        db.close()


@app.post("/api/settings/reset-setup")
async def reset_setup():
    """Reset setup_complete flag to re-run the setup wizard."""
    db = get_db()
    try:
        s = db.query(UserSettings).first()
        if s:
            s.setup_complete = False
            db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@app.post("/api/notifications/test")
async def test_notification():
    """Send a test notification using the user's saved notification settings."""
    from .services.notifications import (
        send_notification, render_template, build_test_variables, DEFAULT_TEMPLATE
    )
    db = get_db()
    try:
        s = db.query(UserSettings).first()
        if not s:
            return {"error": "No settings configured"}
        if not s.notify_enabled:
            return {"error": "Notifications are not enabled. Enable them first, then save."}

        variables = build_test_variables()
        template = s.notify_template or DEFAULT_TEMPLATE
        message = render_template(template, variables)
        title = "🔭 AstroDash Test — GO for Imaging Tonight!"

        result = await send_notification(s, title, message, variables)
        if result.get("ok"):
            return {"status": "sent"}
        else:
            return {"error": result.get("error", "Failed to send.")}
    finally:
        db.close()


@app.get("/api/notifications/variables")
async def list_notification_variables():
    """Return available template variables for the notification message editor."""
    from .services.notifications import TEMPLATE_VARIABLES, DEFAULT_TEMPLATE
    return {"variables": TEMPLATE_VARIABLES, "default_template": DEFAULT_TEMPLATE}


# ═══════════════════════════════════════════════════════════════
# API: Equipment Catalog
# ═══════════════════════════════════════════════════════════════

EQUIPMENT_MODELS = {
    "cameras": Camera,
    "mounts": Mount,
    "telescopes": Telescope,
    "filters": Filter,
    "accessories": Accessory,
}


@app.get("/api/equipment/{category}")
async def list_equipment(category: str):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404, f"Unknown category: {category}")
    db = get_db()
    try:
        model = EQUIPMENT_MODELS[category]
        items = db.query(model).all()
        result = []
        for item in items:
            d = {c.name: getattr(item, c.name) for c in item.__table__.columns}
            # Convert datetime to string
            for k, v in d.items():
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
            result.append(d)
        return result
    finally:
        db.close()


@app.post("/api/equipment/{category}")
async def add_equipment(category: str, request: Request):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404, f"Unknown category: {category}")
    db = get_db()
    try:
        data = await request.json()
        data.pop("id", None)
        data.pop("created_at", None)
        data["is_catalog"] = False
        model = EQUIPMENT_MODELS[category]
        item = model(**data)
        db.add(item)
        db.commit()
        return {"id": item.id, "status": "created"}
    finally:
        db.close()


@app.delete("/api/equipment/{category}/{item_id}")
async def delete_equipment(category: str, item_id: int):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404)
    db = get_db()
    try:
        model = EQUIPMENT_MODELS[category]
        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(404)
        db.delete(item)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


@app.get("/api/equipment/{category}/export/json")
async def export_equipment_json(category: str):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404)
    db = get_db()
    try:
        model = EQUIPMENT_MODELS[category]
        items = db.query(model).all()
        data = []
        for item in items:
            d = {c.name: getattr(item, c.name) for c in item.__table__.columns}
            for k, v in d.items():
                if isinstance(v, datetime):
                    d[k] = v.isoformat()
            data.append(d)
        
        content = json.dumps(data, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={category}.json"}
        )
    finally:
        db.close()


@app.get("/api/equipment/{category}/export/csv")
async def export_equipment_csv(category: str):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404)
    db = get_db()
    try:
        model = EQUIPMENT_MODELS[category]
        items = db.query(model).all()
        if not items:
            return StreamingResponse(io.BytesIO(b""), media_type="text/csv")
        
        columns = [c.name for c in items[0].__table__.columns]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for item in items:
            row = {}
            for c in columns:
                v = getattr(item, c)
                if isinstance(v, datetime):
                    v = v.isoformat()
                row[c] = v
            writer.writerow(row)
        
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={category}.csv"}
        )
    finally:
        db.close()


@app.post("/api/equipment/{category}/import/json")
async def import_equipment_json(category: str, file: UploadFile = File(...)):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404)
    db = get_db()
    try:
        content = await file.read()
        data = json.loads(content)
        model = EQUIPMENT_MODELS[category]
        count = 0
        for item_data in data:
            item_data.pop("id", None)
            item_data.pop("created_at", None)
            cleaned = {k: v for k, v in item_data.items() if hasattr(model, k)}
            db.add(model(**cleaned))
            count += 1
        db.commit()
        return {"imported": count}
    finally:
        db.close()


@app.post("/api/equipment/{category}/import/csv")
async def import_equipment_csv(category: str, file: UploadFile = File(...)):
    if category not in EQUIPMENT_MODELS:
        raise HTTPException(404)
    db = get_db()
    try:
        content = (await file.read()).decode()
        reader = csv.DictReader(io.StringIO(content))
        model = EQUIPMENT_MODELS[category]
        
        # Build column type map for proper coercion
        col_types = {}
        for c in model.__table__.columns:
            col_type = str(c.type).upper()
            if "INT" in col_type:
                col_types[c.name] = "int"
            elif "FLOAT" in col_type or "REAL" in col_type or "NUMERIC" in col_type:
                col_types[c.name] = "float"
            elif "BOOL" in col_type:
                col_types[c.name] = "bool"
            else:
                col_types[c.name] = "str"
        
        count = 0
        for row in reader:
            row.pop("id", None)
            row.pop("created_at", None)
            cleaned = {}
            for k, v in row.items():
                if not hasattr(model, k):
                    continue
                if v == "" or v == "None" or v is None:
                    cleaned[k] = None
                elif col_types.get(k) == "bool":
                    cleaned[k] = v.lower() in ("true", "1", "yes")
                elif col_types.get(k) == "int":
                    try: cleaned[k] = int(float(v))
                    except (ValueError, TypeError): cleaned[k] = None
                elif col_types.get(k) == "float":
                    try: cleaned[k] = float(v)
                    except (ValueError, TypeError): cleaned[k] = None
                else:
                    cleaned[k] = v
            db.add(model(**cleaned))
            count += 1
        db.commit()
        return {"imported": count}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# API: User Equipment
# ═══════════════════════════════════════════════════════════════

@app.get("/api/my-equipment")
async def get_my_equipment():
    db = get_db()
    try:
        items = db.query(UserEquipment).all()
        result = []
        for ue in items:
            d = {c.name: getattr(ue, c.name) for c in ue.__table__.columns}
            # Resolve catalog name
            if ue.catalog_id and ue.category in EQUIPMENT_MODELS:
                model = EQUIPMENT_MODELS[ue.category]
                cat_item = db.query(model).filter(model.id == ue.catalog_id).first()
                if cat_item:
                    d["catalog_name"] = cat_item.name
                    d["manufacturer"] = cat_item.manufacturer
            result.append(d)
        return result
    finally:
        db.close()


class UserEquipmentAdd(BaseModel):
    category: str
    catalog_id: Optional[int] = None
    custom_name: Optional[str] = None
    is_primary: bool = False
    notes: Optional[str] = None


@app.post("/api/my-equipment")
async def add_my_equipment(data: UserEquipmentAdd):
    db = get_db()
    try:
        ue = UserEquipment(**data.dict())
        db.add(ue)
        db.commit()
        return {"id": ue.id}
    finally:
        db.close()


@app.delete("/api/my-equipment/all")
async def purge_all_my_equipment():
    """Remove all user equipment selections (used when re-running setup wizard)."""
    db = get_db()
    try:
        count = db.query(UserEquipment).delete()
        db.commit()
        return {"status": "purged", "count": count}
    finally:
        db.close()


@app.delete("/api/my-equipment/{item_id}")
async def remove_my_equipment(item_id: int):
    db = get_db()
    try:
        ue = db.query(UserEquipment).filter(UserEquipment.id == item_id).first()
        if not ue:
            raise HTTPException(404)
        db.delete(ue)
        db.commit()
        return {"status": "removed"}
    finally:
        db.close()

# ═══════════════════════════════════════════════════════════════

@app.get("/api/targets")
async def list_targets(season: Optional[str] = None, target_type: Optional[str] = None):
    db = get_db()
    try:
        q = db.query(DSOTarget)
        if season:
            q = q.filter(DSOTarget.season == season)
        if target_type:
            q = q.filter(DSOTarget.target_type == target_type)
        targets = q.all()
        
        # Get user's owned filters in a single batch query
        from .models.database import UserEquipment
        owned_filter_ids = [ue.catalog_id for ue in 
                           db.query(UserEquipment).filter(UserEquipment.category == "filters").all()
                           if ue.catalog_id]
        owned_filters = []
        if owned_filter_ids:
            for f in db.query(Filter).filter(Filter.id.in_(owned_filter_ids)).all():
                owned_filters.append({
                    "name": f.name, 
                    "filter_type": f.filter_type,
                    "broadband_friendly": f.broadband_friendly,
                    "narrowband_friendly": f.narrowband_friendly,
                    "moonlight_resistant": f.moonlight_resistant,
                    "bandpass": f.bandpass,
                })
        
        # Pre-compute recommended filters once per NB/BB combination (only 4 combos)
        _filter_cache = {}
        def get_rec_filters(bb, nb):
            key = (bool(bb), bool(nb))
            if key not in _filter_cache:
                _filter_cache[key] = _recommend_filters(bb, nb, owned_filters)
            return _filter_cache[key]
        
        # Column names for fast serialization
        col_names = [c.name for c in DSOTarget.__table__.columns]
        
        result = []
        for t in targets:
            d = {col: getattr(t, col) for col in col_names}
            d["recommended_filters"] = get_rec_filters(t.broadband_target, t.narrowband_target)
            result.append(d)
        return result
    finally:
        db.close()


def _recommend_filters(is_broadband: bool, is_narrowband: bool, owned_filters: list) -> list:
    """Recommend filters from the user's owned equipment for a given target."""
    if not owned_filters:
        return []
    
    recs = []
    for f in owned_filters:
        # Broadband-only targets (galaxies, clusters, reflection nebulae)
        if is_broadband and not is_narrowband:
            if f.get("broadband_friendly"):
                recs.append({"name": f["name"], "reason": "Broadband target"})
        # Narrowband-only targets (emission nebulae)
        elif is_narrowband and not is_broadband:
            if f.get("narrowband_friendly") and not f.get("broadband_friendly"):
                recs.append({"name": f["name"], "reason": "Emission nebula"})
            elif f.get("narrowband_friendly") and f.get("broadband_friendly"):
                # Dual-purpose filters like L-Quad Enhance work too
                recs.append({"name": f["name"], "reason": "Emission nebula (LP+emission)"})
        # Both broadband and narrowband targets
        elif is_broadband and is_narrowband:
            if f.get("broadband_friendly") or f.get("narrowband_friendly"):
                reason = "Broadband + emission" if f.get("broadband_friendly") and f.get("narrowband_friendly") else (
                    "Broadband data" if f.get("broadband_friendly") else "Emission data")
                recs.append({"name": f["name"], "reason": reason})
    
    return recs


@app.get("/api/targets/{target_id}/visibility")
async def target_visibility(target_id: int):
    db = get_db()
    try:
        target = db.query(DSOTarget).filter(DSOTarget.id == target_id).first()
        if not target:
            raise HTTPException(404)
        settings = db.query(UserSettings).first()
        if not settings or not settings.latitude:
            raise HTTPException(400, "Location not configured")
        
        # Determine min altitude based on horizon limits and target direction
        min_alt = min(settings.horizon_north, settings.horizon_east,
                      settings.horizon_south, settings.horizon_west)
        
        vis = compute_target_visibility(
            target.ra_hours, target.dec_degrees,
            settings.latitude, settings.longitude,
            min_altitude=min_alt,
            utc_offset_hours=_get_utc_offset(settings.timezone, settings.longitude)
        )
        
        # Add moon separation
        moon_sep = moon_separation(target.ra_hours, target.dec_degrees,
                                    settings.latitude, settings.longitude)
        vis["moon_separation_deg"] = moon_sep
        vis["target_name"] = target.name
        vis["catalog_id"] = target.catalog_id
        
        return vis
    finally:
        db.close()


@app.get("/api/tonight/targets")
async def tonight_targets():
    """Get recommended targets for tonight with visibility data."""
    db = get_db()
    try:
        settings = db.query(UserSettings).first()
        if not settings or not settings.latitude:
            return {"error": "Location not configured"}
        
        targets = db.query(DSOTarget).all()
        cache = db.query(ForecastCache).order_by(ForecastCache.fetched_at.desc()).first()
        utc_off = _get_utc_offset(settings.timezone, settings.longitude)
        try:
            twilight = get_twilight_times(settings.latitude, settings.longitude,
                                          utc_offset_hours=utc_off)
            moon = get_moon_info(settings.latitude, settings.longitude)
        except Exception as e:
            logger.warning(f"Astronomy calc failed (ephemeris not ready?): {e}")
            return {"targets": [], "moon": {"illumination": 0}, "error": "Ephemeris data not yet downloaded. It will be fetched automatically — try again in a minute."}
        
        moon_ill = moon.get("illumination", 0) if isinstance(moon, dict) else 0
        
        results = []
        for t in targets:
            try:
                vis = compute_target_visibility(
                    t.ra_hours, t.dec_degrees,
                    settings.latitude, settings.longitude,
                    min_altitude=20,
                    utc_offset_hours=utc_off
                )
                
                if vis["never_rises"] or vis["max_altitude"] < 20:
                    continue
                
                if vis["hours_above_min"] < 1:
                    continue
                
                moon_sep = moon_separation(t.ra_hours, t.dec_degrees,
                                            settings.latitude, settings.longitude)
                
                # Check if there's an existing project (active or not_started)
                project = db.query(ImagingProject).filter(
                    ImagingProject.target_id == t.id,
                    ImagingProject.status.in_(["active", "not_started"])
                ).first()
                
                # Score this target for tonight
                target_score = 50  # base
                
                # Altitude bonus
                if vis["max_altitude"] > 60:
                    target_score += 20
                elif vis["max_altitude"] > 40:
                    target_score += 10
                
                # Hours visible bonus
                target_score += min(20, int(vis["hours_above_min"] * 5))
                
                # Moon separation bonus/penalty
                if moon_ill > 30:
                    if moon_sep < 30:
                        target_score -= 20
                    elif moon_sep > 90:
                        target_score += 10
                
                # Active project bonus (prioritize ongoing work)
                if project:
                    remaining = project.goal_hours - project.accumulated_hours
                    if remaining > 0:
                        target_score += 15
                
                # Narrowband target during bright moon = bonus
                if t.narrowband_target and moon_ill > 40:
                    target_score += 15
                # Broadband target during bright moon = penalty
                if not t.narrowband_target and moon_ill > 40:
                    target_score -= 15
                
                results.append({
                    "id": t.id,
                    "name": t.name,
                    "catalog_id": t.catalog_id,
                    "target_type": t.target_type,
                    "constellation": t.constellation,
                    "season": t.season,
                    "difficulty": t.difficulty,
                    "max_altitude": vis["max_altitude"],
                    "transit_time": vis["transit_time"],
                    "hours_above_20": vis["hours_above_min"],
                    "moon_separation": moon_sep,
                    "narrowband_target": t.narrowband_target,
                    "broadband_target": t.broadband_target,
                    "score": min(100, max(0, target_score)),
                    "size_arcmin": t.size_arcmin,
                    "recommended_min_hours": t.recommended_min_hours,
                    "has_active_project": project is not None,
                    "project_id": project.id if project else None,
                    "project_status": project.status if project else None,
                    "project_hours_accumulated": project.accumulated_hours if project else 0,
                    "project_hours_goal": project.goal_hours if project else None,
                })
            except Exception as e:
                logger.warning(f"Error computing target {t.name}: {type(e).__name__}: {e}")
                continue
        
        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return {
            "targets": results,
            "moon": moon,
            "twilight": {
                "imaging_start_hour": twilight.get("imaging_start_hour"),
                "astronomical_dusk": twilight.get("astronomical_dusk"),
            }
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# API: Imaging Projects
# ═══════════════════════════════════════════════════════════════

class ProjectCreate(BaseModel):
    target_id: int
    name: Optional[str] = None
    goal_hours: float = 4.0
    goal_l_hours: float = 0.0
    goal_r_hours: float = 0.0
    goal_g_hours: float = 0.0
    goal_b_hours: float = 0.0
    goal_sii_hours: float = 0.0
    goal_ha_hours: float = 0.0
    goal_oiii_hours: float = 0.0
    goal_rgb_hours: float = 0.0
    filter_used: Optional[str] = None
    gain: Optional[int] = None
    sub_length_s: Optional[int] = None
    notes: Optional[str] = None


@app.get("/api/projects")
async def list_projects(status: Optional[str] = None):
    db = get_db()
    try:
        q = db.query(ImagingProject)
        if status:
            q = q.filter(ImagingProject.status == status)
        projects = q.all()
        result = []
        for p in projects:
            d = {c.name: getattr(p, c.name) for c in p.__table__.columns}
            if p.target:
                d["target_name"] = p.target.name
                d["target_catalog_id"] = p.target.catalog_id
            for k, v in d.items():
                if isinstance(v, (datetime, date)):
                    d[k] = v.isoformat() if v else None
            # Aggregate channel integration from sessions (LRGBSHO)
            d["integration_l_hrs"] = round(sum(
                (s.integration_l_min or 0) for s in p.sessions) / 60, 2)
            d["integration_r_hrs"] = round(sum(
                (s.integration_r_min or 0) for s in p.sessions) / 60, 2)
            d["integration_g_hrs"] = round(sum(
                (s.integration_g_min or 0) for s in p.sessions) / 60, 2)
            d["integration_b_hrs"] = round(sum(
                (s.integration_b_min or 0) for s in p.sessions) / 60, 2)
            d["integration_ha_hrs"] = round(sum(
                (s.integration_ha_min or 0) for s in p.sessions) / 60, 2)
            d["integration_oiii_hrs"] = round(sum(
                (s.integration_oiii_min or 0) for s in p.sessions) / 60, 2)
            d["integration_sii_hrs"] = round(sum(
                (s.integration_sii_min or 0) for s in p.sessions) / 60, 2)
            # Legacy RGB → migrate to L+R+G+B sum for backward compat
            legacy_rgb = round(sum(
                (s.integration_rgb_min or 0) for s in p.sessions) / 60, 2)
            if legacy_rgb > 0 and d["integration_l_hrs"] == 0:
                d["integration_l_hrs"] = legacy_rgb
                d["integration_r_hrs"] = legacy_rgb
                d["integration_g_hrs"] = legacy_rgb
                d["integration_b_hrs"] = legacy_rgb
            result.append(d)
        return result
    finally:
        db.close()


@app.post("/api/projects")
async def create_project(data: ProjectCreate):
    db = get_db()
    try:
        p = ImagingProject(**data.dict())
        db.add(p)
        db.commit()
        return {"id": p.id}
    finally:
        db.close()


@app.put("/api/projects/{project_id}")
async def update_project(project_id: int, request: Request):
    db = get_db()
    try:
        p = db.query(ImagingProject).filter(ImagingProject.id == project_id).first()
        if not p:
            raise HTTPException(404)
        data = await request.json()
        for k, v in data.items():
            if hasattr(p, k):
                setattr(p, k, v)
        if data.get("status") == "complete":
            p.completed_at = datetime.utcnow()
        elif "status" in data and data["status"] != "complete":
            p.completed_at = None
        db.commit()
        return {"status": "updated"}
    finally:
        db.close()


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    db = get_db()
    try:
        p = db.query(ImagingProject).filter(ImagingProject.id == project_id).first()
        if not p:
            raise HTTPException(404)
        # Delete associated sessions
        db.query(SessionLog).filter(SessionLog.project_id == project_id).delete()
        db.delete(p)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


@app.get("/api/my-filters")
async def list_my_filters():
    """Return the user's owned filters with names for dropdown use."""
    db = get_db()
    try:
        owned = db.query(UserEquipment).filter(UserEquipment.category == "filters").all()
        result = []
        for ue in owned:
            if ue.catalog_id:
                f = db.query(Filter).filter(Filter.id == ue.catalog_id).first()
                if f:
                    result.append({"id": f.id, "name": f.name, "manufacturer": f.manufacturer,
                                   "filter_type": f.filter_type, "bandpass": f.bandpass})
        return result
    finally:
        db.close()


@app.get("/api/my-equipment-options")
async def list_my_equipment_options():
    """Return all user's equipment categorized for session modal dropdowns."""
    db = get_db()
    try:
        items = db.query(UserEquipment).all()
        result = {"cameras": [], "telescopes": [], "mounts": [], "filters": []}
        for ue in items:
            if ue.category not in result:
                continue
            if ue.catalog_id and ue.category in EQUIPMENT_MODELS:
                model = EQUIPMENT_MODELS[ue.category]
                cat_item = db.query(model).filter(model.id == ue.catalog_id).first()
                if cat_item:
                    entry = {"name": cat_item.name, "manufacturer": cat_item.manufacturer}
                    if ue.category == "cameras" and hasattr(cat_item, "color_type"):
                        entry["color_type"] = cat_item.color_type
                        entry["pixel_size_um"] = getattr(cat_item, "pixel_size_um", None)
                        entry["sensor_width_mm"] = getattr(cat_item, "sensor_width_mm", None)
                        entry["sensor_height_mm"] = getattr(cat_item, "sensor_height_mm", None)
                        entry["resolution_x"] = getattr(cat_item, "resolution_x", None)
                        entry["resolution_y"] = getattr(cat_item, "resolution_y", None)
                    if ue.category == "telescopes" and hasattr(cat_item, "focal_length_mm"):
                        entry["focal_length_mm"] = cat_item.focal_length_mm
                    if ue.category == "filters":
                        entry["filter_type"] = getattr(cat_item, "filter_type", "")
                        entry["bandpass"] = getattr(cat_item, "bandpass", "")
                    result[ue.category].append(entry)
        return result
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# API: Session Log
# ═══════════════════════════════════════════════════════════════

class SessionCreate(BaseModel):
    project_id: Optional[int] = None
    session_date: str
    target_name: Optional[str] = None
    filter_used: Optional[str] = None
    camera_used: Optional[str] = None
    telescope_used: Optional[str] = None
    mount_used: Optional[str] = None
    bortle: Optional[int] = None
    sub_length_s: Optional[int] = None
    num_subs: Optional[int] = None
    total_integration_min: Optional[float] = None
    gain: Optional[int] = None
    camera_temp_c: Optional[float] = None
    rating: Optional[int] = None
    guiding_rms_arcsec: Optional[float] = None
    notes: Optional[str] = None
    # Auto-fill from forecast
    cloud_cover_pct: Optional[float] = None
    transparency: Optional[str] = None
    seeing: Optional[str] = None
    wind_mph: Optional[float] = None
    temperature_f: Optional[float] = None
    moon_illumination_pct: Optional[float] = None


@app.get("/api/moon-illumination")
async def get_moon_illumination(date_str: str):
    """Get moon illumination % for a given date using configured location."""
    db = get_db()
    try:
        s = db.query(UserSettings).first()
        if not s or not s.latitude or not s.longitude:
            raise HTTPException(400, "Location not configured")
        from .services.astronomy import get_moon_info
        dt = datetime(int(date_str[:4]), int(date_str[5:7]), int(date_str[8:10]), 23, 0)
        info = get_moon_info(s.latitude, s.longitude, dt)
        return {"illumination": round(info["illumination"]), "phase_name": info["phase_name"]}
    except (ValueError, IndexError):
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")
    finally:
        db.close()


@app.get("/api/sessions")
async def list_sessions():
    db = get_db()
    try:
        sessions = db.query(SessionLog).order_by(SessionLog.session_date.desc()).all()
        result = []
        for s in sessions:
            d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
            for k, v in d.items():
                if isinstance(v, (datetime, date)):
                    d[k] = v.isoformat() if v else None
            # Add project info for display
            if s.project:
                d["project_name"] = s.project.name or s.project.target.name if s.project.target else None
                d["project_target_name"] = s.project.target.name if s.project.target else None
                d["project_target_catalog_id"] = s.project.target.catalog_id if s.project.target else None
            else:
                d["project_name"] = None
                d["project_target_name"] = None
                d["project_target_catalog_id"] = None
            result.append(d)
        return result
    finally:
        db.close()


@app.post("/api/sessions")
async def create_session(data: SessionCreate):
    db = get_db()
    try:
        d = data.dict()
        d["session_date"] = date.fromisoformat(d["session_date"])
        
        # Auto-fill target_name from project if not provided
        if d.get("project_id") and not d.get("target_name"):
            project = db.query(ImagingProject).filter(ImagingProject.id == d["project_id"]).first()
            if project and project.target:
                d["target_name"] = project.target.name
        
        # Compute per-channel integration from filter + camera
        total_min = d.get("total_integration_min") or 0
        ch = compute_channel_integration(d.get("filter_used"), total_min, db, d.get("camera_used"))
        d["integration_l_min"] = ch["l"]
        d["integration_r_min"] = ch["r"]
        d["integration_g_min"] = ch["g"]
        d["integration_b_min"] = ch["b"]
        d["integration_ha_min"] = ch["ha"]
        d["integration_oiii_min"] = ch["oiii"]
        d["integration_sii_min"] = ch["sii"]
        d["integration_rgb_min"] = 0  # legacy field
        
        s = SessionLog(**d)
        db.add(s)
        
        # Update project integration time and filter if linked
        if s.project_id:
            project = db.query(ImagingProject).filter(ImagingProject.id == s.project_id).first()
            if project:
                if s.total_integration_min:
                    project.accumulated_hours += s.total_integration_min / 60
                # Update project filter_used to most recently used filter
                if s.filter_used:
                    project.filter_used = s.filter_used
                # Auto-promote not_started → active when first session is logged
                if project.status == "not_started":
                    project.status = "active"
        
        db.commit()
        return {"id": s.id}
    finally:
        db.close()


@app.put("/api/sessions/{session_id}")
async def update_session(session_id: int, request: Request):
    db = get_db()
    try:
        s = db.query(SessionLog).filter(SessionLog.id == session_id).first()
        if not s:
            raise HTTPException(404)
        data = await request.json()
        
        old_integration = s.total_integration_min or 0
        
        for k, v in data.items():
            if k == "session_date" and v:
                v = date.fromisoformat(v)
            if hasattr(s, k) and k not in ("integration_l_min", "integration_r_min", "integration_g_min", "integration_b_min", "integration_rgb_min", "integration_ha_min", "integration_oiii_min", "integration_sii_min"):
                setattr(s, k, v)
        
        # Recompute channel integration
        total_min = s.total_integration_min or 0
        ch = compute_channel_integration(s.filter_used, total_min, db, s.camera_used)
        s.integration_l_min = ch["l"]
        s.integration_r_min = ch["r"]
        s.integration_g_min = ch["g"]
        s.integration_b_min = ch["b"]
        s.integration_ha_min = ch["ha"]
        s.integration_oiii_min = ch["oiii"]
        s.integration_sii_min = ch["sii"]
        s.integration_rgb_min = 0  # legacy
        
        # Update project accumulated hours if integration changed
        if s.project_id:
            new_integration = s.total_integration_min or 0
            diff = new_integration - old_integration
            if diff != 0:
                project = db.query(ImagingProject).filter(ImagingProject.id == s.project_id).first()
                if project:
                    project.accumulated_hours = max(0, project.accumulated_hours + diff / 60)
        
        db.commit()
        return {"status": "updated"}
    finally:
        db.close()


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int):
    db = get_db()
    try:
        s = db.query(SessionLog).filter(SessionLog.id == session_id).first()
        if not s:
            raise HTTPException(404)
        
        # Subtract integration time from project
        if s.project_id and s.total_integration_min:
            project = db.query(ImagingProject).filter(ImagingProject.id == s.project_id).first()
            if project:
                project.accumulated_hours = max(0, project.accumulated_hours - s.total_integration_min / 60)
        
        db.delete(s)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()
# ═══════════════════════════════════════════════════════════════

@app.get("/api/dark-library-status")
async def dark_library_status():
    db = get_db()
    try:
        s = db.query(UserSettings).first()
        if not s or not s.dark_last_date:
            return {"needs_refresh": True, "message": "No dark library recorded yet."}
        
        months_since = (date.today() - s.dark_last_date).days / 30
        needs_refresh = months_since >= (s.dark_reminder_months or 6)
        
        return {
            "needs_refresh": needs_refresh,
            "last_date": str(s.dark_last_date),
            "months_since": round(months_since, 1),
            "reminder_months": s.dark_reminder_months,
            "temp_c": s.dark_temp_c,
            "gain": s.dark_gain,
        }
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
# API: Backup & Restore
# ═══════════════════════════════════════════════════════════════

def _serialize_row(row, exclude=("id",)):
    """Serialize a SQLAlchemy row to a dict, handling dates and excluding IDs."""
    d = {}
    for c in row.__table__.columns:
        if c.name in exclude:
            continue
        v = getattr(row, c.name)
        if isinstance(v, (datetime, date)):
            d[c.name] = v.isoformat() if v else None
        else:
            d[c.name] = v
    return d


@app.get("/api/backup")
async def create_backup():
    """Export all user data as a JSON backup file."""
    db = get_db()
    try:
        # Settings
        s = db.query(UserSettings).first()
        settings_data = _serialize_row(s) if s else {}

        # User equipment (with resolved catalog names for portability)
        equipment = []
        for ue in db.query(UserEquipment).all():
            entry = _serialize_row(ue)
            # Resolve catalog item details for portability
            if ue.catalog_id and ue.category in EQUIPMENT_MODELS:
                model = EQUIPMENT_MODELS[ue.category]
                cat_item = db.query(model).filter(model.id == ue.catalog_id).first()
                if cat_item:
                    entry["_catalog_name"] = cat_item.name
                    entry["_catalog_manufacturer"] = cat_item.manufacturer
            equipment.append(entry)

        # User-added catalog items (is_catalog=False or user_added where applicable)
        custom_equipment = {}
        for cat_key, model in EQUIPMENT_MODELS.items():
            items = db.query(model).filter(model.is_catalog == False).all()
            if items:
                custom_equipment[cat_key] = [_serialize_row(item) for item in items]

        # User-added DSO targets
        custom_targets = []
        for t in db.query(DSOTarget).filter(DSOTarget.user_added == True).all():
            custom_targets.append(_serialize_row(t))

        # Projects (with target name for re-linking)
        projects = []
        for p in db.query(ImagingProject).all():
            d = _serialize_row(p, exclude=("id", "target_id"))
            if p.target:
                d["_target_name"] = p.target.name
                d["_target_catalog_id"] = p.target.catalog_id
            d["_original_id"] = p.id
            projects.append(d)

        # Sessions (with project original ID for re-linking)
        sessions = []
        for sess in db.query(SessionLog).all():
            d = _serialize_row(sess, exclude=("id",))
            d["_original_project_id"] = sess.project_id
            sessions.append(d)

        backup = {
            "astrodash_backup": True,
            "version": 1,
            "exported_at": datetime.utcnow().isoformat(),
            "settings": settings_data,
            "user_equipment": equipment,
            "custom_catalog_equipment": custom_equipment,
            "custom_targets": custom_targets,
            "projects": projects,
            "sessions": sessions,
        }

        content = json.dumps(backup, indent=2, default=str)
        filename = f"astrodash-backup-{date.today().isoformat()}.json"
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    finally:
        db.close()


@app.post("/api/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Restore all user data from a JSON backup file. Wipes existing data."""
    db = get_db()
    try:
        content = await file.read()
        try:
            backup = json.loads(content)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid JSON file")

        if not backup.get("astrodash_backup"):
            raise HTTPException(400, "Not a valid AstroDash backup file")

        # ── Wipe existing user data ──
        db.query(SessionLog).delete()
        db.query(ImagingProject).delete()
        db.query(UserEquipment).delete()
        # Wipe user-added catalog items
        for model in EQUIPMENT_MODELS.values():
            db.query(model).filter(model.is_catalog == False).delete()
        db.query(DSOTarget).filter(DSOTarget.user_added == True).delete()
        db.flush()

        # ── Restore settings ──
        settings_data = backup.get("settings", {})
        if settings_data:
            s = db.query(UserSettings).first()
            if not s:
                s = UserSettings()
                db.add(s)
            for k, v in settings_data.items():
                if hasattr(s, k) and k not in ("id", "created_at", "updated_at"):
                    if k == "preferred_targets" and isinstance(v, str):
                        v = json.loads(v)
                    setattr(s, k, v)
            s.setup_complete = True

        # ── Restore custom catalog equipment ──
        for cat_key, items in backup.get("custom_catalog_equipment", {}).items():
            if cat_key not in EQUIPMENT_MODELS:
                continue
            model = EQUIPMENT_MODELS[cat_key]
            for item_data in items:
                item_data.pop("id", None)
                item_data.pop("created_at", None)
                item_data["is_catalog"] = False
                item = model(**{k: v for k, v in item_data.items() if hasattr(model, k)})
                db.add(item)
        db.flush()

        # ── Restore custom DSO targets ──
        for t_data in backup.get("custom_targets", []):
            t_data.pop("id", None)
            t_data.pop("created_at", None)
            t_data["user_added"] = True
            t = DSOTarget(**{k: v for k, v in t_data.items() if hasattr(DSOTarget, k)})
            db.add(t)
        db.flush()

        # ── Restore user equipment selections ──
        for ue_data in backup.get("user_equipment", []):
            cat_name = ue_data.get("_catalog_name")
            cat_mfr = ue_data.get("_catalog_manufacturer")
            category = ue_data.get("category")

            # Try to find matching catalog item by name + manufacturer
            catalog_id = None
            if cat_name and category and category in EQUIPMENT_MODELS:
                model = EQUIPMENT_MODELS[category]
                match = db.query(model).filter(
                    model.name == cat_name,
                    model.manufacturer == cat_mfr
                ).first()
                if match:
                    catalog_id = match.id

            ue = UserEquipment(
                category=category or "unknown",
                catalog_id=catalog_id or ue_data.get("catalog_id"),
                custom_name=ue_data.get("custom_name"),
                is_primary=ue_data.get("is_primary", False),
                notes=ue_data.get("notes"),
            )
            db.add(ue)
        db.flush()

        # ── Restore projects (re-link to targets by name) ──
        project_id_map = {}  # old_id -> new_id
        for p_data in backup.get("projects", []):
            original_id = p_data.pop("_original_id", None)
            target_name = p_data.pop("_target_name", None)
            target_cat = p_data.pop("_target_catalog_id", None)
            p_data.pop("id", None)

            # Find target by catalog_id first, then name
            target = None
            if target_cat:
                target = db.query(DSOTarget).filter(DSOTarget.catalog_id == target_cat).first()
            if not target and target_name:
                target = db.query(DSOTarget).filter(DSOTarget.name == target_name).first()
            if not target:
                continue  # skip project if target not found

            # Parse dates
            for dk in ("started_at", "completed_at"):
                if p_data.get(dk) and isinstance(p_data[dk], str):
                    try:
                        p_data[dk] = datetime.fromisoformat(p_data[dk])
                    except ValueError:
                        p_data[dk] = None

            p = ImagingProject(
                target_id=target.id,
                **{k: v for k, v in p_data.items()
                   if hasattr(ImagingProject, k) and k not in ("target_id",)}
            )
            db.add(p)
            db.flush()
            if original_id is not None:
                project_id_map[original_id] = p.id

        # ── Restore sessions (re-link to projects) ──
        for s_data in backup.get("sessions", []):
            original_project_id = s_data.pop("_original_project_id", None)
            s_data.pop("id", None)

            # Re-link project
            new_project_id = project_id_map.get(original_project_id)
            s_data["project_id"] = new_project_id

            # Parse date
            if s_data.get("session_date") and isinstance(s_data["session_date"], str):
                try:
                    s_data["session_date"] = date.fromisoformat(s_data["session_date"])
                except ValueError:
                    s_data["session_date"] = date.today()
            if s_data.get("created_at") and isinstance(s_data["created_at"], str):
                try:
                    s_data["created_at"] = datetime.fromisoformat(s_data["created_at"])
                except ValueError:
                    s_data.pop("created_at", None)

            sess = SessionLog(
                **{k: v for k, v in s_data.items() if hasattr(SessionLog, k)}
            )
            db.add(sess)

        db.commit()
        return {"status": "restored", "projects": len(backup.get("projects", [])),
                "sessions": len(backup.get("sessions", []))}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Restore failed: {e}")
        raise HTTPException(500, f"Restore failed: {e}")
    finally:
        db.close()
