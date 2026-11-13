"""Chamber heat, moisture, CO2 and airflow balances (steady state design calculations)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq

RHO_AIR = 1.2
CP_AIR = 1005.0
LATENT = 2.45e6  # J/kg
P_ATM = 101325.0


def p_sat(t_c: float) -> float:
    """Saturation vapour pressure (Pa), Magnus form."""
    return 610.94 * math.exp(17.625 * t_c / (t_c + 243.04))


def abs_humidity(t_c: float, rh_pct: float) -> float:
    """Water vapour density (kg/m3)."""
    return p_sat(t_c) * rh_pct / 100 / (461.5 * (t_c + 273.15))


def vpd_kpa(t_c: float, rh_pct: float) -> float:
    return p_sat(t_c) * (1 - rh_pct / 100) / 1000


def fan_system_flow(air: dict, n_traps: int = 2) -> float:
    """Operating flow (m3/h) of one fan against the light-trap system curve.

    Fan curve approximated as linear between free flow and shut-off pressure (conservative for
    axial fans in mid range). System curve dp = n_traps * K * rho v^2 / 2.
    """
    a = math.pi * (air["duct_d"] / 1000) ** 2 / 4
    qmax = air["fan_free_flow_m3h"] / 3600

    def f(q):
        v = q / a
        return air["fan_static_pressure_pa"] * (1 - q / qmax) - n_traps * air["light_trap_k"] * RHO_AIR * v**2 / 2

    return brentq(f, 1e-6, qmax) * 3600


def wall_ua(pod: dict) -> float:
    """Overall conductance (W/K) of the growth chamber walls to the room."""
    w, dpt, h = pod["chamber_w"] / 1000, pod["chamber_d"] / 1000, (pod["canopy_clear_h"] + 200) / 1000
    area = 2 * (w * h + dpt * h) + w * dpt  # four walls + floor; ceiling is the LED window (handled separately)
    r = 0.13 + pod["panel_t"] / 1000 / pod["panel_k_w_mk"] + 0.13
    return area / r


@dataclass
class ThermalResult:
    exhaust_flow_m3h: float
    air_changes_per_h: float
    ua_w_k: float
    par_radiant_w: float
    chamber_gain_w: float
    dt_lights_on_full_vent_k: float
    dt_lights_on_min_vent_k: float
    led_bay_heat_w: float
    led_bay_dt_k: float
    heater_needed_w: float
    heater_margin: float
    max_setpoint_c: float
    transp_g_h: float
    vent_moisture_capacity_g_h: float
    rh_floor_pct_full_vent: float
    humidifier_needed_g_h: float
    co2_drawdown_ppm_full_vent: float
    min_vent_for_co2_m3h: float
    canopy_air_speed_m_s: float

    def as_rows(self):
        return [
            ("Exhaust fan operating flow (2 light traps)", f"{self.exhaust_flow_m3h:.1f} m3/h", f"{self.air_changes_per_h:.0f} air changes/h"),
            ("Wall conductance UA", f"{self.ua_w_k:.1f} W/K", ""),
            ("PAR radiant power entering chamber", f"{self.par_radiant_w:.1f} W", "at maximum LED output"),
            ("Sensible gain in chamber (lights on)", f"{self.chamber_gain_w:.1f} W", "PAR + window conduction + fans, less latent"),
            ("Chamber rise above room, full ventilation", f"{self.dt_lights_on_full_vent_k:.1f} K", "lowest achievable day temperature = room + this"),
            ("Chamber rise above room, minimum ventilation", f"{self.dt_lights_on_min_vent_k:.1f} K", "heater off"),
            ("LED bay heat to reject", f"{self.led_bay_heat_w:.1f} W", "electrical minus PAR transmitted"),
            ("LED bay air temperature rise", f"{self.led_bay_dt_k:.1f} K", "dedicated fan, room air"),
            ("Heater power for 30 C in 20 C room (lights off, min vent)", f"{self.heater_needed_w:.0f} W", f"installed 100 W: margin x{self.heater_margin:.1f}"),
            ("Maximum sustainable setpoint with heater", f"{self.max_setpoint_c:.1f} C", "lights off, minimum ventilation"),
            ("Peak crop transpiration (6 plants)", f"{self.transp_g_h:.0f} g/h", "assumption: 150 mL/plant/day in 16 h"),
            ("Ventilation moisture removal capacity", f"{self.vent_moisture_capacity_g_h:.0f} g/h", "23 C/70 % chamber vs 20 C/50 % room, full flow"),
            ("RH floor at full ventilation, mature crop", f"{self.rh_floor_pct_full_vent:.0f} %", ""),
            ("Humidifier duty for 70 % RH, empty chamber, min vent", f"{self.humidifier_needed_g_h:.0f} g/h", "installed ~35 g/h"),
            ("CO2 drawdown at full ventilation", f"{self.co2_drawdown_ppm_full_vent:.0f} ppm", "peak assimilation assumption"),
            ("Minimum ventilation for < 100 ppm drawdown", f"{self.min_vent_for_co2_m3h:.1f} m3/h", "sets the minimum fan duty"),
            ("Mean air speed over canopy, mixing fan at 100 %", f"{self.canopy_air_speed_m_s:.2f} m/s", f"jet estimate; run at ~{100 * 0.5 / self.canopy_air_speed_m_s:.0f} % PWM for 0.5 m/s; measure with anemometer"),
        ]


def analyse(d: dict, led_electrical_w: float, ppf_into_chamber_umol_s: float) -> ThermalResult:
    pod, air, fac = d["pod"], d["air"], d["facility"]
    t_room, rh_room = fac["room_setpoint_c"], fac["room_rh_pct"]
    q_full = fan_system_flow(air)
    q_min = 4.0  # m3/h at minimum fan duty (set by CO2 requirement, checked below)
    vol = pod["chamber_w"] * pod["chamber_d"] * (pod["canopy_clear_h"] + 180) / 1e9
    ua = wall_ua(pod)
    par_w = ppf_into_chamber_umol_s / 4.6  # ~4.6 umol/J for phosphor-white LED in the PAR band
    # window conduction from the warm LED bay (bay ~8 K above chamber), 3 mm acrylic k=0.19
    a_win = pod["chamber_w"] * pod["chamber_d"] / 1e6
    u_win = 1 / (0.13 + pod["window_t"] / 1000 / 0.19 + 0.13)
    q_win = u_win * a_win * 8.0
    transp_kg_s = fac["plants_per_pod"] * 0.150 / (16 * 3600)
    latent_w = transp_kg_s * LATENT
    fans_w = air["fan_power_w"] * (air["n_exhaust_fans"] + air["n_mixing_fans"]) + d["hydraulics"]["pump_power_w"] * 0.3
    gain = par_w + q_win + fans_w - 0.6 * latent_w  # 60 % of transpiration energy drawn from air/radiation load

    def dt(q_m3h, load):
        return load / (RHO_AIR * CP_AIR * q_m3h / 3600 + ua)

    led_bay_heat = led_electrical_w - par_w  # electrical input minus PAR transmitted into the chamber
    q_bay = fan_system_flow(air, n_traps=1)
    bay_dt = led_bay_heat / (RHO_AIR * CP_AIR * q_bay / 3600)
    k_min = RHO_AIR * CP_AIR * q_min / 3600 + ua
    heater_needed = 10.0 * k_min - fans_w
    max_sp = t_room + (air["heater_power_w"] + fans_w) / k_min
    # moisture
    rho_in = abs_humidity(23.0, 70.0)
    rho_room = abs_humidity(t_room, rh_room)
    cap = q_full * (rho_in - rho_room) * 1000
    transp_g_h = transp_kg_s * 3.6e6
    rho_eq = rho_room + transp_g_h / 1000 / q_full
    rh_floor = 100 * rho_eq / abs_humidity(23.0, 100.0)
    humid_needed = q_min * (rho_in - rho_room) * 1000
    # CO2: peak net assimilation, 6 plants x 0.8 g DW/day, 1.47 g CO2 per g CH2O / 0.8 conversion
    co2_g_h = fac["plants_per_pod"] * 0.8 * 1.47 / 0.8 / 16
    co2_m3_h = co2_g_h / 44.01 * 0.02445
    drawdown = co2_m3_h / q_full * 1e6
    min_vent = co2_m3_h / 100e-6
    # mixing-fan free jet: centreline decay u/u0 ~ 6 d/x, average over canopy ~ 0.5 of centreline at 0.4 m
    a_fan = math.pi * (air["duct_d"] / 1000) ** 2 / 4
    u0 = air["fan_free_flow_m3h"] / 3600 / a_fan
    canopy_u = 0.5 * min(u0, u0 * 6 * (air["duct_d"] / 1000) / 0.4)
    return ThermalResult(
        exhaust_flow_m3h=q_full, air_changes_per_h=q_full / vol, ua_w_k=ua, par_radiant_w=par_w,
        chamber_gain_w=gain, dt_lights_on_full_vent_k=dt(q_full, gain), dt_lights_on_min_vent_k=dt(q_min, gain),
        led_bay_heat_w=led_bay_heat, led_bay_dt_k=bay_dt, heater_needed_w=heater_needed,
        heater_margin=air["heater_power_w"] / heater_needed, max_setpoint_c=max_sp,
        transp_g_h=transp_g_h, vent_moisture_capacity_g_h=cap, rh_floor_pct_full_vent=rh_floor,
        humidifier_needed_g_h=humid_needed, co2_drawdown_ppm_full_vent=drawdown, min_vent_for_co2_m3h=min_vent,
        canopy_air_speed_m_s=canopy_u,
    )
