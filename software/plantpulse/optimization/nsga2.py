"""NSGA-II (Deb et al. 2002) with constrained domination, SBX crossover and polynomial mutation.
Self-contained (NumPy only) so that the optimisation layer has no heavy dependencies."""
from __future__ import annotations

import numpy as np

from .pareto import crowding_distance, fast_non_dominated_sort, non_dominated


def _sbx(p1, p2, lo, hi, rng, eta=15.0, pc=0.9):
    c1, c2 = p1.copy(), p2.copy()
    if rng.random() < pc:
        u = rng.random(len(p1))
        beta = np.where(u <= 0.5, (2 * u) ** (1 / (eta + 1)), (1 / (2 * (1 - u))) ** (1 / (eta + 1)))
        c1 = 0.5 * ((1 + beta) * p1 + (1 - beta) * p2)
        c2 = 0.5 * ((1 - beta) * p1 + (1 + beta) * p2)
    return np.clip(c1, lo, hi), np.clip(c2, lo, hi)


def _mutate(x, lo, hi, rng, eta=20.0, pm=None):
    pm = pm or 1.0 / len(x)
    y = x.copy()
    for i in range(len(x)):
        if rng.random() < pm:
            u = rng.random()
            delta = (2 * u) ** (1 / (eta + 1)) - 1 if u < 0.5 else 1 - (2 * (1 - u)) ** (1 / (eta + 1))
            y[i] = np.clip(x[i] + delta * (hi[i] - lo[i]), lo[i], hi[i])
    return y


def nsga2(evaluate, bounds: np.ndarray, pop_size: int = 40, generations: int = 30, seed: int = 0, x_init: np.ndarray | None = None, callback=None) -> dict:
    """evaluate(x) -> dict with 'f' (objective vector, minimised) and 'g' (total constraint violation, 0 = feasible).
    Returns the final population and its non-dominated feasible subset."""
    rng = np.random.default_rng(seed)
    lo, hi = bounds[:, 0], bounds[:, 1]
    X = lo + rng.random((pop_size, len(lo))) * (hi - lo)
    if x_init is not None:
        X[: len(np.atleast_2d(x_init))] = np.clip(np.atleast_2d(x_init), lo, hi)
    ev = [evaluate(x) for x in X]
    F, G = np.array([e["f"] for e in ev]), np.array([e["g"] for e in ev])
    n_eval = pop_size
    history = []
    for gen in range(generations):
        fronts = fast_non_dominated_sort(F, G)
        rank = np.empty(len(X), int)
        crowd = np.empty(len(X))
        for r, fr in enumerate(fronts):
            rank[fr] = r
            crowd[fr] = crowding_distance(F[fr])

        def pick():
            i, j = rng.integers(0, len(X), 2)
            return i if (rank[i], -crowd[i]) < (rank[j], -crowd[j]) else j

        children = []
        while len(children) < pop_size:
            c1, c2 = _sbx(X[pick()], X[pick()], lo, hi, rng)
            children += [_mutate(c1, lo, hi, rng), _mutate(c2, lo, hi, rng)]
        C = np.array(children[:pop_size])
        evc = [evaluate(x) for x in C]
        n_eval += pop_size
        X = np.vstack([X, C])
        F = np.vstack([F, [e["f"] for e in evc]])
        G = np.concatenate([G, [e["g"] for e in evc]])
        keep = []
        for fr in fast_non_dominated_sort(F, G):
            if len(keep) + len(fr) <= pop_size:
                keep += list(fr)
            else:
                cd = crowding_distance(F[fr])
                keep += list(fr[np.argsort(-cd)][: pop_size - len(keep)])
                break
        X, F, G = X[keep], F[keep], G[keep]
        history.append({"gen": gen, "n_feasible": int((G == 0).sum()), "best": F[G == 0].min(axis=0).tolist() if (G == 0).any() else None})
        if callback:
            callback(history[-1])
    feas = G == 0
    nd = np.zeros(len(X), bool)
    if feas.any():
        idx = np.where(feas)[0]
        nd[idx[non_dominated(F[idx])]] = True
    return {"X": X, "F": F, "G": G, "pareto": nd, "n_eval": n_eval, "history": history}
