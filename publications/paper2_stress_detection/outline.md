# Paper 2 (working title): Does fusing image and environmental-response signals give earlier detection of abiotic stress in hydroponic lettuce? A replicated, leakage-controlled test

Status: outline; all results sections require Study A (4 runs). Analysis code exists and has been rehearsed on
simulated data (`simulation/reports/virtual_study_report.md`); that rehearsal is not a result.

1. **Introduction** - visible-symptom detectors are late; "multimodal" in the literature usually means image
   modalities; evaluation rarely respects experimental units; sensors that measure the manipulated variable
   trivially "detect" the treatment.
2. **Methods** - platform (cite Paper 1); Study A design (4 x 4 Latin square, onset day 10, treatments and
   rationale); reference onset definition; feature sets ENV(response) / IMG / ENV+IMG, with the setpoint
   channels reported separately; models (logistic baseline, RF, GBM, SVM; CNN/temporal models only if they
   beat baselines under the same splits); leave-one-run-out with nested tuning; alarm rule (zero training
   false alarms, 2-day persistence); primary metric lead time, paired Wilcoxon over 12 stressed pod-runs;
   secondary AUROC/AUPRC/Brier with pod-run cluster bootstrap.
3. **Results** [DATA] - treatment effects on harvest traits (context); detection timing per information set
   and per stressor; false alarms out of sample; calibration; ablations (which channels matter);
   sensitivity to the reference-onset definition.
4. **Discussion** - where fusion helps or does not; cost of the response channels (load cell, CO2);
   limits: n = 16 units, one cultivar, stress applied as a step, heat treatment not blindable.
5. **Data and code availability**.

Pre-specified in `docs/research/hypotheses.md` (H1a, H1b) and the SAP section 5 including the dated amendment.
