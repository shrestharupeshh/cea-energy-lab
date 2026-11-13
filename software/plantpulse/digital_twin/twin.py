"""Pod digital twin: crop model + environment model + the real controller logic + energy accounting.

`PodTwin.run()` is the predictive simulator: give it a recipe (setpoints per day) and room
conditions, it returns a time series of predicted environment, crop state and energy.
Every row is tagged provenance = "predicted"; nothing here may be written to measured tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..acquisition import node_logic as nlg
from . import crop as cropm
from . import environment as envm


@dataclass
class Recipe:
    """Daily setpoints. Scalars apply to every day; arrays give one value per day."""
    days: int = 28
    ppfd: float | np.ndarray = 250.0
    photoperiod_h: float | np.ndarray = 16.0
    air_t_day: float | np.ndarray = 23.0
    air_t_night: float | np.ndarray = 20.0
    rh: float | np.ndarray = 68.0
    ec: float | np.ndarray = 1.4
    lights_on_min: int = 360

    def day(self, d: int) -> dict:
        g = lambda v: float(np.broadcast_to(np.asarray(v, float), (self.days,))[min(d, self.days - 1)])
        return {"ppfd": g(self.ppfd), "photoperiod_h": g(self.photoperiod_h), "air_t_day": g(self.air_t_day),
                "air_t_night": g(self.air_t_night), "rh": g(self.rh), "ec": g(self.ec)}

    def dli(self) -> np.ndarray:
        b = lambda v: np.broadcast_to(np.asarray(v, float), (self.days,))
        return b(self.ppfd) * b(self.photoperiod_h) * 3600 / 1e6


@dataclass
class PodTwin:
    crop: cropm.CropParams = field(default_factory=cropm.CropParams)
    env: envm.EnvParams = field(default_factory=envm.EnvParams.from_design)
    room_t: float = 20.0
    room_rh: float = 50.0
    room_co2: float = 420.0
    init_shoot_dw: float = 0.06

    def run(self, recipe: Recipe, dt_s: float = 60.0, log_every_s: float = 600.0, start_state: cropm.CropState | None = None,
            start_day: int = 0, growth_multiplier: float = 1.0) -> pd.DataFrame:
        p, e = self.crop, self.env
        cs = start_state or cropm.CropState.from_seedling(self.init_shoot_dw, p)
        xn, xs = cs.x_nsdw, cs.x_sdw
        es = envm.EnvState(air_t=self.room_t + 1.0, w=float(envm.abs_hum(self.room_t + 1.0, 60.0)), co2=self.room_co2, sol_t=self.room_t)
        ctl = nlg.Controller(mode=nlg.AUTO)
        rows, energy = [], {k: 0.0 for k in ("led_w", "fan_w", "heater_w", "pump_w", "humid_w", "logic_w", "dc_w", "wall_w")}
        water_g = 0.0
        n_steps = int((recipe.days - start_day) * 86400 / dt_s)
        log_k = max(int(log_every_s / dt_s), 1)
        area = e.grow_area_m2
        for k in range(n_steps):
            t_s = start_day * 86400 + k * dt_s
            day = int(t_s // 86400)
            if k == 0 or (t_s % 86400) < dt_s:
                r = recipe.day(day)
                off = (recipe.lights_on_min + int(round(r["photoperiod_h"] * 60))) % 1440
                ctl.sp = nlg.Setpoints(air_t_day=r["air_t_day"], air_t_night=r["air_t_night"], rh=r["rh"],
                                       led_duty=min(r["ppfd"] / e.ppfd_full, 1.0), lights_on_min=recipe.lights_on_min,
                                       lights_off_min=off, ramp_min=5)
            minute = int((t_s % 86400) // 60)
            o = ctl.step(nlg.Inputs(air_t=es.air_t, rh=es.rh, minute_of_day=minute), dt_s)
            u = envm.Actuators(led=o.led, heater=o.heater, fan=o.fan, mix=o.mix, humidifier=o.humidifier, pump=o.pump)
            ppfd = o.led * e.ppfd_full
            par = ppfd / cropm.UMOL_PER_J
            dn, ds = cropm.derivatives(xn, xs, par, es.co2, es.air_t, p, r["ec"])
            f_phot = float(cropm.gross_photosynthesis(xs, par, es.co2, es.air_t, p, r["ec"])) * growth_multiplier
            transp = float(cropm.transpiration(xs + xn, par, es.air_t, es.rh, p))        # g m-2 s-1
            xn = max(xn + dt_s * dn * growth_multiplier, 0.0)
            xs = max(xs + dt_s * ds * growth_multiplier, 1e-9)
            es = envm.step(es, u, e, dt_s, self.room_t, self.room_rh, self.room_co2,
                           transp_g_s=transp * area, co2_uptake_g_s=0.8 * f_phot * area)   # net uptake ~ 80 % of gross (respiration)
            pw = envm.power_w(u, e)
            for key in energy:
                energy[key] += pw[key] * dt_s / 3.6e6
            water_g += transp * area * dt_s
            if (k + 1) % log_k == 0:
                obs = cropm.outputs(xn, xs, p)
                rows.append({
                    "t_day": (t_s + dt_s) / 86400, "air_t": es.air_t, "rh": es.rh, "co2": es.co2, "sol_t": es.sol_t, "ppfd": ppfd,
                    "u_led": o.led, "u_heat": o.heater, "u_fan": o.fan, "humid": int(o.humidifier),
                    "x_nsdw": xn, "x_sdw": xs, **{k2: float(v) for k2, v in obs.items()},
                    "water_l_pod": water_g / 1000, **{f"kwh_{k2[:-2]}": v for k2, v in energy.items()}, "wall_w": pw["wall_w"],
                })
        df = pd.DataFrame(rows)
        df["provenance"] = "predicted"
        return df

    def summary(self, df: pd.DataFrame, plants: int = 6) -> dict:
        last = df.iloc[-1]
        dm_pod = last["shoot_dw_g"] * plants
        heat_to_room_kwh = last["kwh_wall"]            # all electrical energy ends as heat (or latent) in the room
        return {
            "shoot_fw_g_plant": last["shoot_fw_g"], "shoot_dw_g_plant": last["shoot_dw_g"], "leaf_area_cm2": last["leaf_area_cm2"],
            "kwh_led": last["kwh_led"], "kwh_wall": last["kwh_wall"], "kwh_heater": last["kwh_heater"],
            "kwh_room_hvac_est": heat_to_room_kwh / self.env.room_cop,
            "water_l_pod": last["water_l_pod"],
            "kwh_led_per_g_dw": last["kwh_led"] / dm_pod, "kwh_wall_per_g_dw": last["kwh_wall"] / dm_pod,
            "water_l_per_kg_fw": last["water_l_pod"] / (last["shoot_fw_g"] * plants / 1000),
            "mean_air_t_light": float(df.loc[df.ppfd > 1, "air_t"].mean()), "mean_rh": float(df["rh"].mean()),
            "provenance": "predicted",
        }


def fast_predict(recipe: Recipe, crop: cropm.CropParams = cropm.CropParams(), env: envm.EnvParams | None = None,
                 init_shoot_dw: float = 0.06, co2: float = 420.0, plants: int = 6, start_state=None, start_day: int = 0) -> dict:
    """Fast crop + lighting-energy prediction that assumes the climate loop holds its setpoints.
    Used inside optimisation loops (about 100x faster than PodTwin.run)."""
    env = env or envm.EnvParams.from_design()
    b = lambda v: np.broadcast_to(np.asarray(v, float), (recipe.days,))[start_day:]
    days = recipe.days - start_day
    if start_state is not None:
        init = (start_state.x_nsdw + start_state.x_sdw) * (1 - crop.c_tau) / crop.plant_density
    else:
        init = init_shoot_dw
    res = cropm.simulate_schedule(days, b(recipe.ppfd), b(recipe.photoperiod_h), b(recipe.air_t_day), b(recipe.air_t_night),
                                  co2, b(recipe.ec), b(recipe.rh), crop, init)
    duty = np.minimum(b(recipe.ppfd) / env.ppfd_full, 1.0)
    kwh_led = float(np.sum(duty * env.led_w_full * b(recipe.photoperiod_h)) / 1000)
    i = res["day_end_index"][-1]
    dw = float(res["shoot_dw_g"][i])
    return {"shoot_dw_g_plant": dw, "shoot_fw_g_plant": float(res["shoot_fw_g"][i]), "leaf_area_cm2": float(res["leaf_area_cm2"][i]),
            "kwh_led": kwh_led, "kwh_led_per_g_dw": kwh_led / (dw * plants), "water_l_pod": float(res["transp_g_plant_cum"][-1]) * plants / 1000,
            "dli_max": float(recipe.dli().max()), "daily_dw": res["shoot_dw_g"][res["day_end_index"]], "provenance": "predicted"}
