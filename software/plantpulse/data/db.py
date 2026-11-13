"""Metadata database access (SQLite)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import pandas as pd

from . import naming


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class MetaDB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(resources.files("plantpulse.data").joinpath("schema.sql").read_text())
        self.con.execute("PRAGMA foreign_keys = ON")

    def close(self):
        self.con.commit()
        self.con.close()

    def q(self, sql: str, params=()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.con, params=params)

    def x(self, sql: str, params=()):
        cur = self.con.execute(sql, params)
        self.con.commit()
        return cur

    # ---------------------------------------------------------------- experiment set-up
    def create_experiment(self, experiment_id: str, study: str, title: str, data_class: str, *, hypothesis: str = "",
                          day0_utc: str | None = None, cultivar: str = "Rex", randomization_seed: int | None = None,
                          protocol_version: str = "1.0", notes: str = "") -> str:
        if not naming.validate("experiment", experiment_id):
            raise ValueError(f"bad experiment id {experiment_id}")
        self.x("INSERT INTO experiment (experiment_id, study, title, hypothesis, data_class, day0_utc, start_utc, cultivar,"
               " randomization_seed, protocol_version, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
               (experiment_id, study, title, hypothesis, data_class, day0_utc, day0_utc, cultivar, randomization_seed, protocol_version, notes))
        return experiment_id

    def add_treatment(self, experiment_id: str, code: str, description: str, recipe: dict, onset_day: int = 0) -> str:
        tid = f"{experiment_id}-T{code}"
        self.x("INSERT INTO treatment VALUES (?,?,?,?,?,?)", (tid, experiment_id, code, description, json.dumps(recipe), onset_day))
        return tid

    def assign_units(self, experiment_id: str, allocation: dict[int, str], plants_per_pod: int = 6, seed: int = 0) -> list[str]:
        """allocation: pod -> treatment code. Creates units with blind codes and their plants."""
        import random
        rng = random.Random(seed)
        codes = rng.sample([f"U{n:03d}" for n in range(100, 1000)], len(allocation))
        out = []
        for (pod, tcode), blind in zip(sorted(allocation.items()), codes):
            uid = naming.unit_id(experiment_id, pod)
            self.x("INSERT INTO unit (unit_id, experiment_id, pod, blind_code, treatment_id) VALUES (?,?,?,?,?)",
                   (uid, experiment_id, pod, blind, f"{experiment_id}-T{tcode}"))
            for pos in range(1, plants_per_pod + 1):
                self.x("INSERT INTO plant (plant_id, unit_id, position) VALUES (?,?,?)", (naming.plant_id(experiment_id, pod, pos), uid, pos))
            out.append(uid)
        return out

    # ---------------------------------------------------------------- records
    def add_sensor(self, sensor_id, pod, kind, quantity, unit, model="", serial="", location=""):
        self.x("INSERT OR REPLACE INTO sensor (sensor_id, pod, kind, model, serial, quantity, unit, installed_utc, location)"
               " VALUES (?,?,?,?,?,?,?,?,?)", (sensor_id, pod, kind, model, serial, quantity, unit, now_utc(), location))

    def add_calibration(self, sensor_id, coeffs: dict, method: str, valid_from_utc: str | None = None, u_standard: float | None = None,
                        reference: str = "", operator: str = "", notes: str = ""):
        vf = valid_from_utc or now_utc()
        self.x("UPDATE calibration SET valid_to_utc=? WHERE sensor_id=? AND valid_to_utc IS NULL", (vf, sensor_id))
        self.x("INSERT INTO calibration (sensor_id, valid_from_utc, method, reference_instrument, coeffs_json, u_standard, operator, notes)"
               " VALUES (?,?,?,?,?,?,?,?)", (sensor_id, vf, method, reference, json.dumps(coeffs), u_standard, operator, notes))

    def add_image(self, image_id, experiment_id, unit_id, station, captured_utc, path, sha256, camera_id=None, **extra):
        cols = ["image_id", "experiment_id", "unit_id", "camera_id", "station", "captured_utc", "path", "sha256"] + list(extra)
        vals = [image_id, experiment_id, unit_id, camera_id, station, captured_utc, path, sha256] + list(extra.values())
        self.x(f"INSERT OR REPLACE INTO image ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)

    def add_manual(self, plant_id, quantity, value, unit, measured_utc=None, day=None, destructive=False, operator="", instrument="", entry=1):
        self.x("INSERT INTO manual_measurement (plant_id, measured_utc, day, quantity, value, unit, destructive, instrument, operator, entry)"
               " VALUES (?,?,?,?,?,?,?,?,?,?)", (plant_id, measured_utc or now_utc(), day, quantity, value, unit, int(destructive), instrument, operator, entry))

    def add_intervention(self, unit_id, kind, detail="", quantity=None, unit=None, operator="", utc=None):
        self.x("INSERT INTO intervention (unit_id, utc, kind, detail, quantity, unit, operator) VALUES (?,?,?,?,?,?,?)",
               (unit_id, utc or now_utc(), kind, detail, quantity, unit, operator))

    def log_setpoint(self, unit_id, source, command, accepted, reason=""):
        self.x("INSERT INTO setpoint_log (unit_id, utc, source, command, accepted, reason) VALUES (?,?,?,?,?,?)",
               (unit_id, now_utc(), source, command, int(accepted), reason))

    def allocation(self, experiment_id: str, blinded: bool = True) -> pd.DataFrame:
        cols = "u.unit_id, u.pod, u.blind_code" + ("" if blinded else ", t.code AS treatment, t.onset_day")
        return self.q(f"SELECT {cols} FROM unit u LEFT JOIN treatment t USING (treatment_id) WHERE u.experiment_id=? ORDER BY u.pod", (experiment_id,))
