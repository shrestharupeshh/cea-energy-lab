"""Lighting design: PPFD map, uniformity, DLI and electrical power.

Model: each strip is discretised into Lambertian point sources. Direct irradiance on a horizontal
plane at vertical distance h and slant range r is E = Phi * h^2 / (pi * r^4). Wall reflections use
the image-source method with wall reflectance rho per bounce (white matte walls are diffuse, so
treating them as mirrors of reduced reflectance is an approximation that conserves flux but
slightly misplaces it). The result is a design estimate to be replaced by the measured PPFD map
(validation test VAL-LGT-01).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LightingResult:
    ppf_total_umol_s: float
    electrical_w_full: float
    efficacy_umol_j: float
    ppfd_map: np.ndarray
    xs: np.ndarray
    ys: np.ndarray
    ppfd_plants: np.ndarray
    mean_ppfd_grow_area: float
    min_over_mean_plants: float
    min_over_max_plants: float
    utilisation_grow_area: float
    duty_for_nominal: float
    electrical_w_nominal: float
    dli_nominal: float
    dli_max_16h: float
    energy_kwh_day_nominal: float
    energy_kwh_cycle_nominal: float

    def as_rows(self):
        return [
            ("Photon flux of all strips at 700 mA", f"{self.ppf_total_umol_s:.0f} umol/s", "lm x PPF/klm conversion, thermally derated"),
            ("LED + driver electrical power at 100 %", f"{self.electrical_w_full:.1f} W", ""),
            ("System photon efficacy", f"{self.efficacy_umol_j:.2f} umol/J", "incl. driver"),
            ("Mean PPFD over 600x400 grow area at 100 %", f"{self.mean_ppfd_grow_area:.0f} umol/m2/s", "lid plane, simulated"),
            ("PPFD at the six plant positions at 100 %", ", ".join(f"{v:.0f}" for v in self.ppfd_plants), "umol/m2/s"),
            ("Uniformity min/mean (plant positions)", f"{self.min_over_mean_plants:.2f}", "requirement >= 0.80"),
            ("Uniformity min/max (plant positions)", f"{self.min_over_max_plants:.2f}", ""),
            ("Fraction of emitted photons landing on grow area", f"{self.utilisation_grow_area:.2f}", ""),
            ("PWM duty for 250 umol/m2/s", f"{100 * self.duty_for_nominal:.0f} %", ""),
            ("Electrical power at nominal PPFD", f"{self.electrical_w_nominal:.1f} W", ""),
            ("DLI at nominal (16 h)", f"{self.dli_nominal:.1f} mol/m2/d", ""),
            ("Maximum DLI at 100 % (16 h)", f"{self.dli_max_16h:.1f} mol/m2/d", ""),
            ("Lighting energy at nominal", f"{self.energy_kwh_day_nominal:.2f} kWh/day", f"{self.energy_kwh_cycle_nominal:.1f} kWh per 28-day cycle per pod"),
        ]


def ppfd_field(d: dict, plane_above_lid: float = 0.0, n_seg: int = 28, order: int = 2, grid: int = 5):
    """PPFD (umol m-2 s-1 at 100 % output) on a horizontal plane inside the chamber.

    Returns xs, ys (mm, chamber coordinates) and the map [len(ys), len(xs)].
    """
    pod, lt = d["pod"], d["lighting"]
    w, dep = pod["chamber_w"], pod["chamber_d"]
    h = (lt["led_plane_above_lid"] - plane_above_lid) / 1000.0
    rho = pod["wall_reflectance"]
    ppf_strip = lt["strip_flux_lm"] / 1000 * lt["ppf_per_klm"] * lt["thermal_derate"] * pod["window_par_transmittance"]
    phi = ppf_strip / n_seg
    sx = lt["strip_x_center"] + (np.arange(n_seg) + 0.5 - n_seg / 2) * lt["strip_len"] / n_seg
    src = np.array([(x, y) for y in lt["strip_y_positions"] for x in sx])
    xs = np.arange(grid / 2, w, grid)
    ys = np.arange(grid / 2, dep, grid)
    gx, gy = np.meshgrid(xs, ys)
    e = np.zeros_like(gx)
    for mx in range(-order, order + 1):
        for my in range(-order, order + 1):
            bounces = abs(mx) + abs(my)
            if bounces > order:
                continue
            atten = rho**bounces
            # image of source across walls: x' = 2*k*W +/- x
            ix = src[:, 0] if mx % 2 == 0 else w - src[:, 0]
            iy = src[:, 1] if my % 2 == 0 else dep - src[:, 1]
            ix = ix + mx * w
            iy = iy + my * dep
            for sxi, syi in zip(ix, iy):
                r2 = ((gx - sxi) / 1000) ** 2 + ((gy - syi) / 1000) ** 2 + h**2
                e += atten * phi * h**2 / (np.pi * r2**2)
    return xs, ys, e


def analyse(d: dict) -> LightingResult:
    lt, tub, pod = d["lighting"], d["tub"], d["pod"]
    xs, ys, e = ppfd_field(d)
    n = lt["n_strips"]
    ppf_total = n * lt["strip_flux_lm"] / 1000 * lt["ppf_per_klm"] * lt["thermal_derate"]
    p_full = n * lt["strip_vf_v"] * lt["strip_i_nom_a"] / lt["driver_efficiency"]
    x0, y0 = tub["tub_offset_x"], tub["tub_offset_y"]
    in_grow = (xs[None, :] >= x0) & (xs[None, :] <= x0 + tub["ext_l"]) & (ys[:, None] >= y0) & (ys[:, None] <= y0 + tub["ext_w"])
    mean_grow = float(e[in_grow].mean())
    plants = []
    for py in tub["plant_rows_y"]:
        for px in tub["plant_cols_x"]:
            ix = np.argmin(np.abs(xs - (x0 + px)))
            iy = np.argmin(np.abs(ys - (y0 + py)))
            # average over a 100 mm disc around the plant centre
            m = (xs[None, :] - xs[ix]) ** 2 + (ys[:, None] - ys[iy]) ** 2 <= 50.0**2
            plants.append(float(e[m].mean()))
    plants = np.array(plants)
    grow_area_m2 = tub["ext_l"] * tub["ext_w"] / 1e6
    util = mean_grow * grow_area_m2 / ppf_total
    duty = lt["nominal_ppfd"] / plants.mean()
    p_nom = p_full * duty  # PWM dimming: LED operating point unchanged, power scales with duty
    hours = lt["nominal_photoperiod_h"]
    return LightingResult(
        ppf_total_umol_s=ppf_total, electrical_w_full=p_full, efficacy_umol_j=ppf_total / p_full,
        ppfd_map=e, xs=xs, ys=ys, ppfd_plants=plants, mean_ppfd_grow_area=mean_grow,
        min_over_mean_plants=float(plants.min() / plants.mean()), min_over_max_plants=float(plants.min() / plants.max()),
        utilisation_grow_area=util, duty_for_nominal=duty, electrical_w_nominal=p_nom,
        dli_nominal=lt["nominal_ppfd"] * hours * 3600 / 1e6, dli_max_16h=float(plants.mean()) * 16 * 3600 / 1e6,
        energy_kwh_day_nominal=p_nom * hours / 1000, energy_kwh_cycle_nominal=p_nom * hours * 28 / 1000,
    )


def dli(ppfd: float, photoperiod_h: float) -> float:
    """Daily light integral, mol m-2 d-1."""
    return ppfd * photoperiod_h * 3600 / 1e6
