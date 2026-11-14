import numpy as np
import pandas as pd
import pytest

from plantpulse.machine_learning import features as F
from plantpulse.machine_learning import metrics as M
from plantpulse.machine_learning import models, splits, tasks


def toy(n_runs=4, n_units=4, n_plants=6, seed=0, unit_sd=0.3):
    rng = np.random.default_rng(seed)
    rows = []
    for r in range(n_runs):
        for u in range(n_units):
            ue = rng.normal(0, unit_sd)
            for p in range(n_plants):
                x = rng.normal(0, 1)
                rows.append({"experiment_id": f"E{r}", "unit_id": f"E{r}-U{u}", "plant_id": f"E{r}-U{u}-N{p}", "x": x,
                             "noise": rng.normal(), "unit_key": r * 10 + u + rng.normal(0, 1e-3), "y": np.exp(1 + 0.5 * x + ue + rng.normal(0, 0.05))})
    return pd.DataFrame(rows)


def test_grouped_splits_never_leak():
    df = toy()
    for level in ("plant_id", "unit_id", "experiment_id"):
        n = 0
        for tr, te in splits.grouped_splits(df, level, n_splits=4):
            assert not set(df.iloc[tr][level]) & set(df.iloc[te][level])
            n += 1
        assert n == 4
    assert sum(1 for _ in splits.grouped_splits(df, "experiment_id")) == 4      # leave-one-run-out


def test_leakage_assertion_fires():
    df = toy()
    with pytest.raises(AssertionError, match="leakage"):
        splits.assert_no_leakage(df.iloc[:30], df.iloc[20:60], "unit_id")
    with pytest.raises(AssertionError):                    # same plant on both sides is caught at any level
        splits.assert_no_leakage(df.iloc[:10], df.iloc[5:15], "experiment_id")
    with pytest.raises(ValueError):
        list(splits.grouped_splits(df[df.experiment_id == "E0"], "experiment_id"))


def test_unit_identifier_feature_shows_why_grouping_matters():
    """A feature that identifies the unit lets a flexible model memorise unit effects. Plant-level
    splitting rewards this; run-level splitting does not. This is the leakage the SAP guards against."""
    df = toy(seed=3, unit_sd=0.8)
    rf = models.regressors()["random_forest"]
    leaky = models.cv_predict(df, ["x", "unit_key"], "y", rf, level="plant_id", log_target=True)
    honest = models.cv_predict(df, ["x", "unit_key"], "y", rf, level="experiment_id", log_target=True)
    mape = lambda p: M.regression_metrics(df.y, p)["mape"]
    assert mape(leaky) < 0.75 * mape(honest)


def test_compare_models_reports_cluster_ci():
    df = toy()
    summary, preds = models.compare_models(df, ["x", "noise"], "y", {k: v for k, v in models.regressors().items() if k in ("linear", "random_forest")},
                                           log_target=True, n_boot=200)
    assert set(summary.model) == {"linear", "random_forest"} and (summary.n_clusters == 16).all()
    assert (summary.mape_ci_low <= summary.mape).all() and (summary.mape <= summary.mape_ci_high).all()
    assert preds["linear"].notna().all()


def test_metrics_basics():
    m = M.regression_metrics([1, 2, 3, 4], [1.1, 1.9, 3.2, 3.8])
    assert np.isclose(m["mae"], 0.15) and m["r2"] > 0.95
    c = M.classification_metrics([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8])
    assert np.isclose(c["auroc"], 0.75)
    assert np.isnan(M.classification_metrics([1, 1], [0.2, 0.9])["auroc"])


def test_detection_threshold_and_lead_time():
    days = np.arange(20)
    ctrl = pd.DataFrame({"unit_id": "c", "day": days, "score": 0.1 + 0.02 * np.sin(days)})
    ctrl.loc[5:6, "score"] = 0.4                                   # one 2-day excursion in a control unit
    thr0 = M.threshold_for_false_alarm_budget(ctrl, 0.0)
    assert thr0 >= 0.4 - 1e-9, "zero budget must sit above the control excursion"
    assert M.threshold_for_false_alarm_budget(ctrl, 1.0) < 0.4
    s = pd.DataFrame({"unit_id": "s", "day": days, "score": np.where(days >= 12, 0.9, 0.1)})
    det = M.detection_days(pd.concat([ctrl, s]), thr0)
    d = det.set_index("unit_id").detect_day
    assert np.isnan(d["c"]) and d["s"] == 12
    lt = M.lead_time(det, pd.DataFrame({"unit_id": ["s"], "reference_day": [15]}))
    assert lt.lead_days.iloc[0] == 3
    single = pd.DataFrame({"unit_id": "x", "day": days, "score": np.where(days == 7, 0.9, 0.1)})
    assert np.isnan(M.detection_days(single, 0.5).detect_day.iloc[0]), "a one-day spike is not an alarm"


def test_features_use_past_only_and_tables_build(mini_lab):
    root, runs = mini_lab
    from plantpulse.data.db import MetaDB
    db = MetaDB(root / "plantpulse_meta.db")
    meta = db.q("SELECT plant_id, unit_id, experiment_id, treatment, onset_day FROM v_plant_full")
    traits = pd.concat([r["traits"] for r in runs])
    daily = pd.concat([r["daily"] for r in runs])
    pdt = F.plant_day_table(traits, daily, meta)
    assert {"projected_area_cm2", "rgr_projected_area_cm2", "cum_dli", "water_use_g", "treatment"} <= set(pdt.columns)
    one = pdt[pdt.plant_id == pdt.plant_id.iloc[0]].sort_values("day")
    assert one["cum_dli"].is_monotonic_increasing
    ut = F.unit_day_table(pdt)
    assert len(ut) == 4 * 6 and "projected_area_cm2_sd" in ut
    lag = F.add_lags(ut, ["projected_area_cm2"])
    u0 = lag[lag.unit_id == lag.unit_id.iloc[0]].sort_values("day")
    assert np.isnan(u0["projected_area_cm2_lag1"].iloc[0]) and np.isclose(u0["projected_area_cm2_lag1"].iloc[1], u0["projected_area_cm2"].iloc[0])
    summary, preds = tasks.stress_classification(ut, blind=True, model_names=("logistic",))
    assert set(summary.features) == {"ENV", "IMG", "ENV+IMG"} and "IMG|logistic" in preds
    det = tasks.early_detection(preds)
    assert {"delay_days", "false_alarm"} <= set(det.columns)
    blind_sets = tasks.feature_sets(F.add_lags(ut, F.ENV_FEATURES), blind=True)
    assert not set(blind_sets["ENV"]) & set(F.ENV_SETPOINT_FEATURES), "blind set must not contain manipulated-variable channels"
    db.close()


def test_allometry_fit():
    a = np.linspace(5, 300, 40)
    fn, k, b = F.fit_allometry(a, 0.01 * a**1.3)
    assert np.isclose(b, 1.3) and np.isclose(fn(100.0), 0.01 * 100**1.3)
