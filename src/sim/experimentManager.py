# EXPERIMENT MANAGER #
# sits above queueSimulation

# Purpose:
#   1. loading all selected intersections
#   2. loop through all requested controllers
#   3. run the sim for every intersection-controller pair
#   4. attach metadata columns
#   5. compute imporvement vs baseline
#   6. create the aggregated summary tables
#   7. save outputs to CSV

#------------------------------------------------------------- START OF PROGRAM -------------------------------------------------------------------------------#

from __future__ import annotations

# useful for saving run config to a JSON
from dataclasses import asdict

# imports path for file systems
from pathlib import Path

# dataframe operations
import pandas as pd

# experiment config models
from .simConfigModels import ControllerConfig, DataSelectionConfig, SimulationConfig

# controller models
from .controllerModels import returnController

# selected intersection data loader
from .intersectionDataLoader import intersectionDataClass, loadIntersectionCall

# queue simulation routine for one intersection/controller pair
from .queueSimulation import simIntersection

# this helper creates a dictionary of metadata fields to attach to each sim result row
def metadataDictionary(metaRow: pd.Series, dailyRow: pd.Series) -> dict[str, str | float | int]:
    return {
        # this function adds leg type, peak hour, daily volume, most recent flag
        "leg_type": dailyRow.get("leg_type", metaRow.get("leg_type", "")),
        "peak_hour_start": dailyRow.get("peak_hour_start", ""),
        "total_vehicle_day": dailyRow.get("total_vehicle_day", ""),
        "total_vehicle_day_raw_derived": metaRow.get("total_vehicle_day_raw_derived", ""),
        "summary_total_vehicle": metaRow.get("summary_total_vehicle", ""),
        "is_most_recent_for_location": metaRow.get("is_most_recent_for_location", ""),
    }

# this function computes a new column which is
# improvement_vs_baseline_pct
# it compares each row's total delay against the baseline controller's delay for the same count_id
def controllerComparison(resultsDataFrame: pd.DataFrame, baseline: str) -> pd.DataFrame:
    baselineDf = resultsDataFrame[resultsDataFrame["controller"] == baseline][
        # this builds a baseline only data frame
        #   1. filters resultsDataFrame to only rows whose controller equals baselineName
        #   2. keeps: count_id, total_delay_vehicle_seconds
        #   3. rename delay column to baseline_total_delay_vehicles_seconds
        
        # merged so u can distinguish current row delay vs baseline delay
        ["count_id", "total_delay_vehicle_seconds"]
    ].rename(columns={"total_delay_vehicle_seconds": "baseline_total_delay_vehicle_seconds"})
    
    # merge baseline delay back onto every results row using count_id
    # this means for each row:
    #   i. we have the controllers delay
    #   ii. the baseline controllers delay for the same instruction
    mergedDataFrame = resultsDataFrame.merge(baselineDf, on="count_id", how="left")
    
    # converts baseline to numeric
    baselineDelay = pd.to_numeric(mergedDataFrame["baseline_total_delay_vehicle_seconds"], errors="coerce")
    
    # converts curent row delay to numeric
    currentDelay = pd.to_numeric(mergedDataFrame["total_delay_vehicle_seconds"], errors="coerce")
    
    # this computes percent improvement
    # (baseline delay - current delay)/baseline delay * 100
    # if val is positive, then improvement
    # if val is negative, then worse
    # if val is 0, then same
    mergedDataFrame["improvement_vs_baseline_pct"] = ((baselineDelay - currentDelay) / baselineDelay.replace(0, pd.NA)) * 100.0
    mergedDataFrame["improvement_vs_baseline_pct"] = mergedDataFrame["improvement_vs_baseline_pct"].fillna(0.0)
    return mergedDataFrame

