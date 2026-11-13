"""Measurement-agreement statistics (accuracy is not correlation)."""
from __future__ import annotations

import numpy as np
from scipy import stats


def agreement(reference, estimate) -> dict:
    """Agreement of an estimate with a reference method.

    Returns bias, limits of agreement (Bland-Altman), MAE, RMSE, MAPE, Lin's CCC, R^2 (information
    only) and the slope of difference-vs-mean (proportional bias) with its p-value.
    """
    x = np.asarray(reference, float)
    y = np.asarray(estimate, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 3:
        raise ValueError("need at least 3 paired observations")
    d = y - x
    bias, sd = d.mean(), d.std(ddof=1)
    t = stats.t.ppf(0.975, n - 1)
    sxy = np.cov(x, y, ddof=1)[0, 1]
    ccc = 2 * sxy / (x.var(ddof=1) + y.var(ddof=1) + (x.mean() - y.mean()) ** 2)
    ss_res, ss_tot = np.sum((x - y) ** 2), np.sum((x - x.mean()) ** 2)
    slope, _, _, p_slope, _ = stats.linregress((x + y) / 2, d)
    nz = x != 0
    return {
        "n": n, "bias": bias, "bias_ci": (bias - t * sd / np.sqrt(n), bias + t * sd / np.sqrt(n)),
        "loa_low": bias - 1.96 * sd, "loa_high": bias + 1.96 * sd,
        "loa_pct_of_mean": 100 * 1.96 * sd / x.mean() if x.mean() else np.nan,
        "bias_pct": 100 * bias / x.mean() if x.mean() else np.nan,
        "mae": np.abs(d).mean(), "rmse": np.sqrt((d**2).mean()),
        "mape": 100 * np.mean(np.abs(d[nz] / x[nz])) if nz.any() else np.nan,
        "ccc": ccc, "r2_identity": 1 - ss_res / ss_tot if ss_tot else np.nan,
        "pearson_r": float(np.corrcoef(x, y)[0, 1]),
        "prop_bias_slope": slope, "prop_bias_p": p_slope,
    }


def gauge_rr(values: np.ndarray) -> dict:
    """Repeatability/reproducibility from an array [parts, operators, repeats] (ANOVA method)."""
    v = np.asarray(values, float)
    p, o, r = v.shape
    cell = v.mean(axis=2)
    ms_e = ((v - cell[:, :, None]) ** 2).sum() / (p * o * (r - 1))
    ms_o = p * r * ((v.mean(axis=(0, 2)) - v.mean()) ** 2).sum() / (o - 1)
    ms_p = o * r * ((v.mean(axis=(1, 2)) - v.mean()) ** 2).sum() / (p - 1)
    ms_po = r * ((cell - v.mean(axis=(1, 2))[:, None] - v.mean(axis=(0, 2))[None, :] + v.mean()) ** 2).sum() / ((p - 1) * (o - 1))
    var_rep = ms_e
    var_po = max((ms_po - ms_e) / r, 0)
    var_o = max((ms_o - ms_po) / (p * r), 0)
    var_p = max((ms_p - ms_po) / (o * r), 0)
    return {"repeatability_sd": np.sqrt(var_rep), "reproducibility_sd": np.sqrt(var_o + var_po),
            "part_sd": np.sqrt(var_p), "grr_sd": np.sqrt(var_rep + var_o + var_po)}
