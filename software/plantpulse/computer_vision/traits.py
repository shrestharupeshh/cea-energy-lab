"""Morphological traits from a per-plant mask."""
from __future__ import annotations

import cv2
import numpy as np


def morphology(mask: np.ndarray, mm_per_px: float, image_shape: tuple | None = None) -> dict:
    """Traits of one plant from its binary mask (uint8/bool), scale at the reference plane.

    projected_area_cm2 is the PROJECTED canopy area at the lid-plane scale. It is not leaf area:
    leaves overlap, and tissue above the lid is magnified by perspective (see height.py)."""
    m = (mask > 0).astype(np.uint8)
    area_px = int(m.sum())
    keys = ("projected_area_cm2", "diameter_max_mm", "diameter_perp_mm", "diameter_eq_mm", "convex_area_cm2", "solidity",
            "perimeter_mm", "compactness", "eccentricity", "centroid_x_px", "centroid_y_px", "touches_border")
    if area_px == 0:
        return {k: np.nan for k in keys} | {"projected_area_cm2": 0.0, "touches_border": False}
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pts = np.concatenate(cnts)
    hull = cv2.convexHull(pts)
    hull_area = max(cv2.contourArea(hull), 1.0)
    perim = sum(cv2.arcLength(c, True) for c in cnts)
    # maximum Feret diameter from the hull (rotating over hull vertex pairs)
    hp = hull.reshape(-1, 2).astype(np.float32)
    d = np.linalg.norm(hp[:, None, :] - hp[None, :, :], axis=2)
    i, j = np.unravel_index(np.argmax(d), d.shape)
    dmax = float(d[i, j])
    axis = (hp[j] - hp[i]) / (dmax + 1e-9)
    perp = np.array([-axis[1], axis[0]])
    proj = hp @ perp
    dperp = float(proj.max() - proj.min())
    mom = cv2.moments(m, binaryImage=True)
    cx, cy = mom["m10"] / mom["m00"], mom["m01"] / mom["m00"]
    mu20, mu02, mu11 = mom["mu20"] / mom["m00"], mom["mu02"] / mom["m00"], mom["mu11"] / mom["m00"]
    common = np.sqrt(max((mu20 - mu02) ** 2 + 4 * mu11**2, 0))
    l1, l2 = (mu20 + mu02 + common) / 2, (mu20 + mu02 - common) / 2
    ecc = float(np.sqrt(max(1 - l2 / l1, 0))) if l1 > 0 else 0.0
    h, w = m.shape
    border = bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any())
    s = mm_per_px
    return {
        "projected_area_cm2": area_px * s * s / 100, "diameter_max_mm": dmax * s, "diameter_perp_mm": dperp * s,
        "diameter_eq_mm": 2 * np.sqrt(area_px / np.pi) * s, "convex_area_cm2": hull_area * s * s / 100,
        "solidity": float(min(area_px / hull_area, 1.0)), "perimeter_mm": perim * s,
        "compactness": float(4 * np.pi * area_px / (perim**2 + 1e-9)), "eccentricity": ecc,
        "centroid_x_px": cx, "centroid_y_px": cy, "touches_border": border,
    }


def leaf_count_estimate(mask: np.ndarray, mm_per_px: float, min_leaf_mm: float = 10.0) -> dict:
    """Rough visible-leaf count: local maxima of the distance transform (leaf blades are locally widest).

    Valid only for young, open rosettes. For headed lettuce most leaves are hidden and this count
    saturates; the function returns a confidence flag and the estimate must not be reported as leaf
    number without validation against manual counts (protocol section 2)."""
    m = (mask > 0).astype(np.uint8)
    if m.sum() == 0:
        return {"leaf_count_est": 0, "leaf_count_confident": False}
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    dist = cv2.GaussianBlur(dist, (0, 0), 1.5)
    k = max(int(min_leaf_mm / mm_per_px) | 1, 3)
    peaks = (dist == cv2.dilate(dist, np.ones((k, k), np.uint8))) & (dist > 0.35 * min_leaf_mm / mm_per_px)
    n = int(cv2.connectedComponents(peaks.astype(np.uint8))[0] - 1)
    hull = cv2.convexHull(np.concatenate(cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0]))
    solidity = m.sum() / max(cv2.contourArea(hull), 1.0)
    return {"leaf_count_est": n, "leaf_count_confident": bool(solidity < 0.8 and n <= 12)}


def abnormality(color: dict, reference: dict | None = None) -> dict:
    """Visible-abnormality indicators from colour fractions; optional z-score distance from a
    reference (control) distribution given as {trait: (mean, sd)}."""
    out = {"chlorosis_frac": color.get("yellow_frac", np.nan), "necrosis_frac": color.get("brown_frac", np.nan)}
    if reference:
        z = [(color[k] - mu) / (sd + 1e-9) for k, (mu, sd) in reference.items() if k in color and np.isfinite(color[k])]
        out["color_anomaly_score"] = float(np.sqrt(np.mean(np.square(z)))) if z else np.nan
    return out
