"""Growth rates and temporal change from per-plant trait time series."""
from __future__ import annotations

import numpy as np
import pandas as pd


def relative_growth_rate(t_days, value, window_days: float = 3.0) -> np.ndarray:
    """Local RGR (d-1): slope of ln(value) vs time in a centred window, by least squares.
    NaN where fewer than 3 valid points are available."""
    t = np.asarray(t_days, float)
    y = np.log(np.where(np.asarray(value, float) > 0, value, np.nan))
    out = np.full(len(t), np.nan)
    for i in range(len(t)):
        m = (np.abs(t - t[i]) <= window_days / 2) & np.isfinite(y)
        if m.sum() >= 3 and np.ptp(t[m]) > 0:
            out[i] = np.polyfit(t[m], y[m], 1)[0]
    return out


def daily_traits(traits: pd.DataFrame, value_cols: list[str], time_col: str = "t_day", by: str = "plant_id",
                 qc_mask: int = 0b10010) -> pd.DataFrame:
    """Robust daily value per plant: median of the within-day images that pass QC (blur/exposure)."""
    d = traits.copy()
    if "qc" in d:
        d = d[(d["qc"].astype(int) & qc_mask) == 0]
    d["day"] = np.floor(d[time_col]).astype(int)
    return d.groupby([by, "day"], as_index=False)[value_cols].median()


def add_growth_features(daily: pd.DataFrame, col: str = "projected_area_cm2", by: str = "plant_id") -> pd.DataFrame:
    out = []
    for _, g in daily.sort_values("day").groupby(by):
        g = g.copy()
        g[f"rgr_{col}"] = relative_growth_rate(g["day"], g[col])
        g[f"d_{col}"] = g[col].diff() / g["day"].diff()
        g[f"rgr_change_{col}"] = g[f"rgr_{col}"].diff()
        out.append(g)
    return pd.concat(out, ignore_index=True)
