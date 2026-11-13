"""Canopy height from gantry motion stereo, and perspective correction of projected area.

The gantry takes two exposures at x = station -/+ B/2 (default baseline B = 60 mm). The camera
translates parallel to the image x axis without rotation, so the pair is already rectified up to
the (small) registration error, and depth follows from disparity: Z = f_px * B / d.

STATUS: implemented and tested on synthetic geometry only. Lettuce leaves are low-texture and
specular; real performance must be established against ruler heights (VAL-CV-03).
"""
from __future__ import annotations

import cv2
import numpy as np


def depth_from_disparity(disparity_px, focal_px: float, baseline_mm: float):
    d = np.asarray(disparity_px, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, focal_px * baseline_mm / d, np.nan)


def disparity_map(left_bgr: np.ndarray, right_bgr: np.ndarray, focal_px: float, baseline_mm: float,
                  z_min_mm: float = 250.0, z_max_mm: float = 520.0) -> np.ndarray:
    """Semi-global block matching restricted to the plausible depth range. Returns disparity (px, float32, NaN = invalid)."""
    gl, gr = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY), cv2.cvtColor(right_bgr, cv2.COLOR_BGR2GRAY)
    d_min = int(np.floor(focal_px * baseline_mm / z_max_mm))
    d_max = int(np.ceil(focal_px * baseline_mm / z_min_mm))
    num = int(np.ceil((d_max - d_min) / 16.0)) * 16
    sgbm = cv2.StereoSGBM_create(minDisparity=d_min, numDisparities=max(num, 16), blockSize=7, P1=8 * 49, P2=32 * 49,
                                 uniquenessRatio=10, speckleWindowSize=100, speckleRange=2, disp12MaxDiff=1)
    disp = sgbm.compute(gl, gr).astype(np.float32) / 16.0
    disp[disp < d_min] = np.nan
    return disp


def canopy_height(disparity: np.ndarray, mask: np.ndarray, focal_px: float, baseline_mm: float, lens_to_lid_mm: float) -> dict:
    """Height statistics of the masked canopy above the lid (mm)."""
    z = depth_from_disparity(disparity, focal_px, baseline_mm)
    h = lens_to_lid_mm - z[(mask > 0) & np.isfinite(z)]
    h = h[(h > -10) & (h < lens_to_lid_mm - 150)]
    if h.size < 50:
        return {"height_p95_mm": np.nan, "height_mean_mm": np.nan, "height_valid_frac": float(h.size / max((mask > 0).sum(), 1))}
    return {"height_p95_mm": float(np.percentile(h, 95)), "height_mean_mm": float(h.mean()),
            "height_valid_frac": float(h.size / max((mask > 0).sum(), 1))}


def perspective_area_factor(mean_height_mm: float, lens_to_lid_mm: float) -> float:
    """Multiply lid-plane projected area by this to refer it to the canopy's mean height.
    A surface h above the lid is magnified by (Z/(Z-h))^2 in area."""
    if not np.isfinite(mean_height_mm):
        return np.nan
    return float(((lens_to_lid_mm - mean_height_mm) / lens_to_lid_mm) ** 2)
