import math

import numpy as np

from plantpulse.config import load_design
from plantpulse.engineering import electrical, hydraulics, imaging, lighting, report, structural, thermal


def test_beam_formulas():
    d, m = structural.simply_supported_udl(1.0, 1000.0, 70000.0, 1e4)
    assert math.isclose(d, 5 * 1e12 / (384 * 70000 * 1e4)) and math.isclose(m, 125000.0)
    d, _ = structural.cantilever_point(10.0, 100.0, 70000.0, 1000.0)
    assert math.isclose(d, 10 * 1e6 / (3 * 70000 * 1000))


def test_structure_meets_limits():
    r = structural.analyse(load_design())
    assert 25 < r.water_volume_l < 30
    assert r.cross_member_span_ratio > 250 and r.cross_member_sf_yield > 3 and r.column_sf > 10 and r.joint_sf > 3
    assert r.arm_tip_deflection_mm < 0.1


def test_friction_factor_regimes():
    assert math.isclose(hydraulics.friction_factor(1000), 0.064)
    assert 0.02 < hydraulics.friction_factor(1e4) < 0.04


def test_pump_operating_point_exceeds_requirement():
    d = load_design()
    r = hydraulics.analyse(d, 28.0)
    assert r.operating_flow_lpm > r.required_flow_lpm
    assert abs(hydraulics.pump_head(r.operating_flow_lpm, d["hydraulics"]) - hydraulics.system_head(r.operating_flow_lpm, d["hydraulics"])) < 1e-6


def test_lighting_reaches_nominal_ppfd_with_uniformity():
    r = lighting.analyse(load_design())
    assert r.duty_for_nominal < 0.9, "LED array must reach the control PPFD with dimming headroom"
    assert r.min_over_mean_plants >= 0.8
    assert 2.0 < r.efficacy_umol_j < 3.2
    assert math.isclose(lighting.dli(250, 16), 14.4)


def test_ppfd_field_conserves_flux_roughly():
    d = load_design()
    xs, ys, e = lighting.ppfd_field(d, grid=10)
    flux_on_floor = e.sum() * 0.01 * 0.01
    r = lighting.analyse(d)
    emitted_into_chamber = r.ppf_total_umol_s * d["pod"]["window_par_transmittance"]
    assert 0.5 * emitted_into_chamber < flux_on_floor < emitted_into_chamber


def test_thermal_balances():
    assert math.isclose(thermal.p_sat(20.0), 2337, rel_tol=0.01)
    assert math.isclose(thermal.vpd_kpa(23.0, 70.0), 0.84, abs_tol=0.03)
    d = load_design()
    lt = lighting.analyse(d)
    r = thermal.analyse(d, lt.electrical_w_full, lt.ppf_total_umol_s * 0.92)
    assert 0 < r.exhaust_flow_m3h < d["air"]["fan_free_flow_m3h"]
    assert r.dt_lights_on_full_vent_k < 3.0, "requirement ENV-02: room + 3 K"
    assert r.heater_margin > 1.0 and r.min_vent_for_co2_m3h < r.exhaust_flow_m3h


def test_imaging_requirements():
    r = imaging.analyse(load_design())
    assert r.gsd_lid_mm_px <= 0.2 and r.position_sigma_mm <= 0.5
    assert r.dof_near_mm < 300 and r.dof_far_mm > 500
    assert r.fov_long_mm > 500


def test_electrical_budget_within_supplies():
    d = load_design()
    lt = lighting.analyse(d)
    r = electrical.analyse(d, lt.electrical_w_full, lt.electrical_w_nominal)
    assert r.psu24_load_frac < 0.9 and r.psu48_load_frac < 0.8 and r.mains_current_a < 12
    assert math.isclose(electrical.voltage_drop(5.0, 3.0, 16), 2 * 5 * 1.72e-8 * 3 / 1.31e-6)


def test_report_generation(tmp_path):
    p = report.write_report(tmp_path)
    text = p.read_text()
    assert "design calculation" in text and (tmp_path / "ppfd_map_simulated.png").exists()
