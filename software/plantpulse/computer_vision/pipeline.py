"""Image -> per-plant trait records."""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from . import color as colorm
from . import registration as reg
from . import segmentation as seg
from . import traits as tr

PLANT_XY = {1: (100.0, 100.0), 2: (300.0, 100.0), 3: (500.0, 100.0), 4: (100.0, 300.0), 5: (300.0, 300.0), 6: (500.0, 300.0)}
STATION_X = {1: 100.0, 2: 300.0, 3: 500.0}
STATION_PLANTS = {1: [1, 4], 2: [2, 5], 3: [3, 6]}
QC_NO_FIDUCIAL, QC_BLUR, QC_TRUNCATED, QC_TOUCHING, QC_EXPOSURE = 1, 2, 4, 8, 16


def sharpness(bgr: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def nominal_registration(station: int, w: int, h: int, mm_per_px: float) -> reg.Registration:
    """Fallback when fiducials are hidden: assume the gantry is exactly on station."""
    # px (col,row) -> lid (x,y): x = (row - h/2) s + x_c ; y = (col - w/2) s + 200
    H = np.array([[0, mm_per_px, STATION_X[station] - h / 2 * mm_per_px], [mm_per_px, 0, 200.0 - w / 2 * mm_per_px], [0, 0, 1]], float)
    return reg.Registration(False, mm_per_px, H, 0, np.nan)


def process_image(bgr: np.ndarray, station: int, nominal_mm_per_px: float, ccm: np.ndarray | None = None,
                  blur_threshold: float = 15.0, return_masks: bool = False):
    """Return a list of per-plant trait dicts for the two plants centred at this station (plus
    neighbours used only to split touching canopies)."""
    h, w = bgr.shape[:2]
    if ccm is not None:
        bgr = colorm.apply_ccm(bgr, ccm)
    r = reg.register(bgr, nominal_mm_per_px)
    qc_img = 0
    if not r.ok or r.H_px_to_lid is None or abs(r.mm_per_px / nominal_mm_per_px - 1) > 0.05:
        r = nominal_registration(station, w, h, nominal_mm_per_px)
        qc_img |= QC_NO_FIDUCIAL
    if sharpness(bgr) < blur_threshold:
        qc_img |= QC_BLUR
    mean_v = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean())
    if mean_v < 15 or mean_v > 240:
        qc_img |= QC_EXPOSURE
    mask = seg.segment(bgr)
    # seeds: all plant positions whose centre falls inside (or near) the frame
    centres = {p: r.to_px([xy])[0] for p, xy in PLANT_XY.items()}
    inframe = {p: c for p, c in centres.items() if -0.6 * w < c[0] < 1.6 * w and -0.6 * h < c[1] < 1.6 * h}
    order = sorted(inframe)
    seeds = np.array([inframe[p] for p in order])
    labels = seg.split_plants(mask, seeds, r.mm_per_px)
    out, masks = [], {}
    cover = station_cover(mask, r, station)
    for p in STATION_PLANTS[station]:
        if p not in order:
            continue
        m = (labels == order.index(p) + 1).astype(np.uint8) * 255
        morph = tr.morphology(m, r.mm_per_px)
        col = colorm.color_traits(bgr, m)
        qc = qc_img | (QC_TRUNCATED if morph["touches_border"] else 0)
        others = (labels > 0) & (labels != order.index(p) + 1)
        if (cv2.dilate(m, np.ones((5, 5), np.uint8)) > 0)[others].any():
            qc |= QC_TOUCHING
        rec = {"position": p, "station": station, "station_cover": cover, "mm_per_px": r.mm_per_px, "n_fiducials": r.n_markers,
               "reg_rms_mm": r.reproj_rms_mm, **morph, **col, **tr.leaf_count_estimate(m, r.mm_per_px),
               **tr.abnormality(col), "qc": qc, "provenance": "vision"}
        out.append(rec)
        masks[p] = m
    return (out, masks) if return_masks else out


def station_cover(mask: np.ndarray, r: reg.Registration, station: int, strip_mm: float = 200.0) -> float:
    """Canopy cover fraction (0-1) of the lid strip belonging to this station (its plant column,
    `strip_mm` wide, full lid depth). Summing the three stations gives pod canopy cover without
    double counting, and stays valid after neighbouring canopies touch."""
    h, w = mask.shape
    x0, x1 = STATION_X[station] - strip_mm / 2, STATION_X[station] + strip_mm / 2
    quad = r.to_px([(x0, 0.0), (x0, 400.0), (x1, 400.0), (x1, 0.0)])
    region = np.zeros((h, w), np.uint8)
    cv2.fillPoly(region, [np.round(quad).astype(np.int32)], 255)
    inside = region > 0
    return float((mask[inside] > 0).mean()) if inside.any() else float("nan")


def traits_table(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)
