"""Model registry and grouped cross-validation harness.

Interpretable baselines (linear / ridge / logistic) are always evaluated alongside the flexible
models; a flexible model is only preferred if it beats the baseline on held-out groups."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR

from . import metrics as M
from .splits import grouped_splits


def regressors(seed: int = 0) -> dict:
    imp = lambda: SimpleImputer(strategy="median")
    return {
        "linear": make_pipeline(imp(), StandardScaler(), LinearRegression()),
        "ridge": make_pipeline(imp(), StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 13))),
        "random_forest": make_pipeline(imp(), RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=seed, n_jobs=-1)),
        "gradient_boosting": make_pipeline(imp(), GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed)),
        "svr": make_pipeline(imp(), StandardScaler(), SVR(C=10.0, epsilon=0.05)),
    }


def classifiers(seed: int = 0) -> dict:
    imp = lambda: SimpleImputer(strategy="median")
    return {
        "logistic": make_pipeline(imp(), StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
        "random_forest": make_pipeline(imp(), RandomForestClassifier(n_estimators=300, min_samples_leaf=2, random_state=seed, n_jobs=-1)),
        "gradient_boosting": make_pipeline(imp(), GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed)),
        "svm": make_pipeline(imp(), StandardScaler(), SVC(C=1.0, probability=True, random_state=seed)),
    }


def cv_predict(df: pd.DataFrame, features: list[str], target: str, model, level: str = "experiment_id", log_target: bool = False,
               classification: bool = False) -> np.ndarray:
    """Out-of-fold predictions under grouped CV. Rows with a missing target are skipped (NaN prediction)."""
    from sklearn.base import clone
    pred = np.full(len(df), np.nan)
    ok = df[target].notna().to_numpy()
    X = df[features].to_numpy(float)
    y = df[target].to_numpy(float)
    for tr, te in grouped_splits(df, level):
        tr, te = tr[ok[tr]], te[ok[te]]
        if len(tr) == 0 or len(te) == 0:
            continue
        if classification and len(np.unique(y[tr])) < 2:
            continue
        m = clone(model).fit(X[tr], np.log(y[tr]) if log_target else y[tr])
        if classification:
            pred[te] = m.predict_proba(X[te])[:, 1]
        else:
            p = m.predict(X[te])
            pred[te] = np.exp(p) if log_target else p
    return pred


def compare_models(df: pd.DataFrame, features: list[str], target: str, models: dict, level: str = "experiment_id",
                   log_target: bool = False, classification: bool = False, cluster: str = "unit_id", n_boot: int = 500) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate every model with the same grouped folds. Returns (summary with cluster-bootstrap CIs, out-of-fold predictions)."""
    preds = df[[c for c in ("experiment_id", "unit_id", "plant_id", "day", "treatment") if c in df]].copy()
    preds["y"] = df[target].to_numpy()
    rows = []
    for name, model in models.items():
        p = cv_predict(df, features, target, model, level, log_target, classification)
        preds[name] = p
        d = preds[["unit_id", "y", name]].dropna()
        if classification:
            m = M.classification_metrics(d["y"], d[name])
            ci = M.cluster_bootstrap(d, lambda g: M.classification_metrics(g["y"], g[name])["auroc"], cluster, n_boot)
            rows.append({"model": name, **m, "auroc_ci_low": ci["ci_low"], "auroc_ci_high": ci["ci_high"], "n_clusters": ci["n_clusters"]})
        else:
            m = M.regression_metrics(d["y"], d[name])
            ci = M.cluster_bootstrap(d, lambda g: M.regression_metrics(g["y"], g[name])["mape"], cluster, n_boot)
            rows.append({"model": name, **m, "mape_ci_low": ci["ci_low"], "mape_ci_high": ci["ci_high"], "n_clusters": ci["n_clusters"]})
    return pd.DataFrame(rows), preds


def permutation_importance_grouped(df, features, target, model, level="experiment_id", n_repeats=5, seed=0, log_target=False) -> pd.DataFrame:
    """Held-out permutation importance (increase in MAE when a feature is shuffled within the test fold)."""
    from sklearn.base import clone
    rng = np.random.default_rng(seed)
    X, y = df[features].to_numpy(float), df[target].to_numpy(float)
    imp = np.zeros(len(features))
    n = 0
    for tr, te in grouped_splits(df, level):
        m = clone(model).fit(X[tr], np.log(y[tr]) if log_target else y[tr])
        f = (lambda Z: np.exp(m.predict(Z))) if log_target else m.predict
        base = np.abs(f(X[te]) - y[te]).mean()
        for j in range(len(features)):
            for _ in range(n_repeats):
                Z = X[te].copy()
                Z[:, j] = rng.permutation(Z[:, j])
                imp[j] += np.abs(f(Z) - y[te]).mean() - base
        n += n_repeats
    return pd.DataFrame({"feature": features, "mae_increase": imp / max(n, 1)}).sort_values("mae_increase", ascending=False)
