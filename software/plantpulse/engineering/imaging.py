"""Imaging geometry, depth of field, gantry positioning error budget, motion-stereo depth resolution."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ImagingResult:
    fov_long_mm: float
    fov_short_mm: float
    gsd_lid_mm_px: float
    gsd_canopy_top_mm_px: float
    scale_change_pct_200mm: float
    hyperfocal_mm: float
    dof_near_mm: float
    dof_far_mm: float
    steps_per_mm: float
    step_resolution_mm: float
    position_sigma_mm: float
    position_sigma_px: float
    thermal_growth_mm_10k: float
    stereo_depth_res_mm: float
    offnadir_deg_edge: float

    def as_rows(self):
        return [
            ("Field of view at lid plane", f"{self.fov_long_mm:.0f} x {self.fov_short_mm:.0f} mm", "long axis across the two rows"),
            ("Ground sample distance at lid", f"{self.gsd_lid_mm_px:.3f} mm/px", "requirement <= 0.2"),
            ("GSD at 200 mm canopy height", f"{self.gsd_canopy_top_mm_px:.3f} mm/px", ""),
            ("Apparent area change for a leaf 200 mm above lid", f"+{self.scale_change_pct_200mm:.0f} %", "perspective; corrected with height estimate"),
            ("Hyperfocal distance (f/8, CoC 3 px)", f"{self.hyperfocal_mm:.0f} mm", ""),
            ("Depth of field", f"{self.dof_near_mm:.0f} - {self.dof_far_mm:.0f} mm from lens", "must span canopy top to lid (300-500 mm)"),
            ("Gantry resolution", f"{self.steps_per_mm:.0f} microsteps/mm ({1000 * self.step_resolution_mm:.1f} um)", "GT2 20T, 1/16 microstepping"),
            ("Station repeatability budget (RSS, 1 sigma)", f"{self.position_sigma_mm:.3f} mm = {self.position_sigma_px:.1f} px", "requirement <= 0.5 mm; residual removed by fiducial registration"),
            ("Rail thermal growth for 10 K (600 mm travel)", f"{self.thermal_growth_mm_10k:.2f} mm", "systematic between temperature treatments; fiducials compensate"),
            ("Motion-stereo depth resolution at 400 mm (60 mm baseline, 0.25 px)", f"{self.stereo_depth_res_mm:.2f} mm", "theoretical; texture-limited in practice"),
            ("Off-nadir angle at plant centre (row offset 100 mm)", f"{self.offnadir_deg_edge:.1f} deg", ""),
        ]


def analyse(d: dict) -> ImagingResult:
    im = d["imaging"]
    f, n, z = im["focal_mm"], im["f_number"], im["lens_to_lid"]
    fov_l = z * im["sensor_w_mm"] / f
    fov_s = z * im["sensor_h_mm"] / f
    gsd = fov_l / im["px_w"]
    gsd_top = (z - 200) * im["sensor_w_mm"] / f / im["px_w"]
    scale = ((z / (z - 200)) ** 2 - 1) * 100
    coc = 3 * im["pixel_um"] / 1000
    hyper = f**2 / (n * coc) + f
    s = im["focus_distance"]
    near = hyper * s / (hyper + (s - f))
    far = hyper * s / (hyper - (s - f)) if hyper > (s - f) else math.inf
    steps_mm = im["motor_steps_rev"] * im["microsteps"] / (im["pulley_teeth"] * im["belt_pitch"])
    full_step_mm = im["pulley_teeth"] * im["belt_pitch"] / im["motor_steps_rev"]
    contributions = [
        im["homing_repeatability_mm"],
        im["belt_stretch_mm"],
        0.05 * full_step_mm,           # stepper angular accuracy, 5 % of a full step, non-cumulative
        1 / steps_mm,                  # quantisation
        0.02,                          # carriage clearance / arm vibration residual after 0.5 s settle
    ]
    sigma = math.sqrt(sum(c**2 for c in contributions))
    f_px = f / (im["pixel_um"] / 1000)
    zc = 400.0
    depth_res = zc**2 * 0.25 / (f_px * 60.0)
    return ImagingResult(
        fov_long_mm=fov_l, fov_short_mm=fov_s, gsd_lid_mm_px=gsd, gsd_canopy_top_mm_px=gsd_top,
        scale_change_pct_200mm=scale, hyperfocal_mm=hyper, dof_near_mm=near, dof_far_mm=far,
        steps_per_mm=steps_mm, step_resolution_mm=1 / steps_mm, position_sigma_mm=sigma,
        position_sigma_px=sigma / gsd, thermal_growth_mm_10k=23e-6 * 600 * 10,
        stereo_depth_res_mm=depth_res, offnadir_deg_edge=math.degrees(math.atan(100.0 / z)),
    )
