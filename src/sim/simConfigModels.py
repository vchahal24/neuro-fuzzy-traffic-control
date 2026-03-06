# SIMULATION CONFIGURATION MODELS
# Purpose: It defines fixed typed config objects thtat the CLI builds and passes into the simulator builder

# 1. DataSelectionConfig: filters which intersections you run
# 2. SimulationConfig: simulation + limits (mode, step seconds, cycle length seconds, min max green, etc.)
# 3. ControllerConfig: which controller, and if ANFIS, whether its stub vs MATLAB, and entry point

#------------------------------------------------------------- START OF PROGRAM -------------------------------------------------------------------------------#

from __future__ import annotations

# dataclass is used for simple typed config dataclasses
from dataclasses import dataclass

# automatically genereates
# __init__
# __repr__ - printing/logging
# __eq__ - for easy comparisons
# frozen = True makes this FIXED
@dataclass(frozen=True)


# essentially these are read only structs
# they cannot change values mid run

# controls which intersections we include in the experiment run (when we are still in the filtering stage)
# data loader uses this
class DataSelectionConfig:
    # if true, only keep interesections that appear in "most recent" summary list
    mostRecentOnly: bool = True
    legTypeFilter: str = "all"  # lets us restrict to specific groups: 4_leg, 3_leg, 2_leg_NS,
    # if > 0, keep only the top N intersections by volume
    # 0 means keep all
    topNByVol: int = 0


# controls queue simulation behavior and signal timing bounds
# this affects
#   1. how long you simulate for (full day vs one interval)
#   2. time resolution (step_seconds)
#   3. signal cycle structure (cycle length, yellow, all-red)
#   4. capacity model (saturation flow)
#   5. controller guardrails (min/max green)
#   6. baseline fixed split (fixed-ns ratio)
@dataclass(frozen=True)
class SimulationConfig:
    mode: str = "full_day"  # full_day or single_interval
    interval_index: int = 0  # only used when mode == single_interval
    step_seconds: float = 1.0
    cycle_length_seconds: int = 90
    yellow_seconds: int = 5
    all_red_seconds: int = 2
    saturation_flow_veh_per_sec_per_approach: float = 0.5
    minGreenSecs: int = 10
    maxGreenSecs: int = 60
    fixedNSRatio: float = 0.5
# passed into simulate intersection for timing + queue update rules
# passed into build controller so controllers can respect min/max and effective green
# used when computing green split and discharge very often


# controls which controller implementation to run
# for ANFIS, it also controls whether we are using a python stub or calling from MATLAB
@dataclass(frozen=True)
class ControllerConfig:
    controller_name: str  # baseline_fixed | baseline_proportional | anfis
    anfisMode: str = "stub"  # stub | matlab
    matlabEntry: str = ""  # MATLAB function (currently undefined)
    matlab_timeout_seconds: int = 30
