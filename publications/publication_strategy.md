# Publication strategy

Publication is treated as a deliverable with entry criteria. Technical sophistication is not a
contribution; each paper needs a claim, independent evidence for it, and a reviewer-proof
account of replication. Nothing below is promised: each paper has a go/no-go gate.

## Which evidence supports which claim

| Paper | Central claim | Evidence required (independent of the other papers) | Earliest possible |
|-------|---------------|-----------------------------------------------------|-------------------|
| **1. Platform + dataset** | A documented low-cost, replicated-unit platform produces longitudinal multimodal lettuce data of stated quality; the dataset is released | All validation tests A-F passed; uniformity trials U1-U2 (8 pod-runs); Study B measurement-agreement data; dataset from U1-U2 + B (+ A if complete) | after U2 + B1-B2 (≈ 6 runs) |
| **2. Multimodal early stress detection** | Fusion of image and environment-response channels detects stress earlier than either alone, under leave-one-run-out evaluation | Study A (4 runs, 16 pod-runs) analysed per SAP section 5; ideally A2 or a repeat square as external test | after A1-A4 |
| **3. Hybrid twin validation** | A hybrid crop/energy model forecasts held-out runs better than its components, and model-predictive lighting lowers metered energy per unit dry mass | VAL-DT-01..03; Study B (calibration + forecast); Study C (≥ 4 runs) for the control claim | after C1-C4 |

Dependencies that must be stated in the manuscripts: Paper 2 uses the Paper 1 platform (cite, do
not re-validate); Paper 3's forecasting evidence may reuse Study A harvests as an
out-of-distribution test, but the *control* claim rests on Study C alone. The same pod-run must
not be counted as independent confirmation in two papers.

## Go / no-go gates

- Paper 1 no-go if ICC_pod > 0.25 after one round of fixes, or if vision-vs-destructive limits of
  agreement exceed ± 25 %: then it becomes a hardware/methods note without dataset claims.
- Paper 2 is written whatever the outcome (pre-specified analysis); a null result ("environment
  response channels add nothing to images", or the reverse) is reported as such. With n = 12
  stressed units it is framed as preliminary unless replicated.
- Paper 3's control section is dropped if VAL-DT-01 fails; the forecasting comparison can still
  be reported.

## What reviewers will attack (and the prepared answer)

| Likely criticism | Answer built into the design |
|------------------|------------------------------|
| "Plants in one chamber are pseudoreplicates" | pod-run is the unit; Latin square over runs; unit-level models |
| "Chambers differ" | uniformity trials with variance components; re-randomisation each run |
| "Random train/test splits" | only grouped splits exist in the code; leave-one-run-out primary |
| "Environment sensors just see the treatment" | treatment-blind task with response-only channels; setpoint channels reported separately |
| "Correlation is not accuracy" | Bland-Altman, CCC, proportional bias; reference repeatability measured |
| "Low-cost sensors" | transfer calibration to traceable references; uncertainty budget; drift control charts |
| "Simulation-only twin" | physical validation tests with pre-set thresholds; simulated results never reported as findings |
| "One cultivar, one site" | stated limitation; open design invites replication (H5d) |
| "Synthetic-image results" | used only for software tests; not in any results section |

## Journal fit (to be confirmed against current aims/scope pages before submission)

| Journal | Fit | Use for |
|---------|-----|---------|
| Computers and Electronics in Agriculture | systems + sensing + ML with agricultural validation; expects experimental evidence | Paper 2 or 3 |
| Biosystems Engineering | engineering analysis of biological systems, models with validation | Paper 3 |
| Plant Phenomics | phenotyping methods and datasets; open access | Paper 1 (methods + data) or Paper 2 |
| Smart Agricultural Technology | applied digital agriculture, open access, broader acceptance | fallback for any |
| Sensors (MDPI) | instrument papers; fast | fallback for the platform description only |
| Frontiers in Plant Science (Technical Advances in Plant Science) | methods with biological validation | Paper 1 or 2 |
| Agricultural Systems | farm/system-level analysis | poor fit at pod scale; not targeted |
| HardwareX | open hardware with full build files | strong option for the hardware half of Paper 1 |
| Scientific Data / Data in Brief | data descriptors | dataset half of Paper 1 if split |

Recommended first choices: Paper 1 → Plant Phenomics (or HardwareX + a data descriptor);
Paper 2 → Computers and Electronics in Agriculture; Paper 3 → Biosystems Engineering.
Scope statements, article types, fees and data policies were **not checked online** for this
document; check before drafting to a template.

## Reproducibility package per paper

Tagged repository release + dataset DOI + `publications/<paper>/` containing: manuscript source,
`make_figures.py` (every figure and table regenerated from the dataset bundle), the SAP commit
hash, deviations from the SAP, model info sheets (data, splits, leakage checklist), CRediT roles.
Pre-registration: deposit `hypotheses.md` + SAP on OSF before run A1.
