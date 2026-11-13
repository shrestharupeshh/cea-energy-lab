"""Automated processing: raw 1 Hz frames -> calibrated, QC-flagged 1-minute records -> daily summaries.

Idempotent: processed tables are rebuilt from raw files and the calibration table, so re-running
after a calibration correction reproduces the processed data exactly (raw is never touched).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import validation
from .calibration import apply_coeffs

# raw column -> (calibrated column, sensor kind used to look up the calibration)
CAL_MAP = {"par_raw": ("ppfd", "par"), "res_raw": ("res_g", "loadcell"), "air_t": ("air_t", "air_t"), "rh": ("rh", "rh"),
           "sol_t": ("sol_t", "sol_t"), "ph": ("ph", "ph"), "ec": ("ec", "ec"), "co2": ("co2", "co2")}
MEAN_COLS = ["air_t", "rh", "co2", "ppfd", "sol_t", "ph", "ec", "res_g", "flow_hz", "led_w", "act_w", "u_heat", "u_fan", "u_led"]
LAST_COLS = ["led_wh", "act_wh", "mode"]
MAX_COLS = ["faults", "door", "leak", "humid", "topup"]


def _calibrate(db, df: pd.DataFrame, pod: int) -> pd.DataFrame:
    out = df.copy()
    t = pd.to_datetime(out["utc"], utc=True)
    for raw_col, (cal_col, kind) in CAL_MAP.items():
        if raw_col not in out:
            continue
        cal = db.q("SELECT c.* FROM calibration c JOIN sensor s USING (sensor_id) WHERE s.pod=? AND s.kind=? ORDER BY valid_from_utc", (pod, kind))
        vals = np.full(len(out), np.nan)
        uncal = np.ones(len(out), bool)
        for _, c in cal.iterrows():
            lo = pd.Timestamp(c["valid_from_utc"])
            hi = pd.Timestamp(c["valid_to_utc"]) if c["valid_to_utc"] else pd.Timestamp("2262-01-01", tz="UTC")
            m = ((t >= lo) & (t < hi)).to_numpy()
            vals[m] = apply_coeffs(out.loc[m, raw_col], json.loads(c["coeffs_json"]))
            uncal[m] = False
        if uncal.all() and raw_col == cal_col:
            vals = out[raw_col].to_numpy(float)          # sensors reporting engineering units: pass through, flagged
        elif uncal.any() and raw_col == cal_col:
            vals[uncal] = out.loc[uncal, raw_col].to_numpy(float)
        out[cal_col] = vals
        out[f"{cal_col}_uncal"] = uncal
    return out


def process_sensors(db, store, experiment: str, freq: str = "1min") -> pd.DataFrame:
    raw = store.read_raw(experiment)
    if raw.empty:
        return raw
    parts = []
    for pod, g in raw.groupby("pod"):
        g = _calibrate(db, g.sort_values("utc"), int(pod))
        g = validation.validate_frame(g)
        g = g.set_index(pd.to_datetime(g["utc"], utc=True))
        agg = {}
        for c in MEAN_COLS:
            if c in g:
                good = g[c].where(g.get(f"{c}_qc", 0) & (validation.QC_RANGE | validation.QC_SPIKE | validation.QC_MISSING) == 0) if f"{c}_qc" in g else g[c]
                agg[c] = good.resample(freq).mean()
                agg[f"{c}_n"] = good.resample(freq).count()
                if f"{c}_qc" in g:
                    agg[f"{c}_qc"] = g[f"{c}_qc"].resample(freq).agg(lambda s: int(np.bitwise_or.reduce(s.to_numpy(np.int64))) if len(s) else validation.QC_MISSING)
        for c in LAST_COLS:
            if c in g:
                agg[c] = g[c].resample(freq).last()
        for c in MAX_COLS:
            if c in g:
                agg[c] = g[c].resample(freq).max()
        m = pd.DataFrame(agg)
        m.insert(0, "pod", int(pod))
        m["unit_id"] = f"{experiment}-P{int(pod):02d}"
        m["experiment_id"] = experiment
        # minutes with no frames at all
        for c in MEAN_COLS:
            if f"{c}_qc" in m:
                m.loc[m[f"{c}_n"] == 0, f"{c}_qc"] = m.loc[m[f"{c}_n"] == 0, f"{c}_qc"].fillna(0).astype(int) | validation.QC_MISSING
        parts.append(m.reset_index(names="utc"))
    out = pd.concat(parts, ignore_index=True)
    store.write_processed(experiment, "sensors_1min", out)
    return out


def daily_summary(db, minute: pd.DataFrame, experiment: str) -> pd.DataFrame:
    """Per unit and experiment day: environment means in light/dark, DLI, energy, water use."""
    exp = db.q("SELECT day0_utc FROM experiment WHERE experiment_id=?", (experiment,))
    day0 = pd.Timestamp(exp["day0_utc"].iloc[0])
    day0 = day0.tz_localize("UTC") if day0.tzinfo is None else day0
    m = minute.copy()
    m["day"] = ((pd.to_datetime(m["utc"], utc=True) - day0).dt.total_seconds() // 86400).astype(int)
    rows = []
    for (unit, day), g in m.groupby(["unit_id", "day"]):
        lit = g["ppfd"] > 5 if "ppfd" in g else pd.Series(False, index=g.index)
        row = {"unit_id": unit, "day": int(day), "n_minutes": len(g),
               "air_t_light": g.loc[lit, "air_t"].mean(), "air_t_dark": g.loc[~lit, "air_t"].mean(),
               "rh_mean": g["rh"].mean(), "co2_light": g.loc[lit, "co2"].mean() if "co2" in g else np.nan,
               "ppfd_light": g.loc[lit, "ppfd"].mean() if "ppfd" in g else np.nan, "photoperiod_h": lit.sum() / 60,
               "dli": g["ppfd"].clip(lower=0).sum() * 60 / 1e6 if "ppfd" in g else np.nan,
               "sol_t_mean": g["sol_t"].mean() if "sol_t" in g else np.nan,
               "ph_mean": g["ph"].mean() if "ph" in g else np.nan, "ec_mean": g["ec"].mean() if "ec" in g else np.nan}
        for rail in ("led", "act"):
            if f"{rail}_w" in g:
                row[f"kwh_{rail}"] = g[f"{rail}_w"].sum() / 60 / 1000
        if "res_g" in g and g["res_g"].notna().sum() > 10:
            # water use = sum of negative reservoir mass steps (refills are positive steps and are ignored)
            d = g["res_g"].rolling(5, center=True, min_periods=1).median().diff()
            row["water_use_g"] = float(-d[d < 0].sum())
        vpd = 610.94 * np.exp(17.625 * g["air_t"] / (g["air_t"] + 243.04)) * (1 - g["rh"] / 100) / 1000
        row["vpd_kpa"] = vpd.mean()
        rows.append(row)
    return pd.DataFrame(rows)
