from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PurgedSplit:
    fold: int
    train_index: np.ndarray
    test_index: np.ndarray
    test_start_ts: int
    test_end_ts: int


def purged_walk_forward_splits(
    labels: pd.DataFrame,
    *,
    time_col: str = "ts",
    label_end_col: str = "label_end_ts",
    n_splits: int = 3,
    embargo_ns: int = 0,
) -> list[PurgedSplit]:
    """Create contiguous test folds with purged overlapping training labels.

    A train row is removed when its label interval overlaps the test interval,
    or when its timestamp falls inside the post-test embargo window.
    """

    if n_splits <= 0:
        raise ValueError("n_splits must be positive")
    for col in (time_col, label_end_col):
        if col not in labels.columns:
            raise ValueError(f"labels missing required column {col}")
    frame = labels.sort_values(time_col).reset_index()
    if frame.empty:
        return []
    folds = np.array_split(np.arange(len(frame)), n_splits)
    splits: list[PurgedSplit] = []
    for fold_no, test_pos in enumerate(folds):
        if len(test_pos) == 0:
            continue
        test = frame.iloc[test_pos]
        test_start = int(test[time_col].min())
        test_end = int(test[label_end_col].max())
        starts = frame[time_col]
        ends = frame[label_end_col]
        is_test = frame.index.isin(test_pos)
        overlaps_test = (starts <= test_end) & (ends >= test_start)
        in_embargo = (starts > test_end) & (starts <= test_end + embargo_ns)
        train = frame.loc[~is_test & ~overlaps_test & ~in_embargo]
        splits.append(
            PurgedSplit(
                fold=fold_no,
                train_index=train["index"].to_numpy(),
                test_index=test["index"].to_numpy(),
                test_start_ts=test_start,
                test_end_ts=test_end,
            )
        )
    return splits
