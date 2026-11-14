"""Optimisation problem definition: decision variables, objectives, biological constraints.

Decision vector (stage-wise recipe, 3 growth stages by default):
    [ppfd_1..k, photoperiod_1..k, air_t_day_1..k]      with air_t_night = air_t_day - 3
Objectives (all minimised): -fresh mass per plant, lighting energy (kWh per pod and cycle),
water per pod (L). Constraints are never traded off against objectives: an infeasible recipe is
penalised by its total violation and can never dominate a feasible one.

All objective values are digital-twin PREDICTIONS. A recommended recipe is a hypothesis to test
(Study C), not a result.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..digital_twin import crop as cropm
from ..digital_twin.twin import Recipe, fast_predict


@dataclass
class Constraints:
    dli_max: float = 17.0            # mol m-2 d-1 (tipburn risk above this without extra airflow / Ca management)
    dli_min: float = 6.0             # below this lettuce etiolates and quality drops
    ppfd: tuple = (100.0, 300.0)
    photoperiod_h: tuple = (12.0, 20.0)   # at least 4 h dark
    air_t_day: tuple = (19.0, 27.0)
    min_fw_g: float = 120.0          # marketable head / target mass
    max_daily_ppfd_step: float = 100.0    # between consecutive stages
    max_rgr_fw: float = 0.35         # d-1; very fast late growth is associated with tipburn (proxy, unvalidated)


@dataclass
class LightingProblem:
    days: int = 28
    stages: int = 3
    cons: Constraints = field(default_factory=Constraints)
    crop: cropm.CropParams = field(default_factory=cropm.CropParams)
    ec: float = 1.4
    objectives: tuple = ("neg_fw", "kwh_led", "water_l")
    start_state: cropm.CropState | None = None
    start_day: int = 0

    @property
    def n_var(self) -> int:
        return 3 * self.stages

    @property
    def bounds(self) -> np.ndarray:
        c = self.cons
        return np.array([c.ppfd] * self.stages + [c.photoperiod_h] * self.stages + [c.air_t_day] * self.stages, float)

    def recipe(self, x) -> Recipe:
        x = np.asarray(x, float)
        k = self.stages
        edges = np.linspace(0, self.days, k + 1).round().astype(int)
        per_day = lambda v: np.concatenate([np.full(edges[i + 1] - edges[i], v[i]) for i in range(k)])
        t_day = per_day(x[2 * k:3 * k])
        return Recipe(days=self.days, ppfd=per_day(x[:k]), photoperiod_h=per_day(x[k:2 * k]), air_t_day=t_day, air_t_night=t_day - 3.0, ec=self.ec)

    def evaluate(self, x) -> dict:
        """Return objectives, constraint violations (>= 0, 0 = satisfied) and the prediction."""
        c = self.cons
        r = self.recipe(x)
        pred = fast_predict(r, self.crop, start_state=self.start_state, start_day=self.start_day)
        dli = r.dli()[self.start_day:]
        k = self.stages
        fw = pred["shoot_fw_g_plant"]
        daily = np.asarray(pred["daily_dw"], float)
        rgr_late = float(np.max(np.diff(np.log(daily[len(daily) // 2:])))) if len(daily) > 4 else 0.0
        viol = {
            "dli_max": float(max(dli.max() - c.dli_max, 0.0)),
            "dli_min": float(max(c.dli_min - dli.min(), 0.0)),
            "min_fw": float(max(c.min_fw_g - fw, 0.0)) / 10.0,
            "ppfd_step": float(np.clip(np.abs(np.diff(np.asarray(x[:k], float))) - c.max_daily_ppfd_step, 0, None).sum()) / 50.0,
            "rgr": float(max(rgr_late - c.max_rgr_fw, 0.0)) * 20.0,
        }
        obj = {"neg_fw": -fw, "kwh_led": pred["kwh_led"], "water_l": pred["water_l_pod"],
               "kwh_per_g_dw": pred["kwh_led_per_g_dw"], "neg_dw": -pred["shoot_dw_g_plant"]}
        return {"f": np.array([obj[o] for o in self.objectives]), "g": float(sum(viol.values())), "violations": viol, "pred": pred, "recipe": r}

    def baseline(self) -> np.ndarray:
        k = self.stages
        return np.array([250.0] * k + [16.0] * k + [23.0] * k)
