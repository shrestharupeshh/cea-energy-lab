"""Simulation-based power analysis for the planned designs.

These are planning calculations under ASSUMED variance components. They are not results.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .design import balanced_crossover, latin_square
from .inference import dunnett_critical, latin_square_anova


def _unit_sd(cv_unit: float, cv_plant: float, n_plants: int) -> float:
    return float(np.sqrt(cv_unit**2 + cv_plant**2 / n_plants))


def latin_square_power(effect_ratio: float, cv_unit=0.08, cv_plant=0.15, cv_run=0.10, cv_pod=0.05,
                       n_plants=6, n_trt=4, n_sim=1000, seed=0) -> float:
    """Power to detect one treatment whose true mean is effect_ratio x control (others = control),
    Dunnett-adjusted, on log pod-run means in an n_trt x n_trt Latin square."""
    rng = np.random.default_rng(seed)
    trts = ["C"] + [f"T{i}" for i in range(1, n_trt)]
    sd_u = _unit_sd(cv_unit, cv_plant, n_plants)
    df_res = (n_trt - 1) * (n_trt - 2)
    crit = dunnett_critical(n_trt - 1, df_res, n_sim=100_000)
    hits = 0
    for s in range(n_sim):
        sq = latin_square(trts, seed=int(rng.integers(1 << 31)))
        run_e = rng.normal(0, cv_run, n_trt)
        pod_e = rng.normal(0, cv_pod, n_trt)
        y = np.zeros((n_trt, n_trt))
        for i in range(n_trt):
            for j in range(n_trt):
                mu = np.log(effect_ratio) if sq.iat[i, j] == "T1" else 0.0
                y[i, j] = mu + run_e[i] + pod_e[j] + rng.normal(0, sd_u)
        # closed-form Latin square contrast
        t_means = {t: y[sq.to_numpy() == t].mean() for t in trts}
        g = y.mean()
        fitted = y.mean(axis=1)[:, None] + y.mean(axis=0)[None, :] + np.vectorize(t_means.get)(sq.to_numpy()) - 2 * g
        mse = ((y - fitted) ** 2).sum() / df_res
        tval = (t_means["T1"] - t_means["C"]) / np.sqrt(2 * mse / n_trt)
        hits += abs(tval) > crit
    return hits / n_sim


def crossover_power(effect_ratio: float, n_runs=4, n_pods=4, cv_unit=0.08, cv_plant=0.15, cv_run=0.10,
                    cv_pod=0.05, n_plants=6, one_sided=True, alpha=0.05, n_sim=2000, seed=0) -> float:
    """Power for the two-treatment design of Study C (log scale, run and pod as blocks)."""
    from scipy import stats
    rng = np.random.default_rng(seed)
    sd_u = _unit_sd(cv_unit, cv_plant, n_plants)
    df_res = n_runs * n_pods - 1 - (n_runs - 1) - (n_pods - 1) - 1
    crit = stats.t.ppf(1 - alpha if one_sided else 1 - alpha / 2, df_res)
    hits = 0
    for _ in range(n_sim):
        d = balanced_crossover(("F", "A"), n_pods, n_runs, seed=int(rng.integers(1 << 31))).to_numpy()
        is_a = (d == "A").astype(float)
        y = np.log(effect_ratio) * is_a + rng.normal(0, cv_run, n_runs)[:, None] + rng.normal(0, cv_pod, n_pods)[None, :] \
            + rng.normal(0, sd_u, d.shape)
        # OLS with run and pod blocks
        x = np.column_stack([np.ones(d.size), is_a.ravel(),
                             *(np.repeat(np.eye(n_runs)[:, 1:], n_pods, axis=0).T),
                             *(np.tile(np.eye(n_pods)[:, 1:], (n_runs, 1)).T)])
        beta, res, *_ = np.linalg.lstsq(x, y.ravel(), rcond=None)
        resid = y.ravel() - x @ beta
        mse = resid @ resid / df_res
        se = np.sqrt(mse * np.linalg.inv(x.T @ x)[1, 1])
        t = beta[1] / se
        hits += (-t > crit) if one_sided else (abs(t) > crit)
    return hits / n_sim


def power_table() -> pd.DataFrame:
    rows = []
    for ratio in (0.85, 0.80, 0.70, 0.60, 0.50):
        for cv_u in (0.05, 0.08, 0.12):
            rows.append({"design": "Study A 4x4 Latin square (Dunnett, 2-sided)", "true_ratio": ratio,
                         "cv_unit": cv_u, "power": latin_square_power(ratio, cv_unit=cv_u, n_sim=600, seed=11)})
    for ratio in (0.90, 0.85, 0.80):
        for runs in (4, 6):
            for cv_u in (0.05, 0.08):
                rows.append({"design": f"Study C crossover {runs} runs (1-sided)", "true_ratio": ratio,
                             "cv_unit": cv_u, "power": crossover_power(ratio, n_runs=runs, cv_unit=cv_u, n_sim=1500, seed=12)})
    return pd.DataFrame(rows)
