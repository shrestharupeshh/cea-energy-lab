"""Feature tables for the models. All tables are keyed by plant_id/unit_id/experiment_id/day so that
grouped splitting is always possible, and every feature on day d uses only data from days <= d."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..computer_vision.growth import add_growth_features, daily_traits

IMAGE_FEATURES = ["projected_area_cm2", "diameter_max_mm", "diameter_perp_mm", "convex_area_cm2", "solidity", "compactness",
                  "L_mean", "a_mean", "b_mean", "exg_mean", "ngrdi", "yellow_frac", "brown_frac", "station_cover",
                  "rgr_projected_area_cm2", "d_projected_area_cm2", "rgr_change_projected_area_cm2"]
# Environment channels that directly encode what the experimenter manipulated (the cause):
ENV_SETPOINT_FEATURES = ["air_t_light", "air_t_dark", "ppfd_light", "dli", "photoperiod_h", "ec_mean", "cum_dli", "thermal_time",
                         "rh_mean", "vpd_kpa"]     # RH/VPD are controlled variables and shift with the heat treatment
# Environment channels that carry the plants' RESPONSE (gas exchange, water uptake):
ENV_RESPONSE_FEATURES = ["water_use_g", "co2_drawdown", "water_use_3d", "water_use_rel_change"]
ENV_FEATURES = ENV_SETPOINT_FEATURES + ENV_RESPONSE_FEATURES


def env_features(daily_env: pd.DataFrame, room_co2: float = 420.0) -> pd.DataFrame:
    out = []
    for _, g in daily_env.sort_values("day").groupby("unit_id"):
        g = g.copy()
        g["cum_dli"] = g["dli"].fillna(0).cumsum()
        g["thermal_time"] = ((g["air_t_light"].fillna(g["air_t_dark"]) * g["photoperiod_h"] + g["air_t_dark"] * (24 - g["photoperiod_h"])) / 24).clip(lower=4).sub(4).cumsum()
        g["co2_drawdown"] = room_co2 - g["co2_light"]
        g["water_use_3d"] = g["water_use_g"].rolling(3, min_periods=1).mean()
        g["water_use_rel_change"] = g["water_use_3d"].pct_change(3).replace([np.inf, -np.inf], np.nan)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def plant_day_table(traits: pd.DataFrame, daily_env: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """One row per plant and day: image features (daily median + growth rates), unit-level environment
    features, identifiers. `meta`: plant_id, unit_id, experiment_id (+ optional treatment, onset_day)."""
    cols = [c for c in IMAGE_FEATURES if c in traits.columns]
    d = daily_traits(traits, cols)
    d = add_growth_features(d)
    d = d.merge(meta, on="plant_id", how="left")
    e = env_features(daily_env)
    d = d.merge(e[["unit_id", "day"] + [c for c in ENV_FEATURES if c in e]], on=["unit_id", "day"], how="left")
    return d.sort_values(["plant_id", "day"]).reset_index(drop=True)


def unit_day_table(pd_table: pd.DataFrame) -> pd.DataFrame:
    """Aggregate plant-day rows to the experimental unit (mean and between-plant SD of image features)."""
    img = [c for c in IMAGE_FEATURES if c in pd_table]
    env = [c for c in ENV_FEATURES if c in pd_table]
    keys = ["experiment_id", "unit_id", "day"] + [c for c in ("treatment", "onset_day") if c in pd_table]
    g = pd_table.groupby(keys, as_index=False)
    out = g[img].mean()
    sd = g[img].std().rename(columns={c: f"{c}_sd" for c in img})
    out = out.merge(sd, on=keys).merge(g[env].first(), on=keys)
    return out


def add_lags(table: pd.DataFrame, cols: list[str], lags=(1, 2, 3), by: str = "unit_id") -> pd.DataFrame:
    """Temporal context as lagged copies (past only)."""
    out = table.sort_values([by, "day"]).copy()
    for c in cols:
        for k in lags:
            out[f"{c}_lag{k}"] = out.groupby(by)[c].shift(k)
    return out


def within_run_deviation(table: pd.DataFrame, cols: list[str], reference_mask: pd.Series | None = None) -> pd.DataFrame:
    """Express features as deviation from the same-day mean of that run (optionally of reference units
    only). Removes run-level effects such as seedling vigour. Using the control units as reference
    requires knowing the allocation and is therefore not available to a treatment-blind detector."""
    out = table.copy()
    ref = out if reference_mask is None else out[reference_mask]
    mu = ref.groupby(["experiment_id", "day"])[cols].mean().rename(columns={c: f"{c}__ref" for c in cols}).reset_index()
    out = out.merge(mu, on=["experiment_id", "day"], how="left")
    for c in cols:
        out[f"{c}_dev"] = out[c] - out[f"{c}__ref"]
        out.drop(columns=f"{c}__ref", inplace=True)
    return out


def forecast_table(pd_table: pd.DataFrame, harvest: pd.DataFrame, recipes: pd.DataFrame, t0_days=(7, 14, 21), harvest_day: int = 28,
                   area_to_dw=None) -> pd.DataFrame:
    """Rows for the growth-forecast task (RQ3): state at day t0 -> dry mass at harvest.
    harvest: plant_id, dw_T. recipes: unit_id + ppfd/photoperiod_h/air_t_day/air_t_night/ec planned after t0.
    dw_t0 is derived from the image (projected area) through `area_to_dw` (a fitted allometric
    function), because dry mass is not observable non-destructively."""
    rows = []
    for t0 in t0_days:
        d = pd_table[pd_table["day"] == t0].copy()
        d["t0"] = t0
        d["horizon"] = harvest_day - t0
        rows.append(d)
    out = pd.concat(rows, ignore_index=True).merge(harvest, on="plant_id").merge(recipes, on="unit_id")
    out["dw_t0"] = area_to_dw(out["projected_area_cm2"]) if area_to_dw is not None else np.nan
    return out


def fit_allometry(area_cm2, dw_g):
    """log-log allometric relation dw = a * area^b; returns (callable, a, b)."""
    x, y = np.log(np.asarray(area_cm2, float)), np.log(np.asarray(dw_g, float))
    ok = np.isfinite(x) & np.isfinite(y)
    b, la = np.polyfit(x[ok], y[ok], 1)
    return (lambda area: np.exp(la) * np.asarray(area, float) ** b), float(np.exp(la)), float(b)
