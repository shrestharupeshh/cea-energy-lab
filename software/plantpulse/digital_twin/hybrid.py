"""Physics / machine-learning / hybrid growth predictors with a common interface (RQ3).

Task: given what is known up to forecast day t0 (observed size, environment so far, the planned
recipe), predict shoot dry mass at harvest day T.

  MechanisticModel   calibrated crop model, started from the observed size at t0
  MLModel            gradient boosting / random forest / ridge on tabular features, no physics
  HybridModel        mechanistic prediction + ML correction of its log-ratio residual; the
                     mechanistic prediction is also an input feature

All three consume the same table (one row per plant forecast) so comparisons are like-for-like.
Required columns: dw_t0 (g, observed or vision-estimated), t0 (day), horizon (days),
ppfd_future, photoperiod_future, t_day_future, t_night_future, ec_future, plus any numeric
feature columns listed in `features`. Target column: dw_T.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import crop as cropm

BASE_FEATURES = ["dw_t0", "t0", "horizon", "ppfd_future", "photoperiod_future", "t_day_future", "t_night_future", "ec_future"]


def mechanistic_forecast(row, p: cropm.CropParams) -> float:
    r = cropm.simulate_schedule(int(row["horizon"]), row["ppfd_future"], row["photoperiod_future"], row["t_day_future"],
                                row["t_night_future"], 420.0, row["ec_future"], 70.0, p, float(row["dw_t0"]))
    return float(r["shoot_dw_g"][-1])


@dataclass
class MechanisticModel:
    params: cropm.CropParams = field(default_factory=cropm.CropParams)
    name: str = "mechanistic"

    def fit(self, df: pd.DataFrame, y=None):
        """Calibrate the light-use-efficiency scale by 1-D least squares on log error."""
        from scipy.optimize import minimize_scalar
        target = np.log(df["dw_T"].to_numpy(float))

        def loss(scale):
            p = self.params.with_(c_eps=cropm.CropParams().c_eps * scale)
            pred = np.array([mechanistic_forecast(r, p) for _, r in df.iterrows()])
            return float(np.mean((np.log(pred) - target) ** 2))

        res = minimize_scalar(loss, bounds=(0.5, 1.8), method="bounded", options={"xatol": 1e-2})
        self.params = self.params.with_(c_eps=cropm.CropParams().c_eps * res.x)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        return np.array([mechanistic_forecast(r, self.params) for _, r in df.iterrows()])


def _make(kind: str, seed: int):
    if kind == "gbm":
        return GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed)
    if kind == "rf":
        return RandomForestRegressor(n_estimators=300, min_samples_leaf=2, random_state=seed)
    if kind == "ridge":
        return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 13)))
    raise ValueError(kind)


@dataclass
class MLModel:
    kind: str = "gbm"
    features: list = field(default_factory=lambda: list(BASE_FEATURES))
    seed: int = 0

    @property
    def name(self):
        return f"ml_{self.kind}"

    def fit(self, df, y=None):
        self.model_ = _make(self.kind, self.seed).fit(df[self.features].to_numpy(float), np.log(df["dw_T"].to_numpy(float)))
        return self

    def predict(self, df):
        return np.exp(self.model_.predict(df[self.features].to_numpy(float)))


@dataclass
class HybridModel:
    kind: str = "gbm"
    features: list = field(default_factory=lambda: list(BASE_FEATURES))
    seed: int = 0
    shrink: float = 1.0          # 0 = pure mechanistic, 1 = full residual correction
    name: str = "hybrid"

    def fit(self, df, y=None):
        self.mech_ = MechanisticModel().fit(df)
        m = self.mech_.predict(df)
        x = np.column_stack([df[self.features].to_numpy(float), np.log(m)])
        self.model_ = _make(self.kind, self.seed).fit(x, np.log(df["dw_T"].to_numpy(float)) - np.log(m))
        return self

    def predict(self, df):
        m = self.mech_.predict(df)
        x = np.column_stack([df[self.features].to_numpy(float), np.log(m)])
        return m * np.exp(self.shrink * self.model_.predict(x))
