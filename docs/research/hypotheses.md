# Research questions, hypotheses and study mapping

All hypotheses are stated before any treatment data exist (this file is version-controlled; the
commit hash is the timestamp of record). Thresholds are decision criteria, not predictions of
success. "Unit" = pod-run (one pod during one crop cycle) unless stated.

| RQ | Study that tests it | Evidence level sought |
|----|--------------------|-----------------------|
| RQ1 multimodal early stress detection | Study D (uses Study A data) | confirmatory on held-out runs |
| RQ2 vision-based trait measurement | Pilot + Study B | measurement-agreement study |
| RQ3 hybrid growth prediction | Study B (+ held-out runs from A) | confirmatory on held-out runs |
| RQ4 adaptive control vs energy | Study C | confirmatory, replicated in time |
| RQ5 platform data quality | Pilot (uniformity trial) + all runs | instrument validation |

## RQ1 - multimodal early stress detection

- **H1a (primary)**: For stress onset detection at a fixed false-alarm rate of ≤ 1 false alarm per
  control pod-run, the fused (environment + image) detector's median detection lead time relative
  to the reference onset is at least 24 h earlier than the better single-modality detector.
- **H1b**: Fused-model AUROC for "stressed vs control" at 72 h after treatment onset exceeds that
  of the better single-modality model by ≥ 0.05 (paired, unit-level cluster bootstrap 95 % CI
  excluding 0).
- **H1-null to report**: fusion gives no earliness benefit; environment-only detection is
  sufficient for stresses that are themselves environmental setpoint deviations.

Critical caveat built into the design: for light and temperature treatments the environmental
sensors measure the *cause* directly, so an environment-only model can trivially "detect the
stress" at t = 0. This is detection of the treatment, not of the plant response. Study D therefore
defines two tasks: **D1 treatment-blind plant-response detection** (environment channels that
encode the manipulated variable are masked or the detector is trained to predict the growth
deviation, not the label) and **D2 root-zone stress** (EC treatment), where the air sensors carry
no direct treatment information. H1a is tested on D1 and D2 separately.

Reference onset = first day on which the pod's mean relative growth rate (from destructive-
calibrated projected leaf area) falls below the lower 95 % prediction bound of the control pods in
the same run, or first visible symptom scored by a blinded rater, whichever is earlier.

## RQ2 - computer-vision trait estimation

- **H2a (leaf area)**: Vision projected leaf area vs. destructive leaf area (flatbed scan of
  detached leaves): 95 % limits of agreement within ± 15 % of the mean over the range 20-1500 cm²;
  bias |d| < 5 %.
- **H2b (diameter)**: MAE ≤ 5 mm against caliper/ruler measurement.
- **H2c (biomass)**: Shoot fresh mass predicted from non-destructive features on held-out
  pod-runs: MAPE ≤ 15 %, and performance does not degrade by more than 5 percentage points between
  plant-grouped CV and run-grouped CV.
- **H2d (labour)**: automated measurement replaces ≥ 80 % of manual non-destructive measurements
  planned in the protocol without violating H2a-b. (Descriptive.)

R² is reported but is not an acceptance metric: it depends on the range of the sample and does
not measure agreement.

## RQ3 - hybrid physics + ML growth prediction

- **H3a**: On held-out runs, the hybrid model's RMSE for shoot dry mass at harvest, forecast from
  day 14 after transplant, is lower than both (i) the calibrated mechanistic model and (ii) the
  best pure-ML model, with paired differences whose 95 % cluster-bootstrap CI excludes 0.
- **H3b**: The hybrid model's advantage over pure ML is larger under treatment conditions not
  present in training (leave-one-treatment-out) than under in-distribution splits.
- Comparators are fixed in advance: Van Henten two-state model with re-calibrated parameters;
  logistic/Gompertz empirical curve; ridge regression, random forest, gradient boosting on the
  same information set.

## RQ4 - adaptive lighting and energy

- **H4a (primary)**: Model-predictive adaptive lighting reduces lighting electrical energy per
  gram shoot dry mass by ≥ 10 % versus a fixed 16 h / 250 µmol m⁻² s⁻¹ schedule.
- **H4b (non-inferiority)**: Shoot fresh mass at harvest under adaptive lighting is not more than
  10 % below fixed lighting (one-sided 95 % CI).
- **H4c (quality guard)**: Tipburn incidence and dry-matter content do not differ by more than
  pre-set margins (tipburn incidence difference < 10 percentage points).
- Total system energy per gram is a secondary endpoint, reported with the room-HVAC share
  estimated, not measured.

## RQ5 - platform data quality

- **H5a (uniformity)**: In uniformity trials (all pods at identical setpoints), between-pod
  variance of harvest fresh mass is ≤ 25 % of total variance (ICC_pod ≤ 0.25), and no pod differs
  from the grand mean by > 10 %.
- **H5b (environment)**: Each pod holds air temperature within ± 1.0 °C and RH within ± 7 % RH of
  setpoint for ≥ 95 % of logged minutes outside defined transition windows.
- **H5c (completeness)**: ≥ 98 % of scheduled sensor records and ≥ 97 % of scheduled images are
  present and pass QC over a full crop cycle.
- **H5d (reproducibility)**: A second builder, using only the repository, reproduces a pod whose
  commissioning measurements pass the acceptance criteria in `docs/validation/acceptance_criteria.csv`.
  (Requires an external replication; outside this team's control.)

## What cannot be answered in one experiment

Study A's 4x4 Latin square gives n = 4 pod-runs per treatment: enough for large effects
(see `experiments/analysis/power_analysis.md`), not for interactions between stressors. RQ3's
out-of-distribution claim needs runs from at least two different studies. RQ4 needs its own runs.
Paper-to-evidence mapping is in `publications/publication_strategy.md`.
