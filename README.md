# ENGG4430: Toronto TMC Preprocessing Pipeline

## Table of Contents
1. [Overview](#overview)
2. [What This Project Does](#what-this-project-does)
3. [Project Structure](#project-structure)
4. [Input Files](#input-files)
5. [Output Files](#output-files)
6. [How It Works](#how-it-works)
7. [Leg Type Classification](#leg-type-classification)
8. [Installation](#installation)
9. [How to Run](#how-to-run)
10. [Pseudocode](#pseudocode)
11. [Data and Modeling Notes](#data-and-modeling-notes)
12. [Troubleshooting](#troubleshooting)

## Overview
This repository preprocesses City of Toronto Turning Movement Count (TMC) data for **all intersections** in the provided files.

The goal is to convert raw 15-minute counts into clean, simulation-ready datasets for traffic signal studies (fixed-time vs adaptive/neuro-fuzzy), including:
- per-interval demand features,
- per-count-day aggregated features,
- merged metadata aligned with summary tables.

## What This Project Does
The script `src/preprocess_tmc.py` reads three CSV files and generates three processed CSV files.

It computes:
- total vehicle demand per 15-minute interval,
- directional demand by approach (`N/E/S/W`),
- turn demand (`left/through/right`),
- pedestrian and bike totals,
- daily totals and peak-hour indicators,
- intersection geometry labels (`4_leg`, `3_leg`, `2_leg_NS`, `2_leg_EW`, `2_leg_other`, `other`).

In the script, aggregation loops are driven by these variables:
- `approaches = ("n", "e", "s", "w")`
- `movements = ("r", "t", "l")`
- `vehicleTypes = ("cars", "truck", "bus")`

## Project Structure
```text
ENGG4430/
├─ data/
│  └─ raw/
│     ├─ tmc_raw_data_2020_2029.csv
│     ├─ tmc_summary_data.csv
│     └─ tmc_most_recent_summary_data.csv
├─ outputs/
│  └─ preprocessed/
│     ├─ tmc_interval_features_all.csv
│     ├─ tmc_daily_features_all.csv
│     └─ tmc_intersection_metadata_all.csv
├─ src/
│  └─ preprocess_tmc.py
└─ README.md
```

## Input Files
All inputs are expected as CSV with headers.

### `data/raw/tmc_raw_data_2020_2029.csv`
Core time-series source (15-minute bins). Used to compute all interval and daily derived features.

Important fields used:
- IDs/time/location: `count_id`, `count_date`, `location_name`, `latitude`, `longitude`, `start_time`, `end_time`
- Vehicle movement counts by approach/type/movement:
  - `{n|e|s|w}_appr_{cars|truck|bus}_{r|t|l}`
- Pedestrian counts by approach: `{n|e|s|w}_appr_peds`
- Bike counts by approach: `{n|e|s|w}_appr_bike`

### `data/raw/tmc_summary_data.csv`
Reference summary for all counts. Used in metadata merge for comparison/context.

Examples:
- `total_vehicle`, `total_pedestrian`, `total_bike`
- `am_peak_start`, `am_peak_vehicle`, `pm_peak_start`, `pm_peak_vehicle`
- `count_duration`

### `data/raw/tmc_most_recent_summary_data.csv`
Latest-count table by location. Used to flag whether a processed `count_id` is most recent.

Key field:
- `latest_count_id`

## Output Files
Outputs are written to `outputs/preprocessed/`.

### `tmc_interval_features_all.csv`
One row per 15-minute interval.

Columns:
- `count_id`, `count_date`, `location_name`, `latitude`, `longitude`
- `start_time`, `end_time`
- `total_vehicle_15min`
- `north_vehicle_15min`, `east_vehicle_15min`, `south_vehicle_15min`, `west_vehicle_15min`
- `left_turn_vehicle_15min`, `through_vehicle_15min`, `right_turn_vehicle_15min`
- `total_pedestrian_15min`, `total_bike_15min`

### `tmc_daily_features_all.csv`
One row per `count_id` (count-day aggregate).

Columns:
- identity/location: `count_id`, `count_date`, `location_name`, `latitude`, `longitude`
- geometry: `leg_type`, `active_approaches`, `missing_approaches`, `north_present`, `east_present`, `south_present`, `west_present`
- daily totals: `total_vehicle_day`, `total_pedestrian_day`, `total_bike_day`
- timing/intensity: `intervals_in_count`, `avg_vehicle_per_15min`, `peak_hour_start`, `peak_hour_vehicle`
- direction/turn totals: `north_vehicle_day`, `east_vehicle_day`, `south_vehicle_day`, `west_vehicle_day`, `left_turn_vehicle_day`, `through_vehicle_day`, `right_turn_vehicle_day`

### `tmc_intersection_metadata_all.csv`
Merged dataset combining raw-derived daily outputs with summary tables.

Columns include:
- identity/location and geometry fields,
- raw-derived daily totals (`*_raw_derived`),
- summary-table totals/peaks,
- `is_most_recent_for_location` (`1` or `0`).

## How It Works
`src/preprocess_tmc.py` runs in two major stages.

### Stage 1: Raw to interval + daily features
1. Read each row from `tmc_raw_data_2020_2029.csv`.
2. For each 15-minute row:
   - Sum `cars + truck + bus` across `r/t/l` for each approach (`N/E/S/W`).
   - Sum turn totals across all approaches (`left`, `through`, `right`).
   - Sum pedestrians and bikes across approaches.
3. Write interval-level row to `tmc_interval_features_all.csv`.
4. Group rows by `count_id`, then aggregate daily totals.
5. Compute peak hour by summing interval vehicle totals into hourly buckets.
6. Infer `leg_type` and approach-presence flags from daily approach totals.
7. Write one daily row per `count_id` to `tmc_daily_features_all.csv`.

### Stage 2: Build metadata table
1. Load `tmc_summary_data.csv` keyed by `count_id`.
2. Load `tmc_most_recent_summary_data.csv` keyed by `latest_count_id`.
3. Load daily derived table keyed by `count_id`.
4. Join these sources and write `tmc_intersection_metadata_all.csv`.

## Leg Type Classification
Leg type is based on whether each approach has positive daily vehicle total.

Rules:
- 4 active approaches -> `4_leg`
- 3 active approaches -> `3_leg`
- only `N` and `S` active -> `2_leg_NS`
- only `E` and `W` active -> `2_leg_EW`
- any other 2 active approaches -> `2_leg_other`
- otherwise -> `other`

Related fields:
- `active_approaches` (e.g., `N,E,S`)
- `missing_approaches` (e.g., `W`)
- `{north|east|south|west}_present` as binary flags (`1`/`0`)

## Installation
The script uses Python standard library modules only (`argparse`, `csv`, `datetime`, `pathlib`, etc.).

### Prerequisite
- Python 3.9+ recommended

### Windows (PowerShell)
```powershell
# Check Python
python --version
# If needed, try launcher
py --version
```

### macOS (Terminal)
```bash
python3 --version
```

### Linux (Terminal)
```bash
python3 --version
```

If Python is missing, install it using your OS package manager or the official installer:
- Windows/macOS: https://www.python.org/downloads/
- Linux: distro package manager (`apt`, `dnf`, `pacman`, etc.)

## How to Run
Run from repository root.

### Default run
```bash
python src/preprocess_tmc.py
```

Windows alternative:
```powershell
py src/preprocess_tmc.py
```

### Custom paths
```bash
python src/preprocess_tmc.py \
  --raw data/raw/tmc_raw_data_2020_2029.csv \
  --summary data/raw/tmc_summary_data.csv \
  --most-recent data/raw/tmc_most_recent_summary_data.csv \
  --out-dir outputs/preprocessed
```

### Expected console output
```text
Wrote: outputs\preprocessed\tmc_interval_features_all.csv
Wrote: outputs\preprocessed\tmc_daily_features_all.csv
Wrote: outputs\preprocessed\tmc_intersection_metadata_all.csv
```

## Pseudocode
```text
FUNCTION preprocess(raw_csv, summary_csv, most_recent_csv, out_dir):
    CREATE out_dir if missing

    interval_rows_by_count_id = map(count_id -> list)

    FOR each row in raw_csv:
        north = sum(n_appr_{cars,truck,bus}_{r,t,l})
        east  = sum(e_appr_{cars,truck,bus}_{r,t,l})
        south = sum(s_appr_{cars,truck,bus}_{r,t,l})
        west  = sum(w_appr_{cars,truck,bus}_{r,t,l})

        total_vehicle = north + east + south + west
        left_turn     = sum(all approaches, all types, movement=l)
        through_turn  = sum(all approaches, all types, movement=t)
        right_turn    = sum(all approaches, all types, movement=r)

        total_ped = sum({n,e,s,w}_appr_peds)
        total_bike = sum({n,e,s,w}_appr_bike)

        WRITE interval row
        APPEND interval row into interval_rows_by_count_id[count_id]

    FOR each count_id group:
        aggregate daily totals from interval rows
        compute peak hour from hourly bucketed total_vehicle_15min
        classify leg_type from daily approach totals
        set approach-present flags
        WRITE daily row

    LOAD summary table keyed by count_id
    LOAD most-recent table keyed by latest_count_id
    LOAD daily table keyed by count_id

    FOR each count_id in daily table:
        merge daily + summary + most-recent flag
        WRITE metadata row
END
```

## Data and Modeling Notes
- `0` counts are valid and often represent either:
  - truly low/no demand in that interval, or
  - structurally missing approaches (e.g., 3-leg intersections).
- Numeric parsing uses `to_int(value)` in `src/preprocess_tmc.py`, which returns `int(float(value))` and falls back to `0` for empty/invalid values.
- For simulation continuity, prefer scenario-based modeling (e.g., raw vs floor) instead of silently rewriting raw demand during preprocessing.

## Troubleshooting
### `python: command not found`
- Use `py` on Windows.
- Use `python3` on macOS/Linux.

### Output files not updating
- Confirm you are running from repository root.
- Confirm no file is locked by another process.
- Re-run and check printed `Wrote:` paths.

### Unexpected empty/zero-heavy outputs
- Verify raw file paths and headers are unchanged.
- Inspect a few rows in `data/raw/tmc_raw_data_2020_2029.csv` for expected movement columns.
