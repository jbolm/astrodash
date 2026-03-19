# 🔭 AstroDash — Astrophotography Imaging Dashboard

Self-hosted dashboard for astrophotography session planning. Uses Astrospheric weather forecasting, Skyfield astronomy calculations, and a curated DSO catalog to tell you **what to shoot tonight**.

## Features

- **Dynamic imaging forecast** — Astrospheric weather data scored 0-100 with GO/MAYBE/NO-GO verdict
- **Separate broadband/narrowband verdicts** — knows to recommend emission nebulae on moonlit nights
- **Dynamic imaging window** — computed from real astronomical twilight (Skyfield), handles DST and seasons automatically
- **Curated DSO catalog** — 220+ targets including complete Messier catalog, Caldwell objects, and popular astrophotography targets with RA/Dec, visibility calculations, and tonight's recommended targets
- **Target-specific recommendations** — scored by altitude, visibility hours, moon separation, and active project status
- **FOV-aware equipment filter** — "Best For My Equipment" uses your telescope focal length and camera sensor dimensions to filter targets by angular size
- **Integration time tracking** — track progress toward imaging goals across multiple sessions with per-channel (LRGB/SHO) goal hours
- **Session log** — record conditions, subs captured, quality rating, equipment used, and notes
- **Equipment database** — pre-populated with current ZWO, QHY, Optolong, SkyWatcher, William Optics, SVBony products with detailed specs shown in-line
- **Import/Export** — equipment catalog in JSON or CSV format with proper type coercion
- **Backup/Restore** — full JSON backup of settings, equipment, projects, and sessions
- **Notifications** — Discord, ntfy, and generic webhook support for GO alerts with scheduled delivery, repeat intervals, NO-GO alerts, and quiet hours
- **Dark library reminders** — tracks when your darks were last shot
- **Light/dark theme** — easy on the eyes at night
- **Mobile responsive** — check conditions on your phone in the yard

## Quick Start

```bash
# Clone the repository
git clone https://github.com/jbolm/astrodash.git
cd astrodash

# Build and run
docker compose up -d

# Open browser
open http://localhost:9090
```

The first-run setup wizard will walk you through:
1. Location (lat/lon, Bortle zone)
2. Astrospheric API key (optional — requires Pro subscription for forecast data)
3. Horizon limits (blocked directions)
4. Target preferences
5. Equipment selection from catalog
6. Notification setup (optional)

## Updating

```bash
cd astrodash
git pull
docker compose up -d --build
```

## Architecture

- **Backend:** Python 3.12 + FastAPI + Uvicorn
- **Database:** SQLite (persisted in Docker volume)
- **Astronomy:** Skyfield (twilight, target positions, moon data)
- **Weather:** Astrospheric Pro API (polled every 6 hours, matching CMC data update cadence)
- **Scheduler:** APScheduler (forecast polling every 6h + notification check every 10min)
- **Frontend:** Vanilla HTML/CSS/JS (no build step, no framework)
- **Container:** Single Dockerfile, ~200MB image

## Equipment Database

Each equipment category includes detailed specifications displayed in the selection checklist:

**Cameras** — Color/Mono type, sensor model, pixel size, resolution, sensor dimensions, cooling, bit depth

**Telescopes** — Telescope type, aperture, focal length, focal ratio, weight

**Mounts** — Mount type, max payload, weight, periodic error, GoTo capability

**Filters** — Filter type, bandpass (with color-coded wavelength badges), size, moonlight resistance

**Accessories** — Accessory type, back focus contribution, magnification factor, weight

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/version` | GET | App version |
| `/api/settings` | GET/PUT | User settings |
| `/api/forecast` | GET | Tonight's forecast with scores |
| `/api/forecast/refresh` | POST | Force immediate refresh |
| `/api/forecast/tomorrow` | GET | Tomorrow's forecast |
| `/api/targets` | GET | DSO catalog (filterable by season, type) |
| `/api/targets/{id}/visibility` | GET | Target visibility tonight |
| `/api/tonight/targets` | GET | Ranked targets for tonight |
| `/api/projects` | GET/POST | Imaging projects |
| `/api/projects/{id}` | PUT/DELETE | Update or delete project |
| `/api/sessions` | GET/POST | Session log |
| `/api/sessions/{id}` | PUT/DELETE | Update or delete session |
| `/api/my-equipment` | GET/POST/DELETE | User's selected equipment |
| `/api/my-equipment-options` | GET | Equipment with details for dropdowns |
| `/api/equipment/{category}` | GET/POST/DELETE | Equipment catalog (cameras, telescopes, mounts, filters, accessories) |
| `/api/equipment/{category}/export/{format}` | GET | Export as JSON or CSV |
| `/api/equipment/{category}/import/{format}` | POST | Import from JSON or CSV |
| `/api/notifications/test` | POST | Send a test notification |
| `/api/backup` | GET | Download full JSON backup |
| `/api/restore` | POST | Restore from JSON backup |
| `/api/dark-library-status` | GET | Dark frame reminder status |

## Equipment Import/Export

Export your equipment catalog:
```bash
# JSON (all fields, recommended for round-tripping)
curl http://localhost:9090/api/equipment/cameras/export/json > cameras.json

# CSV (all fields, human-readable)
curl http://localhost:9090/api/equipment/filters/export/csv > filters.csv
```

Import equipment (unknown fields are silently ignored, types are auto-coerced):
```bash
curl -X POST -F "file=@cameras.json" http://localhost:9090/api/equipment/cameras/import/json
curl -X POST -F "file=@filters.csv" http://localhost:9090/api/equipment/filters/import/csv
```

### Required Fields by Category

**Cameras:** `name`, `manufacturer` — plus optional: `sensor_model`, `color_type` (Color (OSC) / Mono), `pixel_size_um`, `resolution_x`, `resolution_y`, `sensor_width_mm`, `sensor_height_mm`, `sensor_diagonal_mm`, `read_noise_e`, `full_well_ke`, `cooling` (bool), `cooling_delta_c`, `back_focus_mm`, `guide_sensor` (bool), `adc_bit`, `usb_type`, `weight_g`, `hcg_gain`, `price_usd`

**Telescopes:** `name`, `manufacturer`, `telescope_type` — plus optional: `aperture_mm`, `focal_length_mm`, `focal_ratio`, `native_back_focus_mm`, `weight_kg`, `field_type`, `image_circle_mm`, `price_usd`

**Mounts:** `name`, `manufacturer`, `mount_type` — plus optional: `max_payload_kg`, `weight_kg`, `periodic_error_arcsec`, `goto` (bool), `tracking_modes`, `power_input`, `price_usd`

**Filters:** `name`, `manufacturer`, `filter_type` — plus optional: `bandpass`, `filter_size`, `thickness_mm`, `transmission_pct`, `broadband_friendly` (bool), `narrowband_friendly` (bool), `moonlight_resistant` (bool), `price_usd`

**Accessories:** `name`, `manufacturer`, `accessory_type` — plus optional: `back_focus_mm`, `magnification`, `input_thread`, `output_thread`, `weight_g`, `price_usd`

## Backup & Restore

Download a full backup (settings, equipment selections, custom equipment, projects, sessions):
```bash
curl http://localhost:9090/api/backup > astrodash-backup.json
```

Restore from backup (replaces all current data):
```bash
curl -X POST -F "file=@astrodash-backup.json" http://localhost:9090/api/restore
```

Backups include resolved equipment names for portability — if you restore on a fresh install, equipment selections are re-linked by name/manufacturer match.

## Notifications

AstroDash can send imaging alerts via Discord webhooks, ntfy, or generic webhooks. Configure in Settings:

- **Hours before dark** — when to send the first alert relative to astronomical dusk
- **Repeat interval** — how often to re-send (24h = once per night)
- **GO threshold** — minimum forecast score to trigger a GO alert
- **NO-GO alerts** — optional single heads-up when conditions are poor
- **Quiet hours** — suppress alerts before a given time (e.g., no alerts before 2 PM)
- **Custom templates** — format your alert message with 12 available variables

The notification scheduler checks every 10 minutes (lightweight time comparison, no API calls).

## Data Persistence

All data is stored in `data/astrodash.db` (SQLite). The `compose.yaml` maps this to a bind mount at `./data/`. To back up the raw database:

```bash
docker cp astrodash:/app/data/astrodash.db ./backup.db
```

Or use the built-in JSON backup (recommended — portable across versions).

## API Credit Usage

Astrospheric Pro gives 100 credits/day:
- Forecast poll: 5 credits (every 6 hours = ~20/day)
- Sky data poll: 1 credit (every 6 hours = ~4/day)
- **Total: ~24 credits/day**

## License

Open source. MIT License.
