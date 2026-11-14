# PLANTPULSE LAB

Open experimental platform for multimodal plant phenotyping and physics-informed digital twins in
controlled-environment agriculture. Primary crop: lettuce (*Lactuca sativa*).

**Status (read this first).** This repository contains a complete *design*, a complete *software
stack tested against simulated hardware*, and a complete *experimental plan*. No hardware has been
built, no plant has been grown, and there are **no experimental results** here. Everything
numerical is either a design calculation, a model prediction, or simulated data, and is labelled
as such. See `docs/phases/PHASE_LOG.md` for what is done, what is open, and what needs physical work.

## Research theme

*Multimodal plant phenotyping and physics-informed digital twins for early stress detection and
resource-efficient controlled-environment agriculture.* Five research questions with
pre-specified hypotheses (`docs/research/hypotheses.md`), tested in separate studies
(`experiments/protocols/`), analysed by a plan written before any data exist
(`experiments/protocols/statistical_analysis_plan.md`).

## The instrument in one paragraph

Four independent growth pods (experimental unit = pod-run), six lettuce plants each in a
deep-water-culture tub; six dimmable Bridgelux LED strips above an acrylic window; ventilation
cooling, PTC heating, ultrasonic humidification; SHT45 / SCD30 / spectral PAR monitor / isolated
pH and EC / load-cell water accounting / per-rail power metering; a single-axis camera gantry
(Raspberry Pi HQ camera) parking outside the canopy; an ESP32-S3 node per pod running a
fail-safe controller; a Raspberry Pi 5 running acquisition, QC, vision, models and the dashboard.
Estimated cost about USD 1,650 per pod and USD 9,200 for the facility with shared reference
instruments (unverified prices).

## Repository map

| Path | Content |
|------|---------|
| `docs/research/` | literature review + matrix, research gap, hypotheses |
| `docs/requirements/`, `docs/architecture/` | requirements, trade studies, environmental control, electronics, data and software architecture |
| `docs/validation/` | validation plan (47 acceptance criteria), calibration procedures, uncertainty budget |
| `docs/manufacturing/` | BOM with sourcing, cost estimate, build guide |
| `docs/phases/PHASE_LOG.md` | per-phase deliverables, tests, open problems, assumptions, physical-work items |
| `hardware/design_parameters.yaml` | single source of truth for dimensions and component data |
| `hardware/mechanical/` | parametric CAD (CadQuery), STEP/STL/3MF/DXF, drawings, calculation report |
| `hardware/electrical/pcb/` | node carrier board: netlist source, KiCad schematic + PCB, Gerbers, DRC |
| `firmware/` | ESP32-S3 node firmware, serial protocol, host-side unit tests |
| `software/plantpulse/` | Python package (acquisition, data, vision, ML, twin, optimisation, stats, dashboard, simulation) |
| `experiments/` | protocols, analysis plans, data roots (raw / processed, git-ignored) |
| `simulation/` | virtual-study driver and reports (simulated data only) |
| `publications/` | strategy, outlines for three papers, figure scripts |
| `tests/` | 78 tests |

## Quick start (no hardware needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dashboard,dev]"
pytest                                            # ~2 min
python simulation/run_virtual_study.py --quick    # simulated Study A through the full pipeline
PLANTPULSE_DATA=simulation/output/lab_quick streamlit run software/plantpulse/dashboard/app.py
```

Regenerate engineering outputs: see `docs/architecture/software_architecture.md`.
CAD needs `pip install cadquery`; PCB scripts need KiCad 7 (`pcbnew` Python module, `kicad-cli`).

## Honest limits

- Pods cool by ventilation: the room must be ≤ 20 °C and pods cannot run below room temperature
  or dehumidify below room dew point. CO₂ is monitored, not enriched.
- n = 4 units per run. Replication comes from repeated runs; a full programme is about 13 crop
  cycles (over a year).
- A single top-view camera at 500 mm: strong perspective magnification with plant height;
  per-plant area becomes unreliable once canopies touch.
- The vision pipeline has only been run on procedurally generated images.
- The digital twin is uncalibrated; its recommendations are hypotheses and are blocked from
  driving hardware until validation tests pass and an experiment opts in.
- Firmware application layer not yet compiled for the target; PCB not fabricated; CNN code
  unexecuted (PyTorch unavailable in the build environment).
- Literature review is a scoping review; many citations still need verification.

## Licences

Software: MIT. Hardware (CAD, PCB): CERN-OHL-P-2.0. Documentation and data: CC BY 4.0.
See `LICENSE`.
