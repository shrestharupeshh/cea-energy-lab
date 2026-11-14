import numpy as np
import pandas as pd
import pytest

from plantpulse.stats import agreement, design, inference, power


def test_latin_square_is_latin_and_reproducible():
    a = design.latin_square(list("CLHN"), seed=7)
    assert design.is_latin(a) and a.equals(design.latin_square(list("CLHN"), seed=7))
    assert not a.equals(design.latin_square(list("CLHN"), seed=8))


def test_balanced_crossover():
    d = design.balanced_crossover(("F", "A"), 4, 4, seed=1)
    assert all((d.iloc[i] == "A").sum() == 2 for i in range(4))
    assert all((d.iloc[:, j] == "A").sum() == 2 for j in range(4))


def test_allocate_seedlings_balances_size():
    rng = np.random.default_rng(0)
    sizes = pd.Series(rng.lognormal(0, 0.3, 48), index=[f"s{i}" for i in range(48)])
    a = design.allocate_seedlings(sizes, 4, 6, seed=3)
    assert len(a) == 24 and a.groupby("pod").size().eq(6).all() and a["seedling_id"].is_unique
    means = a.groupby("pod")["size"].mean()
    assert means.max() / means.min() < 1.15


def test_agreement_separates_bias_from_correlation():
    x = np.linspace(10, 100, 50)
    a = agreement.agreement(x, 1.2 * x)              # perfectly correlated, 20 % proportional bias
    assert a["pearson_r"] > 0.999 and a["bias_pct"] > 15 and a["ccc"] < 0.99 and a["prop_bias_p"] < 0.01
    b = agreement.agreement(x, x + np.random.default_rng(0).normal(0, 1, 50))
    assert abs(b["bias"]) < 0.5 and b["loa_low"] < 0 < b["loa_high"]


def test_gauge_rr_recovers_repeatability():
    rng = np.random.default_rng(1)
    parts = rng.normal(100, 20, 12)[:, None, None]
    v = parts + rng.normal(0, 2.0, (12, 2, 3))
    g = agreement.gauge_rr(v)
    assert 1.5 < g["repeatability_sd"] < 2.6 and g["part_sd"] > 10


def test_latin_square_anova_recovers_planted_effect():
    rng = np.random.default_rng(5)
    sq = design.latin_square(list("CLHN"), seed=2)
    rows = []
    for i, run in enumerate(sq.index):
        for j, pod in enumerate(sq.columns):
            eff = {"C": 1.0, "L": 0.6, "H": 0.95, "N": 0.8}[sq.iat[i, j]]
            rows.append({"run": run, "pod": pod, "treatment": sq.iat[i, j], "y": 8 * eff * np.exp(rng.normal(0, 0.04)) * (1 + 0.1 * i)})
    r = inference.latin_square_anova(pd.DataFrame(rows), "y", "C")
    c = r["contrasts"].set_index("treatment")
    assert r["df_resid"] == 6 and c.loc["L", "significant"] and 0.5 < c.loc["L", "ratio"] < 0.7
    assert c.loc["L", "ratio_ci"][0] < 0.6 < c.loc["L", "ratio_ci"][1]


def test_dunnett_critical_exceeds_t():
    from scipy import stats
    assert inference.dunnett_critical(3, 6, n_sim=50_000) > stats.t.ppf(0.975, 6)


def test_variance_components():
    rng = np.random.default_rng(0)
    rows = []
    for r in range(4):
        for p in range(4):
            u = rng.normal(0, 0.5)
            rows += [{"run": r, "pod": p, "y": 10 + u + rng.normal(0, 1.5)} for _ in range(6)]
    v = inference.variance_components(pd.DataFrame(rows), "y")
    assert 1.0 < v["var_plant"] < 3.5 and v["icc_pod"] < 0.5


def test_cluster_bootstrap_and_noninferiority():
    rng = np.random.default_rng(0)
    cl = pd.Series(np.repeat(np.arange(12), 6))
    r = inference.cluster_bootstrap_diff(pd.Series(rng.normal(0, 1, 72)), pd.Series(rng.normal(0, 3, 72)), cl, n_boot=2000)
    assert r["ci_high"] < 0 and r["n_clusters"] == 12
    assert inference.noninferiority_ratio(np.log(0.98), 0.02, 6)["non_inferior"]
    assert not inference.noninferiority_ratio(np.log(0.92), 0.05, 6)["non_inferior"]


@pytest.mark.slow
def test_power_increases_with_effect():
    lo = power.latin_square_power(0.9, n_sim=150, seed=1)
    hi = power.latin_square_power(0.5, n_sim=150, seed=1)
    assert hi > 0.9 > lo
