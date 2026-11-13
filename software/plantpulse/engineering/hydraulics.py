"""Recirculation loop hydraulics: Darcy-Weisbach losses and pump operating point."""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq

RHO = 998.0
NU = 1.0e-6  # m2/s water at 20 C
G = 9.80665


def friction_factor(re: float, rel_rough: float = 1e-5) -> float:
    """Darcy friction factor: laminar below Re 2300, Haaland above (conservative in transition)."""
    if re < 1e-9:
        return 0.0
    if re < 2300:
        return 64.0 / re
    return (-1.8 * math.log10((rel_rough / 3.7) ** 1.11 + 6.9 / re)) ** -2


def system_head(q_lpm: float, h: dict) -> float:
    """Head (m) required to push q through the loop."""
    q = q_lpm / 60000.0
    d = h["tube_id"] / 1000.0
    a = math.pi * d**2 / 4
    v = q / a
    re = v * d / NU
    f = friction_factor(re)
    k_minor = h["n_elbows"] * 0.9 + h["flow_meter_k_loss"] + 1.0 + 0.5  # elbows, meter, exit, entrance
    hf = (f * h["tube_len_m"] / d + k_minor) * v**2 / (2 * G)
    return h["static_lift_m"] + hf


def pump_head(q_lpm: float, h: dict) -> float:
    """Generic centrifugal curve H = H0 (1 - (Q/Qmax)^2). Replace with the datasheet curve."""
    return h["pump_max_head_m"] * (1 - (q_lpm / h["pump_max_flow_lpm"]) ** 2)


@dataclass
class HydraulicResult:
    required_flow_lpm: float
    operating_flow_lpm: float
    operating_head_m: float
    velocity_m_s: float
    reynolds: float
    turnover_per_h: float
    margin: float
    pressure_loss_kpa_at_required: float

    def as_rows(self):
        return [
            ("Required flow for target turnover", f"{self.required_flow_lpm:.2f} L/min", ""),
            ("Loss at required flow", f"{self.pressure_loss_kpa_at_required:.2f} kPa", "incl. static lift"),
            ("Pump/system operating point", f"{self.operating_flow_lpm:.2f} L/min @ {self.operating_head_m:.2f} m",
             "generic pump curve - verify"),
            ("Tube velocity / Reynolds number", f"{self.velocity_m_s:.2f} m/s / {self.reynolds:.0f}", ""),
            ("Tub turnover at operating point", f"{self.turnover_per_h:.1f} per hour", f"margin x{self.margin:.1f}; throttle with PWM"),
        ]


def analyse(d: dict, tub_volume_l: float) -> HydraulicResult:
    h = d["hydraulics"]
    q_req = tub_volume_l * h["target_turnover_per_h"] / 60.0
    q_op = brentq(lambda q: pump_head(q, h) - system_head(q, h), 1e-4, h["pump_max_flow_lpm"] - 1e-6)
    dia = h["tube_id"] / 1000
    v = (q_op / 60000) / (math.pi * dia**2 / 4)
    return HydraulicResult(
        required_flow_lpm=q_req, operating_flow_lpm=q_op, operating_head_m=system_head(q_op, h),
        velocity_m_s=v, reynolds=v * dia / NU, turnover_per_h=q_op * 60 / tub_volume_l,
        margin=q_op / q_req, pressure_loss_kpa_at_required=system_head(q_req, h) * RHO * G / 1000,
    )
