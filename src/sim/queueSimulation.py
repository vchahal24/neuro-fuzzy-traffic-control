# TRAFFIC QUEUE SIMULATION #
#   1. Takes an intersection's preprocessed TMC data
#   2. Picks full day or one 15-min interval
#   3. Convert those traffic counts into arrival rates
#   4. Runs a discrete-time queue simulation
#   5. Asks and receives the green time N-S from the controller for each cycle
#   6. Moves vehicles through the intersection according to that signal plan
#   7. Accumulates delay, queue, throughput, and stops
#   8. Returns one result row for that intersection controller run

# Purpose: Two-phase traffic signal.
# One is N-S.
# Other is E-W.

# On each cycle:
#   i. the controller picks how much green time to allot to NS
#   ii. the rest of the effective green goes to EW
#   iii. yellow and all-red are dead time between phases
#   iv. arrivals keep entering queues
#   v. departures happen only when a movement has green

#------------------------------------------------------------- START OF PROGRAM -------------------------------------------------------------------------------#

from __future__ import annotations

# dataclass for metric accumulation
from dataclasses import dataclass

# dataframe access for interval rows
import pandas as pd

# simulation settings
from .simConfigModels import SimulationConfig

# controller interface
# bridge to controller code
# has step size, cycle length, yellow time, etc.
from .controllerModels import controlInp, Controller

# selected intersection data package
# has intersection ID, metadata row, daily row, all interval rows
from .intersectionDataLoader import IntersectionData

EPSILON = 1e-6

# this class stores all the cumulative metrics while the simulation is running
@dataclass
class storeMetrics:
    totalDelayVehicleinSeconds: float = 0.0 # total delay over the run in vehicles-seconds
    # for example if 10 vehicles are queued for 1 second, thats 10 vehicles-seconds
    # if 20 vehicles are queued for 3 seconds, thats 60 vehicle-seconds
    
    totalStops: float = 0.0 # an estimated stop count. it estimates how many vehicles depart from an approach with a nonzero queue.
    # aka vehicles that were stopped and then discharged.
    
    throughputVehicles: float = 0.0 # total number of vehicles that departed through the intersection during sim
    # output flow
    
    maxQVehicles: float = 0.0 # largest total queue observed at any timestop
    
    queueOverTime: float = 0.0 # accumulated queue-over-time measure
    # total queue x timestep
    
    steps: int = 0  # steps. number of simulation timesteps executed.
    
    totalArrivals: float = 0.0 # total number of vehicles that entered the system over the simulation.

    # converst raw running totals into final result values
    def convertToResult(value) -> dict[str, float]:
        # calculates average queue
        # queueOverTime is vehicles-seconds
        # dividing queueOverTime by steps gives vehicles-seconds/step and when step = 1s, then this is just vehicles
        averageQ = value.queueOverTime / value.steps if value.steps > 0 else 0.0
        
        # this computes average delay per vehicle
        # total delay divided by total vehicles that got throguh
        # if throughput is 0, then return 0 to avoid division by zero
        averageDelayPerVehicle = (
            value.totalDelayVehicleinSeconds / value.throughputVehicles if value.throughputVehicles > 0 else 0.0
        )
        
        # calculates a ratio of how many arrivals were served
        # if arrives are high and throughput is low, the ratio drops
        # if throughput equals arrivals, then ratio is 1
        
        # this answers the question: how much of the incoming demand actually got processed?
        arrivalThroughputRatio = value.throughputVehicles / value.totalArrivals if value.totalArrivals > 0 else 0.0
        
        # returns all the final metrics
        return {
            "total_delay_vehicle_seconds": value.totalDelayVehicleinSeconds,
            "avg_delay_per_vehicle_seconds": averageDelayPerVehicle,
            "max_queue_vehicles": value.maxQVehicles,
            "avg_queue_vehicles": averageQ,
            "throughput_vehicles": value.throughputVehicles,
            "stops_estimated": value.totalStops,
            "utilization_ratio": arrivalThroughputRatio,
            "total_arrivals_vehicles": value.totalArrivals,
        }


# computes the effective or usable green in one cycle
# in a two phase signal, this includes:
#   i. NS green
#   ii. yellow + all-red
#   iii. EW green
#   iv. yellow + all-red

# so not all cycle time is usable green
def effectiveGreen(simCfg: SimulationConfig) -> float:
    
    # subtract the dead transition time for both phase changes
    # using formula:
    #               effective green = cycle length - 2(yellow + all-red)
    # example:
    # if cycle = 90s
    #   yellow = 5s
    #   all-red = 2s
    # so transition phase = 7s
    # two transitions = 14s
    # then effective green = 76s
    # we have to split that between NS and EW
    
    effectiveSeconds = simCfg.cycle_length_seconds - 2 * (simCfg.yellow_seconds + simCfg.all_red_seconds)
    
    # if effectiveSeconds is too short then the sim is invalid
    # cycle >= 2 * (yellow + all_red)
    if effectiveSeconds <= 0:
        raise ValueError("ERROR. effective green must be > 0.")
    # returns the effective green as a float value
    return float(effectiveSeconds)


# converts one interval row into an arrival rate by the approach
# the input row contains 15 min totals of
# north vehicle 15 min
# east vehicle 15 min
# south vehicle 15 min
# west vehicle 15 min
# but we need vehicles/second, not vehicles/15 min
def arrRateFromIntRow(row: pd.Series) -> dict[str, float]:
    return {
        # divides each by 900 seconds (15 minutes) to get vehicles/second
        # ASSUMPTION: arrivals are uniform within the 15-min interval (a simplification)
        "n": float(row["north_vehicle_15min"]) / 900.0,
        "e": float(row["east_vehicle_15min"]) / 900.0,
        "s": float(row["south_vehicle_15min"]) / 900.0,
        "w": float(row["west_vehicle_15min"]) / 900.0,
    }


def clamp(value: float, minValue: float, maxValue: float) -> float:
    # keeps a number inside [minValue, maxValue]
    # used to avoid target ratios or green values going outside safe bounds
    return max(minValue, min(value, maxValue))


def checkInvariant(enabled: bool, condition: bool, message: str) -> None:
    # invariant checks are optional guardrails for debug/validation runs
    # when enabled, fail immediately if a required condition does not hold
    if enabled and not condition:
        raise AssertionError(f"Simulation invariant failed: {message}")


def buildTrainingRow(
    *,
    controllerName: str,
    countId: str,
    cycleIndex: int,
    qNS: float,
    qEW: float,
    arrivalNS: float,
    arrivalEW: float,
    prevGreenNS: float,
    effectiveGreenSeconds: float,
    queueScale: float,
) -> dict[str, float | int | str]:
    # builds one supervised-training row from the current cycle state
    # this is used when exporting training data for the neuro-fuzzy/octave controller
    queueTotal = qNS + qEW
    # normalize total queue into [0, 1] using the configured scaling constant
    queueTotalNorm = min(queueTotal / max(queueScale, EPSILON), 1.0)
    # phase imbalance: -1 means all EW, +1 means all NS
    imbalance = (qNS - qEW) / max(queueTotal, EPSILON)

    # baseline target starts from demand split and applies queue imbalance correction
    totalArrival = arrivalNS + arrivalEW
    baseRatio = 0.5 if totalArrival <= EPSILON else arrivalNS / totalArrival
    queueCorrection = 0.35 * imbalance
    # cap target ratio to keep supervision stable and realistic
    targetNsRatio = clamp(baseRatio + queueCorrection, 0.20, 0.80)

    return {
        "controller": controllerName,
        "count_id": countId,
        "cycle_index": cycleIndex,
        "queue_total": queueTotal,
        "queue_total_norm": queueTotalNorm,
        "imbalance": imbalance,
        "arrival_ns": arrivalNS,
        "arrival_ew": arrivalEW,
        "prev_green_ns": prevGreenNS,
        "effective_green": effectiveGreenSeconds,
        "target_ns_ratio": targetNsRatio,
    }

# chooses whether to simulate the full day or a specific 15-minute interval
def fullDayOr15Min(intervalRows: pd.DataFrame, simConfig: SimulationConfig) -> pd.DataFrame:
    # sorts the interval rows by time and resets the index
    # chronological order
    # first sorts the interval rows by time and resets the index
    sortedRowsByTime = intervalRows.sort_values("start_time").reset_index(drop=True)
    
    # checks whether the sim is configured to run just one interval
    if simConfig.mode == "single_interval":
        # checks valid range for index
        index = max(0, min(simConfig.intervalIndex, len(sortedRowsByTime) - 1))
        # returns a DataFrame containing that one interval row [[ ]]
        return sortedRowsByTime.iloc[[index]].copy()
    # if its not a single interval, return the full day, so the full day is simulated
    return sortedRowsByTime

# ---------------- CORE FUNCTION -------------------------

# simulates one intersection using one controller and one simulation configuration
# returns a dictionary that becomes one output row in your results table

def simIntersection(
    data: IntersectionData,
    controller: Controller,
    config: SimulationConfig,
) -> tuple[dict[str, float | str], list[dict[str, float | int | str]]]:
    # gets either all interval rows or one interval row depending on full day or 15 min
    intervalRows = fullDayOr15Min(data.interval_rows, config)
    
    # reads through the simulation timestep
    # this is how much simulated time passes each inner loop iteration
    # typically 1s
    stepSeconds = float(config.step_seconds)
    
    # error check because zero or negative timestep breaks logic
    if stepSeconds <= 0:
        raise ValueError("ERROR. step_seconds must be > 0.")
    checkInvariants = bool(config.enableInvariantChecks)
    invariantTolerance = float(config.invariantTolerance)

    # computes the usable green time per cycle
    effectiveGreenSeconds = effectiveGreen(config)
    
    # max service rate per approach
    # example: if dischargeCap = 0.5 veh/s
    # and stepSeconds = 1s
    # then at most 0.5 vehicles can depart that approach per second of green
    dischargeCap = float(config.saturation_flow_veh_per_sec_per_approach)

    # starts every approach queue at zero
    # this means that when the simulation begins, there should be no preloaded congestion
    # ASSUMPTION
    qByApproach = {"n": 0.0, "e": 0.0, "s": 0.0, "w": 0.0}
    initialQueueVehicles = sum(qByApproach.values())
    
    # initializes the previous NS green to half the usable green
    # since we dont have data before the very start, we use a neutral 50/50 split as the controller input
    previousGreenNs = effectiveGreenSeconds * 0.5
    
    # creates a blank metrics accumulator
    metricsStore = storeMetrics()
    cycleTrainingRows: list[dict[str, float | int | str]] = []

    # counters for how many intervals and cycles were simulated
    intervalCounter = 0
    cycleCounter = 0

    # outer loop
    # go interval by interval
    # each interval row represents one 15 minute traffic demand block
    for _, intervalRow in intervalRows.iterrows():
        # increment interval counter
        intervalCounter += 1
        # converts the intervals 15 min approach into per second arrival rates using the helper
        arrivalRateByApproach = arrRateFromIntRow(intervalRow)
        # each interval is 15 mins so 900.0s
        intervalLength = 900.0
        # start the local time counter at 0.0 to keep track of the progress
        simClock = 0.0

        # as long as the 15 min interval is not finished, keep running cycles
        while simClock < intervalLength:
            # increment the cycle
            cycleCounter += 1
            
            # agregates north with south, and east with west to divide into two phases
            queueNs = qByApproach["n"] + qByApproach["s"]
            queueEw = qByApproach["e"] + qByApproach["w"]
            
            # same with arrivals
            arrivalNs = arrivalRateByApproach["n"] + arrivalRateByApproach["s"]
            arrivalEw = arrivalRateByApproach["e"] + arrivalRateByApproach["w"]

            #  builds the input object that is sent to the controller
            # this package sends:
            # current NS queue, current EQ queue, current NS demand, current EW demand, previous NS green, total usable green
            controlInput = controlInp(
                qNS=queueNs,
                qEW=queueEw,
                arrivalNS=arrivalNs,
                arrivalEW=arrivalEw,
                prevGreenNS=previousGreenNs,
                effecGreenSecs=effectiveGreenSeconds,
            )
            
            # asks the controller to decide how much north-south should get of the effective green
            # ------- KEY DECISION ----------
            greenNs = controller.decideGreenNS(controlInput)
            
            # set caps for the NS phase so that its not unreasonable short or long
            greenNs = max(config.minGreenSecs, min(config.maxGreenSecs, greenNs))
            # cap it again but for 0 and total effective green
            greenNs = max(0.0, min(effectiveGreenSeconds, float(greenNs)))
            
            # whatever is leftover goes to east-west phase
            greenEw = effectiveGreenSeconds - greenNs
            checkInvariant(
                checkInvariants,
                abs((greenNs + greenEw) - effectiveGreenSeconds) <= invariantTolerance,
                f"green split mismatch (ns={greenNs}, ew={greenEw}, effective={effectiveGreenSeconds})",
            )
            
            # store the current greenNs in previousGreenNS for next iteration
            previousGreenNs = greenNs

            if config.exportTrainingData:
                # optional dataset export: capture one training row per cycle
                # this row stores normalized state + a target NS ratio label
                cycleTrainingRows.append(
                    buildTrainingRow(
                        controllerName=controller.name,
                        countId=data.count_id,
                        cycleIndex=cycleCounter,
                        qNS=queueNs,
                        qEW=queueEw,
                        arrivalNS=arrivalNs,
                        arrivalEW=arrivalEw,
                        prevGreenNS=controlInput.prevGreenNS,
                        effectiveGreenSeconds=effectiveGreenSeconds,
                        queueScale=float(config.trainingQueueScale),
                    )
                )

            # begins the time in this cycle now
            # inner loop
            # step by step through one signal cycle
            cycleClock = 0.0
            
            # continue through the cycle one timestep until the cycle ends or the 15 min interval ends
            while cycleClock < config.cycle_length_seconds and simClock < intervalLength:
                queueBeforeStep = qByApproach.copy()
                
                # NS green ends after the green NS given by the controller ends
                nsGreenEnd = greenNs
                
                # transition phase that includes the yellow + all-red after NS green
                nsTransition = greenNs + config.yellow_seconds + config.all_red_seconds
                
                # after the transition, EW green runs for greenEW seconds
                ewGreenEnd = nsTransition + greenEw
                
                # check if we are still in NsGreen or EwGreen
                isNsGreenPhase = cycleClock < nsGreenEnd
                isEwGreenPhase = nsTransition <= cycleClock < ewGreenEnd

                # checks which phase is currently being served
                currentlyServed = "none" # during yellow/all-red
                if isNsGreenPhase: # if NS has green
                    currentlyServed = "ns"
                elif isEwGreenPhase: # if EW has green
                    currentlyServed = "ew"

                # converts rate to actual arrivals in this step
                # example:
                # if arrival rate = 0.2 veh/s, and timestep = 1s, then arrivals this step = 0.2 vehicles
                arrivalsStep = {k: arrivalRateByApproach[k] * stepSeconds for k in ("n", "e", "s", "w")}
                
                # for each approach, add arriving vehicles to its queue
                # add them to total arrivals as well to store
                for approach, amount in arrivalsStep.items():
                    qByApproach[approach] += amount
                    metricsStore.totalArrivals += amount

                # we need to compute the departures but start at 0
                departures = {"n": 0.0, "e": 0.0, "s": 0.0, "w": 0.0}
                
                # if we are currently serving ns
                if currentlyServed == "ns":
                    # north and south can discharge
                    # each is limited by: queue available and dischargeCap
                    # so if queue is smaller than capacity, only the queue leave
                    # if queue is larger than capacity, then only capacity leaves
                    departures["n"] = min(qByApproach["n"], dischargeCap * stepSeconds)
                    departures["s"] = min(qByApproach["s"], dischargeCap * stepSeconds)
                elif currentlyServed == "ew":
                    # same thing for EW
                    departures["e"] = min(qByApproach["e"], dischargeCap * stepSeconds)
                    departures["w"] = min(qByApproach["w"], dischargeCap * stepSeconds)

                # saves the queues before departures
                copyOfQueue = qByApproach.copy()
                
                # for each approach,
                #   i. subtract departures from queue
                #   ii. ensure queue does not become negative
                #   iii. add departures to throughput
                # THROUGHPUT IS THE TOTAL DISCHARGED VEHICLES
                for approach in ("n", "e", "s", "w"):
                    qByApproach[approach] -= departures[approach]
                    qByApproach[approach] = max(0.0, qByApproach[approach])
                    metricsStore.throughputVehicles += departures[approach]
                    checkInvariant(
                        checkInvariants,
                        qByApproach[approach] >= -invariantTolerance,
                        f"negative queue on {approach}: {qByApproach[approach]}",
                    )

                if checkInvariants:
                    for approach in ("n", "e", "s", "w"):
                        expectedQueue = queueBeforeStep[approach] + arrivalsStep[approach] - departures[approach]
                        checkInvariant(
                            checkInvariants,
                            abs(qByApproach[approach] - expectedQueue) <= invariantTolerance,
                            (
                                f"queue conservation mismatch on {approach}: "
                                f"expected={expectedQueue}, got={qByApproach[approach]}"
                            ),
                        )
                        checkInvariant(
                            checkInvariants,
                            departures[approach] <= copyOfQueue[approach] + invariantTolerance,
                            (
                                f"departures exceed queue on {approach}: "
                                f"depart={departures[approach]}, queue={copyOfQueue[approach]}"
                            ),
                        )

                    stepCapacity = dischargeCap * stepSeconds
                    for approach in ("n", "e", "s", "w"):
                        checkInvariant(
                            checkInvariants,
                            departures[approach] <= stepCapacity + invariantTolerance,
                            (
                                f"departures exceed saturation on {approach}: "
                                f"depart={departures[approach]}, cap={stepCapacity}"
                            ),
                        )
                    if currentlyServed == "ns":
                        checkInvariant(
                            checkInvariants,
                            departures["e"] <= invariantTolerance and departures["w"] <= invariantTolerance,
                            "EW departures occurred during NS service phase",
                        )
                    elif currentlyServed == "ew":
                        checkInvariant(
                            checkInvariants,
                            departures["n"] <= invariantTolerance and departures["s"] <= invariantTolerance,
                            "NS departures occurred during EW service phase",
                        )
                    else:
                        checkInvariant(
                            checkInvariants,
                            all(departures[a] <= invariantTolerance for a in ("n", "e", "s", "w")),
                            "departures occurred during transition/non-service phase",
                        )

                # ASSUMPTION: assumes vehicles leaving from a nonzero queue had to stop.
                # if NS
                if currentlyServed == "ns":
                    # if North had a queue before departure, then the departing north vehicles are counted as stopped vehicles
                    if copyOfQueue["n"] > 0:
                        metricsStore.totalStops += departures["n"]
                    # same for south
                    if copyOfQueue["s"] > 0:
                        metricsStore.totalStops += departures["s"]
                        
                # same for EW
                elif currentlyServed == "ew":
                    if copyOfQueue["e"] > 0:
                        metricsStore.totalStops += departures["e"]
                    if copyOfQueue["w"] > 0:
                        metricsStore.totalStops += departures["w"]

                # update total queued vehicles across all approaches in this timestep
                totalQueue = qByApproach["n"] + qByApproach["e"] + qByApproach["s"] + qByApproach["w"]
                
                # add queue x time to total delay
                # delay approximation
                # if total queue = 8 vehicles, step = 1 second.
                #   then 8 vehicle-seconds of delay are added.
                metricsStore.totalDelayVehicleinSeconds += totalQueue * stepSeconds
                
                # also store the same value as average queue computation later
                metricsStore.queueOverTime += totalQueue * stepSeconds
                
                # update the max queue ever seen in any approach
                metricsStore.maxQVehicles = max(metricsStore.maxQVehicles, totalQueue)
                
                # count one more timestep
                metricsStore.steps += 1
                checkInvariant(
                    checkInvariants,
                    metricsStore.throughputVehicles <= metricsStore.totalArrivals + initialQueueVehicles + invariantTolerance,
                    (
                        f"throughput exceeds supply: throughput={metricsStore.throughputVehicles}, "
                        f"arrivals={metricsStore.totalArrivals}, initial_queue={initialQueueVehicles}"
                    ),
                )

                # update and advance time inside the current cycle and inside the current 15 min interval
                cycleClock += stepSeconds
                simClock += stepSeconds
                
                # then loop repeats

    # building the final output row
    outputRow = {
        "count_id": data.count_id,
        "controller": controller.name,
        "sim_mode": config.mode,
        "intervals_simulated": intervalCounter,
        "cycles_simulated": cycleCounter,
    }
    # adds the computed performance metrics
    # now we have indentifiers from above and results here
    outputRow.update(metricsStore.convertToResult())
    
    return outputRow, cycleTrainingRows
