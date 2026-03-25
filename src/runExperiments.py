# SIMULATION + EXPERIMENTS (CSVs -> results)
# Purpose: This serves as the main CLI entry for running traffic signal experiments
# 1. Parses command line arguments for:
#    i. Selection filters (most recent, leg type, top N by volume)
#    ii. Simulation settings (mode, step seconds, cycle length, yellow/all-red times
#       saturation flow, min/max green, fixed NS ratio)
#    iii. Controller settings (which controllers to run, ANFIS mode, MATLAB entry point)
#    iv. Input CSV paths and output directory
# 2. Builds typed config objects from the parsed arguments
#    i. DataSelectionConfig for filtering which intersections to run
#    ii. SimulationConfig for how to run the simulations
#    iii. List of ControllerConfig for which controllers to run and their settings
# 3. Calls the main experiment runner function with the configs and CSV paths
# 4. Prints out the paths of the saved results and number of rows for confirmation

#------------------------------------------------------------- START OF PROGRAM -------------------------------------------------------------------------------#

from __future__ import annotations

# this is used for command line args for running experiments
import argparse

# helps create file paths safely
from pathlib import Path

# config models for selection, simulation settings and controller settings

# ControllerConfig: Which controller to run and special settings (ANFIS mode, MATLAB entry point)
# DataSelectionConfig: How to filter/select which intersections to run experiments on
# SimulationConfig: How to run the simulations (mode, step seconds, cycle length, yellow/all-red times, saturation flow, min/max green, fixed NS ratio)
from sim.simConfigModels import ControllerConfig, DataSelectionConfig, SimulationConfig

# main experiment pipeline entry
# loads CSV, filter selections, runs simulations, saves results
from sim.experimentManager import experimentManager

# parses all command line options for experiment runs
def parseCLIArgs() -> argparse.Namespace:
    # --help description line
    parser = argparse.ArgumentParser(
        description="Run TMC traffic signal control experiments."
    )
    # --interval-csv option with default path to preprocessed interval features CSV
    # --daily-csv option with default path to preprocessed daily features CSV
    # --metadata-csv option with default path to preprocessed metadata CSV
    # --out-dir option with default path to save experiment results
    parser.add_argument(
        "--interval-csv",
        default="outputs/preprocessed/tmc_interval_features_all.csv",
    )
    parser.add_argument(
        "--daily-csv",
        default="outputs/preprocessed/tmc_daily_features_all.csv",
    )
    parser.add_argument(
        "--metadata-csv",
        default="outputs/preprocessed/tmc_intersection_metadata_all.csv",
    )
    parser.add_argument("--out-dir", default="outputs/experiments/latest")

    # --controllers option to specify which controllers to run, as a comma-separated list
    parser.add_argument(
        "--controllers",
        default="baseline_fixed,baseline_proportional,anfis",
    )
    
    # --anfis-mode option to specify how to run the ANFIS controller
    # this can be either stub or matlab as choices
    parser.add_argument("--anfis-mode", default="stub", choices=["stub", "matlab", "octave"])
    
    # --matlab-entrypoint option to specify the path to the MATLAB script for ANFIS mode
    parser.add_argument(
        "--matlab-entrypoint",
        default="",
    )
    parser.add_argument(
        "--octave-entrypoint",
        default="",
    )
    parser.add_argument(
        "--octave-cli-path",
        default=r"C:\Program Files\GNU Octave\Octave-11.1.0\mingw64\bin\octave-cli.exe",
    )

    # --most-recent-only flag to only run experiments on the most recent data for each intersection
    parser.add_argument("--most-recent-only", action="store_true")
    
    # --leg-type-filter option to specify which leg types to include in the experiments, with choices for all, 4_leg, 3_leg, 2_leg_NS, 2_leg_EW, 2_leg_other, other
    parser.add_argument(
        "--leg-type-filter",
        default="all",
    )
    
    # --top-n-by-volume option to specify to only run experiments on the top N intersections by volume, with default of 0 for no limit
    parser.add_argument("--top-n-by-volume", type=int, default=0)

    # Simulation settings
    # With defaults and choices where applicable
    # Help strings to explain each option
    parser.add_argument("--sim-mode", default="full_day", choices=["full_day", "single_interval"])
    parser.add_argument("--interval-index", type=int, default=0)
    parser.add_argument("--step-seconds", type=float, default=1.0)
    parser.add_argument("--cycle-length", type=int, default=90)
    parser.add_argument("--yellow", type=int, default=5)
    parser.add_argument("--all-red", type=int, default=2)
    parser.add_argument("--sat-flow", type=float, default=0.5)
    parser.add_argument("--min-green", type=int, default=10)
    parser.add_argument("--max-green", type=int, default=60)
    parser.add_argument("--fixed-ns-ratio", type=float, default=0.5)
    parser.add_argument("--enable-invariant-checks", action="store_true")
    parser.add_argument("--invariant-tolerance", type=float, default=1e-6)
    parser.add_argument("--export-training-data", action="store_true")
    parser.add_argument("--training-queue-scale", type=float, default=40.0)
    parser.add_argument("--training-csv-name", default="cycle_training_data.csv")

    # parse the arguments and return
    return parser.parse_args()

# converts args into typed configs
# takes arguments and returns
# 1. DataSelectionConfig for filtering which intersections to run
# 2. SimulationConfig for how to run the simulations
# 3. List of ControllerConfig for which controllers to run and their settings
def convertToConfig(args: argparse.Namespace) -> tuple[DataSelectionConfig, SimulationConfig, list[ControllerConfig]]:
    selectConfig = DataSelectionConfig(
        # structured config object
        # uses max(0,...) to prevent negative indexes
        mostRecentOnly=args.most_recent_only,
        legTypeFilter=args.leg_type_filter,
        topNByVol=max(0, args.top_n_by_volume),
    )
    
    # converts CLI values into a single object that simulator can consume
    # Uses max(0,...) to prevent negative indexes
    simConfig = SimulationConfig(
        mode=args.sim_mode,
        intervalIndex=max(0, args.interval_index),
        step_seconds=args.step_seconds,
        cycle_length_seconds=args.cycle_length,
        yellow_seconds=args.yellow,
        all_red_seconds=args.all_red,
        saturation_flow_veh_per_sec_per_approach=args.sat_flow,
        minGreenSecs=args.min_green,
        maxGreenSecs=args.max_green,
        fixedNSRatio=args.fixed_ns_ratio,
        enableInvariantChecks=args.enable_invariant_checks,
        invariantTolerance=max(0.0, args.invariant_tolerance),
        exportTrainingData=args.export_training_data,
        trainingQueueScale=max(1e-6, args.training_queue_scale),
        trainingCsvName=args.training_csv_name,
    )

    # list of controllers
    # split the comma separated string into a clean list
    # "baseline_fixed, baseline_proportional, anfis" -> ["baseline_fixed", "baseline_proportional", "anfis"]
    # .strip() is used to remove any extra whitespace around the names
    controllerNames = [name.strip() for name in args.controllers.split(",") if name.strip()]
    
    controllerConfig: list[ControllerConfig] = []
    
    # for each controller name, create a ControllerConfig object and add to the list
    # even baseline controllers have anfis mode and Matlab entry
    for name in controllerNames:
        controllerConfig.append(
            ControllerConfig(
                controller_name=name,
                anfisMode=args.anfis_mode,
                matlabEntry=args.matlab_entrypoint,
                octaveEntry=args.octave_entrypoint,
                octaveCliPath=args.octave_cli_path,
            )
        )
        
    # returns the three configs
    return selectConfig, simConfig, controllerConfig


# running the experimental pipeline
def main() -> None:
    # call the CLI parser and get inputs from the user
    args = parseCLIArgs()
    
    # build the config objects from convertToConfig function
    selectConfig, simConfig, controllerConfig = convertToConfig(args)

    # calls the main experiment pipeline
    # wraps each CSV path and output directory in Path so it operates cleanly
    # expects the runner to return two dataframes:
    # 1. resultsDataFrame with per-intersection results for each controller and interval
    # 2. aggrDataFrame with aggregated results across intersections for each controller and interval
    resultsDataFrame, aggrDataFrame = experimentManager(
        intervalCSV=Path(args.interval_csv),
        dailyCSV=Path(args.daily_csv),
        metadataCSV=Path(args.metadata_csv),
        selectionConfig=selectConfig,
        simConfig=simConfig,
        controllerConfig=controllerConfig,
        outDir=Path(args.out_dir),
    )

    # print where it expects the detailed results to be written
    print(f"Saved per-intersection results: {Path(args.out_dir) / 'results_per_intersection.csv'}")
    
    # prints where it expects the aggregated results to be written
    print(f"Saved aggregated results: {Path(args.out_dir) / 'results_aggregated.csv'}")
    
    # checks the number of rows in each dataframe
    print(f"Rows (per intersection): {len(resultsDataFrame)}")
    print(f"Rows (aggregated): {len(aggrDataFrame)}")

# entrypoint guard
if __name__ == "__main__":
    main()
