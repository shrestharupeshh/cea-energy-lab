"""The five modelling tasks (Models A-E) expressed on the common feature tables.

Each function returns (summary DataFrame, out-of-fold predictions). Splits are grouped at the
level given (default leave-one-run-out); see splits.py. Limitations that apply to every model:
small number of independent units, single cultivar, single platform; performance on another
platform or cultivar is unknown until tested.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import features as F
from . import metrics as M
from .models import classifiers, compare_models, cv_predict, regressors


def _avail(df, cols):
    return [c for c in cols if c in df.columns and df[c].notna().any()]


# ----------------------------------------------------------------------------- Model D: biomass from non-destructive data
def biomass_models(harvest_table: pd.DataFrame, target: str = "shoot_fresh_mass", level: str = "experiment_id", seed: int = 0):
    """harvest_table: one row per harvested plant with image features from the last pre-harvest image
    day, environment summaries, and the destructive target. Baseline = allometric log-log regression
    on projected area alone."""
    feats = _avail(harvest_table, F.IMAGE_FEATURES[:14] + ["cum_dli", "thermal_time", "day"])
    df = harvest_table.dropna(subset=[target, "projected_area_cm2"])
    df = df[(df[target] > 0) & (df["projected_area_cm2"] > 0.5)].reset_index(drop=True)
    df["log_area"] = np.log(df["projected_area_cm2"])
    models = regressors(seed)
    summary, preds = compare_models(df, feats, target, models, level, log_target=True)
    base, bp = compare_models(df, ["log_area"], target, {"allometric_area_only": models["linear"]}, level, log_target=True)
    preds["allometric_area_only"] = bp["allometric_area_only"]
    return pd.concat([base, summary], ignore_index=True), preds


# ----------------------------------------------------------------------------- Model A: growth estimation
def growth_models(pd_table: pd.DataFrame, horizon_days: int = 3, level: str = "experiment_id", seed: int = 0):
    """Predict projected area `horizon_days` ahead from image + environment features (per plant).
    Baseline = persistence of the current relative growth rate."""
    df = pd_table.sort_values(["plant_id", "day"]).copy()
    df["target"] = df.groupby("plant_id")["projected_area_cm2"].shift(-horizon_days)
    df = df.dropna(subset=["target", "projected_area_cm2"])
    df = df[(df["target"] > 0.5) & (df["projected_area_cm2"] > 0.5)].reset_index(drop=True)      # harvested / empty positions
    feats = _avail(df, F.IMAGE_FEATURES + F.ENV_FEATURES + ["day"])
    summary, preds = compare_models(df, feats, "target", regressors(seed), level, log_target=True)
    rgr = df["rgr_projected_area_cm2"].fillna(df["rgr_projected_area_cm2"].median()).clip(0, 0.6)
    naive = df["projected_area_cm2"] * np.exp(rgr * horizon_days)
    m = M.regression_metrics(df["target"], naive)
    preds["persistence_rgr"] = naive.to_numpy()
    summary = pd.concat([pd.DataFrame([{"model": "persistence_rgr", **m}]), summary], ignore_index=True)
    return summary, preds


# ----------------------------------------------------------------------------- Models B, C, E: stress
def _stress_frame(unit_table: pd.DataFrame, label_from_day_offset: int = 0) -> pd.DataFrame:
    df = unit_table.copy()
    df["stressed"] = ((df["treatment"] != "C") & (df["day"] >= df["onset_day"] + label_from_day_offset)).astype(int)
    df["days_since_onset"] = np.where(df["treatment"] != "C", df["day"] - df["onset_day"], np.nan)
    return df


def feature_sets(df: pd.DataFrame, blind: bool = True) -> dict:
    """Information sets compared in Study D. With blind=True the environment set excludes channels
    that directly encode the manipulated variable, so the task is detection of the plant RESPONSE."""
    env = F.ENV_RESPONSE_FEATURES if blind else F.ENV_FEATURES
    img = F.IMAGE_FEATURES + [f"{c}_sd" for c in F.IMAGE_FEATURES]
    lagged = lambda cols: [c for c in df.columns if any(c == f"{b}_lag{k}" for b in cols for k in (1, 2, 3))]
    env_all = _avail(df, env + lagged(env))
    img_all = _avail(df, img + lagged(F.IMAGE_FEATURES))
    return {"ENV": env_all, "IMG": img_all, "ENV+IMG": env_all + img_all}


def stress_classification(unit_table: pd.DataFrame, blind: bool = True, level: str = "experiment_id", seed: int = 0,
                          model_names=("logistic", "random_forest", "gradient_boosting", "svm")):
    """Model B / E: classify stressed vs not on unit-days, for each information set and model family."""
    df = _stress_frame(unit_table)
    lag_cols = _avail(df, F.ENV_FEATURES + F.IMAGE_FEATURES[:6])
    df = F.add_lags(df, lag_cols)
    sets = feature_sets(df, blind)
    rows, all_preds = [], df[["experiment_id", "unit_id", "day", "treatment", "onset_day", "stressed", "days_since_onset"]].copy()
    clf = classifiers(seed)
    for sname, feats in sets.items():
        if not feats:
            continue
        summary, preds = compare_models(df, feats, "stressed", {k: clf[k] for k in model_names}, level, classification=True)
        summary.insert(0, "features", sname)
        rows.append(summary)
        for k in model_names:
            all_preds[f"{sname}|{k}"] = preds[k].to_numpy()
    return pd.concat(rows, ignore_index=True), all_preds


def early_detection(preds: pd.DataFrame, reference_onset: pd.DataFrame | None = None, persist: int = 2, budget: float = 0.0) -> pd.DataFrame:
    """Model C: turn out-of-fold stress probabilities into alarms and score earliness.

    The alarm threshold for a held-out run is the lowest threshold that produces at most `budget`
    alarms per unit on the NEGATIVE unit-days of the other runs (control units, and treated units
    before their onset). Default budget 0: no false alarm in the training runs. False alarms in the
    held-out run are then an honest out-of-sample estimate. Lead time is relative to
    `reference_onset` (unit_id, reference_day); delay = detect day - treatment onset day."""
    score_cols = [c for c in preds.columns if "|" in c]
    rows = []
    for col in score_cols:
        for run in sorted(preds["experiment_id"].unique()):
            neg = preds[(preds["experiment_id"] != run) & (preds["stressed"] == 0)][["unit_id", "day", col]].rename(columns={col: "score"}).dropna()
            if neg.empty:
                continue
            thr = M.threshold_for_false_alarm_budget(neg, budget, persist=persist)
            test = preds[preds["experiment_id"] == run][["unit_id", "day", "treatment", "onset_day", col]].rename(columns={col: "score"}).dropna()
            det = M.detection_days(test, thr, persist=persist).merge(test.drop_duplicates("unit_id")[["unit_id", "treatment", "onset_day"]], on="unit_id")
            for _, r in det.iterrows():
                ref = r["onset_day"]
                if reference_onset is not None and r["unit_id"] in set(reference_onset["unit_id"]):
                    ref = float(reference_onset.set_index("unit_id").loc[r["unit_id"], "reference_day"])
                is_ctrl = r["treatment"] == "C"
                early = (not is_ctrl) and np.isfinite(r["detect_day"]) and r["detect_day"] < r["onset_day"]
                rows.append({"model": col, "experiment_id": run, "unit_id": r["unit_id"], "treatment": r["treatment"], "threshold": thr,
                             "detect_day": r["detect_day"], "false_alarm": bool((is_ctrl and np.isfinite(r["detect_day"])) or early),
                             "delay_days": np.nan if (is_ctrl or early) else r["detect_day"] - r["onset_day"],
                             "lead_vs_reference_days": np.nan if (is_ctrl or early) else ref - r["detect_day"]})
    return pd.DataFrame(rows)


def summarize_detection(det: pd.DataFrame, censor_day: float = 18.0) -> pd.DataFrame:
    """Per model: valid detection rate, median delay after onset (undetected or pre-onset alarms are
    censored at `censor_day`), and out-of-sample false alarms (controls, and treated units before onset)."""
    rows = []
    for model, g in det.groupby("model"):
        s = g[g["treatment"] != "C"]
        c = g[g["treatment"] == "C"]
        delay = s["delay_days"].fillna(censor_day)
        rows.append({"model": model, "n_stressed_units": len(s), "detected_after_onset_frac": float(s["delay_days"].notna().mean()) if len(s) else np.nan,
                     "median_delay_days": float(delay.median()) if len(s) else np.nan,
                     "pre_onset_false_alarms": int(s["false_alarm"].sum()),
                     "n_control_units": len(c), "control_false_alarms": int(c["false_alarm"].sum())})
    return pd.DataFrame(rows).sort_values(["median_delay_days", "control_false_alarms"])


def reference_onset_from_growth(unit_table: pd.DataFrame, col: str = "rgr_projected_area_cm2", z: float = 1.96) -> pd.DataFrame:
    """Reference onset per stressed unit (hypotheses.md): first day after treatment onset on which the
    unit's mean RGR is below the lower prediction bound of that run's control units on that day.
    With few control units per run the bound uses the pooled control SD across days of that run."""
    rows = []
    for run, g in unit_table.groupby("experiment_id"):
        ctrl = g[g["treatment"] == "C"]
        if ctrl.empty:
            continue
        mu = ctrl.groupby("day")[col].mean()
        pooled = (g[g["treatment"] == "C"].set_index("day")[col] - mu).std() if ctrl["unit_id"].nunique() > 1 else np.nan
        resid_sd = pooled if np.isfinite(pooled) and pooled > 0 else float((ctrl.set_index("day")[col].diff()).std() / np.sqrt(2))
        for unit, u in g[g["treatment"] != "C"].groupby("unit_id"):
            u = u.set_index("day").sort_index()
            below = (u[col] < mu.reindex(u.index) - z * resid_sd) & (u.index >= u["onset_day"].iloc[0])
            ref = float(below[below].index.min()) if below.any() else np.nan
            rows.append({"unit_id": unit, "reference_day": ref})
    return pd.DataFrame(rows)
