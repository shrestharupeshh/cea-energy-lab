"""Structural calculations for the pod frame, rack and imaging gantry.

Closed-form Euler-Bernoulli beam results. All lengths mm, forces N, stresses MPa.
These are design calculations, not test results.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

G = 9.80665


def simply_supported_udl(w_n_mm: float, span: float, e: float, i: float) -> tuple[float, float]:
    """Return (max deflection mm, max bending moment N.mm) for a uniformly loaded beam."""
    return 5 * w_n_mm * span**4 / (384 * e * i), w_n_mm * span**2 / 8


def simply_supported_point(p: float, span: float, e: float, i: float) -> tuple[float, float]:
    return p * span**3 / (48 * e * i), p * span / 4


def cantilever_point(p: float, length: float, e: float, i: float) -> tuple[float, float]:
    return p * length**3 / (3 * e * i), p * length


def cantilever_udl(w_n_mm: float, length: float, e: float, i: float) -> tuple[float, float]:
    return w_n_mm * length**4 / (8 * e * i), w_n_mm * length**2 / 2


def euler_buckling(e: float, i: float, length: float, k: float = 1.0) -> float:
    return math.pi**2 * e * i / (k * length) ** 2


@dataclass
class StructuralResult:
    water_volume_l: float
    water_mass_kg: float
    tub_total_mass_kg: float
    cross_member_deflection_mm: float
    cross_member_span_ratio: float
    cross_member_stress_mpa: float
    cross_member_sf_yield: float
    pod_mass_kg: float
    column_load_n: float
    column_buckling_n: float
    column_sf: float
    joint_load_n: float
    joint_sf: float
    reservoir_shelf_deflection_mm: float
    arm_tip_deflection_mm: float
    arm_stress_mpa: float

    def as_rows(self) -> list[tuple[str, str, str]]:
        return [
            ("Solution volume in tub", f"{self.water_volume_l:.1f} L", "at design depth"),
            ("Solution mass", f"{self.water_mass_kg:.1f} kg", ""),
            ("Tub + lid + plants + solution", f"{self.tub_total_mass_kg:.1f} kg", "mature crop"),
            ("Tub cross-member deflection", f"{self.cross_member_deflection_mm:.2f} mm",
             f"L/{self.cross_member_span_ratio:.0f}; limit L/250"),
            ("Tub cross-member bending stress", f"{self.cross_member_stress_mpa:.1f} MPa",
             f"SF on yield {self.cross_member_sf_yield:.1f}"),
            ("Wet pod mass", f"{self.pod_mass_kg:.0f} kg", "frame + panels + equipment + water"),
            ("Lower-pod column load (upper pod on top)", f"{self.column_load_n:.0f} N", "per column, 6 columns"),
            ("Column Euler buckling load", f"{self.column_buckling_n:.0f} N", f"SF {self.column_sf:.0f}"),
            ("Corner joint shear demand", f"{self.joint_load_n:.0f} N", f"SF vs T-nut slip {self.joint_sf:.1f}"),
            ("Top-up reservoir shelf deflection", f"{self.reservoir_shelf_deflection_mm:.3f} mm", "2020 cantilever pair"),
            ("Camera arm tip deflection", f"{self.arm_tip_deflection_mm:.3f} mm", "static, payload + self weight"),
            ("Camera arm root stress", f"{self.arm_stress_mpa:.2f} MPa", ""),
        ]


def analyse(d: dict) -> StructuralResult:
    tub, pod, st, im = d["tub"], d["pod"], d["structure"], d["imaging"]
    e, i20 = st["e_al_mpa"], st["i_2020_mm4"]
    il, iw = tub["ext_l"] - 2 * tub["wall_t"], tub["ext_w"] - 2 * tub["wall_t"]
    vol_l = il * iw * tub["solution_depth"] / 1e6
    m_water = vol_l * 1.0
    m_tub = m_water + 2.2 + 1.0 + d["facility"]["plants_per_pod"] * 0.25  # container, lid, plants+pots
    # Tub rests on two 2020 cross members spanning the chamber depth (plus the base panel, ignored).
    span = pod["chamber_d"]
    w = (m_tub * G / 2) / span
    defl, mom = simply_supported_udl(w, span, e, i20)
    z = i20 / (pod["extrusion"] / 2)
    stress = mom / z

    # Pod mass estimate
    perim = 2 * (pod["chamber_w"] + pod["service_bay_w"] + pod["chamber_d"] + 2 * pod["extrusion"])
    frame_len_m = (3 * perim + 6 * pod["module_h"] + 4 * pod["chamber_d"]) / 1000
    m_frame = frame_len_m * st["mass_2020_kg_m"]
    area_m2 = 2 * (pod["chamber_w"] * pod["module_h"] + pod["chamber_d"] * pod["module_h"]
                   + pod["chamber_w"] * pod["chamber_d"]) / 1e6
    m_panels = area_m2 * pod["panel_t"] / 1000 * 550  # expanded PVC ~550 kg/m3
    m_equipment = 6.0 + d["hydraulics"]["topup_reservoir_l"]  # LEDs, plate, fans, gantry, electronics + reservoir
    m_pod = m_frame + m_panels + m_equipment + m_tub

    n_cols = 6
    col_load = (m_pod * G) / n_cols  # lower pod carries one upper pod
    pcr = euler_buckling(e, i20, pod["module_h"])
    # Corner joint: half of a cross-member reaction per bracket
    joint = m_tub * G / 4
    # Reservoir shelf: two 2020 cantilevers, 150 mm, carrying a full reservoir
    p_res = (d["hydraulics"]["topup_reservoir_l"] + 0.5) * G / 2
    shelf_defl, _ = cantilever_point(p_res, 150.0, e, i20)
    # Camera arm
    p_tip = im["carriage_payload_kg"] * G
    w_self = st["mass_2020_kg_m"] * G / 1000
    d1, m1 = cantilever_point(p_tip, im["arm_len"], e, i20)
    d2, m2 = cantilever_udl(w_self, im["arm_len"], e, i20)
    return StructuralResult(
        water_volume_l=vol_l, water_mass_kg=m_water, tub_total_mass_kg=m_tub,
        cross_member_deflection_mm=defl, cross_member_span_ratio=span / defl,
        cross_member_stress_mpa=stress, cross_member_sf_yield=st["yield_6063_t5_mpa"] / stress,
        pod_mass_kg=m_pod, column_load_n=col_load, column_buckling_n=pcr, column_sf=pcr / col_load,
        joint_load_n=joint, joint_sf=st["m5_tnut_slip_n"] / joint,
        reservoir_shelf_deflection_mm=shelf_defl,
        arm_tip_deflection_mm=d1 + d2, arm_stress_mpa=(m1 + m2) / z,
    )
