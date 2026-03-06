# DATA LOADER FOR SIMULATION STAGE
# Purpose: Read the three preprocessed CSVs, apply the selection filters from the user, return a clean Python object for each intersection for the simulator

from __future__ import annotations

# dataclass for holding all per-intersection tables needed for simulation
from dataclasses import dataclass

# pathlib for csv path args
from pathlib import Path

# iterable typing for helper conversion
from typing import Iterable

# pandas for filtering csv data
import pandas as pd

# config for selecting subsets of intersections
from .SimConfigModels import DataSelectionConfig

# one intersection worth of metadata, daily row, all interval rows
@dataclass(frozen=True)
class intersectionDataClass:
    # unique ID of the intersection
    countID: str
    # one row of metadata
    # contains leg type, location fields, most recent flag, etc.
    metadataOneRow: pd.Series
    # contains daily summary such as: total daily volume, peak hour values, summarized daily features.
    dailyOneRow: pd.Series
    # all 15 minute rows for that intersection
    # this is the time series data the simulator will use cycle by cycle
    intervalAllRows: pd.DataFrame

# we need to convert the count id values to string
# one file might load count ID as float or integer, so for consistency
# make them all strings
def convertToString(series: pd.Series) -> pd.Series:
    return series.astype(str)

# reads all 3 input tables and ensures count_id are consistent
# takes 3 files paths: interval CSV, daily CSV, metadata CSV
# returns 3 pandas DataFrames
def threeDataFrames(
    intervalCSV: Path,
    dailyCSV: Path,
    metadataCSV: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]: # returns exactly 3 data frames in a tuple
    intervalDataFrame = pd.read_csv(intervalCSV) # reads interval CSV into a pandas DataFrame
    dailyDataFrame = pd.read_csv(dailyCSV)
    metadataDataFrame = pd.read_csv(metadataCSV)
    # converts the count_id column in the interval, daily and metadata tables to a string
    intervalDataFrame["count_id"] = convertToString(intervalDataFrame["count_id"])
    dailyDataFrame["count_id"] = convertToString(dailyDataFrame["count_id"])
    metadataDataFrame["count_id"] = convertToString(metadataDataFrame["count_id"])
    
    # returns the three loaded data frames
    return intervalDataFrame, dailyDataFrame, metadataDataFrame


# applies user filters - most recent, leg type, top N volume
# this function takes:
#   1. the daily table
#   2. the metadata table
#   3. the users filter config

# returns a filtered version of the table
def filterTables(
    dailyDataFrame: pd.DataFrame,
    metadataDataFrame: pd.DataFrame,
    config: DataSelectionConfig,
) -> pd.DataFrame:
    # starts by creating a merged DataFrame called "selectedDataFrame"
    # daily rows with one useful metadata column
    selectedDataFrame = dailyDataFrame.merge(
        # we are only interested in keeping count_id and is_most_recent_for_location
        metadataDataFrame[["count_id", "is_most_recent_for_location"]].drop_duplicates("count_id"),
        on="count_id", # merge using count_id as the key
        how="left", # left join
    )
    
    # this cleans up the is_most_recent_for_location
    selectedDataFrame["is_most_recent_for_location"] = (
        pd.to_numeric(selectedDataFrame["is_most_recent_for_location"], errors="coerce").fillna(0).astype(int)
    )

    # checks whether the user requested to keep only the most recent intersections
    if config.mostRecentOnly:
        selectedDataFrame = selectedDataFrame[selectedDataFrame["is_most_recent_for_location"] == 1]

    # checks whether the user requested a specific leg type filter
    if config.legTypeFilter != "all":
        selectedDataFrame = selectedDataFrame[selectedDataFrame["leg_type"] == config.legTypeFilter]

    # checks whether the user wants only the top N intersections by volume
    # if its 0, then keep all
    if config.topNByVol > 0:
        selectedDataFrame = selectedDataFrame.sort_values("total_vehicle_day", ascending=False).head(config.topNByVol)

    # returns filtered daily DataFrame
    return selectedDataFrame


# main loader used by experiments
# returns one object per selected intersection

# 1. loads the 3 CSV tables
# 2. filters which intersections to keep
# 3. collects all needed rows for each selected intersection
# 4. returns a list of IntersectionData objects
def loadIntersectionCall(
    intervalCSV: Path,
    dailyCSV: Path,
    metadataCSV: Path,
    selection: DataSelectionConfig,
) -> list[intersectionDataClass]:
    intervalDataFrame, dailyDataFrame, metadataDataFrame = threeDataFrames(intervalCSV, dailyCSV, metadataCSV) # loads the 3 CSV files
    selectedDailyDf = filterTables(dailyDataFrame, metadataDataFrame, selection) # applies the users selection config to the daily table

    # if filtering has no rows, return empty list
    if selectedDailyDf.empty:
        return []

    # builds a metadata lookup table indexed count_id
    metaLookupTable = (
        # sorts metadata by ID
        metadataDataFrame.sort_values("count_id")
        # ensures only one metadata row per count_id remains
        .drop_duplicates("count_id", keep="last")
        # makes count_id the DataFrame index
        .set_index("count_id")
    )

    # sorts the interval table first by:
    #   1. count_id
    #   2. start_time
    
    # this makes interval rows ordered properly in time for each intersection
    # CRUCIAl so simulator expects interval rows in chronological order
    intervalDataFrame = intervalDataFrame.sort_values(["count_id", "start_time"])
    # creates an empty list that will store final output objects
    outputObjects: list[intersectionDataClass] = []
    # loops through each selected daily row
    # _ is the DataFrame index
    # dailyRow is the actual row data as a pandas Series
    for _, dailyRow in selectedDailyDf.iterrows():
        countId = str(dailyRow["count_id"]) # force count ID to string
        intervalRows = intervalDataFrame[intervalDataFrame["count_id"] == countId].copy() # finds all interval rows in the interval table for specific count ID
        if intervalRows.empty: # skip it if theres no interval data
            continue
        metaRow = metaLookupTable.loc[countId] if countId in metaLookupTable.index else dailyRow # tries to get metadata row for the count ID
        
        # IntersectionData object for the intersection which is appended to output list
        # bundles ID, metadata row, daily summary row, full interval time series
        outputObjects.append(
            intersectionDataClass(
                countID=countId,
                metadataOneRow=metaRow,
                dailyOneRow=dailyRow,
                intervalAllRows=intervalRows,
            )
        )
    return outputObjects

