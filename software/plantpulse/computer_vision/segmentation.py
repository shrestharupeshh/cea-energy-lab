"""Plant / background segmentation for top-view RGB images on a matte black lid.

Baseline (interpretable, no training data): excess-green index + CIELAB a* with Otsu thresholds,
intersected and cleaned morphologically. Known limits: red/purple cultivars need the a* rule
changed; algae on the lid and green reflections are false positives; dark shaded leaf interiors
can be missed. A learned model (U-Net) is the planned upgrade once annotated images from the real
platform exist; it must beat this baseline on held-out pod-runs to be adopted.
"""
from __future__ import annotations

import cv2
import numpy as np


def excess_green(bgr: np.ndarray) -> np.ndarray:
    b, g, r = [bgr[..., i].astype(np.float32) for i in range(3)]
    s = b + g + r + 1e-6
    return 2 * g / s - r / s - b / s


def segment(bgr: np.ndarray, min_area_px: int = 150, exg_floor: float = 0.06, include_senescent: bool = True) -> np.ndarray:
    """Return a uint8 mask (255 = plant)."""
    exg = excess_green(bgr)
    exg8 = np.clip((exg + 1) * 127.5, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(exg8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    t = max(t, (exg_floor + 1) * 127.5)
    green = exg8 > t
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    a = lab[..., 1].astype(np.int16) - 128
    L = lab[..., 0]
    green &= (a < -4) & (L > 25)
    mask = green
    if include_senescent:
        # yellow / brown tissue adjacent to green tissue (chlorosis, tipburn) belongs to the plant
        bch = lab[..., 2].astype(np.int16) - 128
        warm = (bch > 18) & (L > 45) & (a < 25)
        near = cv2.dilate(green.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))) > 0
        mask = green | (warm & near)
    m = mask.astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
    n, lab_, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area_px
    return (keep[lab_] * 255).astype(np.uint8)


def split_plants(mask: np.ndarray, centres_px: np.ndarray, mm_per_px: float = 1.0, seed_radius_mm: float = 18.0,
                 max_stray_mm: float = 170.0) -> np.ndarray:
    """Label each plant pixel with the index (1..n) of the plant it belongs to.

    Plant positions are known (fixed net-pot grid), so assignment is geometric and deterministic:
      1. each connected component is matched to the plant centres that lie on it;
      2. a component holding one centre belongs entirely to that plant;
      3. a component holding several centres (touching canopies) is divided by nearest centre
         (Voronoi cut along the midline). This is a geometric convention, not a biological
         boundary; such plants get the `touching` QC flag and their individual areas are less
         certain than their sum;
      4. a component holding no centre goes to the nearest centre if within `max_stray_mm`.
    Centres may lie outside the image (neighbouring columns)."""
    labels = np.zeros(mask.shape, np.int32)
    if mask.max() == 0 or len(centres_px) == 0:
        return labels
    c = np.asarray(centres_px, float)
    n, comp, stats, cent = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    h, w = mask.shape
    r = max(int(round(seed_radius_mm / mm_per_px)), 3)
    owners: dict[int, list[int]] = {k: [] for k in range(1, n)}
    for i, (x, y) in enumerate(c):
        xi, yi = int(round(x)), int(round(y))
        x0, x1, y0, y1 = max(xi - r, 0), min(xi + r + 1, w), max(yi - r, 0), min(yi + r + 1, h)
        if x0 >= x1 or y0 >= y1:
            continue
        ids, counts = np.unique(comp[y0:y1, x0:x1], return_counts=True)
        ids, counts = ids[ids > 0], counts[ids > 0]
        if len(ids):
            owners[int(ids[np.argmax(counts)])].append(i)
    yy, xx = np.mgrid[0:h, 0:w]
    for k in range(1, n):
        sel = comp == k
        own = owners[k]
        if len(own) == 1:
            labels[sel] = own[0] + 1
        elif len(own) > 1:
            d = np.stack([(xx[sel] - c[i, 0]) ** 2 + (yy[sel] - c[i, 1]) ** 2 for i in own])
            labels[sel] = np.asarray(own)[np.argmin(d, axis=0)] + 1
        else:
            d = np.hypot(c[:, 0] - cent[k, 0], c[:, 1] - cent[k, 1]) * mm_per_px
            if d.min() <= max_stray_mm:
                labels[sel] = int(np.argmin(d)) + 1
    return labels


def iou(pred: np.ndarray, truth: np.ndarray) -> float:
    p, t = pred > 0, truth > 0
    u = (p | t).sum()
    return float((p & t).sum() / u) if u else 1.0
