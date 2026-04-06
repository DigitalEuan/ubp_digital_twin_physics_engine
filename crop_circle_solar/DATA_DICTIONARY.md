# Crop Circle Solar Database — Data Dictionary

**File:** `crop_circle_solar_database.csv`  
**Records:** 1,073 crop circle formations  
**Columns:** 98  
**Date range:** 1982-07-01 to 2024-10-14  
**Sources:** Crop Circle Connector (2014–2024), Crop Circle Archives (1978–2013), curated seed data

---

## Section 1: Formation Identity

| Column | Type | Description |
|--------|------|-------------|
| `year` | int | Year of formation |
| `date_parsed` | date (YYYY-MM-DD) | Best-estimate date of formation |
| `date_raw` | string | Original date string from source |
| `date_confidence` | string | `exact` / `approximate` / `year_only` |
| `location` | string | Full location name as scraped |
| `county` | string | UK county or region |
| `country` | string | Country of formation |
| `lat` | float | Latitude (WGS84, decimal degrees) |
| `lon` | float | Longitude (WGS84, decimal degrees) |
| `os_grid_ref` | string | UK OS National Grid reference (if available) |
| `gps_source` | string | `scraped` / `os_grid` / `nominatim` — how GPS was obtained |

---

## Section 2: Formation Characteristics

| Column | Type | Description |
|--------|------|-------------|
| `crop_type` | string | Crop in which formation appeared (wheat, barley, etc.) |
| `approx_diameter_m` | float | Approximate diameter in metres (from description) |
| `approx_area_m2` | float | Approximate area in m² (from description) |
| `formation_type` | string | `geometric` / `pictogram` / `spiral` / `simple_circle` / `fractal` / `ring` / `mandala` / `unknown` |
| `description` | string | Free-text description from source page |
| `image_url` | string | URL of primary aerial image |
| `source_url` | string | URL of source page |
| `title_raw` | string | Raw title from source page |
| `blt_sampled` | bool | Whether BLT Research soil/plant sampling was conducted |
| `hoax_flag` | bool | Whether formation was confirmed or suspected hoax |
| `notes` | string | Additional notes |
| `data_source` | string | `ccc_scraped` / `ccc_archive` / `seed_curated` |

---

## Section 3: Temporal Features

| Column | Type | Description |
|--------|------|-------------|
| `doy` | int | Day of year (1–366) |
| `month` | int | Month (1–12) |
| `week_of_year` | int | ISO week number |
| `season` | string | `spring` / `summer` / `autumn` / `winter` |

---

## Section 4: Sun Position (computed for formation lat/lon on formation date)

| Column | Type | Units | Description |
|--------|------|-------|-------------|
| `solar_declination` | float | degrees | Solar declination angle |
| `equation_of_time_min` | float | minutes | Equation of time correction |
| `day_length_hours` | float | hours | Length of daylight |
| `sunrise_utc` | float | hours UTC | Time of sunrise |
| `sunset_utc` | float | hours UTC | Time of sunset |
| `solar_noon_utc` | float | hours UTC | Time of solar noon |
| `solar_elevation_noon` | float | degrees | Solar elevation angle at noon |
| `solar_azimuth_noon` | float | degrees from N | Solar azimuth at noon |

---

## Section 5: Solar Activity on Formation Date

All columns prefixed `solar_` are joined from the daily solar database on `date_parsed`.

### Interplanetary Magnetic Field (NASA OMNI2)

| Column | Type | Units | Description |
|--------|------|-------|-------------|
| `solar_IMF_B_mag` | float | nT | IMF field magnitude \|B\| |
| `solar_IMF_Bz_GSM_mean` | float | nT | IMF Bz (GSM) daily mean — negative = southward (geoeffective) |
| `solar_IMF_Bz_GSM_min` | float | nT | IMF Bz (GSM) daily minimum |

### Solar Wind (NASA OMNI2)

| Column | Type | Units | Description |
|--------|------|-------|-------------|
| `solar_SW_speed_mean` | float | km/s | Solar wind speed daily mean |
| `solar_SW_speed_max` | float | km/s | Solar wind speed daily maximum |
| `solar_Proton_density` | float | N/cm³ | Proton density |
| `solar_Flow_pressure` | float | nPa | Solar wind dynamic pressure |
| `solar_Electric_field` | float | mV/m | Interplanetary electric field |

### Geomagnetic Activity

| Column | Type | Units | Description |
|--------|------|-------|-------------|
| `solar_Kp_sum` | float | — | Daily Kp sum (OMNI, 8 × 3-hourly values) |
| `solar_Kp_max` | float | 0–9 | Daily Kp maximum (OMNI) |
| `solar_Kp_mean` | float | 0–9 | Daily Kp mean (OMNI) |
| `solar_Kp_sum_gfz` | float | — | Daily Kp sum (GFZ Potsdam definitive) |
| `solar_Kp_max_gfz` | float | 0–9 | Daily Kp maximum (GFZ Potsdam) |
| `solar_Kp_mean_gfz` | float | 0–9 | Daily Kp mean (GFZ Potsdam) |
| `solar_Kp_sum_best` | float | — | Best-available Kp sum (GFZ preferred over OMNI) |
| `solar_Kp_max_best` | float | 0–9 | **Best-available Kp maximum** — primary geomagnetic variable |
| `solar_Kp_mean_best` | float | 0–9 | Best-available Kp mean |
| `solar_Ap_index` | float | nT×2 | Ap index (OMNI) |
| `solar_Ap_daily_gfz` | float | nT×2 | Daily Ap (GFZ Potsdam) |
| `solar_Dst_min` | float | nT | Dst index minimum (storm indicator; negative = storm) |
| `solar_Dst_mean` | float | nT | Dst index daily mean |
| `solar_G_storm_level` | int | 0–5 | NOAA G-storm level (0=quiet, 1=G1 minor … 5=G5 extreme) |
| `solar_kp_definitive` | int | 0/1/2 | GFZ definitiveness flag (2=fully definitive) |

### Solar Radiation & Sunspot Activity

| Column | Type | Units | Description |
|--------|------|-------|-------------|
| `solar_F10_7_adj` | float | sfu | F10.7 solar flux adjusted to 1 AU (OMNI) |
| `solar_F10_7_gfz` | float | sfu | F10.7 solar flux (GFZ Potsdam) |
| `solar_F10_7_best` | float | sfu | **Best-available F10.7** — primary solar activity proxy |
| `solar_Sunspot_num_omni` | float | — | Daily sunspot number (OMNI) |
| `solar_SSN_gfz` | float | — | Daily sunspot number (GFZ) |
| `solar_SIDC_SSN` | float | — | SIDC/SILSO International Sunspot Number v2 |
| `solar_SIDC_SSN_std` | float | — | SIDC SSN standard deviation |
| `solar_SSN_best` | float | — | **Best-available SSN** (SIDC preferred) |

### Solar Cycle

| Column | Type | Description |
|--------|------|-------------|
| `solar_solar_cycle_phase` | float | Solar cycle phase 0–1 (0=minimum, ~0.5=maximum) |
| `solar_solar_cycle_num` | int | Solar cycle number (e.g., 22, 23, 24, 25) |

### Storm Window Flags

| Column | Type | Description |
|--------|------|-------------|
| `solar_in_G1_window_3d` | bool | Formation date within ±3 days of a G1+ storm |
| `solar_in_G2_window_3d` | bool | Formation date within ±3 days of a G2+ storm |
| `solar_in_G3_window_3d` | bool | Formation date within ±3 days of a G3+ storm |

---

## Section 6: ±7-Day Solar Windows

Pre-formation (7 days before) and post-formation (7 days after) solar statistics.  
These allow testing whether solar activity *precedes* or *follows* formation events.

### Pre-formation (7 days before)

| Column | Description |
|--------|-------------|
| `pre7d_Kp_max_best_mean` | Mean of daily Kp_max in 7 days before formation |
| `pre7d_Kp_max_best_max` | Maximum Kp_max in 7 days before formation |
| `pre7d_Kp_sum_best_mean` | Mean of daily Kp_sum in 7 days before |
| `pre7d_Kp_sum_best_max` | Maximum Kp_sum in 7 days before |
| `pre7d_SW_speed_max_mean` | Mean of daily SW speed max in 7 days before |
| `pre7d_SW_speed_max_max` | Maximum SW speed in 7 days before |
| `pre7d_Dst_min_mean` | Mean of daily Dst_min in 7 days before |
| `pre7d_Dst_min_max` | Most extreme Dst_min in 7 days before |
| `pre7d_SSN_best_mean` | Mean SSN in 7 days before |
| `pre7d_SSN_best_max` | Maximum SSN in 7 days before |
| `pre7d_F10_7_best_mean` | Mean F10.7 in 7 days before |
| `pre7d_F10_7_best_max` | Maximum F10.7 in 7 days before |

### Post-formation (7 days after)

Same columns prefixed `post7d_` — for testing whether formations *precede* solar events.

### Storm Counts in Window

| Column | Description |
|--------|-------------|
| `storms_G1plus_in_window` | Number of G1+ storm days in ±7-day window |
| `storms_G2plus_in_window` | Number of G2+ storm days in ±7-day window |
| `storms_G3plus_in_window` | Number of G3+ storm days in ±7-day window |

---

## Data Sources

| Source | Records | Coverage |
|--------|---------|----------|
| Crop Circle Connector (scraped) | 451 | 2014–2024 |
| Crop Circle Archives (scraped) | 624 | 1978–2013 |
| Curated seed data | 1 | Selected events |
| **Total** | **1,073** | **1982–2024** |

| Solar Source | Parameter | Coverage |
|-------------|-----------|----------|
| NASA OMNI2 hourly | Solar wind, IMF, Kp, Dst, F10.7 | 1963–2024 |
| GFZ Potsdam | Definitive Kp, ap, SSN, F10.7 | 1932–2024 |
| SIDC/SILSO | International Sunspot Number v2 | 1818–2024 |

---

## Key Variables for Hypothesis Testing

To test whether solar activity influences crop circle formation, the most important columns are:

1. **`solar_Kp_max_best`** — Peak geomagnetic activity (0–9 scale)
2. **`solar_F10_7_best`** — Solar UV/EUV proxy (65–270 sfu in dataset)
3. **`solar_SW_speed_mean`** — Solar wind speed (273–765 km/s in dataset)
4. **`solar_Dst_min`** — Geomagnetic storm intensity (nT)
5. **`solar_SSN_best`** — Daily sunspot count
6. **`solar_solar_cycle_phase`** — Position in 11-year solar cycle
7. **`solar_G_storm_level`** — NOAA storm classification (0–5)
8. **`pre7d_Kp_max_best_max`** — Peak geomagnetic activity in 7 days prior
9. **`solar_elevation_noon`** — Solar elevation at formation location/date
10. **`day_length_hours`** — Photoperiod at formation location/date

---

*Generated by the Crop Circle Solar Database pipeline. All solar values are in physical units as specified above.*
