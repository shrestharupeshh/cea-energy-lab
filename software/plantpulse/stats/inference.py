"""Unit-level inference for the planned designs (experimental unit = pod-run)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats


def unit_means(df: pd.DataFrame, value: str, keys=("run", "pod", "treatment")) -> pd.DataFrame:
    """Collapse plant-level data to pod-run means (the experimental units)."""
    return df.groupby(list(keys), as_index=False)[value].mean()


def dunnett_critical(k: int, df: int, alpha: float = 0.05, n_sim: int = 200_000, seed: int = 1) -> float:
    """Two-sided Dunnett critical value for k comparisons with a common control (equal n), by
    Monte Carlo on the multivariate t distribution (correlation 0.5)."""
    rng = np.random.default_rng(seed)
    z0 = rng.standard_normal(n_sim)
    z = (rng.standard_normal((n_sim, k)) - z0[:, None]) / np.sqrt(2)
    s = np.sqrt(rng.chisquare(df, n_sim) / df)
    return float(np.quantile(np.abs(z / s[:, None]).max(axis=1), 1 - alpha))


def latin_square_anova(units: pd.DataFrame, value: str, control: str, log: bool = True, alpha: float = 0.05) -> dict:
    """Classical Latin-square analysis on pod-run means with Dunnett-adjusted contrasts vs control.

    `units` has columns run, pod, treatment, <value>; one row per pod-run.
    """
    d = units.copy()
    d["_y"] = np.log(d[value]) if log else d[value]
    fit = smf.ols("_y ~ C(treatment, Treatment(reference='%s')) + C(run) + C(pod)" % control, data=d).fit()
    k = d["treatment"].nunique() - 1
    crit = dunnett_critical(k, int(fit.df_resid), alpha)
    rows = []
    for name in fit.params.index:
        if not name.startswith("C(treatment"):
            continue
        trt = name.split("[T.")[1].rstrip("]")
        est, se = fit.params[name], fit.bse[name]
        lo, hi = est - crit * se, est + crit * se
        rows.append({"treatment": trt, "estimate": est, "se": se, "t": est / se,
                     "ci_low": lo, "ci_high": hi, "significant": abs(est / se) > crit,
                     "ratio": np.exp(est) if log else np.nan,
                     "ratio_ci": (np.exp(lo), np.exp(hi)) if log else None})
    return {"contrasts": pd.DataFrame(rows), "df_resid": int(fit.df_resid), "mse": float(fit.mse_resid),
            "dunnett_crit": crit, "model": fit}


def variance_components(df: pd.DataFrame, value: str) -> dict:
    """Uniformity-trial variance components: run, pod, run x pod (unit), plant (residual).
    Method-of-moments estimates for a balanced design."""
    g = df[value].mean()
    r, p = df["run"].nunique(), df["pod"].nunique()
    n = len(df) / (r * p)
    cell = df.groupby(["run", "pod"])[value].mean()
    ms_e = ((df[value] - df.set_index(["run", "pod"]).index.map(cell).to_numpy()) ** 2).sum() / (len(df) - r * p)
    run_m, pod_m = df.groupby("run")[value].mean(), df.groupby("pod")[value].mean()
    ms_r = p * n * ((run_m - g) ** 2).sum() / max(r - 1, 1)
    ms_p = r * n * ((pod_m - g) ** 2).sum() / max(p - 1, 1)
    inter = cell - cell.index.get_level_values(0).map(run_m).to_numpy() - cell.index.get_level_values(1).map(pod_m).to_numpy() + g
    ms_rp = n * (inter**2).sum() / max((r - 1) * (p - 1), 1)
    v_e = ms_e
    v_rp = max((ms_rp - ms_e) / n, 0.0)
    v_p = max((ms_p - ms_rp) / (r * n), 0.0)
    v_r = max((ms_r - ms_rp) / (p * n), 0.0)
    tot = v_e + v_rp + v_p + v_r
    return {"var_plant": v_e, "var_unit": v_rp, "var_pod": v_p, "var_run": v_r, "icc_pod": v_p / tot if tot else np.nan,
            "cv_plant_pct": 100 * np.sqrt(v_e) / g, "cv_unit_pct": 100 * np.sqrt(v_rp + v_p) / g, "grand_mean": g}


def cluster_bootstrap_diff(err_a: pd.Series, err_b: pd.Series, clusters: pd.Series, n_boot: int = 10_000, seed: int = 0) -> dict:
    """Paired difference in mean absolute error between two models, resampling whole clusters."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"d": np.abs(err_a.to_numpy()) - np.abs(err_b.to_numpy()), "c": clusters.to_numpy()})
    sums = df.groupby("c")["d"].agg(["sum", "count"]).to_numpy()
    idx = rng.integers(0, len(sums), size=(n_boot, len(sums)))
    boots = sums[idx, 0].sum(axis=1) / sums[idx, 1].sum(axis=1)
    return {"diff": df["d"].mean(), "ci_low": float(np.quantile(boots, 0.025)), "ci_high": float(np.quantile(boots, 0.975)),
            "n_clusters": len(sums)}


def noninferiority_ratio(log_diff: float, se: float, df: int, margin_ratio: float = 0.90, alpha: float = 0.05) -> dict:
    """One-sided non-inferiority test on a log ratio (treatment/control)."""
    lower = log_diff - stats.t.ppf(1 - alpha, df) * se
    return {"ratio": float(np.exp(log_diff)), "lower_bound": float(np.exp(lower)), "non_inferior": bool(np.exp(lower) > margin_ratio)}
