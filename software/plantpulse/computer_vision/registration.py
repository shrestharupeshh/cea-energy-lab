"""Image-to-lid registration from ArUco fiducials on the tub lid.

Each lid carries DICT_4X4_50 markers at known lid coordinates (mm). Detecting them in every image
gives (a) the mm-per-pixel scale at the lid plane, (b) the homography from pixels to lid
coordinates, which removes residual gantry positioning error, and (c) a per-image health check.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
MARKER_MM = 20.0
# marker id -> lid coordinates (mm) of the marker centre. Two per station, on the front and back lid margins,
# midway between plant columns so that leaves cover them as late as possible.
LID_MARKERS = {0: (200.0, 12.0), 1: (200.0, 388.0), 2: (400.0, 12.0), 3: (400.0, 388.0),
               4: (12.0, 200.0), 5: (588.0, 200.0)}


@dataclass
class Registration:
    ok: bool
    mm_per_px: float
    H_px_to_lid: np.ndarray | None        # 3x3 homography, pixels -> lid mm
    n_markers: int
    reproj_rms_mm: float

    def to_lid(self, pts_px: np.ndarray) -> np.ndarray:
        p = cv2.perspectiveTransform(np.asarray(pts_px, np.float32).reshape(-1, 1, 2), self.H_px_to_lid)
        return p.reshape(-1, 2)

    def to_px(self, pts_lid: np.ndarray) -> np.ndarray:
        p = cv2.perspectiveTransform(np.asarray(pts_lid, np.float32).reshape(-1, 1, 2), np.linalg.inv(self.H_px_to_lid))
        return p.reshape(-1, 2)


def marker_corners_lid(mid: int) -> np.ndarray:
    """Lid coordinates of the marker corners in ArUco order (top-left, top-right, bottom-right, bottom-left).
    Mounting convention: the marker's own right-hand direction points along lid +y and its downward
    direction along lid +x. (The opposite assignment would be a mirror image, which cannot be detected.)"""
    cx, cy = LID_MARKERS[mid]
    h = MARKER_MM / 2
    return np.array([[cx - h, cy - h], [cx - h, cy + h], [cx + h, cy + h], [cx + h, cy - h]], np.float32)


def register(image_bgr: np.ndarray, nominal_mm_per_px: float | None = None, max_rms_mm: float = 2.0) -> Registration:
    """Detect lid fiducials and fit the pixel -> lid transform.

    Accepted only with at least two markers and a reprojection RMS below `max_rms_mm`; one marker
    alone (4 points a few pixels apart) gives an ill-conditioned transform. Scale is taken from the
    distances between marker centres, which is far less sensitive to corner localisation bias than
    the marker edge length."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    corners, ids, _ = cv2.aruco.ArucoDetector(DICT, params).detectMarkers(gray)
    fail = Registration(False, nominal_mm_per_px or np.nan, None, 0, np.nan)
    if ids is None:
        return fail
    px, lid = [], []
    for c, i in zip(corners, ids.ravel()):
        if int(i) in LID_MARKERS:
            px.append(c.reshape(4, 2))
            lid.append(marker_corners_lid(int(i)))
    if len(px) < 2:
        fail.n_markers = len(px)
        return fail
    cpx = np.array([q.mean(axis=0) for q in px])
    clid = np.array([q.mean(axis=0) for q in lid])
    ii, jj = np.triu_indices(len(px), 1)
    scale = float(np.sum(np.linalg.norm(clid[ii] - clid[jj], axis=1)) / np.sum(np.linalg.norm(cpx[ii] - cpx[jj], axis=1)))
    px_all, lid_all = np.concatenate(px), np.concatenate(lid)
    if len(px) >= 3:
        H, _ = cv2.findHomography(px_all, lid_all, 0)
    else:
        A, _ = cv2.estimateAffinePartial2D(px_all, lid_all)
        H = np.vstack([A, [0, 0, 1]])
    proj = cv2.perspectiveTransform(px_all.reshape(-1, 1, 2).astype(np.float32), H).reshape(-1, 2)
    rms = float(np.sqrt(np.mean(np.sum((proj - lid_all) ** 2, axis=1))))
    if not np.isfinite(rms) or rms > max_rms_mm:
        fail.n_markers = len(px)
        return fail
    return Registration(True, scale, H, len(px), rms)
