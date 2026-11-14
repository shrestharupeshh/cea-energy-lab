"""Receding-horizon (model-predictive) lighting control - the adaptive arm of Study C.

Each day, after lights-off:
  1. estimate the current crop state from vision (dry mass per plant via the calibrated allometry);
  2. re-plan PPFD and photoperiod for every remaining day to minimise predicted lighting energy,
     subject to reaching the target dry mass on harvest day and to the biological constraints;
  3. apply only tomorrow's setpoints, through the safety envelope.

Feedback through step 1 is what distinguishes this from a pre-computed schedule: if the crop is
behind the prediction, the plan adds light; if ahead, it saves energy.

Safety: the planner only PROPOSES. `plantpulse.acquisition.safety.check_setpoints(source="twin")`
decides, the node enforces its own limits, and the experiment must have opted in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

from ..digital_twin import crop as cropm
from ..digital_twin.environment import EnvParams


@dataclass
class MPCConfig:
    harvest_day: int = 28
    target_dw_g: float = 8.0               # per plant at harvest (set from the fixed arm's prediction)
    ppfd: tuple = (100.0, 300.0)
    photoperiod_h: tuple = (12.0, 20.0)
    dli_max: float = 17.0
    max_ppfd_step: float = 50.0            # day-to-day
    t_day: float = 23.0
    t_night: float = 20.0
    ec: float = 1.4
    co2: float = 420.0
    blocks: int = 4                        # the remaining horizon is parameterised by this many blocks
    shortfall_penalty: float = 50.0        # kWh per g of predicted dry-mass shortfall (soft terminal constraint)


@dataclass
class LightingMPC:
    cfg: MPCConfig = field(default_factory=MPCConfig)
    crop: cropm.CropParams = field(default_factory=cropm.CropParams)
    env: EnvParams = field(default_factory=EnvParams.from_design)

    def _expand(self, z, n_days):
        k = self.cfg.blocks
        edges = np.linspace(0, n_days, min(k, n_days) + 1).round().astype(int)
        kk = len(edges) - 1
        ppfd = np.concatenate([np.full(edges[i + 1] - edges[i], z[i]) for i in range(kk)])
        pp = np.concatenate([np.full(edges[i + 1] - edges[i], z[k + i]) for i in range(kk)])
        return ppfd, pp

    def _predict(self, ppfd, pp, dw_now):
        c = self.cfg
        r = cropm.simulate_schedule(len(ppfd), ppfd, pp, c.t_day, c.t_night, c.co2, c.ec, 70.0, self.crop, dw_now)
        return float(r["shoot_dw_g"][-1])

    def energy_kwh(self, ppfd, pp) -> float:
        return float(np.sum(np.minimum(np.asarray(ppfd) / self.env.ppfd_full, 1.0) * self.env.led_w_full * np.asarray(pp)) / 1000)

    def plan(self, day: int, dw_now_g: float, last_ppfd: float | None = None) -> dict:
        """Plan days `day`..harvest-1 given the current estimated dry mass per plant."""
        c = self.cfg
        n = c.harvest_day - day
        if n <= 0:
            raise ValueError("no days left to plan")
        k = c.blocks

        def cost(z):
            ppfd, pp = self._expand(z, n)
            dli = ppfd * pp * 3600 / 1e6
            pen = 5.0 * np.clip(dli - c.dli_max, 0, None).sum()
            if last_ppfd is not None:
                pen += 0.02 * max(abs(ppfd[0] - last_ppfd) - c.max_ppfd_step, 0.0)
            dw = self._predict(ppfd, pp, dw_now_g)
            return self.energy_kwh(ppfd, pp) + c.shortfall_penalty * max(c.target_dw_g - dw, 0.0) + pen

        bounds = [c.ppfd] * k + [c.photoperiod_h] * k
        best = None
        for z0 in (np.array([200.0] * k + [16.0] * k), np.array([250.0] * k + [16.0] * k), np.array([150.0] * k + [20.0] * k),
                   np.array([300.0] * k + [15.0] * k)):
            res = minimize(cost, z0, method="L-BFGS-B", bounds=bounds, options={"maxiter": 60, "eps": 1.0})
            if best is None or res.fun < best.fun:
                best = res
        ppfd, pp = self._expand(best.x, n)
        # hard post-conditions (never rely on penalties for constraints that matter)
        if last_ppfd is not None:
            ppfd[0] = float(np.clip(ppfd[0], last_ppfd - c.max_ppfd_step, last_ppfd + c.max_ppfd_step))
        pp = np.minimum(pp, c.dli_max * 1e6 / 3600 / np.maximum(ppfd, 1e-9))
        pp = np.clip(pp, c.photoperiod_h[0], c.photoperiod_h[1])
        ppfd = np.where(ppfd * pp * 3600 / 1e6 > c.dli_max + 1e-9, c.dli_max * 1e6 / 3600 / pp, ppfd)
        ppfd = np.clip(ppfd, *c.ppfd)
        dw = self._predict(ppfd, pp, dw_now_g)
        return {"day": day, "ppfd": ppfd, "photoperiod_h": pp, "next": {"ppfd": float(ppfd[0]), "photoperiod_h": float(pp[0])},
                "predicted_dw_g": dw, "predicted_kwh_remaining": self.energy_kwh(ppfd, pp), "target_met": bool(dw >= c.target_dw_g * 0.99),
                "provenance": "predicted"}


def simulate_closed_loop(mpc: LightingMPC, truth: cropm.CropParams, init_dw: float = 0.06, obs_cv: float = 0.08, seed: int = 0,
                         replan_every: int = 1) -> dict:
    """Closed-loop test in simulation: the 'real' crop follows `truth` (which may differ from the
    controller's model); the controller sees a noisy dry-mass estimate each day. SIMULATION ONLY."""
    rng = np.random.default_rng(seed)
    c = mpc.cfg
    dw_true = init_dw
    state = cropm.CropState.from_seedling(init_dw, truth)
    xn, xs = state.x_nsdw, state.x_sdw
    last, plan = None, None
    rows, kwh = [], 0.0
    deriv, _ = cropm._scalar_step_fns(truth)
    for day in range(c.harvest_day):
        if plan is None or day % replan_every == 0:
            est = dw_true * float(np.exp(rng.normal(0, obs_cv)))
            plan = mpc.plan(day, est, last)
            offset = 0
        ppfd, pp = float(plan["ppfd"][offset]), float(plan["photoperiod_h"][offset])
        offset += 1
        for hour in range(24):
            frac = min(max(pp - hour, 0.0), 1.0)
            par = ppfd * frac / cropm.UMOL_PER_J
            t = c.t_day if frac > 0 else c.t_night
            for _ in range(4):
                dn, ds = deriv(xn, xs, par, c.co2, t, c.ec)
                xn, xs = max(xn + 900 * dn, 0.0), max(xs + 900 * ds, 1e-9)
        dw_true = (1 - truth.c_tau) * (xn + xs) / truth.plant_density
        e = mpc.energy_kwh([ppfd], [pp])
        kwh += e
        rows.append({"day": day, "ppfd": ppfd, "photoperiod_h": pp, "dli": ppfd * pp * 3600 / 1e6, "dw_true_g": dw_true, "kwh_day": e})
        last = ppfd
    return {"trajectory": rows, "final_dw_g": dw_true, "kwh_led": kwh, "kwh_per_g_dw": kwh / (dw_true * 6)}
