# Data architecture

## Principles

1. **Raw is immutable.** 1 Hz node frames and images are written once, read-only, with SHA-256.
2. **Processed is disposable.** Everything under `processed_data/` is regenerated from raw data
   and the calibration table by `plantpulse.data.pipeline` (idempotent).
3. **Measured, predicted and simulated never share a table.** Measurements: Parquet +
   `manual_measurement`. Predictions: `prediction` (always with a `model_run`). Simulation:
   experiments with `data_class = 'simulated'`; the daemon refuses to write simulated node data
   into any other experiment, and exports of non-experimental data carry a warning banner.
4. **Traceability by keys**, not by file names: observation → sensor → calibration;
   image → camera, unit, station, gantry position, checksum; plant → unit → treatment → experiment.
5. **Blinding.** Analysis tables carry unit blind codes; the allocation lives in one table/file
   that the analysis script joins last.

## Stores

| Store | Technology | Content |
|-------|-----------|---------|
| Metadata | SQLite (`plantpulse_meta.db`, schema in `plantpulse/data/schema.sql`) | experiment, treatment, unit, plant, sensor, calibration, camera, image, image_plant, manual_measurement, intervention, setpoint_log, model_run, prediction, dataset_version, imaging_schedule |
| Raw time series | Parquet, partitioned `raw_data/<exp>/sensors/pod=NN/date=YYYY-MM-DD/part-*.parquet` | node frames with node time, host arrival time and synchronised UTC |
| Raw images | PNG (lossless) + DNG on the real system, `raw_data/<exp>/images/Pnn/YYYYMMDD/` | one file per exposure |
| Processed | Parquet `processed_data/<exp>/` | `sensors_1min` (calibrated, QC-flagged), `daily_env`, `traits`, feature tables |
| Exports | directory bundle + manifest | `plantpulse.data.export` |

SQLite is sufficient for one facility (single writer, thousands of rows per run); the schema is
plain SQL and ports to PostgreSQL if several facilities share a server.

## Naming convention (`plantpulse.data.naming`)

| Entity | Pattern | Example |
|--------|---------|---------|
| Experiment (run) | `EXP-<year>-<code>` | `EXP-2027-A1` |
| Unit (pod-run) | `<experiment>-P<pod 2d>` | `EXP-2027-A1-P03` |
| Plant | `<unit>-N<position 2d>` | `EXP-2027-A1-P03-N05` |
| Image | `<unit>-S<station>-<UTC yyyymmddThhmmssZ>[-L|-R]` | `EXP-2027-A1-P03-S2-20270304T123005Z-L` |
| Sensor | free text, unique, serial recorded | `P03-SHT45-A` |

Positions 1-3 are the front row (left to right), 4-6 the back row. Station s images positions
s and s+3. All timestamps are UTC, ISO 8601; naive timestamps are rejected.

## Pipeline

```
node frame (1 Hz) -> NodeClient (clock model: utc = offset + node_ms/1000, offset = sliding minimum of arrival delay)
   -> Store.append_raw (immutable Parquet)
   -> pipeline.process_sensors: calibration by validity interval -> QC flags -> 1-min means of QC-passed samples
   -> pipeline.daily_summary: light/dark means, DLI, VPD, kWh per rail, water use from reservoir mass
image -> registration (fiducial bars) -> segmentation -> per-plant split -> traits + QC -> traits.parquet
tables -> machine_learning.features (plant-day, unit-day, forecast tables; past-only features)
```

## Quality flags (`plantpulse.data.validation`)

Bit field per value: 1 missing, 2 outside physical range, 4 spike (Hampel), 8 flatline,
16 uncalibrated, 32 door open, 64 node fault, 128 gap-filled. Image traits: 1 no fiducial,
2 blur, 4 truncated by frame, 8 touching a neighbour, 16 exposure. Flagged values are kept;
aggregates use only values without range/spike/missing flags. Thresholds ship with every export
(`metadata/qc_flags.json`).

Missing-data detection: `find_gaps` and `completeness` per unit and day; unit-level exclusion
rules (SAP section 6) are evaluated by `environment_excursions`.

## Versioning and publication

- Code: git. Dataset versions: `export_dataset(version=...)` writes an immutable bundle
  (refuses to overwrite), records the manifest hash and code commit in `dataset_version`.
- Repository target: Zenodo (DOI, versioning, 50 GB per record) for tables + a representative
  image subset; full image archive in a domain repository if larger (e.g. 4TU.ResearchData).
- Licence: data CC BY 4.0, software MIT, hardware CERN-OHL-P-2.0.
- Metadata: Frictionless `datapackage.json`; fields mapped to MIAPPE 1.1 (investigation →
  programme, study → experiment/run, observation unit → plant with unit as parent, factor →
  treatment, observed variable → trait with method = pipeline version, environment → daily summary).
- Each export states the data class; simulated and pilot data are never mixed into an
  "experimental" release.
