"""Procedural top-view lettuce images with exact ground truth, for software verification only.

These images exist to test that the vision pipeline's geometry, registration, segmentation and
trait code are correct against a known answer. They are NOT a substitute for real images and say
nothing about accuracy on real plants (no specular highlights, veins, overlap shading realism,
algae, water droplets or perspective relief).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..computer_vision import registration as reg

LID_L, LID_W = 600.0, 400.0
PLANT_XY = {1: (100.0, 100.0), 2: (300.0, 100.0), 3: (500.0, 100.0), 4: (100.0, 300.0), 5: (300.0, 300.0), 6: (500.0, 300.0)}
STATION_X = {1: 100.0, 2: 300.0, 3: 500.0}
FOV_LONG_MM = 524.0


@dataclass
class PlantLook:
    area_cm2: float                 # target projected area
    chlorosis: float = 0.0          # 0..1 yellowing
    tipburn: float = 0.0            # 0..1 necrotic margins
    compact: float = 0.0            # 0..1 shorter, rounder leaves
    seed: int = 0


def lid_to_px(xy_lid, station: int, w: int, h: int, dx_mm: float = 0.0):
    s = FOV_LONG_MM / w
    xy = np.atleast_2d(np.asarray(xy_lid, float))
    col = (xy[:, 1] - LID_W / 2) / s + w / 2
    row = (xy[:, 0] - (STATION_X[station] + dx_mm)) / s + h / 2
    return np.column_stack([col, row])


def _leaf_layout(look: PlantLook, scale_mm: float, rng):
    n = int(np.clip(4 + 2.2 * np.sqrt(look.area_cm2 / 10.0), 4, 28))
    leaves = []
    for i in range(n):
        age = 1.0 - i / n                                   # oldest first (largest, outermost)
        length = scale_mm * (0.35 + 0.65 * age) * (1 - 0.25 * look.compact)
        width = length * (0.62 + 0.2 * look.compact)
        ang = np.radians(i * 137.5 + rng.uniform(-8, 8))
        dist = length * (0.42 - 0.12 * look.compact)
        leaves.append((dist * np.cos(ang), dist * np.sin(ang), length / 2, width / 2, np.degrees(ang), age))
    return leaves


def _plant_mask(leaves, centre_px, s, shape):
    m = np.zeros(shape, np.uint8)
    for dx, dy, a, b, ang, _ in leaves:
        c = (int(round(centre_px[0] + dy / s)), int(round(centre_px[1] + dx / s)))
        cv2.ellipse(m, c, (max(int(round(a / s)), 1), max(int(round(b / s)), 1)), 90 - ang, 0, 360, 255, -1)
    return m


def render_station(looks: dict[int, PlantLook], station: int, width: int = 1014, height: int = 760, dx_mm: float = 0.0,
                   seed: int = 0, noise: float = 3.0, with_markers: bool = True):
    """Render one station image. Returns (bgr, truth) where truth = {position: {"mask", "area_cm2", "diameter_mm"}}.
    `dx_mm` shifts the camera along the gantry axis (positioning error or stereo offset)."""
    rng = np.random.default_rng(seed)
    s = FOV_LONG_MM / width
    img = np.full((height, width, 3), (225, 228, 230), np.uint8)             # white chamber floor beyond the lid
    # lid
    c0 = lid_to_px([(0, 0)], station, width, height, dx_mm)[0]
    c1 = lid_to_px([(LID_L, LID_W)], station, width, height, dx_mm)[0]
    cv2.rectangle(img, (int(c0[0]), int(c0[1])), (int(c1[0]), int(c1[1])), (28, 28, 28), -1)
    if with_markers:
        for mid in reg.LID_MARKERS:
            side_f = reg.MARKER_MM / s
            if side_f < 12:
                continue
            base = 200
            tile = cv2.aruco.generateImageMarker(reg.DICT, mid, base)
            quiet = cv2.copyMakeBorder(tile, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
            cx, cy = lid_to_px([reg.LID_MARKERS[mid]], station, width, height, dx_mm)[0]
            k = side_f / base                                    # exact sub-pixel scale and position
            M = np.array([[k, 0, cx - k * quiet.shape[1] / 2], [0, k, cy - k * quiet.shape[0] / 2]], np.float32)
            half = k * quiet.shape[0] / 2
            if cx - half < 1 or cy - half < 1 or cx + half > width - 2 or cy + half > height - 2:
                continue
            warped = cv2.warpAffine(quiet, M, (width, height), flags=cv2.INTER_AREA, borderValue=0)
            cover = cv2.warpAffine(np.full_like(quiet, 255), M, (width, height), flags=cv2.INTER_NEAREST, borderValue=0) > 0
            img[cover] = warped[cover][:, None]
    truth = {}
    visible = [p for p in looks if abs(PLANT_XY[p][0] - STATION_X[station]) < 250]
    # draw order: larger plants first so that smaller neighbours are not fully hidden
    for pos in sorted(visible, key=lambda p: -looks[p].area_cm2):
        look = looks[pos]
        prng = np.random.default_rng(look.seed * 7919 + pos)
        centre = lid_to_px([PLANT_XY[pos]], station, width, height, dx_mm)[0]
        cv2.circle(img, (int(centre[0]), int(centre[1])), int(30 / s), (18, 18, 18), -1)       # net pot
        if look.area_cm2 <= 0:
            truth[pos] = {"mask": np.zeros((height, width), np.uint8), "area_cm2": 0.0, "diameter_mm": 0.0}
            continue
        lo, hi = 2.0, 400.0
        for _ in range(18):                                   # bisection on leaf scale to hit the target area
            mid_ = 0.5 * (lo + hi)
            leaves = _leaf_layout(look, mid_, np.random.default_rng(look.seed * 7919 + pos))
            a = _plant_mask(leaves, centre, s, (height, width)).sum() / 255 * s * s / 100
            lo, hi = (mid_, hi) if a < look.area_cm2 else (lo, mid_)
        leaves = _leaf_layout(look, 0.5 * (lo + hi), np.random.default_rng(look.seed * 7919 + pos))
        full = np.zeros((height, width), np.uint8)
        for dx, dy, a, b, ang, age in leaves:
            c = (int(round(centre[0] + dy / s)), int(round(centre[1] + dx / s)))
            axes = (max(int(round(a / s)), 1), max(int(round(b / s)), 1))
            g = prng.normal(0, 6, 3)
            base = np.array([52, 150, 78], float) * (0.78 + 0.3 * (1 - age)) + g          # BGR, young leaves lighter
            yel = np.array([70, 205, 200], float)
            col = (1 - look.chlorosis * (0.4 + 0.6 * age)) * base + look.chlorosis * (0.4 + 0.6 * age) * yel
            cv2.ellipse(img, c, axes, 90 - ang, 0, 360, tuple(float(v) for v in np.clip(col, 0, 255)), -1)
            cv2.ellipse(img, c, axes, 90 - ang, 0, 360, tuple(float(v) for v in np.clip(col * 0.8, 0, 255)), 1)
            cv2.ellipse(full, c, axes, 90 - ang, 0, 360, 255, -1)
            if look.tipburn > 0 and age < 0.5 and prng.random() < look.tipburn:
                tip = (int(round(centre[0] + (dy + a * np.sin(np.radians(ang)) * 0.9) / s)), int(round(centre[1] + (dx + a * np.cos(np.radians(ang)) * 0.9) / s)))
                cv2.circle(img, tip, max(int(4 / s), 2), (40, 75, 110), -1)
                cv2.circle(full, tip, max(int(4 / s), 2), 255, -1)
        truth[pos] = {"mask": full}
    # resolve occlusion: later-drawn (smaller) plants are on top
    owner = np.zeros((height, width), np.int32)
    for pos in sorted(truth, key=lambda p: -looks[p].area_cm2):
        owner[truth[pos]["mask"] > 0] = pos
    for pos in truth:
        if "area_cm2" in truth[pos]:
            continue
        m = (owner == pos).astype(np.uint8) * 255
        truth[pos]["mask"] = m
        truth[pos]["area_cm2"] = float(m.sum() / 255 * s * s / 100)
        ys, xs = np.nonzero(m)
        if len(xs) > 2:
            hull = cv2.convexHull(np.column_stack([xs, ys]).astype(np.int32)).reshape(-1, 2).astype(float)
            truth[pos]["diameter_mm"] = float(np.max(np.linalg.norm(hull[:, None] - hull[None], axis=2)) * s)
        else:
            truth[pos]["diameter_mm"] = 0.0
        truth[pos]["truncated"] = bool(m[0].any() or m[-1].any() or m[:, 0].any() or m[:, -1].any())
    img = cv2.GaussianBlur(img, (3, 3), 0.7)
    if noise > 0:
        img = np.clip(img.astype(np.float32) + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    return img, truth
