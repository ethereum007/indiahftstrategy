from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PurgedSplit:
    fold: int
    train_index: np.ndarray
    test_index: np.ndarray
    test_start_ts: int
    test_end_ts: int
    purged_index: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    embargoed_index: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))


def purged_walk_forward_splits(
    labels: pd.DataFrame,
    *,
    time_col: str = "ts",
    label_end_col: str = "label_end_ts",
    n_splits: int = 3,
    embargo_ns: int = 0,
    test_size: int | None = None,
) -> list[PurgedSplit]:
    """Create expanding-window test folds without future training observations.

    Every training set contains only rows preceding its contiguous test fold.
    Training labels that reach the test boundary are purged. ``embargo_ns``
    adds a label-resolution gap immediately before that boundary.
    """

    if not isinstance(n_splits, (int, np.integer)) or n_splits <= 0:
        raise ValueError("n_splits must be positive")
    if not isinstance(embargo_ns, (int, np.integer)) or embargo_ns < 0:
        raise ValueError("embargo_ns must be a non-negative integer")
    if test_size is not None and (
        not isinstance(test_size, (int, np.integer)) or test_size <= 0
    ):
        raise ValueError("test_size must be a positive integer when provided")
    for col in (time_col, label_end_col):
        if col not in labels.columns:
            raise ValueError(f"labels missing required column {col}")
    frame = _validated_label_frame(labels, time_col=time_col, label_end_col=label_end_col)
    if frame.empty:
        return []
    if n_splits >= len(frame):
        raise ValueError("n_splits must leave at least one initial training row")
    resolved_test_size = int(test_size or (len(frame) // (n_splits + 1)))
    first_test_position = len(frame) - (n_splits * resolved_test_size)
    if resolved_test_size <= 0 or first_test_position <= 0:
        raise ValueError("test_size and n_splits must leave an initial training window")

    positions = np.arange(len(frame))
    starts = frame["_time"]
    ends = frame["_label_end"]
    splits: list[PurgedSplit] = []
    for fold_no in range(n_splits):
        test_position = first_test_position + (fold_no * resolved_test_size)
        test_pos = np.arange(test_position, test_position + resolved_test_size)
        test = frame.iloc[test_pos]
        test_start = int(test["_time"].min())
        test_end = int(test["_label_end"].max())
        is_past = positions < test_position
        overlaps_test = is_past & (ends.to_numpy() >= test_start)
        in_embargo = np.zeros(len(frame), dtype=bool)
        if embargo_ns:
            embargo_start = test_start - int(embargo_ns)
            in_embargo = (
                is_past
                & ~overlaps_test
                & (ends.to_numpy() > embargo_start)
            )
        train_mask = is_past & ~overlaps_test & ~in_embargo
        splits.append(
            PurgedSplit(
                fold=fold_no,
                train_index=frame.loc[train_mask, "_source_index"].to_numpy(),
                test_index=test["_source_index"].to_numpy(),
                test_start_ts=test_start,
                test_end_ts=test_end,
                purged_index=frame.loc[overlaps_test, "_source_index"].to_numpy(),
                embargoed_index=frame.loc[in_embargo, "_source_index"].to_numpy(),
            )
        )
    return splits


def _validated_label_frame(
    labels: pd.DataFrame,
    *,
    time_col: str,
    label_end_col: str,
) -> pd.DataFrame:
    starts = _integer_timestamps(labels[time_col], time_col)
    ends = _integer_timestamps(labels[label_end_col], label_end_col)
    if bool((ends < starts).any()):
        raise ValueError(f"{label_end_col} must be greater than or equal to {time_col}")
    frame = pd.DataFrame(
        {
            "_source_index": labels.index.to_numpy(copy=True),
            "_source_order": np.arange(len(labels)),
            "_time": starts.to_numpy(),
            "_label_end": ends.to_numpy(),
        }
    )
    return frame.sort_values(["_time", "_source_order"], kind="mergesort").reset_index(drop=True)


def _integer_timestamps(values: pd.Series, name: str) -> pd.Series:
    try:
        numeric = pd.to_numeric(values, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric integer timestamps") from exc
    if numeric.isna().any() or not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"{name} must contain finite integer timestamps")
    if bool((numeric % 1 != 0).any()):
        raise ValueError(f"{name} must contain integer timestamps")
    bounds = np.iinfo(np.int64)
    if bool(((numeric < bounds.min) | (numeric > bounds.max)).any()):
        raise ValueError(f"{name} must fit signed 64-bit integer timestamps")
    try:
        return numeric.astype("int64")
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must fit signed 64-bit integer timestamps") from exc
