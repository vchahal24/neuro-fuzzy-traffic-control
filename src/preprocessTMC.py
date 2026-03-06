# PREPROCESSING PIPELINE FOR TORONTO TMC DATASET
# raw -> interval/daily/metadata
# 1. Parses CLI arguments for input paths and output direcctory
# 2. Creates the output directory
# 3. Runs:
#    a. preprocessRawData to read the raw CSV and write out the cleaned interval features and daily rollups
#    b. generateMetadata to merge together the daily rollups with the provided summary files for a metadata table
# 4. Prints out the paths of the generated files for user confirmation

#!/usr/bin/env python3
# allows you to run the file as "./preprocessTMC.py"

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
"""

#------------------------------------------------------------- START OF PROGRAM -------------------------------------------------------------------------------#

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

# this function basically takes something we read from a CSV and returns a safe integer without error
def parseToInt(value: str) -> int:
    # if the value is none or empty string, return 0
    if value is None:
        return 0
    # get rid of the whitespace and convert it to a string just in case it's not already a string
    text = str(value).strip()
    # if now the string is empty, return 0
    if text == "":
        return 0
    try:
        # get the float of a value in the CSV but then convert it to a round whole int value
        return int(float(text))
    except ValueError:
        return 0

# used for parsing date time values from the CSV
# same as above function but for date time
def parseDateTime(text: str) -> datetime | None:
    # if empty, return none
    if not text:
        return None
    # otherwise return the date time in ISO 8601 format
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None

# calculates the total number of vehicles per approach (n, e, s, w)
def totalVehicleApproach(row: Dict[str, str], appr: str) -> int:
    # begin with total at 0
    tot = 0
    
    # suming all vehicles (cars, trucks, buses) and movements (right, through, left) for a given approach
    for vehType in vehicleTypes:
        for movement in movements:
            col = f"{appr}_appr_{vehType}_{movement}"
            tot += parseToInt(row.get(col, "0"))
    return tot

# calculates the total number of vehicles across all approaches
def totalVehicleAllApproaches(row: Dict[str, str]) -> int:
    # 15 min interval
    return sum(totalVehicleApproach(row, appr) for appr in approaches)


# totals a specific movement type which could be (right, through, left) across all approaches and for all vehicles types
def totalTurnAllApproaches(row: Dict[str, str], mvmnt: str) -> int:
    tot = 0
    for appr in approaches:
        for typeOfVehicle in vehicleTypes:
            col = f"{appr}_appr_{typeOfVehicle}_{mvmnt}"
            tot += parseToInt(row.get(col, "0"))
    return tot

# sums other things such as pedestrians or bikes across all approaches
def totalPedBike(row: Dict[str, str], suffix: str) -> int:
    # suffix can be "peds" or "bike"
    return sum(parseToInt(row.get(f"{appr}_appr_{suffix}", "0")) for appr in approaches)

# gets the peak hour by grouping the 15 min rows into hourly buckets and finding the max hour by volume
def peakHour(intervalRows: List[Dict[str, str]]) -> Tuple[str, int]:
    # per hour volume calculator
    volPerHour: Dict[str, int] = defaultdict(int)
    
    for row in intervalRows:
        dateTime = parseDateTime(row.get("start_time", ""))
        if dateTime is None:
            continue
        key = dateTime.strftime("%Y-%m-%d %H:00")
        volPerHour[key] += parseToInt(row["total_vehicle_15min"])

    if not volPerHour:
        return "", 0

    # picking the hour with the largest summed volume and returning that hour and the volume
    pkHourStart, pkHourVol = max(volPerHour.items(), key=lambda item: item[1])
    return pkHourStart, pkHourVol

# grouping intersections based on leg types
# since not all intersections have 4 legs, some are 3 leg and some are 2 leg, we want to group them
def groupLegType(north: int, east: int, south: int, west: int) -> Tuple[str, str, str]:
    # note: 0 vehicles all day is counted as a missing leg, could be missing data, but we are assuming missing leg for simplicity
    dir = {
        "N": int(north > 0),
        "E": int(east > 0),
        "S": int(south > 0),
        "W": int(west > 0),
    }
    dirLabels = [k for k, v in dir.items() if v == 1]
    missingLabels = [k for k, v in dir.items() if v == 0]
    dirCount = len(dirLabels)

    # divides them into 4 leg, 3 leg, 2 leg (NS or EW) or other
    if dirCount == 4:
        legType = "4_leg"
    elif dirCount == 3:
        legType = "3_leg"
    elif dir["N"] == 1 and dir["S"] == 1 and dir["E"] == 0 and dir["W"] == 0:
        legType = "2_leg_NS"
    elif dir["E"] == 1 and dir["W"] == 1 and dir["N"] == 0 and dir["S"] == 0:
        legType = "2_leg_EW"
    elif dirCount == 2:
        legType = "2_leg_other"
    else:
        legType = "other"

    # returning which legs are active or missing as seperated strings
    return legType, ",".join(dirLabels), ",".join(missingLabels)

# columns that we want for the interval level CSV (one row per 15 min interval)
def preprocessRawData(rawCSV: Path, intOutCSV: Path, dailyOutCSV: Path) -> None:
    fieldsOfCSV = [
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

    # group interval rows by count id so we can late roll them into daily totals
    intByCount: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    # read raw CSV and write out the cleaned interval features
    with rawCSV.open("r", newline="", encoding="utf-8-sig") as infile, intOutCSV.open(
        "w", newline="", encoding="utf-8"
    ) as intOut:
        readsIn = csv.DictReader(infile)
        writesOut = csv.DictWriter(intOut, fieldnames=fieldsOfCSV)
        writesOut.writeheader()

        # per approach totals for vehicles and left, through, right
        for row in readsIn:
            nVehicle = totalVehicleApproach(row, "n")
            eVehicle = totalVehicleApproach(row, "e")
            sVehicle = totalVehicleApproach(row, "s")
            wVehicle = totalVehicleApproach(row, "w")

            # intersection total for this interval
            totVehicle = nVehicle + eVehicle + sVehicle + wVehicle
            
            # movement totals across the intersection
            leftVehicle = totalTurnAllApproaches(row, "l")
            throughVehicle = totalTurnAllApproaches(row, "t")
            rightVehicle = totalTurnAllApproaches(row, "r")

            # peds and bikes totals across the intersection
            totPedestrian = totalPedBike(row, "peds")
            totBike = totalPedBike(row, "bike")

            # creating the cleaned up row with the features we want and writing it out to the interval level CSV
            cleanedUpRow = {
                "count_id": row.get("count_id", ""),
                "count_date": row.get("count_date", ""),
                "location_name": row.get("location_name", ""),
                "latitude": row.get("latitude", ""),
                "longitude": row.get("longitude", ""),
                "start_time": row.get("start_time", ""),
                "end_time": row.get("end_time", ""),
                "total_vehicle_15min": str(totVehicle),
                "north_vehicle_15min": str(nVehicle),
                "east_vehicle_15min": str(eVehicle),
                "south_vehicle_15min": str(sVehicle),
                "west_vehicle_15min": str(wVehicle),
                "left_turn_vehicle_15min": str(leftVehicle),
                "through_vehicle_15min": str(throughVehicle),
                "right_turn_vehicle_15min": str(rightVehicle),
                "total_pedestrian_15min": str(totPedestrian),
                "total_bike_15min": str(totBike),
            }

            # writes the interval row right away
            writesOut.writerow(cleanedUpRow)
            
            # also stores it for daily later
            intByCount[cleanedUpRow["count_id"]].append(cleanedUpRow)

    # columns that we want for the daily CSV (one row for each count id)
    dailyFields = [
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

    # writing the daily totals
    with dailyOutCSV.open("w", newline="", encoding="utf-8") as dOut:
        writesOut = csv.DictWriter(dOut, fieldnames=dailyFields)
        writesOut.writeheader()

        # if something goes wrong and theres no intervals, we basically want to skip that count id
        for count_id, rows in intByCount.items():
            if not rows:
                continue

            # find the busiest hour (based on the intervals)
            pkHourStart, pkHourVehicle = peakHour(rows)

            # computes the daily totals (sums across every interval)
            totalVehicleDay = sum(parseToInt(r["total_vehicle_15min"]) for r in rows)
            totalPedDay = sum(parseToInt(r["total_pedestrian_15min"]) for r in rows)
            totalBikeDay = sum(parseToInt(r["total_bike_15min"]) for r in rows)
            
            # count how many 15 min intervals we have for the day
            intervals = len(rows)
            
            # avg vehicles per 15 mins (used later)
            avgVehiclePer15 = round(totalVehicleDay / intervals, 3) if intervals else 0
            
            # north east south west vehicle per approach totals
            nVehicleDay = sum(parseToInt(r["north_vehicle_15min"]) for r in rows)
            eVehicleDay = sum(parseToInt(r["east_vehicle_15min"]) for r in rows)
            sVehicleDay = sum(parseToInt(r["south_vehicle_15min"]) for r in rows)
            wVehicleDay = sum(parseToInt(r["west_vehicle_15min"]) for r in rows)
            
            # we group based on intersection shape (the legs show how traffic flows)
            legType, activeApprs, missingApprs = groupLegType(
                nVehicleDay, eVehicleDay, sVehicleDay, wVehicleDay
            )

            # building the final daily row and writing it out to the daily level CSV
            dailyRow = {
                "count_id": count_id,
                "count_date": rows[0]["count_date"],
                "location_name": rows[0]["location_name"],
                "latitude": rows[0]["latitude"],
                "longitude": rows[0]["longitude"],
                "leg_type": legType,
                "active_approaches": activeApprs,
                "missing_approaches": missingApprs,
                "north_present": "1" if nVehicleDay > 0 else "0",
                "east_present": "1" if eVehicleDay > 0 else "0",
                "south_present": "1" if sVehicleDay > 0 else "0",
                "west_present": "1" if wVehicleDay > 0 else "0",
                "intervals_in_count": str(intervals),
                "total_vehicle_day": str(totalVehicleDay),
                "total_pedestrian_day": str(totalPedDay),
                "total_bike_day": str(totalBikeDay),
                "avg_vehicle_per_15min": str(avgVehiclePer15),
                "peak_hour_start": pkHourStart,
                "peak_hour_vehicle": str(pkHourVehicle),
                "north_vehicle_day": str(nVehicleDay),
                "east_vehicle_day": str(eVehicleDay),
                "south_vehicle_day": str(sVehicleDay),
                "west_vehicle_day": str(wVehicleDay),
                "left_turn_vehicle_day": str(sum(parseToInt(r["left_turn_vehicle_15min"]) for r in rows)),
                "through_vehicle_day": str(sum(parseToInt(r["through_vehicle_15min"]) for r in rows)),
                "right_turn_vehicle_day": str(sum(parseToInt(r["right_turn_vehicle_15min"]) for r in rows)),
            }
            writesOut.writerow(dailyRow)


def readCSV(path: Path, key: str) -> Dict[str, Dict[str, str]]:
    # basically we want to read a CSV and return a dictionary where the keys are from
    # the column specified by the key parameter and the values are the rows as dictionaries
    data: Dict[str, Dict[str, str]] = {}
    with path.open("r", newline="", encoding="utf-8-sig") as infile:
        readIn = csv.DictReader(infile)
        for row in readIn:
            z = row.get(key, "").strip()
            if z:
                data[z] = row
    return data

# function for generating the metadata CSV
def generateMetadata(
    summaryCSV: Path,
    mostRecentCSV: Path,
    dailyCSV: Path,
    metaOutCSV: Path,
) -> None:
    # pull in the summary CSVs and our computed daily CSV so they are merged
    summaryByCount = readCSV(summaryCSV, "count_id")
    mostRecentByCount = readCSV(mostRecentCSV, "latest_count_id")
    dailyByCount = readCSV(dailyCSV, "count_id")

    # this is the final metadata file
    # we want to include the raw daily totals we computed, the summary totals from the city, and whether this count id is the most recent for its location (since some locations have multiple count ids over time)
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

    # writing the metadata CSV
    with metaOutCSV.open("w", newline="", encoding="utf-8") as outFile:
        writesOut = csv.DictWriter(outFile, fieldnames=fields)
        writesOut.writeheader()

        for count_id, daily in dailyByCount.items():
            # look up matching rows from the other tables
            sum = summaryByCount.get(count_id, {})
            
            # which is keyed on "latest_count_id" values from that file
            mostRec = mostRecentByCount.get(count_id)

            # merge it into one row
            writesOut.writerow(
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
                    "summary_total_vehicle": sum.get("total_vehicle", ""),
                    "summary_total_pedestrian": sum.get("total_pedestrian", ""),
                    "summary_total_bike": sum.get("total_bike", ""),
                    "summary_count_duration_hr": sum.get("count_duration", ""),
                    "summary_am_peak_start": sum.get("am_peak_start", ""),
                    "summary_am_peak_vehicle": sum.get("am_peak_vehicle", ""),
                    "summary_pm_peak_start": sum.get("pm_peak_start", ""),
                    "summary_pm_peak_vehicle": sum.get("pm_peak_vehicle", ""),
                    "is_most_recent_for_location": "1" if mostRec else "0",
                }
            )

# function for parsing command line arguments
def argFunc() -> argparse.Namespace:
    # this sets up command line arguments so that you can specify different input and output files without editing the script
    parser = argparse.ArgumentParser(description="Preprocess Toronto TMC data for all intersections.")
    
    # raw interval data (15-min rows)
    parser.add_argument("--raw", default="data/raw/tmc_raw_data_2020_2029.csv")
    
    # summary table (already aggregated in the dataset)
    parser.add_argument("--summary", default="data/raw/tmc_summary_data.csv")
    
    # most recent count per location
    parser.add_argument("--most-recent", default="data/raw/tmc_most_recent_summary_data.csv")
    
    # output folder
    parser.add_argument("--out-dir", default="outputs/preprocessed")
    
    return parser.parse_args()


def main() -> None:
    # entry
    # parse args, make output folder, run preprocessing
    args = argFunc()
    
    rawCSV = Path(args.raw)
    sumCSV = Path(args.summary)
    mostRecCSV = Path(args.most_recent)
    outDir = Path(args.out_dir)
    outDir.mkdir(parents=True, exist_ok=True)

    # output file paths
    intOutCSV = outDir / "tmc_interval_features_all.csv"
    dOutCSV = outDir / "tmc_daily_features_all.csv"
    mOutCSV = outDir / "tmc_intersection_metadata_all.csv"

    # step 1: raw -> interval features + daily rollups
    preprocessRawData(rawCSV, intOutCSV, dOutCSV)
    
    # step 2: merge daily rollups with provided summary files for a metadata table
    generateMetadata(sumCSV, mostRecCSV, dOutCSV, mOutCSV)

    # outputs to the user so we know it actually produced said files
    print(f"Successfully wrote: {intOutCSV}")
    print(f"Successfully wrote: {dOutCSV}")
    print(f"Successfully wrote: {mOutCSV}")


if __name__ == "__main__":
    main()
