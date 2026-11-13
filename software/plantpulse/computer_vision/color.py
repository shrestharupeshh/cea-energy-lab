"""Colour calibration and colour traits."""
from __future__ import annotations

import cv2
import numpy as np

# sRGB values (0-255) of the six neutral + six chromatic reference patches printed on the lid card.
REFERENCE_PATCHES_RGB = np.array([
    [243, 243, 242], [200, 200, 200], [160, 160, 160], [122, 122, 121], [85, 85, 85], [52, 52, 52],
    [175, 54, 60], [70, 148, 73], [56, 61, 150], [231, 199, 31], [187, 86, 149], [8, 133, 161]], np.float32)


def fit_ccm(measured_rgb: np.ndarray, reference_rgb: np.ndarray = REFERENCE_PATCHES_RGB) -> np.ndarray:
    """Least-squares 3x4 affine colour-correction matrix (linear RGB domain is preferable; with fixed
    exposure and a linear camera response the affine fit in display RGB is an adequate first step)."""
    m = np.asarray(measured_rgb, np.float32)
    A = np.hstack([m, np.ones((len(m), 1), np.float32)])
    ccm, *_ = np.linalg.lstsq(A, np.asarray(reference_rgb, np.float32), rcond=None)
    return ccm.T                                         # 3 x 4


def apply_ccm(bgr: np.ndarray, ccm: np.ndarray) -> np.ndarray:
    rgb = bgr[..., ::-1].reshape(-1, 3).astype(np.float32)
    out = rgb @ ccm[:, :3].T + ccm[:, 3]
    return np.clip(out, 0, 255).astype(np.uint8).reshape(bgr.shape)[..., ::-1]


def color_traits(bgr: np.ndarray, mask: np.ndarray) -> dict:
    """Colour statistics of the plant pixels. Meaningful across time and pods only after colour
    calibration and under the fixed imaging illumination."""
    m = mask > 0
    if m.sum() == 0:
        return {k: np.nan for k in ("L_mean", "a_mean", "b_mean", "hue_deg", "exg_mean", "ngrdi", "vari", "yellow_frac", "brown_frac", "dark_green_frac")}
    px = bgr[m].astype(np.float32)
    b, g, r = px[:, 0], px[:, 1], px[:, 2]
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[m].astype(np.float32)
    L, a, bb = lab[:, 0] * 100 / 255, lab[:, 1] - 128, lab[:, 2] - 128
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[m].astype(np.float32)
    hue = hsv[:, 0] * 2.0
    s = r + g + b + 1e-6
    yellow = (hue >= 36) & (hue < 64) & (hsv[:, 1] > 60) & (hsv[:, 2] > 110)
    brown = ((hue < 36) | (hue > 330)) & (hsv[:, 2] > 40)
    return {
        "L_mean": float(L.mean()), "a_mean": float(a.mean()), "b_mean": float(bb.mean()),
        "hue_deg": float(np.degrees(np.arctan2(np.sin(np.radians(hue)).mean(), np.cos(np.radians(hue)).mean())) % 360),
        "exg_mean": float(((2 * g - r - b) / s).mean()), "ngrdi": float(((g - r) / (g + r + 1e-6)).mean()),
        "vari": float(np.clip((g - r) / (g + r - b + 1e-6), -5, 5).mean()),
        "yellow_frac": float(yellow.mean()), "brown_frac": float(brown.mean()),
        "dark_green_frac": float(((hue >= 64) & (hue < 170) & (hsv[:, 2] < 90)).mean()),
    }
