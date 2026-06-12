from __future__ import annotations

from typing import Iterable

import pandas as pd


FILL_REQUIRED = ["ts_ns", "instrument_id", "side", "qty", "price"]
SURFACE_REQUIRED = ["ts", "instrument_id", "theo"]


def compute_surface_markouts(
    fills: pd.DataFrame,
    surface_values: pd.DataFrame,
    *,
    horizons_ns: Iterable[int],
) -> pd.DataFrame:
    """Compute signed fill markouts versus future theoretical values."""

    _require(fills, FILL_REQUIRED, "fills")
    _require(surface_values, SURFACE_REQUIRED, "surface_values")
    if fills.empty:
        return pd.DataFrame()
    rows = []
    fills_base = fills.copy().reset_index(drop=True)
    fills_base["fill_id"] = fills_base.index
    surface = surface_values.sort_values(["instrument_id", "ts"]).copy()
    for horizon_ns in horizons_ns:
        target = fills_base.copy()
        target["target_ts"] = target["ts_ns"] + int(horizon_ns)
        joined_parts = []
        for instrument_id, group in target.groupby("instrument_id", sort=False):
            surface_group = surface.loc[surface["instrument_id"] == instrument_id]
            joined = pd.merge_asof(
                group.sort_values("target_ts"),
                surface_group[["ts", "theo"]].sort_values("ts"),
                left_on="target_ts",
                right_on="ts",
                direction="forward",
            )
            joined_parts.append(joined)
        joined = pd.concat(joined_parts, ignore_index=True, sort=False)
        joined["horizon_ns"] = int(horizon_ns)
        joined["surface_markout_per_unit"] = joined["side"] * (joined["theo"] - joined["price"])
        joined["surface_markout"] = joined["surface_markout_per_unit"] * joined["qty"]
        rows.append(joined)
    out = pd.concat(rows, ignore_index=True, sort=False)
    return out.sort_values(["fill_id", "horizon_ns"]).reset_index(drop=True)


def surface_markout_summary(
    markouts: pd.DataFrame,
    *,
    bucket_cols: list[str] | None = None,
) -> pd.DataFrame:
    if markouts.empty:
        return pd.DataFrame(
            columns=[
                "horizon_ns",
                "count",
                "surface_markout_mean",
                "surface_markout_median",
                "win_rate",
            ]
        )
    groups = ["horizon_ns"] + (bucket_cols or [])
    return (
        markouts.groupby(groups, dropna=False)
        .agg(
            count=("surface_markout", "size"),
            surface_markout_mean=("surface_markout", "mean"),
            surface_markout_median=("surface_markout", "median"),
            win_rate=("surface_markout", lambda s: float((s > 0).mean())),
        )
        .reset_index()
    )


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
