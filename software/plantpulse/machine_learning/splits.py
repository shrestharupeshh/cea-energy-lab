"""Leakage-safe data splitting.

Rows from the same plant, the same pod-run (experimental unit) or - for transfer claims - the same
run must never straddle train and test. Random row-level splits are not offered at all.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut

LEVELS = ("plant_id", "unit_id", "experiment_id")


def grouped_splits(df: pd.DataFrame, level: str = "experiment_id", n_splits: int | None = None):
    """Yield (train_idx, test_idx) positional index arrays. Default: leave-one-run-out."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    groups = df[level].to_numpy()
    n_groups = len(np.unique(groups))
    if n_groups < 2:
        raise ValueError(f"need at least 2 distinct {level} groups, got {n_groups}")
    splitter = LeaveOneGroupOut() if n_splits is None or n_splits >= n_groups else GroupKFold(n_splits)
    for tr, te in splitter.split(df, groups=groups):
        assert_no_leakage(df.iloc[tr], df.iloc[te], level)
        yield tr, te


def assert_no_leakage(train: pd.DataFrame, test: pd.DataFrame, level: str = "unit_id"):
    """Raise if any group at `level` (or any finer level nested in it) appears on both sides."""
    idx = LEVELS.index(level)
    for lv in LEVELS[: idx + 1]:
        if lv in train and lv in test:
            common = set(train[lv]) & set(test[lv])
            if common:
                raise AssertionError(f"data leakage: {len(common)} {lv} value(s) in both train and test, e.g. {sorted(common)[:3]}")


def leave_one_treatment_out(df: pd.DataFrame, treatment_col: str = "treatment", control: str = "C"):
    """Out-of-distribution splits: train on runs' data excluding one stress treatment entirely, test on
    that treatment in a held-out run (both the run and the condition are unseen)."""
    for trt in sorted(set(df[treatment_col]) - {control}):
        for run in sorted(df["experiment_id"].unique()):
            tr = np.where((df[treatment_col] != trt) & (df["experiment_id"] != run))[0]
            te = np.where((df[treatment_col] == trt) & (df["experiment_id"] == run))[0]
            if len(tr) and len(te):
                yield trt, run, tr, te
