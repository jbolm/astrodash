"""Database models for AstroDash."""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, Text, DateTime, Date,
    ForeignKey, JSON, Enum as SAEnum, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import enum

Base = declarative_base()


# ─── Enums ───────────────────────────────────────────────────────────

class MountType(str, enum.Enum):
    EQ = "Equatorial"
    AZ = "Alt-Azimuth"
    EQ_AZ = "EQ/AZ Hybrid"
    STAR_TRACKER = "Star Tracker"

class TelescopeType(str, enum.Enum):
    REFRACTOR = "Refractor"
    REFLECTOR = "Reflector"
    SCT = "Schmidt-Cassegrain"
    RASA = "Rowe-Ackermann Schmidt"
    EDGEHD = "EdgeHD"
    CAMERA_LENS = "Camera Lens"
    MAKSUTOV = "Maksutov"
    RITCHEY_CHRETIEN = "Ritchey-Chrétien"

class CameraSensorType(str, enum.Enum):
    CMOS = "CMOS"
    CCD = "CCD"

class CameraColorType(str, enum.Enum):
    COLOR = "Color (OSC)"
    MONO = "Mono"

class FilterType(str, enum.Enum):
    BROADBAND = "Broadband/LP"
    NARROWBAND = "Narrowband"
    DUOBAND = "Duo-Band"
    TRIBAND = "Tri-Band"
    QUADBAND = "Quad-Band"
    UV_IR_CUT = "UV/IR Cut"
    CLEAR = "Clear"
    HA = "Hydrogen-Alpha"
    OIII = "Oxygen-III"
    SII = "Sulfur-II"
    HB = "Hydrogen-Beta"
    LUMINANCE = "Luminance"
    RED = "Red"
    GREEN = "Green"
    BLUE = "Blue"

class FilterSize(str, enum.Enum):
    S_1_25 = '1.25"'
    S_2 = '2"'
    S_36MM = "36mm"
    S_50MM = "50mm"
    S_54MM = "54mm"
    UNMOUNTED = "Unmounted"
    DROP_IN = "Drop-In"

class AccessoryType(str, enum.Enum):
    FIELD_FLATTENER = "Field Flattener"
    REDUCER = "Focal Reducer"
    FLATTENER_REDUCER = "Flattener/Reducer"
    COMA_CORRECTOR = "Coma Corrector"
    FILTER_DRAWER = "Filter Drawer"
    FILTER_WHEEL = "Filter Wheel"
    OAG = "Off-Axis Guider"
    GUIDE_SCOPE = "Guide Scope"
    ROTATOR = "Rotator"
    FOCUSER = "Electronic Focuser"
    DEW_HEATER = "Dew Heater"
    ADAPTER = "Adapter/Spacer"
    POWER = "Power Supply"

class TargetType(str, enum.Enum):
    EMISSION_NEBULA = "Emission Nebula"
    PLANETARY_NEBULA = "Planetary Nebula"
    REFLECTION_NEBULA = "Reflection Nebula"
    DARK_NEBULA = "Dark Nebula"
    SUPERNOVA_REMNANT = "Supernova Remnant"
    SPIRAL_GALAXY = "Spiral Galaxy"
    ELLIPTICAL_GALAXY = "Elliptical Galaxy"
    IRREGULAR_GALAXY = "Irregular Galaxy"
    GALAXY_GROUP = "Galaxy Group"
    OPEN_CLUSTER = "Open Cluster"
    GLOBULAR_CLUSTER = "Globular Cluster"
    PLANET = "Planet"
    MOON = "Moon"
    SUN = "Sun"
    STAR_FIELD = "Star Field"
    MIXED = "Mixed/Complex"


# ─── User Settings ───────────────────────────────────────────────────

class UserSettings(Base):
    __tablename__ = "user_settings"
    id = Column(Integer, primary_key=True, default=1)
    # API & Location
    astrospheric_api_key = Column(String(256), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String(128), nullable=True)
    timezone = Column(String(64), default="America/Denver")  # Set during setup
    bortle_zone = Column(Integer, default=5)
    # Horizon limits (minimum altitude in degrees per direction)
    horizon_north = Column(Integer, default=30)
    horizon_east = Column(Integer, default=15)
    horizon_south = Column(Integer, default=15)
    horizon_west = Column(Integer, default=15)
    # Preferences
    preferred_targets = Column(JSON, default=list)  # list of TargetType values
    imaging_end_hour = Column(Integer, default=1)  # 0=midnight, 1=1AM, etc.
    # Notifications
    notify_enabled = Column(Boolean, default=False)
    notify_method = Column(String(32), default="ntfy")  # "ntfy", "discord", "webhook"
    notify_webhook_url = Column(String(512), nullable=True)
    notify_discord_url = Column(String(512), nullable=True)
    notify_ntfy_server = Column(String(256), default="https://ntfy.sh")
    notify_ntfy_topic = Column(String(128), nullable=True)
    notify_go_threshold = Column(Integer, default=70)
    notify_hours_before_dark = Column(Integer, default=6)  # hours before astronomical dusk
    notify_interval_hours = Column(Integer, default=24)  # re-send interval in hours
    notify_template = Column(Text, nullable=True)  # custom message template with {variables}
    notify_nogo = Column(Boolean, default=False)  # also notify on NO-GO conditions
    notify_quiet_start = Column(Integer, nullable=True)  # don't notify before this hour (0-23 local)
    notify_last_sent_date = Column(String(10), nullable=True)  # 'YYYY-MM-DD' of last sent, prevents dups
    notify_last_sent_ts = Column(Float, nullable=True)  # unix timestamp of last sent, for repeat interval
    # Dark library tracking
    dark_last_date = Column(Date, nullable=True)
    dark_temp_c = Column(Float, nullable=True)
    dark_gain = Column(Integer, nullable=True)
    dark_reminder_months = Column(Integer, default=6)
    # Setup state
    setup_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Equipment Catalog ───────────────────────────────────────────────

class Mount(Base):
    __tablename__ = "mounts"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    manufacturer = Column(String(64), nullable=False)
    mount_type = Column(String(32), nullable=False)
    max_payload_kg = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    periodic_error_arcsec = Column(Float, nullable=True)
    goto = Column(Boolean, default=True)
    tracking_modes = Column(String(128), nullable=True)  # "Sidereal,Lunar,Solar"
    power_input = Column(String(64), nullable=True)
    price_usd = Column(Integer, nullable=True)
    url = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    is_catalog = Column(Boolean, default=True)  # False for user-added
    created_at = Column(DateTime, default=datetime.utcnow)


class Telescope(Base):
    __tablename__ = "telescopes"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    manufacturer = Column(String(64), nullable=False)
    telescope_type = Column(String(32), nullable=False)
    aperture_mm = Column(Float, nullable=True)
    focal_length_mm = Column(Float, nullable=True)
    focal_ratio = Column(Float, nullable=True)
    native_back_focus_mm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    field_type = Column(String(32), nullable=True)  # "Flat", "Curved"
    image_circle_mm = Column(Float, nullable=True)
    price_usd = Column(Integer, nullable=True)
    url = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    is_catalog = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    manufacturer = Column(String(64), nullable=False)
    sensor_model = Column(String(64), nullable=True)
    sensor_type = Column(String(16), default="CMOS")
    color_type = Column(String(16), default="Color (OSC)")
    pixel_size_um = Column(Float, nullable=True)
    resolution_x = Column(Integer, nullable=True)
    resolution_y = Column(Integer, nullable=True)
    sensor_width_mm = Column(Float, nullable=True)
    sensor_height_mm = Column(Float, nullable=True)
    sensor_diagonal_mm = Column(Float, nullable=True)
    read_noise_e = Column(Float, nullable=True)  # at unity/HCG gain
    full_well_ke = Column(Float, nullable=True)
    cooling = Column(Boolean, default=False)
    cooling_delta_c = Column(Float, nullable=True)
    back_focus_mm = Column(Float, nullable=True)
    guide_sensor = Column(Boolean, default=False)
    guide_sensor_model = Column(String(64), nullable=True)
    adc_bit = Column(Integer, nullable=True)  # 12, 14, 16
    usb_type = Column(String(16), nullable=True)
    weight_g = Column(Integer, nullable=True)
    hcg_gain = Column(Integer, nullable=True)  # HCG/Unity gain value
    price_usd = Column(Integer, nullable=True)
    url = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    is_catalog = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Filter(Base):
    __tablename__ = "filters"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    manufacturer = Column(String(64), nullable=False)
    filter_type = Column(String(32), nullable=False)
    bandpass = Column(String(256), nullable=True)  # e.g. "Ha 7nm, OIII 7nm"
    filter_size = Column(String(16), nullable=True)
    thickness_mm = Column(Float, nullable=True)
    transmission_pct = Column(Float, nullable=True)  # peak transmission
    broadband_friendly = Column(Boolean, default=True)
    narrowband_friendly = Column(Boolean, default=False)
    moonlight_resistant = Column(Boolean, default=False)
    price_usd = Column(Integer, nullable=True)
    url = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    is_catalog = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Accessory(Base):
    __tablename__ = "accessories"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    manufacturer = Column(String(64), nullable=False)
    accessory_type = Column(String(32), nullable=False)
    back_focus_mm = Column(Float, nullable=True)
    magnification = Column(Float, nullable=True)  # e.g. 0.8 for reducer
    input_thread = Column(String(32), nullable=True)
    output_thread = Column(String(32), nullable=True)
    weight_g = Column(Integer, nullable=True)
    price_usd = Column(Integer, nullable=True)
    url = Column(String(512), nullable=True)
    notes = Column(Text, nullable=True)
    is_catalog = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── User Equipment (what the user actually owns) ────────────────────

class UserEquipment(Base):
    __tablename__ = "user_equipment"
    id = Column(Integer, primary_key=True)
    category = Column(String(32), nullable=False)  # "mount","telescope","camera","filter","accessory"
    catalog_id = Column(Integer, nullable=True)  # FK to the catalog table
    custom_name = Column(String(128), nullable=True)  # for custom entries
    is_primary = Column(Boolean, default=False)  # primary imaging setup
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── DSO Catalog ─────────────────────────────────────────────────────

class DSOTarget(Base):
    __tablename__ = "dso_targets"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)  # "Orion Nebula"
    catalog_id = Column(String(32), nullable=True)  # "M42"
    alt_catalog_ids = Column(String(256), nullable=True)  # "NGC 1976, Sh2-281"
    target_type = Column(String(32), nullable=False)
    ra_hours = Column(Float, nullable=False)  # Right Ascension in decimal hours
    dec_degrees = Column(Float, nullable=False)  # Declination in decimal degrees
    magnitude = Column(Float, nullable=True)
    size_arcmin = Column(Float, nullable=True)  # Largest angular dimension
    size_arcmin_minor = Column(Float, nullable=True)  # Minor axis
    constellation = Column(String(32), nullable=True)
    season = Column(String(32), nullable=True)  # "Winter", "Spring", etc.
    difficulty = Column(String(16), nullable=True)  # "Easy", "Moderate", "Hard"
    recommended_min_hours = Column(Float, nullable=True)  # min integration time
    recommended_focal_length_min = Column(Integer, nullable=True)
    recommended_focal_length_max = Column(Integer, nullable=True)
    narrowband_target = Column(Boolean, default=False)
    broadband_target = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    is_catalog = Column(Boolean, default=True)
    user_added = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── Integration Time Tracking ───────────────────────────────────────

class ImagingProject(Base):
    __tablename__ = "imaging_projects"
    id = Column(Integer, primary_key=True)
    target_id = Column(Integer, ForeignKey("dso_targets.id"), nullable=False)
    name = Column(String(128), nullable=True)  # Custom project name
    goal_hours = Column(Float, default=4.0)
    goal_l_hours = Column(Float, default=0.0)
    goal_r_hours = Column(Float, default=0.0)
    goal_g_hours = Column(Float, default=0.0)
    goal_b_hours = Column(Float, default=0.0)
    goal_sii_hours = Column(Float, default=0.0)
    goal_ha_hours = Column(Float, default=0.0)
    goal_oiii_hours = Column(Float, default=0.0)
    goal_rgb_hours = Column(Float, default=0.0)  # legacy, kept for migration
    accumulated_hours = Column(Float, default=0.0)
    status = Column(String(16), default="not_started")  # "not_started", "active", "complete"
    filter_used = Column(String(64), nullable=True)
    gain = Column(Integer, nullable=True)
    sub_length_s = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    target = relationship("DSOTarget")
    sessions = relationship("SessionLog", back_populates="project")


# ─── Session Log ─────────────────────────────────────────────────────

class SessionLog(Base):
    __tablename__ = "session_logs"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("imaging_projects.id"), nullable=True)
    session_date = Column(Date, nullable=False)
    target_name = Column(String(128), nullable=True)
    # Conditions recorded
    cloud_cover_pct = Column(Float, nullable=True)
    transparency = Column(String(32), nullable=True)
    seeing = Column(String(32), nullable=True)
    wind_mph = Column(Float, nullable=True)
    temperature_f = Column(Float, nullable=True)
    moon_illumination_pct = Column(Float, nullable=True)
    bortle = Column(Integer, nullable=True)
    # Equipment used
    camera_used = Column(String(128), nullable=True)
    telescope_used = Column(String(128), nullable=True)
    mount_used = Column(String(128), nullable=True)
    # Imaging details
    filter_used = Column(String(64), nullable=True)
    sub_length_s = Column(Integer, nullable=True)
    num_subs = Column(Integer, nullable=True)
    total_integration_min = Column(Float, nullable=True)
    integration_l_min = Column(Float, nullable=True)
    integration_r_min = Column(Float, nullable=True)
    integration_g_min = Column(Float, nullable=True)
    integration_b_min = Column(Float, nullable=True)
    integration_rgb_min = Column(Float, nullable=True)  # legacy
    integration_ha_min = Column(Float, nullable=True)
    integration_oiii_min = Column(Float, nullable=True)
    integration_sii_min = Column(Float, nullable=True)
    gain = Column(Integer, nullable=True)
    camera_temp_c = Column(Float, nullable=True)
    # Quality assessment
    rating = Column(Integer, nullable=True)  # 1-5 stars
    guiding_rms_arcsec = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("ImagingProject", back_populates="sessions")


# ─── Cached Forecast ─────────────────────────────────────────────────

class ForecastCache(Base):
    __tablename__ = "forecast_cache"
    id = Column(Integer, primary_key=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    model_time = Column(String(32), nullable=True)
    local_start_time = Column(String(32), nullable=True)
    utc_start_time = Column(String(32), nullable=True)
    utc_minute_offset = Column(Integer, nullable=True)
    # Store only evening hours (compact JSON)
    cloud_data = Column(JSON, nullable=True)  # [{hour: 20, value: 25.9}, ...]
    transparency_data = Column(JSON, nullable=True)
    seeing_data = Column(JSON, nullable=True)
    wind_data = Column(JSON, nullable=True)
    temperature_data = Column(JSON, nullable=True)
    dewpoint_data = Column(JSON, nullable=True)
    # Moon
    moon_illumination = Column(Float, nullable=True)
    moon_altitude = Column(Float, nullable=True)
    moon_phase = Column(Float, nullable=True)
    # Computed
    credits_used = Column(Integer, nullable=True)


# ─── Database Setup ──────────────────────────────────────────────────

def get_engine(db_path="data/astrodash.db"):
    return create_engine(f"sqlite:///{db_path}", echo=False)

def create_tables(engine):
    Base.metadata.create_all(engine)

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
