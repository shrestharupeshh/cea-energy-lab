# Statistical analysis plan (SAP) - all studies

Version 1.0, written before any treatment data exist. Changes after data collection begins go in
a dated amendment section at the end, with reasons; the original text is never edited.

## 0. Principles

1. The **experimental unit is the pod-run** for every treatment applied to a pod's air, light or
   solution. Plants are subsamples. Inference on treatments uses pod-run means or mixed models
   with pod-run as a random effect; plant-level p-values that ignore this are not reported.
2. Runs are blocks in time. Treatments are re-randomized to pods each run under the design
   constraints (Latin square or balanced crossover). Randomization uses
   `plantpulse.stats.design` with a recorded seed.
3. Primary endpoints, models and decision thresholds are fixed here. Everything else is labelled
   exploratory.
4. Analysts work on pod/position codes; the allocation table is joined by script at the last step.
5. No results are simulated into the record. Simulation is used only for power analysis and
   software verification and is stored under `simulation/`.

## 1. Pilot: uniformity trials (U1, U2)

- All four pods at control setpoints for two full crop cycles.
- Endpoints: shoot fresh mass, dry mass, leaf area at harvest; environmental statistics.
- Model: `y_ijk = mu + run_i + pod_j + (run x pod)_ij + e_ijk` (random effects). Report variance
  components, ICC, and each pod's BLUP with 95 % interval.
- Acceptance: H5a-c. If a pod deviates > 10 %, find the cause, fix, repeat a trial.
- Output used for planning: between-unit CV (`cv_unit`) and within-unit plant CV (`cv_plant`),
  which replace the assumed values in the power analysis.

## 2. Study A - stress treatments (4 x 4 Latin square)

- Factors: treatment (Control, Low-light, Heat, Low-EC); rows = runs 1-4; columns = pods 1-4.
- Primary endpoint: shoot dry mass per plant at harvest (pod-run mean, log scale).
- Model: `log(y) ~ treatment + (1|run) + (1|pod)` on pod-run means (16 observations; residual
  df = 6), fitted by REML; plant-level model with an additional `(1|run:pod)` term as sensitivity.
- Contrasts: each stress vs control, Dunnett-adjusted, two-sided alpha = 0.05.
- Secondary: fresh mass, leaf area, dry-matter content, tipburn incidence (binomial GLMM),
  water use, relative growth rate from image series (linear mixed model with random slopes).
- Missing pod-run (equipment failure): analyse as incomplete Latin square by REML; if two or more
  cells are lost, add a fifth run.

## 3. Study B - trait measurement and growth prediction

- Measurement agreement (RQ2): Bland-Altman bias and 95 % limits of agreement (with repeated-
  measures correction for multiple plants per pod-run), Lin's concordance correlation, MAE, RMSE,
  MAPE; proportional bias tested by regressing differences on means. R² reported, not used for
  acceptance.
- Prediction (RQ3): forecasts issued at days 7, 14, 21 for harvest dry mass. Evaluation on
  held-out runs only (leave-one-run-out). Paired comparison of absolute errors between models by
  cluster bootstrap over pod-runs (10 000 resamples); Holm correction over the two primary
  comparisons (hybrid vs mechanistic, hybrid vs best ML).
- The ML "best model" is chosen by nested CV inside the training runs, never on the test run.

## 4. Study C - adaptive vs fixed lighting

- Design: 2 treatments x 2 pods per run, ≥ 4 runs, balanced so every pod receives each treatment
  equally often (AB/BA crossover on pods across runs).
- Primary endpoint: lighting energy per gram shoot dry mass (kWh g⁻¹) per pod-run, log scale.
  Model: `log(E/DM) ~ treatment + (1|run) + (1|pod)`. Superiority test, one-sided alpha = 0.05,
  target ratio ≤ 0.90.
- Co-primary guard: non-inferiority of shoot fresh mass, margin −10 % (ratio > 0.90, one-sided
  95 % CI). Claim "improved energy productivity" only if both hold.
- Secondary: total metered energy per gram, tipburn, dry-matter content, water use.

## 5. Study D - multimodal detection

- Data: Study A runs. Models trained on 3 runs, tested on the 4th, rotated (leave-one-run-out);
  all hyper-parameter selection nested within training runs, grouped by pod-run.
- Task D1 (treatment-blind response detection) and D2 (root-zone stress) defined in
  `hypotheses.md`. Information sets: ENV, IMG, ENV+IMG; identical model families and tuning budget
  for each set.
- Primary metric: detection lead time with the alarm threshold set to give zero false alarms on the
  negative unit-days (controls, and treated units before onset) of the training runs; out-of-sample
  false alarms in the held-out run are reported alongside,
  compared by paired Wilcoxon signed-rank test over stressed pod-runs (n = 12) with Hodges-Lehmann
  estimate and bootstrap CI. Secondary: AUROC/AUPRC at 24/48/72/120 h after onset with pod-run
  cluster bootstrap CIs; calibration (Brier score, reliability curve).
- With 12 stressed and 4 control pod-runs, this is a small-sample study: results are reported
  with intervals and described as preliminary unless replicated in further runs.

## 6. Exclusion criteria (all studies, decided blind to treatment where possible)

- Plant: failed establishment by day 3 after transplant (replaced from spare seedlings, logged);
  mechanical damage by operator; pathogen/pest confirmed by inspection (pod-run is flagged and
  analysed both ways).
- Pod-run: environmental excursion beyond pre-set limits for > 6 cumulative hours outside
  intended treatment (air T > ± 3 °C, PPFD > ± 20 %, pump/aeration failure > 4 h); data loss > 10 %
  of scheduled records. Excluded pod-runs are reported with reasons; never silently dropped.
- Observation: QC flag set by `plantpulse.data.validation` (sensor fault, calibration expired,
  image blur/occlusion). Flagged observations stay in the raw data.

## 7. Multiplicity, reporting

- One primary endpoint per study; secondary endpoints Holm-adjusted within families or reported
  as exploratory with unadjusted intervals.
- Report effect sizes with 95 % CIs, variance components, all exclusions, deviations from the SAP,
  and environment summaries per pod-run following Poorter et al. (2012) reporting guidance.

## 8. Sample size rationale

See `experiments/analysis/power_analysis.md` (generated by `scripts/run_power_analysis.py`). The
planning values (`cv_unit` = 8 %, `cv_plant` = 15 %) are assumptions until the uniformity trials
replace them.

## Amendments

- 2026-11 (before any plant data): the Study D false-alarm rule was changed from "≤ 1 false alarm per
  control pod-run" to "zero false alarms on training-run negatives". The rehearsal on simulated data
  (`simulation/reports/virtual_study_report.md`) showed that the original budget selects a threshold at
  which every control unit alarms, which makes lead time meaningless. No real data existed at the time.
