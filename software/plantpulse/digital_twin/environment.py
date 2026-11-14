"""Lumped-parameter pod environment and energy model.

States: air temperature, absolute humidity, CO2, nutrient-solution temperature.
Inputs: actuator duties (LED, heater, exhaust fan, mixing fan, humidifier), room conditions,
crop transpiration and CO2 uptake. Parameters default to the design calculations and are meant
to be re-identified from commissioning step tests (VAL-DT-02). All outputs are PREDICTIONS.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..config import load_design
from ..engineering import lighting, thermal

RHO, CP, LATENT = 1.2, 1005.0, 2.45e6
_DESIGN_CACHE = None


@dataclass
class EnvParams:
    volume_m3: float = 0.29
    ua_w_k: float = 7.0                 # walls + floor to room
    c_air_j_k: float = 8000.0           # effective capacitance of air + wall inner layer
    q_fan_full_m3h: float = 22.6        # exhaust flow at 100 % duty
    q_leak_m3h: float = 1.0
    ppfd_full: float = 338.0            # umol m-2 s-1 at lid, 100 % duty
    led_w_full: float = 84.4            # electrical incl. driver
    par_w_full: float = 44.7            # radiant PAR entering the chamber at 100 %
    window_w_k: float = 1.1             # conduction from LED bay per K of bay excess (~8 K at full power)
    heater_w: float = 100.0
    fan_w: float = 0.96
    pump_w: float = 5.0
    humid_g_h: float = 35.0
    humid_w: float = 2.5
    logic_w: float = 3.7                # node + camera node
    c_sol_j_k: float = 28.1 * 4186.0
    ua_sol_air_w_k: float = 1.2         # lid + tub upper area to chamber air
    ua_sol_room_w_k: float = 0.8        # tub base/walls to floor and room
    grow_area_m2: float = 0.24
    psu_eff: float = 0.90
    room_cop: float = 3.0               # assumed COP of room HVAC for the heat rejected to the room

    @classmethod
    def from_design(cls) -> "EnvParams":
        global _DESIGN_CACHE
        if _DESIGN_CACHE is None:
            _DESIGN_CACHE = cls._from_design()
        return replace(_DESIGN_CACHE)

    @classmethod
    def _from_design(cls) -> "EnvParams":
        d = load_design()
        lt = lighting.analyse(d)
        th = thermal.analyse(d, lt.electrical_w_full, lt.ppf_total_umol_s * d["pod"]["window_par_transmittance"])
        pod = d["pod"]
        return cls(
            volume_m3=pod["chamber_w"] * pod["chamber_d"] * (pod["canopy_clear_h"] + 180) / 1e9,
            ua_w_k=th.ua_w_k, q_fan_full_m3h=th.exhaust_flow_m3h, ppfd_full=float(lt.ppfd_plants.mean()),
            led_w_full=lt.electrical_w_full, par_w_full=th.par_radiant_w, heater_w=d["air"]["heater_power_w"],
            fan_w=d["air"]["fan_power_w"], pump_w=d["hydraulics"]["pump_power_w"], humid_g_h=d["air"]["humidifier_ml_h"],
            grow_area_m2=d["tub"]["ext_l"] * d["tub"]["ext_w"] / 1e6, psu_eff=d["electrical"]["psu_efficiency"],
        )


def p_sat(t_c):
    return 610.94 * np.exp(17.625 * t_c / (t_c + 243.04))


def abs_hum(t_c, rh):
    return p_sat(t_c) * rh / 100.0 / (461.5 * (t_c + 273.15))


def rh_from_abs(t_c, w):
    return 100.0 * w * 461.5 * (t_c + 273.15) / p_sat(t_c)


@dataclass
class EnvState:
    air_t: float = 20.0
    w: float = field(default_factory=lambda: float(abs_hum(20.0, 50.0)))
    co2: float = 420.0
    sol_t: float = 20.0

    @property
    def rh(self) -> float:
        return float(np.clip(rh_from_abs(self.air_t, self.w), 0.0, 100.0))


@dataclass
class Actuators:
    led: float = 0.0
    heater: float = 0.0
    fan: float = 0.15
    mix: float = 0.3
    humidifier: bool = False
    pump: bool = True


def power_w(u: Actuators, p: EnvParams) -> dict:
    """Electrical power by consumer (DC side) and wall power."""
    led = u.led * p.led_w_full
    bay_fan = p.fan_w * (0.3 + 0.7 * u.led) ** 3 if u.led > 0.02 else 0.0
    fans = p.fan_w * (u.fan**3 + u.mix**3) + bay_fan
    heater = u.heater * p.heater_w
    pump = p.pump_w if u.pump else 0.0
    humid = p.humid_w if u.humidifier else 0.0
    dc = led + fans + heater + pump + humid + p.logic_w
    return {"led_w": led, "fan_w": fans, "heater_w": heater, "pump_w": pump, "humid_w": humid, "logic_w": p.logic_w,
            "dc_w": dc, "wall_w": dc / p.psu_eff}


def step(s: EnvState, u: Actuators, p: EnvParams, dt: float, room_t: float = 20.0, room_rh: float = 50.0,
         room_co2: float = 420.0, transp_g_s: float = 0.0, co2_uptake_g_s: float = 0.0) -> EnvState:
    """Advance the environment by dt seconds (explicit Euler with sub-stepping for stability)."""
    n = max(int(np.ceil(dt / 30.0)), 1)
    h = dt / n
    t, w, c, ts = s.air_t, s.w, s.co2, s.sol_t
    q = (p.q_leak_m3h + u.fan * p.q_fan_full_m3h) / 3600.0
    w_room = abs_hum(room_t, room_rh)
    for _ in range(n):
        latent_w = transp_g_s / 1000.0 * LATENT
        q_par = u.led * p.par_w_full
        q_win = u.led * p.window_w_k * 8.0
        q_fans = p.fan_w * (u.fan**3 + u.mix**3) + (0.3 * p.pump_w if u.pump else 0.0)
        q_heat = u.heater * p.heater_w
        q_sol = p.ua_sol_air_w_k * (t - ts)
        dT = (q_par + q_win + q_fans + q_heat - 0.6 * latent_w - RHO * CP * q * (t - room_t) - p.ua_w_k * (t - room_t) - q_sol) / p.c_air_j_k
        hum = p.humid_g_h / 3.6e6 if u.humidifier else 0.0
        dw = (transp_g_s / 1000.0 + hum - q * (w - w_room)) / p.volume_m3
        dc = (q * (room_co2 - c) - co2_uptake_g_s / 44.01 * 0.02445 * 1e6) / p.volume_m3
        dts = (q_sol + p.ua_sol_room_w_k * (room_t - ts) + (0.5 * p.pump_w if u.pump else 0.0)) / p.c_sol_j_k
        t += h * dT
        w = max(w + h * dw, 1e-5)
        w_sat = abs_hum(t, 100.0)
        if w > w_sat:                       # condensation on walls: clip to saturation
            w = w_sat
        c = max(c + h * dc, 150.0)
        ts += h * dts
    return EnvState(air_t=float(t), w=float(w), co2=float(c), sol_t=float(ts))
