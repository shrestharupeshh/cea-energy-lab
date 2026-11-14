# Phase log

One entry per phase: deliverables, tests run, unresolved problems, assumptions, and what needs
physical intervention. Phases 1-6 were executed in a software-only environment. Phases 7-12
need hardware, plants and time; for those the log records what is prepared and what is not.

Legend: DONE = produced and checked here; PREPARED = procedure/code exists, not executed;
NOT STARTED = requires physical work.

---

## Phase 1 - Literature, research gap, requirements, experimental design: DONE (with caveats)

Deliverables: `docs/research/literature_review.md`, `literature_matrix.csv` (36 entries),
`hypotheses.md`, `docs/requirements/requirements.md`, `experiments/protocols/` (study protocols,
SAP, manual measurement protocol, husbandry SOP), `experiments/analysis/power_analysis.md`.

Tests: power analysis by simulation; randomisation code unit-tested.

Unresolved:
- The review is a scoping review. 22 of 36 matrix entries are cited from memory or from search
  snippets and are flagged for verification; several 2024-2026 papers were not read in full.
  A formal search (strings provided) must precede any manuscript.
- Van Henten parameter values come from secondary reproductions.

Assumptions: between-unit CV 8 %, plant CV 15 % (planning values until uniformity trials);
cultivar 'Rex'; 28-day cycle; room ≤ 20 °C.

Physical: none. Pre-register hypotheses + SAP (OSF) before run A1.

## Phase 2 - Architecture and component selection: DONE

Deliverables: `docs/architecture/` (facility + trade studies, environmental control,
electronics, data, software), `hardware/design_parameters.yaml`, engineering calculation package
and `hardware/mechanical/calculations/calculation_report.md`, `docs/manufacturing/bom.csv`,
`sourcing.md`, `cost_estimate.md`.

Tests: 10 engineering tests (formulas, requirement checks).

Findings that changed the design: four LED strips could not reach 250 µmol m⁻² s⁻¹ → six strips
and a 600 W 48 V supply; LDD-700H listed obsolete → wired variant / successor to confirm.

Unresolved: prices and most part numbers unverified; cost estimate is about USD 1,655 per pod and
USD 9,200 for the facility, which **misses** targets COST-01 (1,600 / 8,500) by 3-8 %; light-trap
loss coefficient, wall reflectance and PPF-per-lumen factor are estimates; pump curve generic.

Physical: site survey of the room (temperature, power).

## Phase 3 - Mechanical CAD and electrical design: DONE as design, NOT built

Deliverables: parametric CadQuery model; STEP assemblies (pod, rack), 10 printed parts as
STEP/STL/3MF, DXF sheet parts, 15 drawing sheets (SVG/PDF/PNG), mechanical BOM, interference
report; KiCad 7 node board: schematic (+PDF), routed PCB, Gerber/drill/position/STEP, BOM, DRC
and netlist-consistency reports.

Tests: CAD build runs clean, 9 boolean clash checks clear; PCB: 0 unconnected, 0 clearance
violations, schematic = netlist = PCB.

Unresolved:
- SolidWorks/FreeCAD were unavailable; CadQuery was used (STEP is neutral). Drawing sheets are
  generated views with key dimensions, not fully dimensioned manufacturing drawings.
- Freerouting could not be executed (sandbox policy), so the PCB was routed by a purpose-built
  grid router; a human layout review and KiCad ERC are still required. Review items are listed
  in `electronics_architecture.md` (header spacing, heater track neck-down → 2 oz copper,
  TSR-2 footprint, enclosure size vs 175 x 120 mm board).
- Door hardware, glands, tubing and harness are not modelled. Printed parts not fit-checked.

Physical: print and fit-check parts; order one PCB batch; assemble one board.

## Phase 4 - Software and data acquisition: DONE (simulated hardware)

Deliverables: firmware control core + ESP32 application + protocol; `plantpulse.acquisition`
(client, safety envelope, simulated node, scheduler, daemon); `plantpulse.data` (schema, store,
calibration, QC, time sync, pipeline, export); dashboard.

Tests: firmware core unit tests (g++), Python port tests, protocol session, QC, traceability,
export/verify, dashboard smoke test.

Unresolved:
- `firmware/node/src/main.cpp` has **not been compiled** for the ESP32 (PlatformIO toolchain not
  available) and never run on hardware; library API calls may need adjustment.
- Camera-node capture/sync service (picamera2) not written. Stereo offset moves are specified in
  the scheduler but the firmware `MOVE` command only accepts station indices.
- No systemd units; no automatic dosing.

Physical: flash and bring up a node; write/validate the camera service on a Pi Zero 2 W.

## Phase 5 - Computer vision and digital-twin simulation: DONE (synthetic / uncalibrated)

Deliverables: registration, segmentation, colour, traits, height, growth, pipeline, evaluation;
crop, environment, energy models; coupled twin; calibration; hybrid models; optimisation
(NSGA-II, Bayesian optimisation, MPC).

Tests: vision against synthetic ground truth (isolated plants: area bias < 1 %, diameter MAE
< 1 mm on synthetic images); twin sign/plausibility tests; parameter recovery; Pareto and
constraint tests.

Unresolved (important):
- Vision has seen **no real image**. Thresholds will need tuning; real leaves have glare, veins,
  overlap, algae. The U-Net upgrade needs annotated real images. PyTorch could not be installed,
  so `machine_learning/cnn.py` is unexecuted code.
- Perspective: a leaf 200 mm above the lid appears 2.8x larger in area. Height correction
  (motion stereo) is implemented only at the geometry level and is untested on plants.
- After canopy closure (about day 8-12 at 25 plants m⁻²) per-plant area is a geometric split;
  on synthetic data its error is about 15-25 %. Use unit-level canopy cover from then on.
- The twin is uncalibrated; the temperature-penalty and nutrient factors are assumptions.

Physical: collect and annotate real images; step tests for the climate model.

## Phase 6 - Simulated experimental environment: DONE

Deliverables: synthetic image renderer, virtual laboratory, `simulation/run_virtual_study.py`,
`simulation/reports/virtual_study_report.md` (full simulated Study A through the SAP).

Tests: integration tests on a mini virtual lab; full rehearsal (16 pod-runs, 645 k sensor
records, 1,344 images).

What the rehearsal changed: fiducials moved off the lid to bars beside the tub (registration
33 % → 98.6 % of records); Study D false-alarm rule replaced (dated SAP amendment); humidifier
resized (twin predicted about 54 % RH against a 68 % setpoint with a small canopy); rejected
commands now acknowledged with their id; RH/VPD removed from the "response" feature set because
they are controlled variables.

Caveat: the simulator's hidden plant model is the same family as the twin, so simulated model
comparisons favour the physics-based models and carry no evidential weight.

## Phase 7 - Assemble a physical pilot facility: NOT STARTED

Prepared: `docs/manufacturing/build_guide.md`, BOM, CAD/PCB outputs.
Requires: budget (about USD 9-10.5 k), room, about 60-80 h build labour for four pods (estimate),
tools (3D printer, saw or cut-to-length order, soldering station).
Recommendation: build ONE pod first.

## Phase 8 - Calibration and pilot experiments: NOT STARTED

Prepared: validation plan with 47 pre-set acceptance criteria, calibration procedures,
uncertainty budget template, pilot P0 and uniformity protocols.
Requires: reference instruments, 3 crop cycles (P0, U1, U2 ≈ 3.5 months).

## Phase 9 - Full experimental data collection: NOT STARTED

Prepared: protocols for Studies A, B, C; randomisation and experiment-creation tools.
Requires: about 10 further crop cycles (≈ 10-11 months of chamber time).

## Phase 10 - Model development and statistical analysis: PREPARED

Analysis code for every pre-specified analysis runs end to end on simulated data. No real-data
model exists. Models will be re-fit from scratch on real data; nothing learned from the
simulation carries over except the code.

## Phase 11 - Experimental validation: NOT STARTED

VAL-CV-02/04 and VAL-DT-01..04 depend on Study B; H1-H4 on Studies A, C, D.

## Phase 12 - Research documentation and publication: PREPARED (outlines only)

`publications/` holds the strategy, journal-fit notes (not checked online), three outlines and a
figure script that currently produces only prediction-class figures, labelled as such.
No manuscript can be completed before the corresponding runs.

---

## Standing assumptions register

| Assumption | Used in | How it gets replaced |
|------------|---------|----------------------|
| PPF = 14.6 µmol s⁻¹ per klm for the 4000 K strips | lighting calcs, twin | VAL-LGT-01 |
| Wall reflectance 0.85, window transmittance 0.92 | lighting | VAL-LGT-01 |
| Light-trap K = 6, linear fan curve | airflow, thermal | VAL-ENV-04 |
| Effective air/wall capacitance 8 kJ K⁻¹, UA 7 W K⁻¹ | twin | VAL-DT-02 |
| Van Henten parameters + extensions | twin, optimisation | Study B calibration |
| Dry-matter content 4.8 %, SLA 350 cm² g⁻¹ | twin outputs | Study B |
| Unit CV 8 %, plant CV 15 % | power analysis | U1-U2 |
| Room at 20 °C / 50 % RH | all thermal results | site survey + logging |
