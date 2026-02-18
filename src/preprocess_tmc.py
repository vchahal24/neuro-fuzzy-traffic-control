#!/usr/bin/env python3
# allows you to run the file as "./preprocess_tmc.py"

"""
ENGG4430 - Traffic Light Controller (Baseline)
Preprocessing the Toronto TMC datasets for every intersection.

Inputs (.csv):
- data/raw/tmc_raw_data_2020_2029.csv
- data/raw/tmc_summary_data.csv
- data/raw/tmc_most_recent_summary_data.csv

Outputs (under outputs/preprocessed):
- tmc_interval_features_all.csv
- tmc_daily_features_all.csv
- tmc_intersection_metadata_all.csv

Assumptions:
- Input CSV headers follow City of Toronto TMC naming.
- Counts are non-negative; invalid text is treated as 0 by to_int().
- 15-minute rows are aggregated by count_id for daily features.
"""

# enables forward refs in type hints
from __future__ import annotations;

# this is used for command line flags (e.g. --raw)
import argparse;

# built in csv reader
# this is going to be used to read in the input data files and write out the processed data files to csv
import csv;

# this is just a dictionary used for auto creating default values
from collections import defaultdict;

# works with timestamps when parsing csvs
from datetime import datetime;

#  helps create nicer file paths than concatenating strings
from pathlib import Path;

# this is used for type hints to make it clear what types of data are being passed around
from typing import Dict, List, Tuple;

# we have 3 dimensions in our data set:
# approaches is used for north, east, south, west
# movements for right, through, left
# vehicle types for cars, trucks, buses
approaches = ("n", "e", "s", "w");
movements = ("r", "t", "l");
vehicleTypes = ("cars", "truck", "bus");


def validate_required_columns(fieldnames: List[str] | None) -> None:
    if fieldnames is None:
        raise ValueError("Raw CSV has no header row.")

    required = {
        "count_id",
        "count_date",
        "location_name",
        "latitude",
        "longitude",
        "start_time",
        "end_time",
    }

    for approach in approaches:
        required.add(f"{approach}_appr_peds")
        required.add(f"{approach}_appr_bike")
        for vehicle_type in vehicleTypes:
            for movement in movements:
                required.add(f"{approach}_appr_{vehicle_type}_{movement}")

    missing = sorted(required.difference(set(fieldnames)))
    if missing:
        raise ValueError(
            "Raw CSV is missing required columns: "
            + ", ".join(missing[:12])
            + (" ..." if len(missing) > 12 else "")
        )


def row_has_negative_vehicle_value(row: Dict[str, str]) -> bool:
    for approach in approaches:
        for vehicle_type in vehicleTypes:
            for movement in movements:
                col = f"{approach}_appr_{vehicle_type}_{movement}"
                raw = str(row.get(col, "")).strip()
                if raw.startswith("-"):
                    return True
    return False


def to_int(value: str) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if text == "":
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_dt(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def sum_vehicle_for_approach(row: Dict[str, str], approach: str) -> int:
    total = 0
    for vehicle_type in vehicleTypes:
        for movement in movements:
            col = f"{approach}_appr_{vehicle_type}_{movement}"
            total += to_int(row.get(col, "0"))
    return total


def sum_vehicle_all_approaches(row: Dict[str, str]) -> int:
    return sum(sum_vehicle_for_approach(row, approach) for approach in approaches)


def sum_turn_all_approaches(row: Dict[str, str], movement: str) -> int:
    total = 0
    for approach in approaches:
        for vehicle_type in vehicleTypes:
            col = f"{approach}_appr_{vehicle_type}_{movement}"
            total += to_int(row.get(col, "0"))
    return total


def sum_mode(row: Dict[str, str], suffix: str) -> int:
    return sum(to_int(row.get(f"{approach}_appr_{suffix}", "0")) for approach in approaches)


def get_peak_hour(interval_rows: List[Dict[str, str]]) -> Tuple[str, int]:
    per_hour: Dict[str, int] = defaultdict(int)
    for row in interval_rows:
        dt = parse_dt(row.get("start_time", ""))
        if dt is None:
            continue
        key = dt.strftime("%Y-%m-%d %H:00")
        per_hour[key] += to_int(row["total_vehicle_15min"])

    if not per_hour:
        return "", 0

    peak_hour_start, peak_hour_volume = max(per_hour.items(), key=lambda item: item[1])
    return peak_hour_start, peak_hour_volume


def classify_leg_type(north: int, east: int, south: int, west: int) -> Tuple[str, str, str]:
    active = {
        "N": int(north > 0),
        "E": int(east > 0),
        "S": int(south > 0),
        "W": int(west > 0),
    }
    active_labels = [k for k, v in active.items() if v == 1]
    missing_labels = [k for k, v in active.items() if v == 0]
    active_count = len(active_labels)

    if active_count == 4:
        leg_type = "4_leg"
    elif active_count == 3:
        leg_type = "3_leg"
    elif active["N"] == 1 and active["S"] == 1 and active["E"] == 0 and active["W"] == 0:
        leg_type = "2_leg_NS"
    elif active["E"] == 1 and active["W"] == 1 and active["N"] == 0 and active["S"] == 0:
        leg_type = "2_leg_EW"
    elif active_count == 2:
        leg_type = "2_leg_other"
    else:
        leg_type = "other"

    return leg_type, ",".join(active_labels), ",".join(missing_labels)


def preprocess_raw(raw_csv: Path, interval_out_csv: Path, daily_out_csv: Path) -> None:
    interval_fields = [
        "count_id",
        "count_date",
        "location_name",
        "latitude",
        "longitude",
        "start_time",
        "end_time",
        "total_vehicle_15min",
        "north_vehicle_15min",
        "east_vehicle_15min",
        "south_vehicle_15min",
        "west_vehicle_15min",
        "left_turn_vehicle_15min",
        "through_vehicle_15min",
        "right_turn_vehicle_15min",
        "total_pedestrian_15min",
        "total_bike_15min",
    ]

    intervals_by_count: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    with raw_csv.open("r", newline="", encoding="utf-8-sig") as infile, interval_out_csv.open(
        "w", newline="", encoding="utf-8"
    ) as interval_out:
        reader = csv.DictReader(infile)
        validate_required_columns(reader.fieldnames)
        writer = csv.DictWriter(interval_out, fieldnames=interval_fields)
        writer.writeheader()
        rows_with_all_zero_vehicle = 0
        rows_with_negative_vehicle_values = 0

        for row in reader:
            north_vehicle = sum_vehicle_for_approach(row, "n")
            east_vehicle = sum_vehicle_for_approach(row, "e")
            south_vehicle = sum_vehicle_for_approach(row, "s")
            west_vehicle = sum_vehicle_for_approach(row, "w")

            total_vehicle = north_vehicle + east_vehicle + south_vehicle + west_vehicle
            if total_vehicle == 0:
                rows_with_all_zero_vehicle += 1
            if row_has_negative_vehicle_value(row):
                rows_with_negative_vehicle_values += 1

            left_turn_vehicle = sum_turn_all_approaches(row, "l")
            through_vehicle = sum_turn_all_approaches(row, "t")
            right_turn_vehicle = sum_turn_all_approaches(row, "r")

            total_pedestrian = sum_mode(row, "peds")
            total_bike = sum_mode(row, "bike")

            clean_row = {
                "count_id": row.get("count_id", ""),
                "count_date": row.get("count_date", ""),
                "location_name": row.get("location_name", ""),
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
                "start_time": row.get("start_time", ""),
                "end_time": row.get("end_time", ""),
                "total_vehicle_15min": str(total_vehicle),
                "north_vehicle_15min": str(north_vehicle),
                "east_vehicle_15min": str(east_vehicle),
                "south_vehicle_15min": str(south_vehicle),
                "west_vehicle_15min": str(west_vehicle),
                "left_turn_vehicle_15min": str(left_turn_vehicle),
                "through_vehicle_15min": str(through_vehicle),
                "right_turn_vehicle_15min": str(right_turn_vehicle),
                "total_pedestrian_15min": str(total_pedestrian),
                "total_bike_15min": str(total_bike),
            }

            writer.writerow(clean_row)
            intervals_by_count[clean_row["count_id"]].append(clean_row)

        # Non-blocking data quality counters to make assumptions explicit.
        print(f"Data QA: rows with all-zero vehicle demand = {rows_with_all_zero_vehicle}")
        print(f"Data QA: rows with negative raw vehicle values = {rows_with_negative_vehicle_values}")

    daily_fields = [
        "count_id",
        "count_date",
        "location_name",
        "latitude",
        "longitude",
        "leg_type",
        "active_approaches",
        "missing_approaches",
        "north_present",
        "east_present",
        "south_present",
        "west_present",
        "intervals_in_count",
        "total_vehicle_day",
        "total_pedestrian_day",
        "total_bike_day",
        "avg_vehicle_per_15min",
        "peak_hour_start",
        "peak_hour_vehicle",
        "north_vehicle_day",
        "east_vehicle_day",
        "south_vehicle_day",
        "west_vehicle_day",
        "left_turn_vehicle_day",
        "through_vehicle_day",
        "right_turn_vehicle_day",
    ]

    with daily_out_csv.open("w", newline="", encoding="utf-8") as daily_out:
        writer = csv.DictWriter(daily_out, fieldnames=daily_fields)
        writer.writeheader()

        for count_id, rows in intervals_by_count.items():
            if not rows:
                continue

            peak_hour_start, peak_hour_vehicle = get_peak_hour(rows)

            total_vehicle_day = sum(to_int(r["total_vehicle_15min"]) for r in rows)
            total_pedestrian_day = sum(to_int(r["total_pedestrian_15min"]) for r in rows)
            total_bike_day = sum(to_int(r["total_bike_15min"]) for r in rows)
            intervals = len(rows)
            avg_vehicle_per_15min = round(total_vehicle_day / intervals, 3) if intervals else 0
            north_vehicle_day = sum(to_int(r["north_vehicle_15min"]) for r in rows)
            east_vehicle_day = sum(to_int(r["east_vehicle_15min"]) for r in rows)
            south_vehicle_day = sum(to_int(r["south_vehicle_15min"]) for r in rows)
            west_vehicle_day = sum(to_int(r["west_vehicle_15min"]) for r in rows)
            leg_type, active_approaches, missing_approaches = classify_leg_type(
                north_vehicle_day, east_vehicle_day, south_vehicle_day, west_vehicle_day
            )

            daily_row = {
                "count_id": count_id,
                "count_date": rows[0]["count_date"],
                "location_name": rows[0]["location_name"],
                "latitude": rows[0]["latitude"],
                "longitude": rows[0]["longitude"],
                "leg_type": leg_type,
                "active_approaches": active_approaches,
                "missing_approaches": missing_approaches,
                "north_present": "1" if north_vehicle_day > 0 else "0",
                "east_present": "1" if east_vehicle_day > 0 else "0",
                "south_present": "1" if south_vehicle_day > 0 else "0",
                "west_present": "1" if west_vehicle_day > 0 else "0",
                "intervals_in_count": str(intervals),
                "total_vehicle_day": str(total_vehicle_day),
                "total_pedestrian_day": str(total_pedestrian_day),
                "total_bike_day": str(total_bike_day),
                "avg_vehicle_per_15min": str(avg_vehicle_per_15min),
                "peak_hour_start": peak_hour_start,
                "peak_hour_vehicle": str(peak_hour_vehicle),
                "north_vehicle_day": str(north_vehicle_day),
                "east_vehicle_day": str(east_vehicle_day),
                "south_vehicle_day": str(south_vehicle_day),
                "west_vehicle_day": str(west_vehicle_day),
                "left_turn_vehicle_day": str(sum(to_int(r["left_turn_vehicle_15min"]) for r in rows)),
                "through_vehicle_day": str(sum(to_int(r["through_vehicle_15min"]) for r in rows)),
                "right_turn_vehicle_day": str(sum(to_int(r["right_turn_vehicle_15min"]) for r in rows)),
            }
            writer.writerow(daily_row)


def _read_csv_by_key(path: Path, key: str) -> Dict[str, Dict[str, str]]:
    data: Dict[str, Dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8-sig") as infile:
        reader = csv.DictReader(infile)
        for row in reader:
            k = row.get(key, "").strip()
            if k:
                data[k] = row
    return data


def build_metadata(
    summary_csv: Path,
    most_recent_csv: Path,
    daily_csv: Path,
    metadata_out_csv: Path,
) -> None:
    summary_by_count = _read_csv_by_key(summary_csv, "count_id")
    most_recent_by_count = _read_csv_by_key(most_recent_csv, "latest_count_id")
    daily_by_count = _read_csv_by_key(daily_csv, "count_id")

    fields = [
        "count_id",
        "count_date",
        "location_name",
        "latitude",
        "longitude",
        "leg_type",
        "active_approaches",
        "missing_approaches",
        "north_present",
        "east_present",
        "south_present",
        "west_present",
        "total_vehicle_day_raw_derived",
        "total_pedestrian_day_raw_derived",
        "total_bike_day_raw_derived",
        "summary_total_vehicle",
        "summary_total_pedestrian",
        "summary_total_bike",
        "summary_count_duration_hr",
        "summary_am_peak_start",
        "summary_am_peak_vehicle",
        "summary_pm_peak_start",
        "summary_pm_peak_vehicle",
        "is_most_recent_for_location",
    ]

    with metadata_out_csv.open("w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fields)
        writer.writeheader()

        for count_id, daily in daily_by_count.items():
            summary = summary_by_count.get(count_id, {})
            most_recent = most_recent_by_count.get(count_id)

            writer.writerow(
                {
                    "count_id": count_id,
                    "count_date": daily.get("count_date", ""),
                    "location_name": daily.get("location_name", ""),
                    "latitude": daily.get("latitude", ""),
                    "longitude": daily.get("longitude", ""),
                    "leg_type": daily.get("leg_type", ""),
                    "active_approaches": daily.get("active_approaches", ""),
                    "missing_approaches": daily.get("missing_approaches", ""),
                    "north_present": daily.get("north_present", ""),
                    "east_present": daily.get("east_present", ""),
                    "south_present": daily.get("south_present", ""),
                    "west_present": daily.get("west_present", ""),
                    "total_vehicle_day_raw_derived": daily.get("total_vehicle_day", ""),
                    "total_pedestrian_day_raw_derived": daily.get("total_pedestrian_day", ""),
                    "total_bike_day_raw_derived": daily.get("total_bike_day", ""),
                    "summary_total_vehicle": summary.get("total_vehicle", ""),
                    "summary_total_pedestrian": summary.get("total_pedestrian", ""),
                    "summary_total_bike": summary.get("total_bike", ""),
                    "summary_count_duration_hr": summary.get("count_duration", ""),
                    "summary_am_peak_start": summary.get("am_peak_start", ""),
                    "summary_am_peak_vehicle": summary.get("am_peak_vehicle", ""),
                    "summary_pm_peak_start": summary.get("pm_peak_start", ""),
                    "summary_pm_peak_vehicle": summary.get("pm_peak_vehicle", ""),
                    "is_most_recent_for_location": "1" if most_recent else "0",
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess Toronto TMC data for all intersections.")
    parser.add_argument("--raw", default="data/raw/tmc_raw_data_2020_2029.csv")
    parser.add_argument("--summary", default="data/raw/tmc_summary_data.csv")
    parser.add_argument("--most-recent", default="data/raw/tmc_most_recent_summary_data.csv")
    parser.add_argument("--out-dir", default="outputs/preprocessed")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    raw_csv = Path(args.raw)
    summary_csv = Path(args.summary)
    most_recent_csv = Path(args.most_recent)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    interval_out_csv = out_dir / "tmc_interval_features_all.csv"
    daily_out_csv = out_dir / "tmc_daily_features_all.csv"
    metadata_out_csv = out_dir / "tmc_intersection_metadata_all.csv"

    preprocess_raw(raw_csv, interval_out_csv, daily_out_csv)
    build_metadata(summary_csv, most_recent_csv, daily_out_csv, metadata_out_csv)

    print(f"Wrote: {interval_out_csv}")
    print(f"Wrote: {daily_out_csv}")
    print(f"Wrote: {metadata_out_csv}")


if __name__ == "__main__":
    main()
