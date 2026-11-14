"""Bayesian optimisation (Gaussian-process surrogate, expected improvement) for expensive
single-objective problems - e.g. tuning a recipe with the full closed-loop twin, or, later,
sequential physical experiments where each evaluation is one pod-run."""
from __future__ import annotations

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel


def expected_improvement(mu, sigma, best, xi=0.01):
    sigma = np.maximum(sigma, 1e-12)
    z = (best - mu - xi) / sigma
    return (best - mu - xi) * norm.cdf(z) + sigma * norm.pdf(z)


def bayes_opt(objective, bounds: np.ndarray, n_init: int = 8, n_iter: int = 25, seed: int = 0, n_candidates: int = 4000) -> dict:
    """Minimise objective(x) -> float (use a penalty for constraint violations).
    Returns best x, best value, and the full evaluation history (X, y)."""
    rng = np.random.default_rng(seed)
    lo, hi = bounds[:, 0], bounds[:, 1]
    d = len(lo)
    unit = lambda X: (X - lo) / (hi - lo)
    # Latin-hypercube-like initial design
    X = np.array([(rng.permutation(n_init) + rng.random(n_init)) / n_init for _ in range(d)]).T * (hi - lo) + lo
    y = np.array([objective(x) for x in X], float)
    kernel = (ConstantKernel(1.0, (1e-2, 1e2)) * Matern(length_scale=np.full(d, 0.3), length_scale_bounds=(0.03, 30.0), nu=2.5)
              + WhiteKernel(1e-4, (1e-8, 1e-1)))
    import warnings
    from sklearn.exceptions import ConvergenceWarning
    warnings.filterwarnings("ignore", category=ConvergenceWarning)   # flat directions hit kernel bounds; harmless here
    for _ in range(n_iter):
        gp = GaussianProcessRegressor(kernel, normalize_y=True, n_restarts_optimizer=2, random_state=int(rng.integers(1 << 30)))
        gp.fit(unit(X), y)
        cand = lo + rng.random((n_candidates, d)) * (hi - lo)
        best_x = X[np.argmin(y)]
        local = np.clip(best_x + rng.normal(0, 0.05, (n_candidates // 4, d)) * (hi - lo), lo, hi)   # exploit near the incumbent
        cand = np.vstack([cand, local])
        mu, sd = gp.predict(unit(cand), return_std=True)
        x_next = cand[np.argmax(expected_improvement(mu, sd, y.min()))]
        X = np.vstack([X, x_next])
        y = np.append(y, objective(x_next))
    i = int(np.argmin(y))
    return {"x": X[i], "y": float(y[i]), "X": X, "Y": y}
