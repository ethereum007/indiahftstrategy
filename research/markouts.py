from __future__ import annotations

from typing import Iterable

import pandas as pd


FILL_REQUIRED = ["ts_ns", "side", "qty", "price"]
BOOK_REQUIRED = ["ts", "bid", "ask"]


def compute_markouts(
    fills: pd.DataFrame,
    book: pd.DataFrame,
    *,
    horizons_ns: Iterable[int],
    timestamp_col: str = "ts_ns",
) -> pd.DataFrame:
    _require(fills, [timestamp_col, "side", "qty", "price"], "fills")
    _require(book, BOOK_REQUIRED, "book")
    if fills.empty:
        return pd.DataFrame()

    fills_base = fills.copy().reset_index(drop=True)
    fills_base["fill_id"] = fills_base.index
    book_mid = book.sort_values("ts").copy()
    book_mid["mid"] = 0.5 * (book_mid["bid"] + book_mid["ask"])
    rows = []
    for horizon_ns in horizons_ns:
        target = fills_base.copy()
        target["target_ts"] = target[timestamp_col] + int(horizon_ns)
        joined = pd.merge_asof(
            target.sort_values("target_ts"),
            book_mid[["ts", "mid"]].sort_values("ts"),
            left_on="target_ts",
            right_on="ts",
            direction="forward",
        )
        joined["horizon_ns"] = int(horizon_ns)
        joined["markout_per_unit"] = joined["side"] * (joined["mid"] - joined["price"])
        joined["markout"] = joined["markout_per_unit"] * joined["qty"]
        rows.append(joined)
    out = pd.concat(rows, ignore_index=True, sort=False)
    return out.sort_values(["fill_id", "horizon_ns"]).reset_index(drop=True)


def markout_summary(
    markouts: pd.DataFrame,
    *,
    bucket_cols: list[str] | None = None,
) -> pd.DataFrame:
    if markouts.empty:
        return pd.DataFrame(
            columns=["horizon_ns", "count", "markout_mean", "markout_median", "win_rate"]
        )
    groups = ["horizon_ns"] + (bucket_cols or [])
    return (
        markouts.groupby(groups, dropna=False)
        .agg(
            count=("markout", "size"),
            markout_mean=("markout", "mean"),
            markout_median=("markout", "median"),
            win_rate=("markout", lambda s: float((s > 0).mean())),
        )
        .reset_index()
    )


def add_pickoff_flag(
    fills: pd.DataFrame,
    leader_events: pd.DataFrame,
    *,
    window_ns: int,
    fill_ts_col: str = "ts_ns",
    leader_ts_col: str = "ts",
) -> pd.DataFrame:
    _require(fills, [fill_ts_col], "fills")
    _require(leader_events, [leader_ts_col], "leader_events")
    out = fills.copy().reset_index(drop=False).rename(columns={"index": "_original_index"})
    leaders = leader_events[[leader_ts_col]].sort_values(leader_ts_col)
    joined = pd.merge_asof(
        out.sort_values(fill_ts_col),
        leaders,
        left_on=fill_ts_col,
        right_on=leader_ts_col,
        direction="backward",
        tolerance=window_ns,
    )
    flagged = joined[["_original_index", leader_ts_col]].copy()
    flagged["pickoff"] = flagged[leader_ts_col].notna()
    return (
        out.merge(flagged[["_original_index", "pickoff"]], on="_original_index", how="left")
        .sort_values("_original_index")
        .drop(columns=["_original_index"])
        .reset_index(drop=True)
    )


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
