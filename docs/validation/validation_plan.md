# Validation plan

Acceptance criteria are fixed here **before** any test is run. Machine-readable copy:
`acceptance_criteria.csv`. Results go in `docs/validation/results/<test-id>_<date>.md` with raw
data under `experiments/raw_data/validation/`. A criterion may only be changed by a dated
amendment that states why, made before the corresponding test.

## Evidence classes (never mixed)

| Class | Meaning | Where it lives | May support a paper claim? |
|-------|---------|----------------|----------------------------|
| **Design calculation** | closed-form / numerical estimate from datasheets | `hardware/mechanical/calculations/` | no - only motivates the design |
| **Simulated** | virtual laboratory, digital-twin runs | `simulation/`, experiments with `data_class = simulated` | no - software verification only |
| **Pilot** | commissioning and uniformity runs on the real platform | `data_class = pilot` | platform characterisation only |
| **Validated experimental** | protocol-compliant runs after all acceptance tests passed | `data_class = experimental` | yes |

The database, the dashboard, dataset exports and every figure script carry the class label.

Status today: all items below are **not started** (no hardware exists). The software
verification that could be done without hardware is in `tests/` and
`simulation/reports/virtual_study_report.md`.

## A. Sensors

| ID | Test | Method | Acceptance |
|----|------|--------|------------|
| VAL-SEN-01 | Air temperature accuracy | All SHT45 + reference thermometer (± 0.1 °C, traceable) in a stirred insulated box at 15, 23, 30 °C, 30 min soak each | each sensor within ± 0.3 °C before correction; after per-sensor offset, residual ≤ 0.15 °C; between-pod spread ≤ 0.2 °C |
| VAL-SEN-02 | RH accuracy | Saturated-salt fixed points (MgCl₂ 33 %, NaCl 75 %) at 23 °C, 4 h equilibration | within ± 2.5 %RH at both points; between-pod spread ≤ 2 %RH |
| VAL-SEN-03 | CO₂ | Zero (soda lime) / ambient outdoor air / one span gas or a calibrated reference analyser; ASC disabled | within ± (40 ppm + 4 %) |
| VAL-SEN-04 | PAR monitor transfer calibration | Apogee quantum sensor at each plant position vs AS7341 counts at 10 duty levels, per pod | linear fit R² irrelevant; residual SD ≤ 3 % of reading over 50-300 µmol; repeat after 30 days: drift ≤ 3 % |
| VAL-SEN-05 | Solution temperature | DS18B20 vs reference in water bath at 15, 22, 28 °C | ± 0.2 °C after offset |
| VAL-SEN-06 | pH | 3-point calibration, then check in pH 5.00 and 6.00 buffers (not used for calibration) | ± 0.05 pH |
| VAL-SEN-07 | EC | Calibrate at 1413 µS cm⁻¹, check at 500 and 2000 (dilutions / standards) | ± 3 % |
| VAL-SEN-08 | Load cell | 0, 1, 2, 5 kg check weights, ascending/descending, at 18 and 28 °C | non-linearity + hysteresis ≤ 5 g; temperature effect ≤ 10 g per 10 K |
| VAL-SEN-09 | Power monitors | Resistive load + reference wattmeter at 3 loads per rail | ± 2 % of reading |
| VAL-SEN-10 | Drift | Repeat SEN-01, -02, -04, -06, -07 after each run; control chart per sensor | drift within the accuracy limit per 35 days; otherwise shorten the calibration interval and flag the interval |

## B. Environment and lighting

| ID | Test | Method | Acceptance |
|----|------|--------|------------|
| VAL-ENV-01 | Temperature control | 48 h empty and 48 h with mature crop at 23/20 °C; step to 30/26 °C | within ± 1.0 °C of setpoint ≥ 95 % of minutes outside 30 min transition windows; no sustained oscillation > 0.5 °C p-p |
| VAL-ENV-02 | Humidity control | Same runs, RH 68 % | within ± 7 %RH ≥ 90 % of minutes (empty) / ≥ 95 % (crop); no condensation on window |
| VAL-ENV-03 | Spatial temperature uniformity | 6 loggers at plant positions, canopy height, lights on | max-min ≤ 1.0 °C |
| VAL-ENV-04 | Air speed and ventilation | Hot-wire anemometer at 6 positions; exhaust flow by CO₂ decay | 0.3-0.7 m s⁻¹ at canopy; flow ≥ 15 m³ h⁻¹ at 100 % |
| VAL-ENV-05 | Pod equivalence | All pods, same recipe, 7 days | between-pod difference of mean air T ≤ 0.4 °C, RH ≤ 4 %RH, PPFD ≤ 4 % |
| VAL-LGT-01 | PPFD map | Quantum sensor on a 5 x 4 grid at lid plane and at +150 mm, 100 % and 74 % duty | min/mean ≥ 0.80 over plant positions; mean at 100 % ≥ 280 µmol m⁻² s⁻¹ |
| VAL-LGT-02 | Gantry shading | PPFD at 6 plant positions, gantry parked vs removed | change < 2 % |
| VAL-LGT-03 | Light leak | Neighbour pod at 100 %, room lights on, test pod dark | < 0.5 µmol m⁻² s⁻¹ |
| VAL-LGT-04 | Dimming linearity and warm-up | PPFD vs duty (10 levels); PPFD vs time from cold | deviation from linear ≤ 3 %; drift after 15 min ≤ 2 % |

## C. Water and nutrient system

| ID | Test | Acceptance |
|----|------|------------|
| VAL-WQ-01 | Circulation flow (timed volume) | ≥ 2 tub volumes h⁻¹; flow-meter alarm threshold set at 50 % |
| VAL-WQ-02 | Leak test, 48 h, tissue under every joint | no moisture |
| VAL-WQ-03 | Dissolved oxygen with aeration at 23 °C (borrowed DO meter) | ≥ 6 mg L⁻¹ |
| VAL-WQ-04 | Water accounting: withdraw known masses (50-500 g) from the tub; plant-free 7-day blank | top-up mass within ± 20 g d⁻¹ of the withdrawn mass; blank evaporation ≤ 30 g d⁻¹ and reported |
| VAL-WQ-05 | Top-up flood guard: hold float low | pump stops at 60 s; budget fault raised |

## D. Imaging and computer vision

| ID | Test | Method | Acceptance |
|----|------|--------|------------|
| VAL-IMG-01 | Gantry repeatability | 30 cycles park → station, fiducial centroid in image | SD ≤ 0.5 mm per station (≈ 4 px) |
| VAL-IMG-02 | Photometric stability | Grey card + colour target imaged every 2 h for 7 days | mean grey value CV ≤ 2 %; ΔE*ab of patches ≤ 3 after colour correction |
| VAL-IMG-03 | Geometric accuracy | Printed checkerboard and discs of known area (10-700 cm²) at lid height and on 50/100/150 mm stands | area error ≤ 2 % at lid height; with height correction ≤ 5 % on stands |
| VAL-IMG-04 | Sharpness over depth | Slanted-edge target at 0, 100, 200 mm above lid | MTF50 ≥ 0.15 cycles px⁻¹ at all three |
| VAL-CV-01 | Segmentation | 100 hand-annotated images sampled across days, treatments, pods (annotator blind to treatment; 20 double-annotated) | IoU ≥ 0.90 vs annotation; report inter-annotator IoU as the ceiling |
| VAL-CV-02 | Trait agreement | Study B destructive and manual data | H2a, H2b in `hypotheses.md` |
| VAL-CV-03 | Height from motion stereo | Ruler height on 40 plants | MAE ≤ 10 mm, else the feature is dropped and area is reported at lid-plane scale only |
| VAL-CV-04 | Biomass prediction | Held-out pod-runs | H2c |

## E. Data system

| ID | Test | Acceptance |
|----|------|------------|
| VAL-DATA-01 | 7-day unattended logging with scheduled imaging | ≥ 98 % sensor records, ≥ 97 % images; every gap explained |
| VAL-DATA-02 | Traceability audit: 20 random observations traced to plant, unit, treatment, sensor, calibration, image file and checksum | 20 / 20 |
| VAL-DATA-03 | Clock: node vs host vs NTP over 7 days; camera-node timestamps | sensor timestamps within ± 1 s; image timestamps within ± 2 s |
| VAL-DATA-04 | Power-cut recovery: cut mains for 60 s mid-photoperiod | nodes resume recipe; host resumes logging; gap flagged; no corrupt files |
| VAL-DATA-05 | Backup restore drill | restored bundle passes manifest verification |

## F. Safety and control

| ID | Test | Acceptance |
|----|------|------------|
| VAL-SAF-01 | E-stop | LED and actuator rails dead < 1 s; logging continues; event recorded |
| VAL-SAF-02 | Heater cut-out: force heater on with fan blocked (attended) | bimetal opens ≤ 50 °C at the heater outlet; firmware trip at 36 °C air |
| VAL-SAF-03 | Host loss: unplug USB for 10 min | recipe continues, heater capped, fault flagged, clean reconnect |
| VAL-SAF-04 | Leak sensor, door switch | pumps stop / gantry stops within 2 s |
| VAL-CTL-01 | Disturbance rejection: door open 3 min; room +2 °C step | return to band within 20 min, overshoot ≤ 1.5 °C |
| VAL-CTL-02 | Safety envelope: 20 scripted out-of-range / malformed commands from each source | all rejected at host; node also rejects when host check is bypassed |

## G. Digital twin

| ID | Test | Method | Acceptance |
|----|------|--------|------------|
| VAL-DT-01 | Growth forecast | Calibrate on Study B run 1, forecast run 2 (and vice versa) from day 14 | harvest dry-mass MAPE ≤ 20 %; bias CI includes 0 |
| VAL-DT-02 | Thermal model | Step tests: LED 0→100 %, heater 0→50 %, fan 15→100 % | air-temperature RMSE ≤ 0.7 °C after identification on half the steps |
| VAL-DT-03 | Energy model | Predicted vs metered daily kWh over a run | lighting within ± 5 %; total DC within ± 15 % |
| VAL-DT-04 | Water model | Predicted vs measured cumulative water use | reported; no acceptance threshold (exploratory) |

The twin is not allowed to propose setpoints for a physical experiment until VAL-DT-01 and
VAL-CTL-02 have passed, and then only in experiments that opt in (`Envelope.allow_twin`).

## Uncertainty reporting

Each measured quantity is reported with a standard uncertainty combining (i) calibration residual
(`calibration.u_standard`), (ii) reference-instrument uncertainty, (iii) resolution, (iv) drift
bound over the calibration interval, in quadrature (GUM type A + B). The template and the current
*expected* budget (to be replaced by measured values) are in `uncertainty_budget.md`.
