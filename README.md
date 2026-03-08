# Neuro-Fuzzy Traffic Signal Control for Urban Intersections

## Project Overview

In general cases, the control of traffic signals in urban areas follows a fixed time control pattern based on historical traffic information. Though the system is simple and effective, the traffic signals do not adapt to the changes occurring in the traffic pattern in real time.

This results in:

- unnecessary vehicle delays
- long queues due to uneven traffic demands
- inefficient utilization of green time for the traffic signals.

Adaptive Signal Control attempts to solve the above-occurring issues by adapting to the changes occurring due to traffic demands.

This project aims to find whether the performance of a traffic intersection can be improved by implementing a Neuro-Fuzzy traffic controller.

In this project, we will implement the following traffic controllers by simulating the traffic flow with actual Toronto Traffic Monitoring Count (TMC) data for various intersections:

- Baseline traffic controllers
- A Neuro-Fuzzy Adaptive Controller (ANFIS) traffic controller

---

## Problem Statement

Most traffic signal systems are pre-timed signal plans, where a set of green time is provided per phase in a signal cycle.

However, in a real-world scenario, traffic demands are highly variable because of factors such as:

- time-of-day variations
- directional demands
- daily demands
- unpredictable congestion

Pre-timing is not suitable to address these demands.

For example, in a situation where north-south traffic is high and east-west traffic is low, a pre-timed controller will still provide equal green time to both directions, thus wasting capacity.

Queues are formed even when green time is available in another direction.

Therefore, the research question is:

**Can a neuro-fuzzy controller be employed to dynamically allocate green time in response to traffic demands in order to reduce congestion and delay?**

---

## Our Approach

The project follows a three-stage approach.

---

## 1. Data Processing

In this stage, raw Toronto Traffic Monitoring Count (TMC) data is processed to derive useful traffic flow data.

From raw count data, we derive:

- 15-minute vehicle arrival rates
- directional traffic volumes (N/E/S/W)
- peak hour statistics
- intersection metadata

Data preprocessing generates three data sets:

- tmc_interval_features_all.csv
- tmc_daily_features_all.csv
- tmc_intersection_metadata_all.csv

This data represents traffic demands at every intersection in the data set.

---

## 2. Traffic Simulation

A deterministic queue-based traffic simulation is carried out to simulate traffic flow through intersections.

In this simulation, we:

- perform discrete time-step simulation in 1-second intervals
- map 15-minute count data to arrival rates
- simulate queues forming and clearing during signal phases

A signal controller regulates signal timings, allocating green time per cycle.

Key performance metrics are tracked during simulation:

- vehicle delay
- queue length
- throughput
- stop counts

This simulation architecture is implemented in the sim package and follows a clean design.

---

## 3. Controller Comparison

Three different controllers will be used in the simulation.

### Baseline Fixed Controller

Assigns a constant green time for the North-South direction every cycle.

Example:

```
Cycle = 90 seconds
NS Green = 45 seconds
EW Green = 45 seconds
```

---

### Baseline Proportional Controller

Assigns the green time for the North-South direction based on the ratios of the traffic demands.

```
green_NS = cycle * (arrival_NS / total_arrivals)
```

This is a simple heuristic commonly used in adaptive signal control.

---

### Neuro-Fuzzy Controller (ANFIS)

The proposed controller utilizes the adaptive neuro-fuzzy inference systems to calculate the optimal green time for the North-South direction based on the current traffic conditions.

Inputs:

- north-south queue length
- east-west queue length
- arrival rates
- previous allocation of the green time

The proposed ANFIS controller will have the following outputs:

- optimal_green_time_NS - will be used by the simulation to determine the signal phase.

Currently included in the repository:

- stub controller for development
- MATLAB interface hook for ANFIS

---

## Simulation Model

The intersection is considered as a two-phase signalized intersection:

**Phase 1:** North-South Green  
**Intergreen:** Yellow + All Red  
**Phase 2:** East-West Green  
**Intergreen:** Yellow + All Red  

---

## Supported Intersection Types

- 4-leg intersection
- 3-leg intersection
- 2-leg intersection

---

## Missing Approaches

Zero demand is used.

---

## Key Simulation Assumptions

- Discrete time simulation with 1 second steps
- Arrivals based on actual traffic counts
- Departures are restricted by Saturation Flow Rate
- Queues evolve deterministically

---

## Metrics Recorded

- Total Vehicle Delay
- Average Vehicle Delay
- Queue Lengths
- Throughput
- Estimated Stops

---

## Repository Structure

```
src/
 preprocessTMC.py
 runExperiments.py
 plotResults.py

 sim/
   config.py
   intersectionDataLoader.py
   controllerModels.py
   queueSimulation.py
   experimentManager.py

data/raw/
outputs/preprocessed/
outputs/experiments/
```

---

## Running the Pipeline

Run from the repository root.

### 1. Preprocess the TMC Data

```
python src/preprocessTMC.py
```

Outputs:

```
outputs/preprocessed/
```

---

### 2. Run Traffic Experiments

Run simulations across many intersections:

```
python src/runExperiments.py --most-recent-only --top-n-by-volume 50 --sim-mode full_day
```

---

### 3. Run Baseline Controllers Only

```
python src/runExperiments.py \
--controllers baseline_fixed,baseline_proportional \
--most-recent-only \
--sim-mode single_interval \
--top-n-by-volume 50
```

---

### 4. Run ANFIS Stub Controller

```
python src/runExperiments.py \
--controllers anfis \
--anfis-mode stub
```

---

### 5. Run ANFIS with MATLAB

```
python src/runExperiments.py \
--controllers anfis \
--anfis-mode matlab \
--matlab-entrypoint path/to/matlab_wrapper.py
```

---

## Experiment Outputs

Results are saved under:

```
outputs/experiments/latest/
```

Files include:

- results_per_intersection.csv
- results_aggregated.csv
- run_config.json

These datasets contain simulation metrics used for analysis and visualization.

---

## Visualization

Generate experiment plots:

```
python src/plotResults.py --results-dir outputs/experiments/latest
```

Generated charts include:

- mean delay per vehicle
- queue length comparison
- improvement vs baseline
- delay by intersection type

---

## Research Goal

Finally, the last goal of this project is to determine whether a neuro-fuzzy adaptive traffic control system can be more effective than conventional methods of determining traffic signal timings.

Performance will be evaluated on a large number of intersections by means of the following parameters:

- Average vehicle delays
- Queue lengths
- Throughput efficiencies
