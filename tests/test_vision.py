import cv2
import numpy as np
import pytest

from plantpulse.computer_vision import color, height, registration, segmentation, traits
from plantpulse.computer_vision.evaluation import compare, scanner_area
from plantpulse.computer_vision.growth import relative_growth_rate
from plantpulse.computer_vision.pipeline import QC_BLUR, QC_NO_FIDUCIAL, QC_TOUCHING, QC_TRUNCATED, process_image
from plantpulse.simulation.synth_images import PlantLook, render_station

W, H = 760, 570
S = 524.0 / W


def test_registration_recovers_scale_and_gantry_offset():
    looks = {p: PlantLook(40.0, seed=p) for p in range(1, 7)}
    for dx in (0.0, 1.5, -2.0):
        img, _ = render_station(looks, 2, W, H, dx_mm=dx, seed=1)
        r = registration.register(img, S)
        assert r.ok and r.n_markers == 4 and abs(r.mm_per_px / S - 1) < 0.005 and r.reproj_rms_mm < 1.0
        centre_lid = r.to_lid([[W / 2, H / 2]])[0]
        assert abs(centre_lid[0] - (300.0 + dx)) < 0.6, "image centre must map to the true gantry position"
        assert abs(centre_lid[1] - 200.0) < 0.6


def test_registration_refuses_images_without_markers():
    img, _ = render_station({p: PlantLook(40.0) for p in range(1, 7)}, 2, W, H, with_markers=False)
    assert not registration.register(img, S).ok
    rec = process_image(img, 2, S)
    assert all(r["qc"] & QC_NO_FIDUCIAL for r in rec)


def test_segmentation_and_traits_on_known_shapes():
    img = np.full((400, 400, 3), 28, np.uint8)
    cv2.circle(img, (200, 200), 80, (52, 150, 78), -1)
    mask = segmentation.segment(img)
    truth = np.zeros((400, 400), np.uint8)
    cv2.circle(truth, (200, 200), 80, 255, -1)
    assert segmentation.iou(mask, truth) > 0.97
    m = traits.morphology(truth, 0.5)
    assert abs(m["projected_area_cm2"] - np.pi * 40**2 / 100) / (np.pi * 16) < 0.01
    assert abs(m["diameter_max_mm"] - 80) < 1.5 and m["solidity"] > 0.98 and m["compactness"] > 0.85 and not m["touches_border"]
    assert traits.morphology(np.zeros((10, 10), np.uint8), 1.0)["projected_area_cm2"] == 0.0


def test_background_is_not_segmented():
    img = np.full((300, 300, 3), (225, 228, 230), np.uint8)       # white floor
    img[100:200] = 28                                              # black lid
    assert segmentation.segment(img).sum() == 0


def test_split_assigns_components_to_known_positions():
    mask = np.zeros((300, 600), np.uint8)
    cv2.circle(mask, (150, 150), 60, 255, -1)
    cv2.circle(mask, (450, 150), 60, 255, -1)
    lab = segmentation.split_plants(mask, np.array([[150, 150], [450, 150]]), 1.0)
    assert set(np.unique(lab)) == {0, 1, 2} and (lab[150, 150], lab[150, 450]) == (1, 2)
    cv2.rectangle(mask, (150, 140), (450, 160), 255, -1)          # bridge: canopies touch
    lab = segmentation.split_plants(mask, np.array([[150, 150], [450, 150]]), 1.0)
    assert lab[150, 290] == 1 and lab[150, 310] == 2, "touching canopies are cut at the midline"
    assert abs((lab == 1).sum() - (lab == 2).sum()) < 50


def test_pipeline_accuracy_on_isolated_synthetic_plants():
    err = []
    for area in (8, 40, 110):
        looks = {p: PlantLook(area * (0.85 + 0.05 * p), seed=p) for p in range(1, 7)}
        for st in (1, 2, 3):
            img, truth = render_station(looks, st, W, H, dx_mm=0.5, seed=st)
            for r in process_image(img, st, S):
                assert not r["qc"] & (QC_TOUCHING | QC_TRUNCATED | QC_BLUR)
                err.append(r["projected_area_cm2"] / truth[r["position"]]["area_cm2"] - 1)
                assert abs(r["diameter_max_mm"] - truth[r["position"]]["diameter_mm"]) < 4.0
    assert np.abs(err).max() < 0.08 and abs(np.mean(err)) < 0.04


def test_touching_and_blur_are_flagged():
    looks = {p: PlantLook(330.0, seed=p) for p in range(1, 7)}
    img, _ = render_station(looks, 2, W, H, seed=3)
    assert all(r["qc"] & QC_TOUCHING for r in process_image(img, 2, S))
    blurred = cv2.GaussianBlur(img, (0, 0), 9)
    assert any(r["qc"] & QC_BLUR for r in process_image(blurred, 2, S, blur_threshold=15.0))


def test_colour_traits_detect_chlorosis_and_ccm():
    looks = lambda c: {p: PlantLook(60.0, chlorosis=c, seed=p) for p in range(1, 7)}
    healthy = process_image(render_station(looks(0.0), 2, W, H, seed=1)[0], 2, S)
    yellow = process_image(render_station(looks(0.7), 2, W, H, seed=1)[0], 2, S)
    assert yellow[0]["yellow_frac"] > healthy[0]["yellow_frac"] + 0.2 and yellow[0]["a_mean"] > healthy[0]["a_mean"]
    ref = color.REFERENCE_PATCHES_RGB
    distorted = np.clip(ref * np.array([0.8, 1.0, 1.15]) + 6, 0, 255)
    ccm = color.fit_ccm(distorted, ref)
    patch = distorted[7].astype(np.uint8)[None, None, ::-1]
    assert np.abs(color.apply_ccm(patch, ccm)[0, 0, ::-1].astype(float) - ref[7]).max() < 3


def test_stereo_geometry():
    f_px, base = 6.0 / 0.00155, 60.0
    d = f_px * base / np.array([300.0, 400.0, 500.0])
    assert np.allclose(height.depth_from_disparity(d, f_px, base), [300, 400, 500])
    assert np.isclose(height.perspective_area_factor(100.0, 500.0), 0.64)
    disp = np.full((50, 50), f_px * base / 380.0, np.float32)
    h = height.canopy_height(disp, np.ones((50, 50), np.uint8), f_px, base, 500.0)
    assert abs(h["height_mean_mm"] - 120.0) < 0.5


def test_leaf_count_flags_low_confidence_for_closed_heads():
    disc = np.zeros((300, 300), np.uint8)
    cv2.circle(disc, (150, 150), 120, 255, -1)
    assert not traits.leaf_count_estimate(disc, 1.0)["leaf_count_confident"]


def test_rgr_and_agreement_helpers():
    t = np.arange(10.0)
    assert np.allclose(relative_growth_rate(t, 5 * np.exp(0.2 * t))[1:-1], 0.2, atol=1e-6)
    import pandas as pd
    df = pd.DataFrame({"manual": np.linspace(10, 200, 30)})
    df["auto"] = df.manual * 1.1
    out = compare(df, {"manual": "auto"})
    assert out.bias_pct[0] > 8 and out.pearson_r[0] > 0.999, "high correlation must not hide a 10 % bias"


def test_scanner_area_with_reference_card():
    img = np.full((1400, 2300, 3), 250, np.uint8)
    px_cm = 300 / 2.54
    side = int(round(10 * px_cm))
    img[50:50 + side, 50:50 + side] = (140, 40, 20)                       # blue 100 cm2 card (BGR)
    cv2.circle(img, (1800, 600), int(round(3 * px_cm)), (60, 150, 70), -1)   # green leaf, r = 3 cm
    r = scanner_area(img, 300.0)
    assert abs(r["leaf_area_cm2"] - np.pi * 9) < 0.6 and abs(r["scale_check_ratio"] - 1) < 0.01
