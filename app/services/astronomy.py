"""Astronomy computation service using Skyfield."""
import logging
from datetime import datetime, timedelta
from typing import Optional
import math

logger = logging.getLogger(__name__)

# Lazy-load skyfield to avoid slow import on startup
_ts = None
_planets = None


def _init_skyfield():
    global _ts, _planets
    if _ts is not None and _planets is not None:
        return  # Already initialized successfully
    from skyfield.api import Loader
    import os
    data_dir = os.environ.get('ASTRODASH_DATA', 'data')
    os.makedirs(data_dir, exist_ok=True)
    loader = Loader(data_dir)
    _ts = loader.timescale()
    try:
        _planets = loader('de421.bsp')
    except OSError as e:
        logger.warning(f"Failed to download de421.bsp: {e}. Trying de440s.bsp...")
        try:
            _planets = loader('de440s.bsp')
        except OSError as e2:
            logger.error(f"Cannot download any ephemeris file: {e2}")
            # Reset _ts so we retry next time
            _ts = None
            _planets = None
            raise RuntimeError(
                "Could not download ephemeris data from NASA JPL. "
                "Check your internet connection and try again."
            ) from e2


def get_twilight_times(lat: float, lon: float, dt: Optional[datetime] = None,
                       utc_offset_hours: float = -7.0) -> dict:
    """
    Compute sunset, civil/nautical/astronomical twilight for a given date.
    Returns all times in LOCAL time with formatted strings.
    Imaging window starts at the hour of civil twilight end.
    
    utc_offset_hours: offset from UTC in hours (e.g., -5 for EST, -7 for MST, +1 for CET).
                      Should be passed from the user's timezone setting.
    """
    _init_skyfield()
    from skyfield import almanac
    from skyfield.api import wgs84
    
    if dt is None:
        dt = datetime.now()
    
    location = wgs84.latlon(lat, lon)
    
    # Search window: noon local today to noon local tomorrow
    local_noon_utc_hour = 12 - utc_offset_hours
    t0 = _ts.utc(dt.year, dt.month, dt.day, int(local_noon_utc_hour), 0)
    t1 = _ts.utc(dt.year, dt.month, dt.day + 1, int(local_noon_utc_hour), 0)
    
    f = almanac.dark_twilight_day(_planets, location)
    times, events = almanac.find_discrete(t0, t1, f)
    
    def utc_to_local_str(t_utc):
        """Convert a UTC datetime to a local time string like '5:42 PM'."""
        if t_utc is None:
            return None
        total_hours = t_utc.hour + t_utc.minute / 60.0 + t_utc.second / 3600.0 + utc_offset_hours
        if total_hours < 0: total_hours += 24
        elif total_hours >= 24: total_hours -= 24
        h = int(total_hours)
        m = int((total_hours - h) * 60)
        if h == 0: return f"12:{m:02d} AM"
        elif h < 12: return f"{h}:{m:02d} AM"
        elif h == 12: return f"12:{m:02d} PM"
        else: return f"{h-12}:{m:02d} PM"
    
    def utc_to_local_hour(t_utc):
        """Convert a UTC datetime to local hour (float, for window filtering)."""
        if t_utc is None:
            return None
        h = t_utc.hour + t_utc.minute / 60.0 + utc_offset_hours
        if h < 0: h += 24
        elif h >= 24: h -= 24
        return h

    # Parse twilight transitions
    raw = {
        "sunset": None, "civil_end": None, "nautical_end": None, "astro_end": None,
        "astro_start": None, "nautical_start": None, "civil_start": None, "sunrise": None,
    }
    
    # Initialize prev_event from the state at search start (local noon).
    # This ensures we detect sunset (4→3) even if it's the first transition found.
    prev_event = int(f(t0))
    for t, e in zip(times, events):
        t_utc = t.utc_datetime()
        e = int(e)
        if prev_event == 4 and e == 3: raw["sunset"] = t_utc
        elif prev_event == 3 and e == 2: raw["civil_end"] = t_utc
        elif prev_event == 2 and e == 1: raw["nautical_end"] = t_utc
        elif prev_event == 1 and e == 0: raw["astro_end"] = t_utc
        elif prev_event == 0 and e == 1: raw["astro_start"] = t_utc
        elif prev_event == 1 and e == 2: raw["nautical_start"] = t_utc
        elif prev_event == 2 and e == 3: raw["civil_start"] = t_utc
        elif prev_event == 3 and e == 4: raw["sunrise"] = t_utc
        prev_event = e
    
    # Imaging starts at the hour of civil twilight end (when it's dark enough to begin setup)
    # This is rounded down to the hour — e.g. civil end at 6:12 PM → imaging start hour = 18
    civil_local_h = utc_to_local_hour(raw["civil_end"])
    if civil_local_h is not None:
        img_start_hour = int(civil_local_h)
    else:
        # Fallback: use sunset hour + 1
        sunset_local_h = utc_to_local_hour(raw["sunset"])
        img_start_hour = int(sunset_local_h) + 1 if sunset_local_h is not None else None
    
    if img_start_hour is not None and img_start_hour >= 24:
        img_start_hour -= 24

    result = {
        # Evening transitions (local time strings)
        "sunset": utc_to_local_str(raw["sunset"]),
        "civil_dusk": utc_to_local_str(raw["civil_end"]),
        "nautical_dusk": utc_to_local_str(raw["nautical_end"]),
        "astronomical_dusk": utc_to_local_str(raw["astro_end"]),
        # Morning transitions (kept for internal use)
        "astronomical_dawn": utc_to_local_str(raw["astro_start"]),
        "nautical_dawn": utc_to_local_str(raw["nautical_start"]),
        "civil_dawn": utc_to_local_str(raw["civil_start"]),
        "sunrise": utc_to_local_str(raw["sunrise"]),
        # Imaging window
        "imaging_start_hour": img_start_hour,
        "utc_offset_hours": utc_offset_hours,
    }

    logger.info(f"Twilight for ({lat:.2f}, {lon:.2f}) utc_offset={utc_offset_hours}h: "
                f"sunset_utc={raw['sunset']}, civil_end_utc={raw['civil_end']}, "
                f"sunset_local={result['sunset']}, "
                f"civil_dusk={result['civil_dusk']}, "
                f"nautical_dusk={result['nautical_dusk']}, "
                f"astro_dusk={result['astronomical_dusk']}, "
                f"imaging_start_hour={img_start_hour}")
    
    return result


def compute_target_position(ra_hours: float, dec_degrees: float, lat: float, lon: float,
                             dt: Optional[datetime] = None) -> dict:
    """
    Compute altitude, azimuth, and transit time for a target.
    
    ra_hours: Right Ascension in decimal hours (0-24)
    dec_degrees: Declination in decimal degrees (-90 to +90)
    """
    _init_skyfield()
    from skyfield.api import Star, wgs84
    
    if dt is None:
        dt = datetime.now()
    
    # Create target as a fixed star
    target = Star(ra_hours=ra_hours, dec_degrees=dec_degrees)
    location = wgs84.latlon(lat, lon)
    
    t = _ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute)
    
    # Compute position
    observer = (_planets['earth'] + location).at(t)
    apparent = observer.observe(target).apparent()
    alt, az, _ = apparent.altaz()
    
    return {
        "altitude": round(alt.degrees, 1),
        "azimuth": round(az.degrees, 1),
    }


def compute_target_visibility(ra_hours: float, dec_degrees: float, lat: float, lon: float,
                                dt: Optional[datetime] = None, min_altitude: float = 20,
                                utc_offset_hours: float = -7.0) -> dict:
    """
    Compute a target's visibility for tonight's imaging window.
    Returns transit time, max altitude, hours above min_altitude, etc.
    Uses sunset (derived from location and date) as the starting point.
    """
    _init_skyfield()
    from skyfield.api import Star, wgs84
    from skyfield import almanac
    
    if dt is None:
        dt = datetime.now()
    
    target = Star(ra_hours=ra_hours, dec_degrees=dec_degrees)
    location = wgs84.latlon(lat, lon)
    
    # Compute sunset for this location to determine when to start checking
    local_noon_utc_hour = 12 - utc_offset_hours
    t0 = _ts.utc(dt.year, dt.month, dt.day, int(local_noon_utc_hour), 0)
    t1 = _ts.utc(dt.year, dt.month, dt.day + 1, int(local_noon_utc_hour), 0)
    
    f = almanac.dark_twilight_day(_planets, location)
    times, events = almanac.find_discrete(t0, t1, f)
    
    # Find civil dusk (sunset as fallback)
    prev_event = int(f(t0))
    start_utc = None
    for t_ev, e in zip(times, events):
        e = int(e)
        if prev_event == 3 and e == 2:  # civil dusk
            start_utc = t_ev
            break
        if prev_event == 4 and e == 3 and start_utc is None:  # sunset as fallback
            start_utc = t_ev
        prev_event = e
    
    if start_utc is None:
        # Last resort: use local noon + 6 hours (roughly sunset)
        start_utc = t0
    
    # Check positions every 30 minutes from civil dusk for 12 hours
    positions = []
    max_alt = -90
    transit_time = None
    hours_above_min = 0
    
    start_jd = start_utc.tt  # Julian date
    for step in range(24):  # 12 hours in 30-min steps
        t = _ts.tt(jd=start_jd + step * (30 / 1440))  # 30 min = 30/1440 day
        
        observer = (_planets['earth'] + location).at(t)
        apparent = observer.observe(target).apparent()
        alt, az, _ = apparent.altaz()
        alt_deg = alt.degrees
        
        # Convert to local time for display
        utc_dt = t.utc_datetime()
        local_h = utc_dt.hour + utc_dt.minute / 60.0 + utc_offset_hours
        if local_h < 0: local_h += 24
        elif local_h >= 24: local_h -= 24
        local_hour = int(local_h)
        local_min = int((local_h - local_hour) * 60)
        time_str = f"{local_hour:02d}:{local_min:02d}"
        
        positions.append({
            "time": time_str,
            "altitude": round(float(alt_deg), 1),
            "azimuth": round(float(az.degrees), 1),
        })
        
        if alt_deg > max_alt:
            max_alt = float(alt_deg)
            transit_time = time_str
        
        if alt_deg >= min_altitude:
            hours_above_min += 0.5  # 30-min intervals
    
    # Determine cardinal direction at max altitude for horizon check
    if transit_time:
        for p in positions:
            if p["time"] == transit_time:
                az = p["azimuth"]
                if az >= 315 or az < 45:
                    direction = "N"
                elif az >= 45 and az < 135:
                    direction = "E"
                elif az >= 135 and az < 225:
                    direction = "S"
                else:
                    direction = "W"
                break
        else:
            direction = "?"
    else:
        direction = "?"
    
    # Is it circumpolar?
    circumpolar = bool((dec_degrees > (90 - lat)) if lat > 0 else (dec_degrees < (-90 - lat)))
    
    # Never rises check
    never_rises = bool(max_alt < 0)
    
    return {
        "max_altitude": round(float(max_alt), 1),
        "transit_time": transit_time,
        "transit_direction": direction,
        "hours_above_min": float(hours_above_min),
        "min_altitude_used": float(min_altitude),
        "circumpolar": circumpolar,
        "never_rises": never_rises,
        "positions": positions,
    }


def get_moon_info(lat: float, lon: float, dt: Optional[datetime] = None) -> dict:
    """Get moon illumination, phase, altitude, azimuth."""
    _init_skyfield()
    from skyfield.api import wgs84
    from skyfield.almanac import moon_phase
    
    if dt is None:
        dt = datetime.now()
    
    t = _ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute)
    location = wgs84.latlon(lat, lon)
    
    # Moon position
    moon = _planets['moon']
    earth = _planets['earth']
    sun = _planets['sun']
    
    observer = (earth + location).at(t)
    moon_apparent = observer.observe(moon).apparent()
    alt, az, _ = moon_apparent.altaz()
    
    # Phase angle for illumination
    phase_deg = moon_phase(_planets, t).degrees
    illumination = round((1 - math.cos(math.radians(phase_deg))) / 2 * 100, 1)
    
    # Moon separation from sun for phase name
    if phase_deg < 22.5:
        phase_name = "New Moon"
    elif phase_deg < 67.5:
        phase_name = "Waxing Crescent"
    elif phase_deg < 112.5:
        phase_name = "First Quarter"
    elif phase_deg < 157.5:
        phase_name = "Waxing Gibbous"
    elif phase_deg < 202.5:
        phase_name = "Full Moon"
    elif phase_deg < 247.5:
        phase_name = "Waning Gibbous"
    elif phase_deg < 292.5:
        phase_name = "Last Quarter"
    elif phase_deg < 337.5:
        phase_name = "Waning Crescent"
    else:
        phase_name = "New Moon"
    
    return {
        "illumination": float(illumination),
        "phase_degrees": round(float(phase_deg), 1),
        "phase_name": phase_name,
        "altitude": round(float(alt.degrees), 1),
        "azimuth": round(float(az.degrees), 1),
        "is_up": bool(alt.degrees > 0),
    }


def moon_separation(target_ra_hours: float, target_dec_degrees: float,
                     lat: float, lon: float, dt: Optional[datetime] = None) -> float:
    """Compute angular separation between moon and target in degrees."""
    _init_skyfield()
    from skyfield.api import Star, wgs84
    
    if dt is None:
        dt = datetime.now()
    
    t = _ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute)
    location = wgs84.latlon(lat, lon)
    
    target = Star(ra_hours=target_ra_hours, dec_degrees=target_dec_degrees)
    
    observer = (_planets['earth'] + location).at(t)
    moon_pos = observer.observe(_planets['moon']).apparent()
    target_pos = observer.observe(target).apparent()
    
    sep = moon_pos.separation_from(target_pos)
    return round(float(sep.degrees), 1)

def get_moon_window_info(lat: float, lon: float, img_start_hour: int, img_end_hour: int,
                          utc_offset_hours: float = -7.0, dt: Optional[datetime] = None) -> dict:
    """Compute moon altitude range and rise/set times during the imaging window.
    
    Returns min/max altitude, whether moon is up during window, and moon rise/set
    times if they fall within the window.
    """
    _init_skyfield()
    from skyfield.api import wgs84
    from skyfield.almanac import moon_phase
    
    if dt is None:
        dt = datetime.now()
    
    location = wgs84.latlon(lat, lon)
    moon = _planets['moon']
    earth = _planets['earth']
    
    # Build list of UTC hours to sample across the imaging window
    # img_start_hour and img_end_hour are local hours (e.g. 20, 1)
    sample_hours = []
    h = img_start_hour
    while True:
        sample_hours.append(h)
        if h == img_end_hour:
            break
        h = (h + 1) % 24
        if len(sample_hours) > 14:
            break
    
    altitudes = []
    for local_h in sample_hours:
        # Convert local hour to UTC
        utc_h = local_h - utc_offset_hours
        # Determine the correct date — hours after midnight are next day
        day_offset = 0
        if local_h < 12:  # early morning hours = next calendar day
            day_offset = 1
        t = _ts.utc(dt.year, dt.month, dt.day + day_offset, int(utc_h), 30)
        observer = (earth + location).at(t)
        moon_apparent = observer.observe(moon).apparent()
        alt, _, _ = moon_apparent.altaz()
        altitudes.append({"hour": local_h, "altitude": round(float(alt.degrees), 1)})
    
    alts_above = [a for a in altitudes if a["altitude"] > 0]
    all_alts = [a["altitude"] for a in altitudes]
    
    # Find when moon crosses the horizon during the window
    rises_at = None
    sets_at = None
    for i in range(1, len(altitudes)):
        prev = altitudes[i-1]["altitude"]
        curr = altitudes[i]["altitude"]
        if prev <= 0 and curr > 0:
            rises_at = altitudes[i]["hour"]
        elif prev > 0 and curr <= 0:
            sets_at = altitudes[i]["hour"]
    
    # Format rise/set as local time strings
    def hour_to_str(h):
        if h is None:
            return None
        ampm = "AM" if h < 12 else "PM"
        h12 = h % 12
        if h12 == 0:
            h12 = 12
        return f"{h12}:30 {ampm}"
    
    # Illumination (doesn't change meaningfully during one night)
    t_mid = _ts.utc(dt.year, dt.month, dt.day, int(12 - utc_offset_hours + 6), 0)
    phase_deg = moon_phase(_planets, t_mid).degrees
    illumination = round((1 - math.cos(math.radians(phase_deg))) / 2 * 100, 1)
    
    return {
        "illumination": illumination,
        "alt_min": min(all_alts) if all_alts else 0,
        "alt_max": max(all_alts) if all_alts else 0,
        "up_during_window": len(alts_above) > 0,
        "hours_above_horizon": len(alts_above),
        "total_window_hours": len(altitudes),
        "rises_at": hour_to_str(rises_at),
        "sets_at": hour_to_str(sets_at),
        "altitudes": altitudes,
    }
