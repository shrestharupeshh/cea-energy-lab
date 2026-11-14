"""Evaluation metrics with cluster (experimental-unit) bootstrap confidence intervals."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def regression_metrics(y, yhat) -> dict:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    e = yhat - y
    ss_tot = np.sum((y - y.mean()) ** 2)
    return {"n": len(y), "mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e**2).mean())), "bias": float(e.mean()),
            "mape": float(100 * np.mean(np.abs(e) / np.maximum(np.abs(y), 1e-9))),
            "r2": float(1 - np.sum(e**2) / ss_tot) if ss_tot > 0 else float("nan")}


def cluster_bootstrap(df: pd.DataFrame, fn, cluster: str = "unit_id", n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> dict:
    """Percentile CI of a statistic fn(df) -> float, resampling whole clusters with replacement."""
    rng = np.random.default_rng(seed)
    groups = [g for _, g in df.groupby(cluster)]
    stats = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        try:
            stats.append(fn(pd.concat([groups[i] for i in pick], ignore_index=True)))
        except ValueError:
            continue
    stats = np.asarray(stats, float)
    stats = stats[np.isfinite(stats)]
    return {"estimate": float(fn(df)), "ci_low": float(np.quantile(stats, alpha / 2)), "ci_high": float(np.quantile(stats, 1 - alpha / 2)),
            "n_clusters": len(groups), "n_boot_valid": int(len(stats))}


def classification_metrics(y, p) -> dict:
    y, p = np.asarray(y, int), np.asarray(p, float)
    if len(np.unique(y)) < 2:
        return {"n": len(y), "auroc": float("nan"), "auprc": float("nan"), "brier": float(brier_score_loss(y, p)) if len(y) else float("nan")}
    return {"n": len(y), "auroc": float(roc_auc_score(y, p)), "auprc": float(average_precision_score(y, p)), "brier": float(brier_score_loss(y, p))}


def detection_days(scores: pd.DataFrame, threshold: float, score_col: str = "score", persist: int = 2) -> pd.DataFrame:
    """First day on which each unit's score exceeds the threshold for `persist` consecutive days.
    scores: columns unit_id, day, <score_col>. Returns unit_id, detect_day (NaN if never)."""
    rows = []
    for unit, g in scores.sort_values("day").groupby("unit_id"):
        above = (g[score_col] > threshold).to_numpy()
        run, day = 0, np.nan
        for d, a in zip(g["day"].to_numpy(), above):
            run = run + 1 if a else 0
            if run >= persist:
                day = d - persist + 1
                break
        rows.append({"unit_id": unit, "detect_day": day})
    return pd.DataFrame(rows)


def threshold_for_false_alarm_budget(control_scores: pd.DataFrame, max_false_alarms_per_unit: float = 1.0, score_col: str = "score",
                                     persist: int = 2) -> float:
    """Smallest threshold whose alarm count on control units does not exceed the budget (alarms are
    counted as distinct excursions of at least `persist` days)."""
    cands = np.unique(np.round(control_scores[score_col].dropna().to_numpy(), 6))
    n_units = control_scores["unit_id"].nunique()
    for thr in cands:
        alarms = 0
        for _, g in control_scores.sort_values("day").groupby("unit_id"):
            a = (g[score_col] > thr).to_numpy().astype(int)
            run = 0
            for v in a:
                run = run + 1 if v else 0
                alarms += run == persist
        if alarms / n_units <= max_false_alarms_per_unit:
            return float(thr)
    return float(cands[-1]) if len(cands) else float("inf")


def lead_time(detect: pd.DataFrame, reference_onset: pd.DataFrame) -> pd.DataFrame:
    """lead = reference_onset_day - detect_day (positive = detected before the reference event)."""
    m = detect.merge(reference_onset, on="unit_id", how="inner")
    m["lead_days"] = m["reference_day"] - m["detect_day"]
    m["detected"] = m["detect_day"].notna()
    return m
