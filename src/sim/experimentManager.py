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

# this function converts detailed per insection rows into grouped stats
# instead of one row per pair of intersection-controller, we get grouped summaries
# useful for charting
def groupedStats(resultsDataFrame: pd.DataFrame) -> pd.DataFrame:
    # make a copy so the original results table is saved
    copy = resultsDataFrame.copy()
    
    # take the peak hour start column, replace missing values with empty string, convert everything to string
    peakHourString = copy["peak_hour_start"].fillna("").astype(str)
    
    # creates a grouping for the peak hour bucket
    # it takes the last 5 characters of a peak hour string
    # 2026-03-01 07:30 turns to 07:30
    # 07:30 turns to 07:30
    copy["peak_hour_bucket"] = peakHourString.str[-5:].replace("", "unknown")
    
    # converts daily traffic volume to numeric
    convertToNumeric = pd.to_numeric(copy["total_vehicle_day"], errors="coerce").fillna(0)
    
    # creates a categorical bucket for total daily volume
    # so each intersection result row gets assigned to one volume bucket
    # useful for comparing controller behaviour across different traffic sizes
    copy["volume_bucket"] = pd.cut(
        convertToNumeric,
        bins=[-1, 10000, 25000, 50000, 100000, 1_000_000_000],
        labels=["<=10k", "10k-25k", "25k-50k", "50k-100k", "100k+"],
    ).astype(str)

    # group the data by four dimensions: controller, leg type, peak hour bucket, volume bucket
    fourDimensions = (
        copy.groupby(
            ["controller", "leg_type", "peak_hour_bucket", "volume_bucket"], dropna=False
        )
        # count how many result rows / intersections are in that group
        .agg(
            intersections=("count_id", "count"),
            total_delay_vehicle_seconds=("total_delay_vehicle_seconds", "sum"), # sum total delay across group
            mean_delay_vehicle_seconds=("avg_delay_per_vehicle_seconds", "mean"), # compute avg delay per intersection
            mean_max_queue_vehicles=("max_queue_vehicles", "mean"),
            mean_avg_queue_vehicles=("avg_queue_vehicles", "mean"),
            total_throughput_vehicles=("throughput_vehicles", "sum"),
            mean_stops_estimated=("stops_estimated", "mean"),
            mean_utilization_ratio=("utilization_ratio", "mean"),
            mean_improvement_vs_baseline_pct=("improvement_vs_baseline_pct", "mean"),
        )
        .reset_index()
    )
    return fourDimensions

#------------------ MAIN FUNCTION ----------------------#
# the actual experiment pipeline

# inputs:
#   3 CSV paths
#   selection config
#   simulation config
#   list of controller configs
#   output directory

# outputs
#   per intersection results (DataFrame)
#   aggregated results (DataFrame)
def experimentManager(
    intervalCSV: Path,
    dailyCSV: Path,
    metadataCSV: Path,
    selectionConfig: DataSelectionConfig,
    simConfig: SimulationConfig,
    controllerConfig: list[ControllerConfig],
    outDir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    
    # create the output directory if it does not already exist
    outDir.mkdir(parents=True, exist_ok=True)

    # load the intersections using the loader
    # this step:
    #   reads inputs CSVs
    #   applies selection filters
    #   packages each selected intersection into one object
    intersections: list[intersectionDataClass] = loadIntersectionCall(
        intervalCSV=intervalCSV,
        dailyCSV=dailyCSV,
        metadataCSV=metadataCSV,
        selection=selectionConfig,
    )
    
    # if no intersections selected, ERROR.
    if not intersections:
        raise RuntimeError("ERROR. No intersections matched the selection filters.")

    # create a list of empty list to store individual result rows
    # each row represents:
    #   one intersection
    #   one controller
    #   one sim result
    outputRows: list[dict[str, object]] = []
    trainingRows: list[dict[str, object]] = []
    # loop through each selected intersection
    for trafficData in intersections:
        # for each intersection, loop through each controller config
        # so if theres 100 intersections, 3 controllers = 300 runs
        for controllerCfg in controllerConfig:
            # build the controller object
            # examples: baselinefixed, baselineproportional, anfis
            controller = returnController(simConfig, controllerCfg)
            
            # run the actual queue sim for this: intersection, controller, sim config
            simulationResult, cycleRows = simIntersection(trafficData, controller, simConfig)
            
            # make a plain dictionary copy of the sim result
            mergedRow = dict(simulationResult)
            
            # attach metadata columns from the intersection date
            # now the row contains: simulation metrics, descriptive fields like leg type and total volume
            mergedRow.update(metadataDictionary(trafficData.metadataOneRow, trafficData.dailyOneRow))
            
            # add the completed row to the master output list
            # this repeats for each intersection-controller pair
            outputRows.append(mergedRow)
            if simConfig.exportTrainingData:
                trainingRows.extend(cycleRows)

    # converts every collected row into a DataFrame
    # this becomes the detailed per intersection results table
    resultsDataFrame = pd.DataFrame(outputRows)

    # default controller is baseline fixed
    baselineName = "baseline_fixed"
    # if its not run, then run baseline_proportional
    if baselineName not in set(resultsDataFrame["controller"]):
        baselineName = "baseline_proportional"
        
    # add this improvement-vs-baseline pct column
    # now every result row include its relative performance compare to the baseline
    resultsDataFrame = controllerComparison(resultsDataFrame, baselineName)

    # build the grouped summary table
    # now we have:
    #   1. detailed per intersection rows
    #   2. aggregated summary rows
    groupedSumTable = groupedStats(resultsDataFrame)

    # build the output file paths
    # three files will be written
    # detailed results CSV
    # aggregated results CSV
    # run config JSON
    resultsPath = outDir / "results_per_intersection.csv"
    groupedPath = outDir / "results_aggregated.csv"
    configPath = outDir / "run_config.json"
    trainingPath = outDir / simConfig.trainingCsvName

    # write rper intersection results to CSV
    resultsDataFrame.to_csv(resultsPath, index=False)
    
    # write grouped summary results to CSV
    groupedSumTable.to_csv(groupedPath, index=False)
    
    # save config snapshot
    # this records exactly how the experiment was run
    # it contains: sim settings, selection settings, all controller settings
    configSnapshot = {
        "selection": asdict(selectionConfig),
        "simulation": asdict(simConfig),
        "controllers": [asdict(cfg) for cfg in controllerConfig],
    }
    
    # writes the config snapshot to the JSON file
    pd.Series(configSnapshot).to_json(configPath, indent=2)

    if simConfig.exportTrainingData:
        trainingDataFrame = pd.DataFrame(trainingRows)
        trainingDataFrame.to_csv(trainingPath, index=False)

    # returns both DataFrame to caller
    # so now the function:
    #   1. saves outputs to disk
    #   2. gives the tables back in memory for any further use
    return resultsDataFrame, groupedSumTable
