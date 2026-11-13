"""Validation of automated traits against manual ground truth, and flatbed-scanner leaf area."""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from ..stats.agreement import agreement


def compare(df: pd.DataFrame, pairs: dict[str, str], group: str | None = None) -> pd.DataFrame:
    """pairs: {manual_column: automated_column}. Returns one row of agreement statistics per trait
    (and per group if given). Reports bias and limits of agreement first; R2 is informational."""
    rows = []
    groups = [(None, df)] if group is None else list(df.groupby(group))
    for gname, g in groups:
        for ref, est in pairs.items():
            d = g[[ref, est]].dropna()
            if len(d) < 3:
                continue
            a = agreement(d[ref], d[est])
            rows.append({"trait": ref, "estimate": est, "group": gname, **{k: v for k, v in a.items() if k != "bias_ci"},
                         "bias_ci_low": a["bias_ci"][0], "bias_ci_high": a["bias_ci"][1]})
    return pd.DataFrame(rows)


def scanner_area(image_bgr: np.ndarray, dpi: float = 300.0, reference_cm2: float | None = 100.0) -> dict:
    """Leaf area from a flatbed scan of detached leaves on a white background.
    If a dark-blue reference card of known area is present (largest blue blob), it is used to
    verify the nominal dpi scale; a deviation > 1 % should be investigated."""
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    leaf = ((hsv[..., 1] > 50) & (hsv[..., 0] > 20) & (hsv[..., 0] < 95)).astype(np.uint8)
    leaf = cv2.morphologyEx(leaf, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    px_cm2 = (2.54 / dpi) ** 2
    out = {"leaf_area_cm2": float(leaf.sum() * px_cm2), "scale_check_ratio": np.nan}
    if reference_cm2:
        blue = ((hsv[..., 0] > 100) & (hsv[..., 0] < 130) & (hsv[..., 1] > 80)).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(blue, 8)
        if n > 1:
            out["scale_check_ratio"] = float(stats[1:, cv2.CC_STAT_AREA].max() * px_cm2 / reference_cm2)
    return out
