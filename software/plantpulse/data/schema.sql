-- PLANTPULSE LAB experiment metadata (SQLite). Time-series live in Parquet; images on disk.
-- Every measured value is traceable: observation -> sensor -> calibration, plant -> unit -> treatment -> experiment.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS experiment (
  experiment_id TEXT PRIMARY KEY,            -- e.g. EXP-2027-A1
  study TEXT NOT NULL,                       -- pilot | uniformity | A | B | C | D
  title TEXT NOT NULL, hypothesis TEXT, protocol_version TEXT, sap_commit TEXT,
  data_class TEXT NOT NULL CHECK (data_class IN ('simulated','pilot','experimental')),
  start_utc TEXT, end_utc TEXT, day0_utc TEXT, cultivar TEXT, seed_lot TEXT,
  randomization_seed INTEGER, status TEXT DEFAULT 'planned', notes TEXT
);
CREATE TABLE IF NOT EXISTS treatment (
  treatment_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiment,
  code TEXT NOT NULL, description TEXT, recipe_json TEXT NOT NULL, onset_day INTEGER DEFAULT 0,
  UNIQUE (experiment_id, code)
);
CREATE TABLE IF NOT EXISTS unit (                 -- experimental unit = pod within a run
  unit_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiment,
  pod INTEGER NOT NULL, blind_code TEXT NOT NULL, treatment_id TEXT REFERENCES treatment,
  excluded INTEGER DEFAULT 0, exclusion_reason TEXT, UNIQUE (experiment_id, pod)
);
CREATE TABLE IF NOT EXISTS plant (
  plant_id TEXT PRIMARY KEY, unit_id TEXT NOT NULL REFERENCES unit,
  position INTEGER NOT NULL, seedling_id TEXT, seedling_size REAL,
  status TEXT DEFAULT 'growing', harvest_day INTEGER, excluded INTEGER DEFAULT 0, exclusion_reason TEXT,
  UNIQUE (unit_id, position)
);
CREATE TABLE IF NOT EXISTS sensor (
  sensor_id TEXT PRIMARY KEY, pod INTEGER, kind TEXT NOT NULL, model TEXT, serial TEXT,
  quantity TEXT NOT NULL, unit TEXT NOT NULL, installed_utc TEXT, retired_utc TEXT, location TEXT
);
CREATE TABLE IF NOT EXISTS calibration (
  calibration_id INTEGER PRIMARY KEY AUTOINCREMENT, sensor_id TEXT NOT NULL REFERENCES sensor,
  valid_from_utc TEXT NOT NULL, valid_to_utc TEXT, method TEXT NOT NULL, reference_instrument TEXT,
  coeffs_json TEXT NOT NULL,                 -- {"type":"linear","gain":..,"offset":..} | {"type":"poly","c":[..]}
  u_standard REAL,                           -- standard uncertainty after calibration, in sensor units
  operator TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS camera (
  camera_id TEXT PRIMARY KEY, pod INTEGER, model TEXT, lens TEXT, serial TEXT,
  intrinsics_json TEXT, settings_json TEXT, valid_from_utc TEXT
);
CREATE TABLE IF NOT EXISTS image (
  image_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiment, unit_id TEXT NOT NULL REFERENCES unit,
  camera_id TEXT REFERENCES camera, station INTEGER NOT NULL, stereo_offset_mm REAL DEFAULT 0,
  captured_utc TEXT NOT NULL, path TEXT NOT NULL, raw_path TEXT, sha256 TEXT NOT NULL,
  exposure_us INTEGER, gain REAL, gantry_steps INTEGER, session TEXT, qc_flags INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS image_plant (          -- which plants are in which image, and where
  image_id TEXT NOT NULL REFERENCES image, plant_id TEXT NOT NULL REFERENCES plant,
  roi_x INTEGER, roi_y INTEGER, roi_w INTEGER, roi_h INTEGER, PRIMARY KEY (image_id, plant_id)
);
CREATE TABLE IF NOT EXISTS manual_measurement (
  measurement_id INTEGER PRIMARY KEY AUTOINCREMENT, plant_id TEXT NOT NULL REFERENCES plant,
  measured_utc TEXT NOT NULL, day INTEGER, quantity TEXT NOT NULL, value REAL NOT NULL, unit TEXT NOT NULL,
  destructive INTEGER DEFAULT 0, instrument TEXT, operator TEXT, entry INTEGER DEFAULT 1, notes TEXT
);
CREATE TABLE IF NOT EXISTS intervention (          -- anything a human did to a unit
  intervention_id INTEGER PRIMARY KEY AUTOINCREMENT, unit_id TEXT REFERENCES unit, utc TEXT NOT NULL,
  kind TEXT NOT NULL, detail TEXT, quantity REAL, unit TEXT, operator TEXT
);
CREATE TABLE IF NOT EXISTS setpoint_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, unit_id TEXT REFERENCES unit, utc TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('recipe','manual','twin')), command TEXT NOT NULL, accepted INTEGER NOT NULL, reason TEXT
);
CREATE TABLE IF NOT EXISTS model_run (
  model_run_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, model TEXT NOT NULL, version TEXT, code_commit TEXT,
  training_data TEXT, split TEXT, metrics_json TEXT, notes TEXT
);
CREATE TABLE IF NOT EXISTS prediction (             -- predictions never share a table with measurements
  prediction_id INTEGER PRIMARY KEY AUTOINCREMENT, model_run_id TEXT NOT NULL REFERENCES model_run,
  plant_id TEXT REFERENCES plant, unit_id TEXT REFERENCES unit, issued_utc TEXT NOT NULL, target_utc TEXT,
  quantity TEXT NOT NULL, value REAL NOT NULL, lower REAL, upper REAL, unit TEXT
);
CREATE TABLE IF NOT EXISTS dataset_version (
  version TEXT PRIMARY KEY, created_utc TEXT NOT NULL, experiments TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
  code_commit TEXT, license TEXT, doi TEXT, notes TEXT
);
CREATE VIEW IF NOT EXISTS v_plant_full AS
  SELECT p.plant_id, p.position, p.status, p.excluded AS plant_excluded, u.unit_id, u.pod, u.blind_code,
         u.excluded AS unit_excluded, t.code AS treatment, t.onset_day, e.experiment_id, e.study, e.data_class, e.day0_utc
  FROM plant p JOIN unit u USING (unit_id) LEFT JOIN treatment t USING (treatment_id) JOIN experiment e ON e.experiment_id = u.experiment_id;
CREATE TABLE IF NOT EXISTS imaging_schedule (
  experiment_id TEXT PRIMARY KEY REFERENCES experiment, interval_min INTEGER NOT NULL DEFAULT 120,
  window_start_min INTEGER NOT NULL DEFAULT 390, window_end_min INTEGER NOT NULL DEFAULT 1290,   -- inside the photoperiod only
  stereo INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1
);
