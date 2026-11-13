"""Randomisation utilities. Every function takes an explicit seed that is stored with the experiment."""
from __future__ import annotations

import numpy as np
import pandas as pd


def latin_square(treatments: list[str], seed: int) -> pd.DataFrame:
    """Randomised Latin square: rows = runs, columns = pods. Standard square with rows, columns
    and treatment labels permuted."""
    rng = np.random.default_rng(seed)
    n = len(treatments)
    base = (np.arange(n)[:, None] + np.arange(n)[None, :]) % n
    base = base[rng.permutation(n)][:, rng.permutation(n)]
    labels = np.array(treatments)[rng.permutation(n)]
    return pd.DataFrame(labels[base], index=[f"run{i + 1}" for i in range(n)], columns=[f"pod{j + 1}" for j in range(n)])


def is_latin(df: pd.DataFrame) -> bool:
    n = len(df)
    return all(df.iloc[i].nunique() == n for i in range(n)) and all(df.iloc[:, j].nunique() == n for j in range(n))


def balanced_crossover(treatments: tuple[str, str], n_pods: int, n_runs: int, seed: int) -> pd.DataFrame:
    """Two-treatment design: each run has n_pods/2 pods per treatment and each pod receives each
    treatment equally often (n_runs must be even)."""
    if n_pods % 2 or n_runs % 2:
        raise ValueError("n_pods and n_runs must be even")
    rng = np.random.default_rng(seed)
    a, b = treatments
    first = np.array([a] * (n_pods // 2) + [b] * (n_pods // 2))
    rows = []
    for _ in range(n_runs // 2):
        p = rng.permutation(first)
        rows += [p, np.where(p == a, b, a)]
    order = rng.permutation(n_runs)
    arr = np.array(rows)[order]
    return pd.DataFrame(arr, index=[f"run{i + 1}" for i in range(n_runs)], columns=[f"pod{j + 1}" for j in range(n_pods)])


def allocate_seedlings(sizes: pd.Series, n_pods: int, per_pod: int, seed: int, trim: float = 0.15) -> pd.DataFrame:
    """Stratified allocation: trim extremes, rank by size, form strata of n_pods seedlings and deal
    one per pod at random; positions randomised within pod."""
    rng = np.random.default_rng(seed)
    need = n_pods * per_pod
    s = sizes.sort_values()
    k = int(len(s) * trim)
    s = s.iloc[k: len(s) - k] if len(s) - 2 * k >= need else s
    mid = (len(s) - need) // 2
    s = s.iloc[mid: mid + need]
    rows = []
    positions = {p: list(rng.permutation(per_pod) + 1) for p in range(1, n_pods + 1)}
    for stratum in range(per_pod):
        ids = s.index[stratum * n_pods:(stratum + 1) * n_pods]
        for pod, sid in zip(rng.permutation(n_pods) + 1, ids):
            rows.append({"seedling_id": sid, "size": s[sid], "pod": int(pod), "position": int(positions[int(pod)].pop())})
    return pd.DataFrame(rows).sort_values(["pod", "position"]).reset_index(drop=True)


def measurement_order(n_pods: int, per_pod: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for pod in rng.permutation(n_pods) + 1:
        for pos in rng.permutation(per_pod) + 1:
            rows.append({"pod": int(pod), "position": int(pos)})
    return pd.DataFrame(rows)
