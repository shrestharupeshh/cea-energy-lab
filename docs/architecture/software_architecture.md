# Software architecture

```
software/plantpulse/
  config.py            repository paths, design-parameter loader
  engineering/         design calculations (structure, hydraulics, lighting, thermal, imaging, electrical) + report
  acquisition/         node protocol client, safety envelope, simulated node, control-logic port, scheduler, daemon
  data/                schema, database access, naming, raw/processed store, calibration, QC, time sync, pipeline, export
  computer_vision/     registration, segmentation, colour, traits, height (motion stereo), growth, pipeline, evaluation
  machine_learning/    leakage-safe splits, metrics with cluster bootstrap, features, model harness, tasks A-E, optional CNN/GRU
  digital_twin/        crop model, environment + energy model, coupled twin, calibration, hybrid models
  optimization/        problem definition, Pareto tools, NSGA-II, Bayesian optimisation, model-predictive lighting control
  stats/               randomisation, agreement statistics, unit-level inference, power simulation
  simulation/          synthetic image renderer, virtual laboratory
  dashboard/           services (testable) + Streamlit app
firmware/node/         ESP32-S3 firmware: portable control core (host-tested) + hardware layer
simulation/            virtual-study driver and its reports
tests/                 pytest suite (78 tests) incl. firmware core via g++
```

Design choices:

- **One description, several consumers.** `hardware/design_parameters.yaml` feeds the
  calculations, the CAD and the twin defaults; `node_netlist.py` feeds schematic, PCB and BOM;
  the firmware control core is mirrored in `acquisition/node_logic.py` and both are tested
  against the same cases.
- **Hardware abstraction at the transport.** `NodeClient` talks to anything with
  `write(line)` / `readlines()`. `SimNode` implements the same protocol on top of the twin, so the
  daemon, pipeline, dashboard and analyses run unchanged with or without hardware.
- **Dashboard = thin UI over `dashboard/services.py`.** Streamlit was chosen because the whole
  stack is Python and the user group is small; services are plain functions so a FastAPI layer
  can be added without touching logic.
- **Models are comparable by construction.** Every model is evaluated through
  `models.compare_models` / `splits.grouped_splits` (no row-level random split exists in the code
  base) and reported with cluster-bootstrap intervals over pod-runs.
- **Predictions are labelled.** Twin and model outputs carry `provenance = "predicted"`; the
  database separates `prediction` from measurement tables.

Running things:

```
pytest                                         # 78 tests, about 2 min
python -m plantpulse.engineering.report        # calculation report + PPFD map
python hardware/mechanical/cad/build_all.py    # CAD outputs (needs cadquery)
python hardware/electrical/pcb/generate_pcb.py && python hardware/electrical/pcb/export_fab.py && python hardware/electrical/pcb/generate_schematic.py
python simulation/run_virtual_study.py --quick # simulated Study A rehearsal (~2 min; full run ~6 min)
streamlit run software/plantpulse/dashboard/app.py
make -C firmware/node/test_host test           # firmware control-core tests on the host
```

Not yet written: camera-node capture/sync service (picamera2), systemd units, U-Net training
script, automatic pH/EC dosing. See `docs/phases/PHASE_LOG.md`.
