# AstroDash — Project Brief

*Last updated: March 16, 2026 · Session 18 (current)*

---

## Executive Summary

AstroDash is a self-hosted astrophotography planning dashboard built over 18 development sessions since February 2026. It combines Astrospheric weather forecasting, Skyfield ephemeris calculations, and a curated 220-target DSO catalog into a single Docker-deployed web application. The tool answers the nightly question: **what should I shoot tonight, and is it worth setting up?**

The project is actively deployed and in daily use from south Fort Collins, Colorado (Bortle 5-6).

---

## Architecture

### Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Python 3.12, FastAPI, Uvicorn | 39 API endpoints |
| Database | SQLite via SQLAlchemy | Single file, bind-mounted from Docker |
| Astronomy | Skyfield | Twilight, target positions, moon ephemeris |
| Weather | Astrospheric Pro API | Polled every 6h (matching CMC data update cadence) |
| Scheduler | APScheduler | Forecast poll (6h) + notification check (10min) |
| Frontend | Vanilla HTML/CSS/JS | No build step, no framework, ~1,800 lines |
| Deployment | Docker (single container) | ~200MB image, port 9090 |

### Codebase Size

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | 2,117 | API endpoints, scheduler, database init |
| `app.js` | 1,783 | All frontend logic (SPA-style tab navigation) |
| `expanded_catalog.py` | 947 | 157 additional DSO targets |
| `equipment_seed.py` | 609 | 128 pre-populated equipment items |
| `astrospheric.py` | 542 | Forecast fetching, parsing, scoring |
| `astronomy.py` | 459 | Twilight, visibility, moon calculations |
| `database.py` | 406 | SQLAlchemy models (12 tables) |
| `dso_catalog.py` | 396 | Base 63 DSO targets + solar system |
| `dashboard.html` | 334 | Main template with tab structure |
| `setup.html` | 510 | First-run setup wizard |
| `notifications.py` | 230 | Discord, ntfy, generic webhook delivery |
| `style.css` | 208 | Theming, layout, responsive design |
| **Total** | **~8,750** | |

### Data Model

**User Configuration:** UserSettings (location, timezone, Bortle zone, horizon limits, API key, notification preferences, dark library tracking)

**Equipment Catalog (5 tables):** Camera (22 items), Telescope (28), Mount (9), Filter (45), Accessory (24) — each with full manufacturer specs. UserEquipment links selections to catalog items.

**Observation Planning:** DSOTarget (220 entries), ImagingProject (linked to targets, per-channel LRGBSHO goal hours), SessionLog (per-channel integration, equipment used, conditions)

**Weather:** ForecastCache (hourly cloud/transparency/seeing/wind/temperature/dewpoint, rolling 48h retention)

---

## Feature Inventory

### Dashboard
- GO/MAYBE/NO-GO verdict with 0-100 score
- Separate broadband and narrowband verdicts
- Filter recommendation based on conditions + owned filters
- Imaging window from astronomical twilight (Skyfield-computed)
- Moon illumination + altitude range during imaging window (rise/set within window)
- Hour-by-hour forecast table (cloud, transparency, seeing, wind, temperature, dewpoint)
- Tonight's top-5 recommended targets (scored by altitude, visibility hours, moon separation, active project bonus)
- Tomorrow night preview

### Targets (220 DSO + 10 solar system)
- Complete Messier catalog (110 objects)
- 39 Caldwell objects
- 31 popular NGC/IC/Sh2/Abell astrophotography targets
- 8 planets + Moon + Sun
- Search across name, catalog ID, alt IDs, type, constellation
- Season, type, and difficulty filtering
- "Best For My Equipment" filter: FOV-aware (telescope FL + camera sensor → angular size filtering, 5% to 95% of FOV), NB/BB filter compatibility
- Sortable columns, Astrobin search links
- +Project button creates project and opens edit modal directly

### Projects
- Linked to catalog targets (enforced relationship)
- Per-channel goal hours: L, R, G, B, SII, Hα, OIII
- Auto-summing total with progress bars per channel
- Status tracking: Not Started → Active → Complete (auto-promoted on first session)
- Expandable channel detail view with per-channel progress and remaining hours
- Session logging directly from project cards

### Sessions
- Linked to projects (enforced relationship)
- Full equipment selection per session (camera, telescope, mount, filter)
- Per-channel integration time (auto-populated from filter bandpass)
- Moon illumination auto-populated from date
- Bortle zone, gain, sub count, sub length, rating, notes
- Stacked channel display (compact 11-column layout vs. 15)
- Project filter view (click project → see its sessions)

### Equipment (128 catalog items)
- 5 categories: Cameras, Telescopes, Mounts, Filters, Accessories
- Table-based checklist with category-specific spec columns displayed inline
- Cameras: Type, Sensor, Pixel size, Resolution, Sensor size, Cooled, Bit depth
- Telescopes: Type, Aperture, FL, f/ratio, Weight
- Mounts: Type, Payload, Weight, PE, GoTo
- Filters: Type, Bandpass (color-coded), Size, Moon resistant
- Accessories: Type, Back focus, Magnification, Weight
- Import/export in JSON and CSV with type coercion
- Manufacturer grouping with checked-item highlighting

### Notifications
- Methods: Discord webhook, ntfy, generic webhook (JSON POST)
- Scheduling: Hours before astronomical dusk, repeat interval, quiet hours
- GO alerts: Fires when forecast score meets threshold
- NO-GO alerts: Optional single heads-up when conditions are poor
- Custom message templates with 12 variables and clickable chip insertion
- 10-minute check cycle (lightweight time comparison, no API calls)
- Timezone-aware scheduling (UTC→local conversion for Docker containers)

### Settings & Configuration
- First-run setup wizard (6 steps)
- Location, timezone, Bortle zone, horizon limits
- Astrospheric API key (optional — twilight/moon data works without it)
- Target type preferences
- Imaging end hour
- Dark library date/temperature/gain tracking with reminder interval

### Data Management
- Full JSON backup/restore (settings, equipment, projects, sessions, custom items)
- Equipment catalog import/export (JSON and CSV per category)
- Backup portability: equipment re-linked by name/manufacturer on restore
- Auto-migration: new columns added to existing databases on startup

---

## Key Design Decisions

1. **Self-hosted Docker app** over Home Assistant integration — HA's Jinja2 templating proved too limiting for complex astronomy calculations and rich UI.

2. **Vanilla JS frontend** over React/Vue — no build step, instant deployment, full control. Entire UI is a single-page app with tab navigation in ~1,800 lines.

3. **SQLite over Postgres** — single-file database simplifies Docker deployment and backup. No concurrent write pressure in a single-user app.

4. **Astrospheric API over Open-Meteo/NWS** — only astronomy-specific weather service with seeing, transparency, and smoke data. 6-hour polling matches their CMC data update cadence (~24 API credits/day of 100 available).

5. **Skyfield over astropy** — lighter weight, better suited for the specific calculations needed (twilight, target altitude, moon position). No NumPy dependency issues.

6. **Forecast scoring** uses separate broadband/narrowband verdicts — recognizes that narrowband imaging tolerates poor transparency and moonlight, enabling useful "image emission nebulae tonight" recommendations on otherwise marginal nights.

7. **Per-channel LRGBSHO tracking** with SHO Hubble Palette colors (SII=red, Hα=green, OIII=blue) throughout the interface.

8. **FOV equipment filter** uses hybrid approach: minimum target size = 5% of short FOV axis, maximum = 95% of long FOV axis. Requires both camera and telescope in equipment; falls back to NB/BB filtering only otherwise.

9. **Notification timing** computed in user's local timezone (converted from UTC in Docker) to avoid the timezone mismatch bug discovered in session 18.

10. **Channel mode / exposure time calculation** was explored (OSC simultaneous channels vs. mono separate) but intentionally reverted — the combinatorics of dual-band filter pairings made a clean general solution too complex. Left as simple channel sum for now.

---

## Known Issues & Technical Debt

1. **Target page performance** — Rendering 220 targets was fixed (innerHTML += → join), and API optimized (batch filter query, cached recommended_filters by NB/BB combo), but could benefit from pagination or virtual scrolling if catalog grows further.

2. **Season assignment** — RA-based season cutoffs are approximate. Objects at RA ~21.5h (M2, M15) are classified "Summer" but are really autumn targets. Works for rough filtering but isn't precise.

3. **Notification scheduling edge cases** — The scheduler doesn't handle the case where dusk_time is before noon (high-latitude summer), and the quiet hours check uses simple hour comparison which doesn't account for DST transitions mid-day.

4. **No pagination** — All 220 targets, all projects, all sessions load in full. Fine at current scale but won't scale to thousands.

5. **Single-user design** — No authentication, no multi-user support. Appropriate for self-hosted personal use but limits sharing.

6. **`dso_catalog_expansion.py`** — A 200-line file exists alongside `expanded_catalog.py` that may be orphaned/redundant from an earlier catalog expansion attempt. Should be audited.

---

## Feature Candidates (Prioritized)

Inspired by competitive analysis of Messier Planner and prior session discussions:

### High Priority
- **Multi-night planning timeline** — 7-14 day forward view per target showing visibility windows, moon conditions, and weather scores. Currently only "tonight" is shown.
- **Per-target visibility timeline** — Visual horizontal bar showing rise/peak/set overlaid with twilight and moon rise/set. More intuitive than text-based altitude.
- **Target detail pages** — Click a target to see a dedicated panel with description, sky position, altitude curve, best months, and active project status.
- **Catalog completion tracking** — "47/110 Messier objects imaged" progress view across catalogs.

### Medium Priority
- **Best months indicator** — Per-target month-by-month visibility rating, not just "Spring"/"Winter."
- **Interactive sky atlas** — Simple polar projection or hemisphere map of tonight's targets.
- **Target imagery** — Thumbnail reference images per catalog entry (even a link to a standard DSS image).
- **Tags and custom lists** — User-defined labels on targets ("Hubble Palette", "Quick win", "Mosaic candidate").
- **Session weather snapshot** — Auto-attach forecast data to session records at logging time.

### Lower Priority
- **PWA support** — Manifest + service worker for mobile home screen installation.
- **Richer object descriptions** — Expand one-liner descriptions to educational paragraphs for popular targets.
- **Glossary** — Built-in reference for astrophotography terms (Bortle, plate scale, back focus, etc.).

---

## Development History

| Session | Date | Key Deliverables |
|---------|------|-----------------|
| 1-2 | Feb 10-14 | Equipment compatibility research, imaging train planning |
| 3 | Feb 16 | Target planning, HA Astrospheric integration design |
| 4 | Feb 19 | HA integration debugging (abandoned approach) |
| 5 | Feb 19 | Architecture design, decision to build standalone app |
| 6-7 | Feb 19-20 | Initial build: full app (3,600+ lines), Docker deployment |
| 8-9 | Feb 20-21 | Bug fixes, equipment catalog expansion, Skyfield fixes |
| 10-11 | Feb 21-22 | Twilight fixes, NumPy issues, tomorrow forecast, Astrobin |
| 12 | Feb 22 | Filters, sorting, sessions, recommended filters per target |
| 13 | Feb 22 | Per-channel integration, search, project-session linking |
| 14 | Feb 22-23 | Location/timezone fix, SHO palette, project UI refinements |
| 15 | Feb 28 | Mono imaging prep, camera-aware channels, equipment in sessions |
| 16 | Feb 28 | Discord notifications, template system, custom message editor |
| 17 | Mar 1 | Notification scheduling, backup/restore, projects refactor |
| 18 | Mar 4-16 | Catalog expansion (220 targets), equipment tables, FOV filter, notification timezone fix, moon window range, +Project flow, import/export updates, Messier Planner competitive analysis |

---

## User Equipment Profile

| Category | Item |
|----------|------|
| Telescope | William Optics Zenithstar 81 APO (382mm FL) + Flat6AIII + manual rotator |
| Camera | ZWO ASI2600MC Duo (IMX571, OSC, 3.76µm, 6248×4176) |
| Mount | Sky-Watcher EQ6-R Pro |
| Controller | ASIAIR Pro 32GB |
| Filter drawer | ZWO 54mm (single filter) |
| Current filters | Optolong L-Pro, Optolong L-Quad Enhance |
| Planned filters | Optolong L2 Dual-Combo (L-eXtreme + L-Synergy) |
| Processing | PixInsight + RC Astro plugins (BlurX, StarX, NoiseX) |
| Location | South Fort Collins, CO (Bortle 5-6) |
