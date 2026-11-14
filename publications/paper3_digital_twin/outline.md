# Paper 3 (working title): Experimental validation of a hybrid physics-machine-learning digital twin for growth forecasting and energy-aware lighting control in a replicated lettuce platform

Status: outline; requires Study B (forecasting) and Study C (control).

1. **Introduction** - lettuce twins and hybrid models are mostly validated in simulation; physical closed-loop
   evidence with metered energy is scarce.
2. **Models** - Van Henten two-state model and the declared extensions (temperature penalty, nutrient factor,
   transpiration); lumped pod climate and energy model; calibration procedure and identifiability
   (c_eps and c_gr_max are partly confounded - shown in the simulated parameter-recovery test);
   hybrid residual model; comparators.
3. **Validation design** - VAL-DT-01..03 thresholds fixed in advance; leave-one-run-out; leave-one-treatment-out
   for out-of-distribution behaviour (H3b); model-predictive lighting controller, constraints and the safety
   envelope; Study C crossover design; endpoints (lighting kWh per g dry mass; non-inferior fresh mass).
4. **Results** [DATA] - parameter estimates with unit-bootstrap intervals; forecast errors by horizon and
   model; step-response and energy-model errors; Study C: energy per unit dry mass, yield, quality guard
   variables, total energy including heater, with pod-run level inference.
5. **Discussion** - when the hybrid helps; PWM dimming means savings must come from plant light-use
   efficiency; limits of a pod-scale result for production systems; what the twin must not be trusted for.

The twin's current predictions (e.g. the Pareto front in `publications/figures/`) are hypotheses for Study C.
