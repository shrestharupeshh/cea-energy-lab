"""Data validation and quality flags for sensor time series.

Flags are a bit field per value (column `<name>_qc`); 0 = passed all checks. Flagged values are
kept; downstream code decides what to mask. Thresholds are in CHECKS and are part of the dataset
metadata (exported with every dataset version).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

QC_MISSING, QC_RANGE, QC_SPIKE, QC_FLATLINE, QC_UNCALIBRATED, QC_DOOR_OPEN, QC_FAULT, QC_GAP_FILLED = (1 << i for i in range(8))
QC_NAMES = {QC_MISSING: "missing", QC_RANGE: "out_of_physical_range", QC_SPIKE: "spike", QC_FLATLINE: "flatline",
            QC_UNCALIBRATED: "uncalibrated", QC_DOOR_OPEN: "door_open", QC_FAULT: "node_fault", QC_GAP_FILLED: "gap_filled"}

# column: (physical min, physical max, Hampel threshold in robust SDs, flatline window in samples or None)
CHECKS = {
    "air_t": (5.0, 45.0, 6.0, 120), "rh": (5.0, 100.0, 6.0, 240), "co2": (250.0, 5000.0, 8.0, 240),
    "ppfd": (0.0, 600.0, 10.0, None), "sol_t": (5.0, 40.0, 6.0, None), "ph": (3.0, 9.0, 6.0, None),
    "ec": (0.0, 5000.0, 6.0, None), "res_g": (-50.0, 6000.0, 8.0, None), "flow_hz": (0.0, 500.0, 10.0, None),
    "led_w": (0.0, 150.0, 10.0, None), "act_w": (0.0, 250.0, 10.0, None),
}


def hampel(x: pd.Series, window: int = 15, n_sigma: float = 6.0) -> pd.Series:
    """Boolean mask of outliers relative to a rolling median (robust to the spikes themselves)."""
    med = x.rolling(window, center=True, min_periods=5).median()
    mad = (x - med).abs().rolling(window, center=True, min_periods=5).median()
    sigma = 1.4826 * mad
    floor = max(float(np.nanmedian(sigma)) if np.isfinite(sigma).any() else 0.0, 1e-9) * 0.5
    return ((x - med).abs() > n_sigma * np.maximum(sigma, floor)).fillna(False)


def flatline(x: pd.Series, window: int) -> pd.Series:
    """True where the value has not changed at all for `window` consecutive samples (stuck sensor)."""
    same = x.diff().abs() < 1e-12
    run = same.groupby((~same).cumsum()).cumsum()
    return run >= window


def find_gaps(utc: pd.Series, expected_s: float, tolerance: float = 2.5) -> pd.DataFrame:
    """Gaps longer than tolerance x expected interval. Returns start, end, duration_s, missing_samples."""
    t = pd.to_datetime(utc, utc=True).sort_values().reset_index(drop=True)
    dt = t.diff().dt.total_seconds()
    idx = dt[dt > tolerance * expected_s].index
    return pd.DataFrame({"start": t[idx - 1].to_numpy(), "end": t[idx].to_numpy(), "duration_s": dt[idx].to_numpy(),
                         "missing_samples": np.round(dt[idx].to_numpy() / expected_s - 1).astype(int)})


def completeness(utc: pd.Series, expected_s: float, start=None, end=None) -> float:
    t = pd.to_datetime(utc, utc=True)
    start, end = start or t.min(), end or t.max()
    expected = (end - start).total_seconds() / expected_s + 1
    return float(min(t.between(start, end).sum() / expected, 1.0)) if expected > 0 else float("nan")


def validate_frame(df: pd.DataFrame, checks: dict | None = None) -> pd.DataFrame:
    """Add `<col>_qc` columns to a single-pod, time-sorted frame."""
    checks = checks or CHECKS
    out = df.copy()
    door = out["door"].astype(bool) if "door" in out else pd.Series(False, index=out.index)
    fault = (out["faults"].fillna(0).astype(int) & 0b10) > 0 if "faults" in out else pd.Series(False, index=out.index)
    for col, (lo, hi, nsig, flat) in checks.items():
        if col not in out:
            continue
        x = out[col].astype(float)
        qc = np.zeros(len(out), dtype=np.int16)
        qc[x.isna().to_numpy()] |= QC_MISSING
        qc[((x < lo) | (x > hi)).to_numpy()] |= QC_RANGE
        qc[hampel(x, n_sigma=nsig).to_numpy()] |= QC_SPIKE
        if flat:
            qc[flatline(x, flat).to_numpy()] |= QC_FLATLINE
        if col in ("air_t", "rh", "co2"):
            qc[door.to_numpy()] |= QC_DOOR_OPEN
            qc[fault.to_numpy()] |= QC_FAULT
        if f"{col}_uncal" in out:
            qc[out[f"{col}_uncal"].astype(bool).to_numpy()] |= QC_UNCALIBRATED
        out[f"{col}_qc"] = qc
    return out


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in [c[:-3] for c in df.columns if c.endswith("_qc")]:
        q = df[f"{col}_qc"].to_numpy()
        row = {"column": col, "n": len(q), "pass_frac": float((q == 0).mean())}
        row.update({name: int(((q & bit) > 0).sum()) for bit, name in QC_NAMES.items()})
        rows.append(row)
    return pd.DataFrame(rows)


def environment_excursions(df: pd.DataFrame, setpoints: dict, tol: dict | None = None) -> dict:
    """Cumulative hours outside tolerance of setpoint (exclusion rule in the SAP)."""
    tol = tol or {"air_t": 3.0, "ppfd_rel": 0.20}
    dt_h = pd.to_datetime(df["utc"], utc=True).diff().dt.total_seconds().median() / 3600
    out = {}
    if "air_t" in df and "air_t_sp" in df:
        out["air_t_hours"] = float(((df["air_t"] - df["air_t_sp"]).abs() > tol["air_t"]).sum() * dt_h)
    if "ppfd" in df and "ppfd_sp" in df:
        lit = df["ppfd_sp"] > 1
        out["ppfd_hours"] = float((((df["ppfd"] - df["ppfd_sp"]).abs() / df["ppfd_sp"].where(lit)) > tol["ppfd_rel"]).sum() * dt_h)
    out["exclude_unit"] = any(v > 6.0 for v in out.values())
    return out
