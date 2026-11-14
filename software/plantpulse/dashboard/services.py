"""Dashboard back-end functions (no Streamlit imports here, so they are unit-testable)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..data import naming
from ..data.db import MetaDB
from ..data.export import export_dataset
from ..data.store import Store
from ..digital_twin.twin import PodTwin, Recipe
from ..stats.design import balanced_crossover, latin_square


def open_lab(root: str | Path) -> tuple[MetaDB, Store]:
    root = Path(root)
    return MetaDB(root / "plantpulse_meta.db"), Store(root)


def experiments(db: MetaDB) -> pd.DataFrame:
    return db.q("SELECT experiment_id, study, title, data_class, status, day0_utc, end_utc FROM experiment ORDER BY day0_utc DESC")


def units(db: MetaDB, experiment: str, unblind: bool) -> pd.DataFrame:
    df = db.allocation(experiment, blinded=not unblind)
    df["label"] = df["treatment"] + " (pod " + df["pod"].astype(str) + ")" if unblind else df["blind_code"]
    return df


def create_experiment(db: MetaDB, year: int, code: str, study: str, title: str, data_class: str, treatments: dict[str, dict],
                      allocation: dict[int, str] | None, day0_utc: str, seed: int, hypothesis: str = "", onset_day: int = 0) -> str:
    """Create experiment, treatments, units and plant IDs. If `allocation` is None the pods are
    randomised: Latin-square row when #treatments == #pods (4), otherwise balanced random."""
    exp = naming.experiment_id(year, code)
    db.create_experiment(exp, study, title, data_class, hypothesis=hypothesis, day0_utc=day0_utc, randomization_seed=seed)
    for tcode, t in treatments.items():
        db.add_treatment(exp, tcode, t.get("description", ""), t["recipe"], 0 if tcode == "C" else onset_day)
    if allocation is None:
        codes = list(treatments)
        if len(codes) == 4:
            allocation = {i + 1: c for i, c in enumerate(latin_square(codes, seed).iloc[0])}
        elif len(codes) == 2:
            allocation = {i + 1: c for i, c in enumerate(balanced_crossover(tuple(codes), 4, 2, seed).iloc[0])}
        else:
            rng = np.random.default_rng(seed)
            allocation = {i + 1: c for i, c in enumerate(rng.permutation([codes[i % len(codes)] for i in range(4)]))}
    db.assign_units(exp, allocation, seed=seed)
    db.x("INSERT OR REPLACE INTO imaging_schedule (experiment_id) VALUES (?)", (exp,))
    return exp


def set_imaging_schedule(db: MetaDB, experiment: str, interval_min: int, start_min: int, end_min: int, stereo: bool, enabled: bool = True):
    db.x("INSERT OR REPLACE INTO imaging_schedule VALUES (?,?,?,?,?,?)", (experiment, interval_min, start_min, end_min, int(stereo), int(enabled)))


def current_conditions(store: Store, experiment: str) -> pd.DataFrame:
    m = store.read_processed(experiment, "sensors_1min")
    if m.empty:
        return m
    last = m.sort_values("utc").groupby("pod").tail(1)
    cols = [c for c in ("pod", "utc", "air_t", "rh", "co2", "ppfd", "sol_t", "ph", "ec", "led_w", "act_w", "faults") if c in last]
    return last[cols].reset_index(drop=True)


def history(store: Store, experiment: str, column: str, resample: str = "30min") -> pd.DataFrame:
    m = store.read_processed(experiment, "sensors_1min")
    if m.empty or column not in m:
        return pd.DataFrame()
    m["utc"] = pd.to_datetime(m["utc"], utc=True)
    w = m.pivot_table(index="utc", columns="pod", values=column).resample(resample).mean()
    w.columns = [f"pod {c}" for c in w.columns]
    return w


def growth_curves(store: Store, db: MetaDB, experiment: str, trait: str = "projected_area_cm2", unblind: bool = False) -> pd.DataFrame:
    t = store.read_processed(experiment, "traits")
    if t.empty or trait not in t:
        return pd.DataFrame()
    t["day"] = np.floor(t["t_day"]).astype(int)
    g = t.groupby(["unit_id", "day"])[trait].mean().reset_index().merge(units(db, experiment, unblind)[["unit_id", "label"]], on="unit_id")
    return g.pivot_table(index="day", columns="label", values=trait)


def resources(store: Store, experiment: str) -> pd.DataFrame:
    d = store.read_processed(experiment, "daily_env")
    if d.empty:
        return d
    cols = [c for c in ("kwh_led", "kwh_act", "water_use_g") if c in d]
    out = d.groupby("unit_id")[cols].sum().reset_index()
    if {"kwh_led", "kwh_act"} <= set(out):
        out["kwh_total_dc"] = out["kwh_led"] + out["kwh_act"]
    return out


def progress(db: MetaDB, experiment: str, days_planned: int = 28) -> dict:
    e = db.q("SELECT * FROM experiment WHERE experiment_id=?", (experiment,)).iloc[0]
    n_img = int(db.q("SELECT COUNT(*) n FROM image WHERE experiment_id=?", (experiment,)).n[0])
    n_man = int(db.q("SELECT COUNT(*) n FROM manual_measurement m JOIN plant p USING (plant_id) JOIN unit u USING (unit_id) WHERE u.experiment_id=?", (experiment,)).n[0])
    day = None
    if e["day0_utc"]:
        ref = pd.Timestamp(e["end_utc"]) if e["end_utc"] else pd.Timestamp(datetime.now(timezone.utc))
        d0 = pd.Timestamp(e["day0_utc"])
        ref = ref.tz_localize("UTC") if ref.tzinfo is None else ref
        d0 = d0.tz_localize("UTC") if d0.tzinfo is None else d0
        day = int((ref - d0).total_seconds() // 86400)
    return {"status": e["status"], "data_class": e["data_class"], "day": day, "days_planned": days_planned, "images": n_img, "manual_records": n_man}


def compare_conditions(db: MetaDB, experiment: str, quantity: str = "shoot_dry_mass") -> pd.DataFrame:
    """Unit-level means of a manual quantity by treatment (requires unblinding). Descriptive only:
    inference belongs to the pre-specified analysis scripts, not to the dashboard."""
    return db.q("""SELECT t.code AS treatment, u.pod, AVG(m.value) AS unit_mean, COUNT(*) AS n_plants
                   FROM manual_measurement m JOIN plant p USING (plant_id) JOIN unit u USING (unit_id) JOIN treatment t USING (treatment_id)
                   WHERE u.experiment_id=? AND m.quantity=? GROUP BY u.unit_id ORDER BY t.code""", (experiment, quantity))


def predictions(db: MetaDB, experiment: str) -> pd.DataFrame:
    return db.q("""SELECT pr.*, mr.model FROM prediction pr JOIN model_run mr USING (model_run_id)
                   LEFT JOIN unit u ON u.unit_id = pr.unit_id WHERE u.experiment_id=? ORDER BY issued_utc""", (experiment,))


def model_runs(db: MetaDB) -> pd.DataFrame:
    df = db.q("SELECT * FROM model_run ORDER BY created_utc DESC")
    if not df.empty:
        df["metrics"] = df["metrics_json"].map(lambda s: json.loads(s) if s else {})
    return df


def what_if(ppfd: float, photoperiod_h: float, air_t_day: float, air_t_night: float, rh: float, ec: float, days: int = 28, room_t: float = 20.0) -> tuple[pd.DataFrame, dict]:
    """Digital-twin scenario: returns the predicted trajectory and summary (provenance = predicted)."""
    tw = PodTwin(room_t=room_t)
    df = tw.run(Recipe(days=days, ppfd=ppfd, photoperiod_h=photoperiod_h, air_t_day=air_t_day, air_t_night=air_t_night, rh=rh, ec=ec), dt_s=120.0, log_every_s=3600.0)
    return df, tw.summary(df)


def export(db: MetaDB, store: Store, exps: list[str], out_dir: str, version: str) -> str:
    return str(export_dataset(db, store, exps, out_dir, version))
