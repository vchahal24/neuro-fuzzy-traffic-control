# SIMULATION + EXPERIMENTS (CSVs -> results)
# Purpose: This serves as the main CLI entry for running traffic signal experiments
# 1. Parses command line arguments for:
#    a. Selection filters (most recent, leg type, top N by volume)
#    b. Simulation settings (mode, step seconds, cycle length, yellow/all-red times
#       saturation flow, min/max green, fixed NS ratio)
#    c. Controller settings (which controllers to run, ANFIS mode, MATLAB entry point)
#    d. Input CSV paths and output directory
# 2. Builds typed config objects from the parsed arguments
#    a. DataSelectionConfig for filtering which intersections to run
#    b. SimulationConfig for how to run the simulations
#    c. List of ControllerConfig for which controllers to run and their settings
# 3. Calls the main experiment runner function with the configs and CSV paths
# 4. Prints out the paths of the saved results and number of rows for confirmation

from __future__ import annotations

# this is used for command line args for running experiments
import argparse

# helps create file paths safely
from pathlib import Path

# config models for selection, simulation settings and controller settings
# ControllerConfig: Which controller to run and special settings (ANFIS mode, MATLAB entry point)
# DataSelectionConfig: How to filter/select which intersections to run experiments on
# SimulationConfig: How to run the simulations (mode, step seconds, cycle length, yellow/all-red times, saturation flow, min/max green, fixed NS ratio)
from sim.simulationConfigurationModels import ControllerConfig, DataSelectionConfig, SimulationConfig

# main experiment pipeline entry
# loads CSV, filter selections, runs simulations, saves results
from sim.trafficExperimentRunner import run_experiments


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
        help="Path to the preprocessed interval features CSV file."
    )
    parser.add_argument(
        "--daily-csv",
        default="outputs/preprocessed/tmc_daily_features_all.csv",
        help="Path to the preprocessed daily features CSV file."
    )
    parser.add_argument(
        "--metadata-csv",
        default="outputs/preprocessed/tmc_intersection_metadata_all.csv",
        help="Path to the preprocessed metadata CSV file."
    )
    parser.add_argument("--out-dir", default="outputs/experiments/latest", help="Path to the output directory for saving experiment results.")

    # --controllers option to specify which controllers to run, as a comma-separated list
    parser.add_argument(
        "--controllers",
        default="baseline_fixed,baseline_proportional,anfis",
        help="Comma-separated list from: baseline_fixed, baseline_proportional, anfis",
    )
    
    # --anfis-mode option to specify how to run the ANFIS controller
    # this can be either stub or matlab as choices
    parser.add_argument("--anfis-mode", default="stub", choices=["stub", "matlab"])
    
    # --matlab-entrypoint option to specify the path to the MATLAB script for ANFIS mode
    parser.add_argument(
        "--matlab-entrypoint",
        default="",
        help="Path to wrapper script/function entry for MATLAB integration mode.",
    )

    # --most-recent-only flag to only run experiments on the most recent data for each intersection
    parser.add_argument("--most-recent-only", action="store_true", help="Only run experiments on the most recent data for each intersection.")
    
    # --leg-type-filter option to specify which leg types to include in the experiments, with choices for all, 4_leg, 3_leg, 2_leg_NS, 2_leg_EW, 2_leg_other, other
    parser.add_argument(
        "--leg-type-filter",
        default="all",
        help="all | 4_leg | 3_leg | 2_leg_NS | 2_leg_EW | 2_leg_other | other",
    )
    
    # --top-n-by-volume option to specify to only run experiments on the top N intersections by volume, with default of 0 for no limit
    parser.add_argument("--top-n-by-volume", type=int, default=0, help="Only run experiments on the top N intersections by volume.")

    # Simulation settings
    # With defaults and choices where applicable
    # Help strings to explain each option
    parser.add_argument("--sim-mode", default="full_day", choices=["full_day", "single_interval"], help="Simulation mode.")
    parser.add_argument("--interval-index", type=int, default=0, help="Index of the interval to simulate.")
    parser.add_argument("--step-seconds", type=float, default=1.0, help="Simulation step size in seconds.")
    parser.add_argument("--cycle-length", type=int, default=90, help="Length of the signal cycle in seconds.")
    parser.add_argument("--yellow", type=int, default=5, help="Yellow light duration in seconds.")
    parser.add_argument("--all-red", type=int, default=2, help="All-red light duration in seconds.")
    parser.add_argument("--sat-flow", type=float, default=0.5, help="Saturation flow rate in vehicles per second per approach.")
    parser.add_argument("--min-green", type=int, default=10, help="Minimum green light duration in seconds.")
    parser.add_argument("--max-green", type=int, default=60, help="Maximum green light duration in seconds.")
    parser.add_argument("--fixed-ns-ratio", type=float, default=0.5, help="Fixed north-south split ratio.")

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
        interval_index=max(0, args.interval_index),
        step_seconds=args.step_seconds,
        cycle_length_seconds=args.cycle_length,
        yellow_seconds=args.yellow,
        all_red_seconds=args.all_red,
        saturation_flow_veh_per_sec_per_approach=args.sat_flow,
        min_green_seconds=args.min_green,
        max_green_seconds=args.max_green,
        fixed_ns_ratio=args.fixed_ns_ratio,
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
    resultsDataFrame, aggrDataFrame = run_experiments(
        intervalCSV=Path(args.interval_csv),
        dailyCSV=Path(args.daily_csv),
        metadataCSV=Path(args.metadata_csv),
        selectionCFG=selectConfig,
        simCFG=simConfig,
        controllersCFG=controllerConfig,
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
