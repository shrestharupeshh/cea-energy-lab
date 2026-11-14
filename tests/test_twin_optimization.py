import numpy as np
import pandas as pd
import pytest

from plantpulse.digital_twin import calibration as cal
from plantpulse.digital_twin import crop
from plantpulse.digital_twin import environment as envm
from plantpulse.digital_twin.twin import PodTwin, Recipe, fast_predict
from plantpulse.optimization import pareto
from plantpulse.optimization.mpc import LightingMPC, MPCConfig
from plantpulse.optimization.nsga2 import nsga2
from plantpulse.optimization.problem import LightingProblem


def test_scalar_and_numpy_derivatives_agree():
    p = crop.CropParams()
    f, tr = crop._scalar_step_fns(p)
    for args in [(2.0, 9.0, 54.0, 410.0, 24.0, 1.0), (0.3, 1.2, 0.0, 420.0, 20.0, None), (5.0, 60.0, 65.0, 380.0, 31.0, 0.4)]:
        assert np.allclose(f(*args), crop.derivatives(*args[:5], p, args[5]), rtol=1e-10)
    assert np.isclose(tr(11.0, 54.0, 24.0, 65.0), float(crop.transpiration(11.0, 54.0, 24.0, 65.0, p)))


def test_crop_responses_have_expected_signs():
    base = crop.simulate_schedule(28, 250, 16)["shoot_dw_g"][-1]
    assert 4 < base < 14, "28-day dry mass per plant should be in a plausible range for lettuce"
    assert crop.simulate_schedule(28, 125, 16)["shoot_dw_g"][-1] < 0.8 * base
    assert crop.simulate_schedule(28, 250, 16, t_day=32, t_night=28)["shoot_dw_g"][-1] < base
    assert crop.simulate_schedule(28, 250, 16, ec=0.4)["shoot_dw_g"][-1] < base
    assert crop.simulate_schedule(28, 250, 16, co2=800)["shoot_dw_g"][-1] > base
    r = crop.simulate_schedule(10, 0.0, 16)
    assert r["shoot_dw_g"][-1] < 0.06, "no light: dry mass must not increase"
    assert np.all(np.diff(r["transp_g_plant_cum"]) >= 0)


def test_equal_dli_longer_photoperiod_is_more_efficient_in_model():
    a = fast_predict(Recipe(days=28, ppfd=250, photoperiod_h=16))
    b = fast_predict(Recipe(days=28, ppfd=200, photoperiod_h=20))
    assert np.isclose(a["dli_max"], b["dli_max"]) and b["shoot_dw_g_plant"] > a["shoot_dw_g_plant"]


def test_environment_relaxes_to_room_and_heats_with_load():
    p = envm.EnvParams.from_design()
    s = envm.EnvState(air_t=28.0, w=float(envm.abs_hum(28.0, 60.0)))
    for _ in range(600):
        s = envm.step(s, envm.Actuators(fan=1.0), p, 60.0)
    assert abs(s.air_t - 20.0) < 0.3
    for _ in range(600):
        s = envm.step(s, envm.Actuators(led=1.0, fan=0.15), p, 60.0)
    assert 21.0 < s.air_t < 30.0 and 0 <= s.rh <= 100
    pw = envm.power_w(envm.Actuators(led=1.0, heater=1.0, fan=1.0, mix=1.0, humidifier=True), p)
    assert pw["wall_w"] > pw["dc_w"] > 180


def test_twin_holds_setpoints_and_accounts_energy():
    tw = PodTwin()
    df = tw.run(Recipe(days=3), dt_s=60.0, log_every_s=600.0)
    lit = df[df.ppfd > 200]
    assert abs(lit.air_t.mean() - 23.0) < 0.5 and (df.provenance == "predicted").all()
    s = tw.summary(df)
    expected_led = 3 * 16 * (250 / tw.env.ppfd_full) * tw.env.led_w_full / 1000
    assert abs(s["kwh_led"] - expected_led) / expected_led < 0.03
    assert s["kwh_wall"] > s["kwh_led"]


def test_calibration_recovers_known_parameters():
    truth = crop.CropParams(c_eps=14.5e-6, c_gr_max=6.0e-6, sla_obs=0.030)
    rng = np.random.default_rng(0)
    data = []
    for i, (ppfd, pp) in enumerate([(250, 16), (150, 16), (200, 20), (300, 14)]):
        r = crop.simulate_schedule(28, ppfd, pp, p=truth)
        days = np.array([7, 14, 21, 28])
        obs = pd.DataFrame({"day": days, "shoot_dw_g": r["shoot_dw_g"][r["day_end_index"][days - 1]] * np.exp(rng.normal(0, 0.03, 4)),
                            "leaf_area_cm2": r["leaf_area_cm2"][r["day_end_index"][days - 1]] * np.exp(rng.normal(0, 0.03, 4))})
        data.append(cal.Series(f"u{i}", np.full(28, ppfd), np.full(28, pp), np.full(28, 23.0), np.full(28, 20.0), obs))
    fit = cal.fit(data)
    assert fit["success"] and fit["rmse_log"] < 0.06
    assert abs(fit["estimates"]["sla_obs"] / 0.030 - 1) < 0.05
    pred = crop.simulate_schedule(28, 250, 16, p=fit["params"])["shoot_dw_g"][-1]
    assert abs(pred / crop.simulate_schedule(28, 250, 16, p=truth)["shoot_dw_g"][-1] - 1) < 0.05


def test_pareto_utilities():
    F = np.array([[1, 5], [2, 3], [3, 4], [4, 1], [5, 5.0]])
    assert pareto.non_dominated(F).tolist() == [True, True, False, True, False]
    assert pareto.non_dominated(F, np.array([0, 1, 0, 0, 0])).tolist() == [True, False, True, True, False]
    assert np.isclose(pareto.hypervolume_2d(F, (6, 6)), 5 * 1 + 4 * 2 + 2 * 2)
    assert pareto.knee_point(F[[0, 1, 3]]) == 1


def test_nsga2_respects_constraints_and_finds_tradeoff():
    prob = LightingProblem(objectives=("neg_fw", "kwh_led"))
    res = nsga2(prob.evaluate, prob.bounds, pop_size=16, generations=6, seed=0, x_init=prob.baseline())
    P = res["X"][res["pareto"]]
    assert len(P) >= 3
    for x in P:
        e = prob.evaluate(x)
        assert e["g"] == 0 and e["recipe"].dli().max() <= 17.0 + 1e-9 and -e["f"][0] >= prob.cons.min_fw_g
    F = res["F"][res["pareto"]]
    assert np.corrcoef(-F[:, 0], F[:, 1])[0, 1] > 0.8, "more biomass should cost more light energy along the front"


def test_infeasible_recipe_is_penalised():
    prob = LightingProblem()
    x = prob.baseline().copy()
    x[:3], x[3:6] = 300.0, 20.0                       # DLI 21.6
    assert prob.evaluate(x)["violations"]["dli_max"] > 0


@pytest.mark.slow
def test_mpc_plan_respects_hard_limits():
    mpc = LightingMPC(MPCConfig(target_dw_g=7.5, blocks=2))
    p = mpc.plan(0, 0.06, last_ppfd=200.0)
    dli = p["ppfd"] * p["photoperiod_h"] * 3600 / 1e6
    assert dli.max() <= 17.0 + 1e-6 and p["ppfd"].min() >= 100 and p["ppfd"].max() <= 300
    assert abs(p["ppfd"][0] - 200.0) <= 50.0 + 1e-9 and p["provenance"] == "predicted"
