"""Astrospheric API service — handles forecast fetching, caching, and scoring.

API Reference: https://www.astrospheric.com/DynamicContent/api_info.html

Key facts from the Astrospheric API:
- GetForecastData_V1 returns an 81-hour forecast (5 credits)
- Each weather variable is Array<HourValue> — one entry per hour
- HourValue has "Value" (raw number) and "MapColor" (hex color string)
- Arrays are index-based: index 0 = LocalStartTime, index 1 = +1 hour, etc.
- Temperature and DewPoint are in KELVIN
- Wind is in meters/second
- Cloud cover is 0-100 percent
- Transparency is unitless (0-5 Excellent, 6-9 Above Average, etc.)
- Seeing is unitless (0 Cloudy through 5 Excellent)
"""
import httpx
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from ..models.database import ForecastCache, UserSettings, get_engine, get_session

logger = logging.getLogger(__name__)

FORECAST_URL = "https://astrosphericpublicaccess.azurewebsites.net/api/GetForecastData_V1"
SKY_URL = "https://astrosphericpublicaccess.azurewebsites.net/api/GetSky_V1"


async def fetch_forecast(api_key: str, lat: float, lon: float) -> Optional[dict]:
    """Fetch forecast from Astrospheric (5 credits)."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(FORECAST_URL, json={
                "Latitude": lat, "Longitude": lon, "APIKey": api_key
            })
            if resp.status_code == 200:
                data = resp.json()
                # Log structure for debugging
                cloud_arr = data.get("RDPS_CloudCover", [])
                if cloud_arr:
                    logger.info(f"Forecast received: {len(cloud_arr)} hours, "
                               f"LocalStartTime={data.get('LocalStartTime')}, "
                               f"first cloud entry keys: {list(cloud_arr[0].keys()) if cloud_arr else 'empty'}")
                return data
            else:
                logger.error(f"Astrospheric forecast HTTP {resp.status_code}: {resp.text[:500]}")
                return None
    except httpx.ConnectError as e:
        logger.error(f"Astrospheric connection failed: {type(e).__name__}: {e}")
        return None
    except httpx.TimeoutException as e:
        logger.error(f"Astrospheric timed out: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.error(f"Astrospheric exception: {type(e).__name__}: {e}", exc_info=True)
        return None


async def fetch_sky(api_key: str, lat: float, lon: float) -> Optional[dict]:
    """Fetch sky data from Astrospheric (1 credit)."""
    import time
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(SKY_URL, json={
                "Latitude": lat, "Longitude": lon,
                "MSSinceEpoch": int(time.time() * 1000),
                "APIKey": api_key
            })
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.error(f"Astrospheric sky HTTP {resp.status_code}: {resp.text[:500]}")
                return None
    except Exception as e:
        logger.error(f"Astrospheric sky exception: {type(e).__name__}: {e}", exc_info=True)
        return None


def get_value(hour_value_obj) -> float:
    """Extract numeric value from an Astrospheric HourValue object.
    
    Actual API format (confirmed from live data):
    {"Value": {"ValueColor": "#2666A6", "ActualValue": 21.176}, "HourOffset": 0}
    
    So: obj["Value"]["ActualValue"] is the number we want.
    """
    if hour_value_obj is None:
        return 0.0
    if isinstance(hour_value_obj, (int, float)):
        return float(hour_value_obj)
    if isinstance(hour_value_obj, dict):
        val = hour_value_obj.get("Value", 0)
        if isinstance(val, dict):
            # Primary path: Value -> ActualValue
            return float(val.get("ActualValue", 0))
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return 0.0
        return 0.0
    return 0.0


def extract_all_hours(raw_data: dict) -> dict:
    """
    Extract ALL 81 forecast hours into structured data.
    Returns dict with arrays indexed by local hour, each entry having
    the raw value and the local hour number.
    """
    local_start = raw_data.get("LocalStartTime", "")
    if "T" in local_start:
        start_h = int(local_start.split("T")[1].split(":")[0])
    else:
        start_h = datetime.now().hour

    variables = {
        "cloud": "RDPS_CloudCover",
        "transparency": "Astrospheric_Transparency",
        "seeing": "Astrospheric_Seeing",
        "wind": "RDPS_WindVelocity",
        "temperature": "RDPS_Temperature",
        "dewpoint": "RDPS_DewPoint",
    }

    # Find the longest array to know how many hours we have
    max_hours = 0
    for api_key in variables.values():
        arr = raw_data.get(api_key, [])
        if len(arr) > max_hours:
            max_hours = len(arr)

    result = {k: [] for k in variables}
    result["hours"] = []
    result["start_hour"] = start_h
    result["num_forecast_hours"] = max_hours

    for i in range(max_hours):
        local_h = (start_h + i) % 24
        result["hours"].append(local_h)

        for key, api_key in variables.items():
            arr = raw_data.get(api_key, [])
            if i < len(arr):
                val = get_value(arr[i])
            else:
                val = 0.0
            result[key].append({"hour": local_h, "hour_index": i, "value": round(val, 2)})

    return result


def filter_imaging_window(all_hours: dict, img_start_hour: int, img_end_hour: int) -> dict:
    """
    Filter the full forecast to only TONIGHT's imaging window hours.
    img_start_hour: e.g. 18 for 6 PM (civil dusk, local)
    img_end_hour: e.g. 1 for 1 AM (user stop time, local)
    
    The window wraps past midnight: e.g. 18, 19, 20, 21, 22, 23, 0, 1
    Only takes the FIRST occurrence (tonight), not subsequent days.
    
    Important: the forecast may not start until after img_start_hour
    (e.g., forecast starts at 20:00 but civil dusk is 18:00).
    In that case, we start from the first available hour.
    """
    variables = ["cloud", "transparency", "seeing", "wind", "temperature", "dewpoint"]
    result = {k: [] for k in variables}
    result["hours"] = []

    all_hour_list = all_hours.get("hours", [])
    if not all_hour_list:
        return result

    forecast_start_hour = all_hour_list[0]

    # Determine the effective start hour.
    # If civil dusk (img_start_hour) is BEFORE the forecast start in tonight's sequence,
    # we can't show those hours (no data), so start from the forecast's first hour.
    # Example: civil dusk at 18, forecast starts at 20 → effective start = 20
    effective_start = img_start_hour
    
    if img_start_hour != forecast_start_hour:
        if img_start_hour > img_end_hour:
            # Window crosses midnight (e.g., 18 -> 1)
            # If img_start is before forecast_start in tonight's sequence, use forecast_start
            if img_start_hour < forecast_start_hour:
                effective_start = forecast_start_hour
        else:
            # Window doesn't cross midnight
            if img_start_hour < forecast_start_hour:
                effective_start = forecast_start_hour

    if effective_start != img_start_hour:
        logger.info(f"Imaging window adjusted: civil dusk hour {img_start_hour} before "
                     f"forecast start {forecast_start_hour}, using {effective_start}")

    found_start = False
    collected_count = 0

    for i, local_h in enumerate(all_hour_list):
        if not found_start:
            if local_h == effective_start:
                found_start = True
            else:
                continue

        if found_start:
            # Check if we've passed the end of the window
            if effective_start > img_end_hour:
                # Window crosses midnight
                if local_h > img_end_hour and local_h < effective_start:
                    break
            else:
                if local_h > img_end_hour:
                    break

            # Safety: don't collect more than 24 hours
            if collected_count >= 24:
                break

            result["hours"].append(local_h)
            for key in variables:
                arr = all_hours.get(key, [])
                if i < len(arr):
                    result[key].append(arr[i])
                else:
                    result[key].append({"hour": local_h, "hour_index": i, "value": 0})
            collected_count += 1

    return result


def filter_tomorrow_window(all_hours: dict, img_start_hour: int, img_end_hour: int) -> dict:
    """
    Filter the forecast to TOMORROW NIGHT's imaging window.
    Skips past tonight's window and finds the second occurrence.
    
    With an 82-hour forecast starting at 8 PM today, tomorrow's 
    imaging window (e.g., 18-01) starts around index 22-46.
    """
    variables = ["cloud", "transparency", "seeing", "wind", "temperature", "dewpoint"]
    result = {k: [] for k in variables}
    result["hours"] = []

    all_hour_list = all_hours.get("hours", [])
    if not all_hour_list:
        return result

    # Strategy: find the SECOND occurrence of img_start_hour in the forecast.
    # The first occurrence is tonight's window start; the second is tomorrow's.
    start_index = None
    occurrences = 0
    for i, h in enumerate(all_hour_list):
        if h == img_start_hour:
            occurrences += 1
            if occurrences >= 2:
                start_index = i
                break
    
    # If we only found one occurrence, the forecast may be too short for tomorrow
    if start_index is None:
        logger.info("Tomorrow forecast: could not find tomorrow's imaging window in forecast data")
        return result

    collected = 0
    for i in range(start_index, len(all_hour_list)):
        local_h = all_hour_list[i]
        
        # Check end condition
        if collected > 0:
            if img_start_hour > img_end_hour:
                if local_h > img_end_hour and local_h < img_start_hour:
                    break
            else:
                if local_h > img_end_hour:
                    break
        
        if collected >= 24:
            break

        result["hours"].append(local_h)
        for key in variables:
            arr = all_hours.get(key, [])
            if i < len(arr):
                result[key].append(arr[i])
            else:
                result[key].append({"hour": local_h, "hour_index": i, "value": 0})
        collected += 1

    logger.info(f"Tomorrow window: found {collected} hours starting at index {start_index} "
                f"(hours: {result['hours']})")
    return result


def score_hour(cloud: float, transparency: float, seeing: float, wind_ms: float) -> int:
    """Score a single hour 0-100 for imaging quality."""
    score = 100

    # Cloud penalty (biggest factor)
    if cloud > 30:
        score -= 60
    elif cloud > 10:
        score -= int((cloud - 10) * 1.5)

    # Transparency penalty
    if transparency >= 24:
        score -= 30
    elif transparency >= 14:
        score -= 20
    elif transparency > 9:
        score -= 8

    # Seeing penalty
    if seeing <= 1:
        score -= 15
    elif seeing == 2:
        score -= 8
    elif seeing == 3:
        score -= 3

    # Wind penalty
    wind_mph = wind_ms * 2.237
    if wind_mph >= 25:
        score -= 25
    elif wind_mph >= 15:
        score -= int((wind_mph - 10) * 1.5)
    elif wind_mph >= 10:
        score -= 5

    return max(0, min(100, score))


def kelvin_to_f(k: float) -> int:
    """Convert Kelvin to Fahrenheit."""
    return round((k - 273.15) * 9 / 5 + 32)


def transparency_label(val: float) -> str:
    """Convert transparency value to text label."""
    if val <= 5: return "Excellent"
    if val <= 9: return "Above Average"
    if val <= 13: return "Average"
    if val <= 23: return "Below Average"
    if val <= 27: return "Poor"
    return "Cloudy"


def seeing_label(val: float) -> str:
    """Convert seeing value to text label."""
    labels = {0: "Cloudy", 1: "Poor", 2: "Below Average",
              3: "Average", 4: "Above Average", 5: "Excellent"}
    return labels.get(int(round(val)), "Average")


def format_hour(h: int) -> str:
    """Format hour number to readable time string."""
    if h == 0: return "12:00 AM"
    if h < 12: return f"{h}:00 AM"
    if h == 12: return "12:00 PM"
    return f"{h-12}:00 PM"


def compute_tonight_forecast(all_hours: dict, img_start_hour: int, img_end_hour: int = 1,
                              moon_illumination: float = 0) -> dict:
    """
    Compute tonight's imaging forecast from the full forecast data.
    """
    window = filter_imaging_window(all_hours, img_start_hour, img_end_hour)
    
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

        temp_f = kelvin_to_f(temp_k) if temp_k > 100 else 0  # sanity check
        dew_f = kelvin_to_f(dew_k) if dew_k > 100 else 0
        wind_mph = round(w * 2.237)

        logger.info(f"Hour {local_h}: cloud={c}%, transp={t}, see={s}, "
                     f"wind={w}m/s={wind_mph}mph, temp={temp_k}K={temp_f}F, dew={dew_k}K={dew_f}F")

        hours.append({
            "hour": local_h,
            "time": format_hour(local_h),
            "score": hour_score,
            "cloud_pct": round(c, 1),
            "transparency": transparency_label(t),
            "transparency_raw": round(t, 1),
            "seeing": seeing_label(s),
            "seeing_raw": round(s, 1),
            "wind_mph": wind_mph,
            "wind_ms": round(w, 2),
            "temp_f": temp_f,
            "dew_point_f": dew_f,
            "dew_depression_f": temp_f - dew_f,
        })

    avg_score = round(sum(scores) / len(scores)) if scores else 0

    # Verdict
    if avg_score >= 70: verdict = "GO"
    elif avg_score >= 45: verdict = "MAYBE"
    else: verdict = "NO-GO"

    # Worst issue
    if max_cloud > 30:
        worst = f"Clouds ({round(max_cloud)}%)"
    elif max_wind > 8.9:
        worst = f"Wind ({round(max_wind * 2.237)} mph)"
    elif max_transp > 14:
        worst = "Poor transparency"
    else:
        worst = "All clear"

    # Filter recommendation
    if moon_illumination > 40:
        filter_rec = "L-Quad Enhance"
        filter_detail = f"Moon {round(moon_illumination)}% — too bright for broadband. Use narrowband on emission targets."
    elif moon_illumination > 15:
        filter_rec = "L-Pro or L-Quad"
        filter_detail = f"Moon {round(moon_illumination)}% — L-Pro early, switch to L-Quad when Moon rises."
    else:
        filter_rec = "L-Pro"
        filter_detail = f"Moon {round(moon_illumination)}% — dark skies! Use L-Pro on galaxies and broadband targets."

    best = max(hours, key=lambda x: x["score"]) if hours else None

    # Target-type verdicts
    bb_score = avg_score
    nb_score = avg_score
    if moon_illumination > 40: bb_score = max(0, bb_score - 30)
    if moon_illumination > 70: bb_score = max(0, bb_score - 20)

    return {
        "score": avg_score,
        "verdict": verdict,
        "hours": hours,
        "filter_recommendation": filter_rec,
        "filter_detail": filter_detail,
        "worst_issue": worst,
        "best_hour": best,
        "imaging_window_start": img_start_hour,
        "imaging_window_end": img_end_hour,
        "num_hours": len(hours),
        "broadband_verdict": "GO" if bb_score >= 70 else ("MAYBE" if bb_score >= 45 else "NO-GO"),
        "broadband_score": bb_score,
        "narrowband_verdict": "GO" if nb_score >= 70 else ("MAYBE" if nb_score >= 45 else "NO-GO"),
        "narrowband_score": nb_score,
        "moon_illumination": round(moon_illumination, 1),
    }


async def poll_and_cache(db_path: str = "data/astrodash.db"):
    """Background task: fetch forecast and cache it."""
    engine = get_engine(db_path)
    session = get_session(engine)

    try:
        settings = session.query(UserSettings).first()
        if not settings or not settings.astrospheric_api_key:
            logger.info("No API key configured, skipping poll")
            return
        if not settings.latitude or not settings.longitude:
            logger.info("No location configured, skipping poll")
            return

        # Fetch forecast
        raw = await fetch_forecast(settings.astrospheric_api_key,
                                    settings.latitude, settings.longitude)
        if not raw:
            logger.warning("Failed to fetch forecast")
            return

        # Fetch sky data
        sky = await fetch_sky(settings.astrospheric_api_key,
                               settings.latitude, settings.longitude)

        # Extract all hours (store full forecast)
        all_hours = extract_all_hours(raw)

        # Log first entry of each variable for debugging
        for var_name in ["RDPS_CloudCover", "RDPS_Temperature", "RDPS_WindVelocity",
                         "Astrospheric_Transparency", "Astrospheric_Seeing"]:
            arr = raw.get(var_name, [])
            if arr:
                logger.info(f"DEBUG {var_name}[0] = {arr[0]}")

        # Build cache entry — store the full extracted data as JSON
        cache = ForecastCache(
            fetched_at=datetime.utcnow(),
            model_time=raw.get("ModelTime"),
            local_start_time=raw.get("LocalStartTime"),
            utc_start_time=raw.get("UTCStartTime"),
            utc_minute_offset=raw.get("UTCMinuteOffset"),
            cloud_data=all_hours["cloud"],
            transparency_data=all_hours["transparency"],
            seeing_data=all_hours["seeing"],
            wind_data=all_hours["wind"],
            temperature_data=all_hours["temperature"],
            dewpoint_data=all_hours["dewpoint"],
            credits_used=raw.get("APICreditUsedToday"),
        )

        if sky:
            moon = sky.get("Moon", {})
            cache.moon_illumination = moon.get("Illumination", 0)
            cache.moon_altitude = moon.get("Altitude", 0)
            cache.moon_phase = moon.get("Phase", 0)

        session.add(cache)

        # Keep only last 48 hours of cache
        cutoff = datetime.utcnow() - timedelta(hours=48)
        session.query(ForecastCache).filter(ForecastCache.fetched_at < cutoff).delete()

        session.commit()
        logger.info(f"Forecast cached. {all_hours['num_forecast_hours']} hours, "
                     f"start_hour={all_hours['start_hour']}. Credits: {cache.credits_used}")

    except Exception as e:
        logger.error(f"Poll error: {type(e).__name__}: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()
