"""Parameter estimation for the crop model from measured growth data.

Fits a small, identifiable subset of parameters (default: light-use efficiency scale, growth-rate
constant, observable SLA) by non-linear least squares on log dry mass and log leaf area, and
reports asymptotic standard errors and, optionally, a cluster bootstrap over experimental units.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from . import crop as cropm

DEFAULT_FREE = {"c_eps": (8e-6, 30e-6), "c_gr_max": (2e-6, 1.2e-5), "sla_obs": (0.015, 0.07)}


@dataclass
class Series:
    """One experimental unit's inputs and observations. Daily resolution.
    obs: DataFrame with columns day (1-based, end of day), and any of shoot_dw_g, leaf_area_cm2."""
    unit: str
    ppfd: np.ndarray
    photoperiod_h: np.ndarray
    t_day: np.ndarray
    t_night: np.ndarray
    obs: pd.DataFrame
    co2: float = 420.0
    ec: np.ndarray | float | None = None
    init_shoot_dw: float = 0.06


def _predict(series: Series, p: cropm.CropParams) -> dict:
    days = len(series.ppfd)
    r = cropm.simulate_schedule(days, series.ppfd, series.photoperiod_h, series.t_day, series.t_night, series.co2,
                                series.ec, 70.0, p, series.init_shoot_dw)
    idx = r["day_end_index"]
    return {"shoot_dw_g": r["shoot_dw_g"][idx], "leaf_area_cm2": r["leaf_area_cm2"][idx]}


def residuals(theta, names, base: cropm.CropParams, data: list[Series], weights=None):
    p = base.with_(**dict(zip(names, theta)))
    weights = weights or {"shoot_dw_g": 1.0, "leaf_area_cm2": 1.0}
    out = []
    for s in data:
        pred = _predict(s, p)
        d = s.obs["day"].to_numpy(int) - 1
        for col, w in weights.items():
            if col in s.obs:
                y = s.obs[col].to_numpy(float)
                ok = np.isfinite(y) & (y > 0)
                out.append(w * (np.log(pred[col][d[ok]]) - np.log(y[ok])))
    return np.concatenate(out)


def fit(data: list[Series], base: cropm.CropParams = cropm.CropParams(), free: dict | None = None, weights=None) -> dict:
    free = free or DEFAULT_FREE
    names = list(free)
    x0 = np.array([getattr(base, n) for n in names])
    lo, hi = np.array([free[n][0] for n in names]), np.array([free[n][1] for n in names])
    sol = least_squares(residuals, x0, bounds=(lo, hi), x_scale=x0, args=(names, base, data, weights))
    n, k = len(sol.fun), len(names)
    s2 = float(sol.fun @ sol.fun) / max(n - k, 1)
    try:
        cov = s2 * np.linalg.inv(sol.jac.T @ sol.jac)
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        cov, se = None, np.full(k, np.nan)
    return {"params": base.with_(**dict(zip(names, sol.x))), "estimates": dict(zip(names, sol.x)), "se": dict(zip(names, se)),
            "cov": cov, "rmse_log": float(np.sqrt(np.mean(sol.fun**2))), "n_obs": n, "success": bool(sol.success),
            "note": "asymptotic SEs assume independent residuals; prefer the unit bootstrap for inference"}


def bootstrap(data: list[Series], n_boot: int = 200, seed: int = 0, **kw) -> pd.DataFrame:
    """Resample experimental units with replacement; returns the bootstrap distribution of estimates."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_boot):
        sample = [data[i] for i in rng.integers(0, len(data), len(data))]
        rows.append(fit(sample, **kw)["estimates"])
    return pd.DataFrame(rows)
