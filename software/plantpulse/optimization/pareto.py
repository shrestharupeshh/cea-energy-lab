"""Pareto utilities (all objectives minimised)."""
from __future__ import annotations

import numpy as np


def dominates(a, b) -> bool:
    return bool(np.all(a <= b) and np.any(a < b))


def non_dominated(F: np.ndarray, G: np.ndarray | None = None) -> np.ndarray:
    """Boolean mask of the non-dominated set under constrained domination (feasible beats infeasible;
    among infeasible, smaller violation wins)."""
    F = np.asarray(F, float)
    n = len(F)
    G = np.zeros(n) if G is None else np.asarray(G, float)
    mask = np.ones(n, bool)
    for i in range(n):
        for j in range(n):
            if i == j or not mask[i]:
                continue
            if (G[j] == 0 and G[i] > 0) or (G[i] > 0 and G[j] > 0 and G[j] < G[i]) or (G[i] == 0 and G[j] == 0 and dominates(F[j], F[i])):
                mask[i] = False
                break
    return mask


def fast_non_dominated_sort(F: np.ndarray, G: np.ndarray) -> list[np.ndarray]:
    n = len(F)
    remaining = np.arange(n)
    fronts = []
    while len(remaining):
        m = non_dominated(F[remaining], G[remaining])
        fronts.append(remaining[m])
        remaining = remaining[~m]
    return fronts


def crowding_distance(F: np.ndarray) -> np.ndarray:
    n, m = F.shape
    d = np.zeros(n)
    if n <= 2:
        return np.full(n, np.inf)
    for k in range(m):
        order = np.argsort(F[:, k])
        span = F[order[-1], k] - F[order[0], k]
        d[order[0]] = d[order[-1]] = np.inf
        if span > 0:
            d[order[1:-1]] += (F[order[2:], k] - F[order[:-2], k]) / span
    return d


def hypervolume_2d(F: np.ndarray, ref) -> float:
    """Hypervolume of a 2-objective front relative to a reference point (larger = better)."""
    P = F[non_dominated(F)]
    P = P[np.argsort(P[:, 0])]
    hv, prev = 0.0, ref[1]
    for f0, f1 in P:
        if f0 < ref[0] and f1 < prev:
            hv += (ref[0] - f0) * (prev - f1)
            prev = f1
    return float(hv)


def knee_point(F: np.ndarray) -> int:
    """Index of the point farthest from the line joining the extremes of a normalised 2-D front."""
    Fn = (F - F.min(0)) / np.maximum(F.max(0) - F.min(0), 1e-12)
    a, b = Fn[np.argmin(Fn[:, 0])], Fn[np.argmin(Fn[:, 1])]
    ab = b - a
    d = np.abs(ab[0] * (Fn[:, 1] - a[1]) - ab[1] * (Fn[:, 0] - a[0])) / (np.linalg.norm(ab) + 1e-12)
    return int(np.argmax(d))
