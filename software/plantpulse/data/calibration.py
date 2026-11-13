"""Apply sensor calibration records to raw values. Raw values are never overwritten."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd


def apply_coeffs(raw, coeffs: dict):
    raw = np.asarray(raw, float)
    kind = coeffs.get("type", "linear")
    if kind == "linear":
        return coeffs.get("gain", 1.0) * raw + coeffs.get("offset", 0.0)
    if kind == "poly":
        return np.polyval(coeffs["c"], raw)
    if kind == "two_point":            # e.g. load cell: counts at zero and at a reference mass
        return (raw - coeffs["raw0"]) * coeffs["ref"] / (coeffs["raw_ref"] - coeffs["raw0"])
    raise ValueError(f"unknown calibration type {kind}")


def fit_linear(raw, reference) -> dict:
    """Least-squares gain/offset against a reference instrument, with residual SD as u_standard."""
    raw, reference = np.asarray(raw, float), np.asarray(reference, float)
    gain, offset = np.polyfit(raw, reference, 1)
    resid = reference - (gain * raw + offset)
    return {"coeffs": {"type": "linear", "gain": float(gain), "offset": float(offset)},
            "u_standard": float(resid.std(ddof=2)) if len(raw) > 2 else float("nan"), "n": int(len(raw))}


def calibrate_series(db, sensor_id: str, t_utc: pd.Series, raw: pd.Series) -> pd.DataFrame:
    """Return calibrated values plus the calibration id used for each sample and an 'uncalibrated' mask."""
    cal = db.q("SELECT * FROM calibration WHERE sensor_id=? ORDER BY valid_from_utc", (sensor_id,))
    out = pd.DataFrame({"value": np.full(len(raw), np.nan), "calibration_id": pd.array([pd.NA] * len(raw), dtype="Int64")}, index=raw.index)
    t = pd.to_datetime(t_utc, utc=True)
    for _, c in cal.iterrows():
        lo = pd.Timestamp(c["valid_from_utc"])
        hi = pd.Timestamp(c["valid_to_utc"]) if c["valid_to_utc"] else pd.Timestamp.max.tz_localize("UTC")
        m = (t >= lo) & (t < hi)
        out.loc[m.to_numpy(), "value"] = apply_coeffs(raw[m.to_numpy()], json.loads(c["coeffs_json"]))
        out.loc[m.to_numpy(), "calibration_id"] = int(c["calibration_id"])
    out["uncalibrated"] = out["calibration_id"].isna()
    return out
