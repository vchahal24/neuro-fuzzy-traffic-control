# CONTROLLER LAYER OF THE PROJECT

# Purpose: Defines
#               1. what information is sent to the controller
#               2. what interface the controller follows
#               3. the actual implementations are built here
#                   i. fixed baseline
#                   ii. proportional baseline
#                   iii. ANFIS stub / MATLAB ANFIS
#               4. a function that picks the right controller based on config

# Computes:
#   i. current NS queue
#   ii. current EW queue
#   iii. NS arrivals
#   iv. EW arrivals
#   v. previous NS green
#   vi. effective green available this cycle

# This is passed to a controller

# Controller returns
# green_ns_seconds

# The simulator uses that to split the cycle
#   i. NS gets green_ns_seconds
#   ii. EW gets the rest of the effective green

#------------------------------------------------------------- START OF PROGRAM -------------------------------------------------------------------------------#

from __future__ import annotations

# imports pythons threading tools
# to ensure MATLAB engine is only started once and only once even if multiple calls
# aka a lock
import threading

# imports dataclass for data containers
from dataclasses import dataclass

# path parsing for matlab entrypoints
from pathlib import Path

# importing protocol, for defining types
from typing import Protocol

# imports dataclasses from simConfigModels
from .simConfigModels import ControllerConfig, SimulationConfig

# tries to import MATLAB
# if it doesnt import MATLAB engine, then project still runs baseline_fixed, baseline_proportional, anfis (in stub mode)
try:
    import matlab.engine as _matlab_engine  # type: ignore[import-not-found]
except Exception:
    _matlab_engine = None


# defines the exact info the controller receives at runtime
@dataclass(frozen=True)
class controlInp:
    qNS: float # current queue size on the NS phase
    qEW: float # current queue size on the EW phase
    arrivalNS: float # current NS arrival demand
    arrivalEW: float # current EW arrival demand
    prevGreenNS: float # how much green was on the last NS cycle
    effecGreenSecs: float # total usable green this cycle after subtracting yellow/all red


# defines the expected interface for any controller
# valid controller has: a name, a method for deciding green NS
class Controller(Protocol):
    name: str

    def decideGreenNS(self, signal_input: controlInp) -> float:
        ...

# restricts the number to a valid range
# so the controller doesn't propose unrealistic values
# aka the green cant be too long or too short, so we set minimum and max values
def minMaxCaps(proposedVal: float, min: float, max: float) -> float:
    return max(min, min(proposedVal, max))

# ---------------------- CONTROLLERS ----------------------------- #

# the simplest controller
class baselineFixed:
    def __init__(controller, simConfig: SimulationConfig) -> None: # takes simulation config because it needs min green, max green, NS ratio
        controller.nameOfController = "baseline_fixed" # controller name
        controller.minGreen = float(simConfig.minGreenSecs) # stores as floats for min and max green bounds
        controller.maxGreen = float(simConfig.maxGreenSecs)
        controller.fixedRatio = simConfig.fixedNSRatio # stores the fixed ns green ratio
        # for example, if ratio is 0.5, then NS gets 50% of the effective green
        # ratio is a value from 0.0 to 1.0 representing 0% to 100%

    # DECISION METHOD
    def decisionGreenNS(controller, input: controlInp) -> float:
        desiredGreen = controller.fixedRatio * input.effecGreenSecs # computes the desired NS green using a fixed proportion of the effective green
        # for example, if effective green is 76 s, and ratio is 0.5, then desired green is 38 s.
        
        # ensures the result is within the legal range and this is then returned
        return minMaxCaps(desiredGreen, controller.minGreen, controller.maxGreen)

# a bit more advanced than baseline fixed
# defines a controller that splits based on observed arrival demand
class baselineProportional:
    def __init__(controller, simConfig: SimulationConfig) -> None:
        controller.name = "baseline_proportional" # controller name
        controller.minGreen = float(simConfig.minGreenSecs) # stores green bounds
        controller.maxGreen = float(simConfig.maxGreenSecs)

    def decisionGreenNS(controller, input: controlInp) -> float:
        totalArrival = input.arrivalNS + input.arrivalEW # this time it adds total arrival demand across both phases, this is the denominator for the ratio
        if totalArrival <= 0: # if no arrivals, then default to 0.5 split
            nsRatio = 0.5
        else: # else, compute the fraction of total arrivals on north-south
            # for example, if NS arrival is 20, EW arrival is 30, then NS ratio is 20/50 so 0.4
            nsRatio = input.arrivalNS / totalArrival
        # so it allocates the same fraction for effective green time
        # aka if NS is 0.4 ratio, then 40% of the effective green is given
        desiredGreen = nsRatio * input.effecGreenSecs
        
        # check bounds and return
        return minMaxCaps(desiredGreen, controller.minGreen, controller.maxGreen)

# advanced controller
# utilizing ANFIS
# two modes: stub and MATLAB

# the stub works by using python heuristics rather than an actual matlab call

class anfisController:
    def __init__(controller, simConfig: SimulationConfig, contConfig: ControllerConfig) -> None:
        controller.name = "anfis" # name
        controller.minGreen = float(simConfig.minGreenSecs) # min max green
        controller.maxGreen = float(simConfig.maxGreenSecs)
        controller.mode = contConfig.anfisMode # whether its stub or matlab
        controller.matlabEntrypoint = contConfig.matlabEntry # stores the matlab function name or path
        controller.timeoutSeconds = contConfig.matlab_timeout_seconds # stores the timeout limit for matlab calls
        controller.matlabLock = threading.Lock() # creates a lockwhen initializing matlab engine, so only one thread can initialize at once
        controller.matlabEngineObj = None # empty right now, will hold a MATLAB engine object later
        controller.matlabFuncName = "" # starts empty until the matlab entrypoint is parsed

    # placeholder until the full neuro fuzzy controller is implemented
    # it behaves adaptively, but its a placeholder heuristic
    def decisionStub(controller, input: controlInp) -> float:
        
        # computes a NS score weighing at 65% for arrivals, queues at 35%
        nsScore = 0.65 * input.arrivalNS + 0.35 * input.qNS
        ewScore = 0.65 * input.arrivalEW + 0.35 * input.qEW
        
        # adds both scores
        totalScore = nsScore + ewScore
        
        # if both scores are zero, split evenly 50/50
        nsRatio = 0.5 if totalScore <= 0 else nsScore / totalScore
        return nsRatio * input.effecGreenSecs

    # calls user-provided MATLAB function via matlab engine
    def decisionMATLAB(controller, input: controlInp) -> float:
        if not controller.matlabEntrypoint: # if the user selected matlab mode did not provide a matlab function , error
            raise RuntimeError(
                "To run this, we need a --matlab-entrypoint. "
                "If there is no MATLAB entrypoint, run --anfis-mode stub."
            )
            # if issues importing, also error
        if _matlab_engine is None:
            raise RuntimeError(
                "ANFIS MATLAB mode requires the use of MATLAB Engine "
                "Failed to import matlab.engine."
            )

        # gets the MATLAB engine session or creates if needed
        matlabEng = controller.matlabEngineCache()
        
        # starts a function call in MATLAB using feval
        funcCall = matlabEng.feval(
            controller.matlabFuncName, # calls the MATLAB function name
            float(input.qNS), # passes six numeric inputs into MATLAB
            float(input.qEW),
            float(input.arrivalNS),
            float(input.arrivalEW),
            float(input.prevGreenNS),
            float(input.effecGreenSecs),
            nargout=1, # tells MATLAB to output one value
            background=True, # Runs the MATLAB function in the background and returns a future object
        )
        # waits for MATLAB result
        # then converts the returned value to a Python float
        return float(funcCall.result(timeout=float(controller.timeoutSeconds))) # returns a single float green time

    # cache for MATLAB engine session
    def matlabEngineCache(controller):
        if controller.matlabEngineObj is not None: # if the MATLAB engine already exists, just use it without restarting
            return controller.matlabEngineObj

        with controller.matlabLock: # acquires the lock so only one thread runs at a time
            if controller.matlabEngineObj is not None:
                return controller.matlabEngineObj

            # actually start the MATLAB engine session, done once
            startEngine = _matlab_engine.start_matlab()
            
            # converts entrypoint to a string
            entryPoint = str(controller.matlabEntrypoint)
            
            # wraps it in a Path object
            entryPath = Path(entryPoint)
            
            # checks whether it is a .m file or a path containing backslashes
            # examples:
            #   1. anfis_controller.m
            #   2. matlab/anfis_controller.m
            #   3. controllers\\anfis_controller.m
            
            if entryPath.suffix.lower() == ".m" or any(sep in entryPoint for sep in ("\\", "/")):
                if str(entryPath.parent) not in ("", "."): # if it has a parent directory add that folder to the search path
                    startEngine.addpath(str(entryPath.parent), nargout=0)
                controller.matlabFuncName = entryPath.stem # stores only the base function name and removes the extension
            else:
                controller.matlabFuncName = entryPoint # if its already a function name, then just use it

            controller.matlabEngineObj = startEngine # caching it to reuse on future calls
            return controller.matlabEngineObj

    # the simulator calls this for anfiscontroller
    def decisionGreenNS(controller, input: controlInp) -> float:
        if controller.mode == "matlab": # if in matlab mode, call the matlab implementation
            rawGreen = controller.decisionMATLAB(input)
        else: # otherwise use the python stub heuristic (backup) -- fallback
            rawGreen = controller.decisionStub(input)
        return minMaxCaps(rawGreen, controller.minGreen, controller.maxGreen) # checks min max bounds and returns

# builds the correct controller object
# returns it
# based on controller configurations
def returnController(simConfig: SimulationConfig, controlConfig: ControllerConfig) -> Controller:
    if controlConfig.controller_name == "baseline_fixed": # if asking for baseline fixed, then use that
        return baselineFixed(simConfig)
    if controlConfig.controller_name == "baseline_proportional": # if asking for baseline proportional, use that
        return baselineProportional(simConfig)
    if controlConfig.controller_name == "anfis": # if asking for anfis use that
        # this needs both configs to determine whether matlab or stub
        return anfisController(simConfig, controlConfig)
    # error - crash if it doesn't recognize the controller type
    raise ValueError(f"ERROR. Controller not recognized: {controlConfig.controller_name}")
