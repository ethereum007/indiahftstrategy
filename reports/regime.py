from __future__ import annotations

import pandas as pd

from data.loaders import tag_regime


def attach_regime(df: pd.DataFrame, *, ts_col: str) -> pd.DataFrame:
    if ts_col not in df.columns:
        raise ValueError(f"df missing timestamp column {ts_col}")
    out = df.copy()
    out["regime"] = tag_regime(out[ts_col])
    return out


def fill_summary_by_regime(
    fills: pd.DataFrame,
    *,
    ts_col: str = "ts_ns",
) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(
            columns=[
                "regime",
                "fills",
                "qty",
                "turnover",
                "costs",
                "maker_share",
            ]
        )
    required = [ts_col, "qty", "price", "cost", "maker"]
    missing = [col for col in required if col not in fills.columns]
    if missing:
        raise ValueError(f"fills missing required columns: {missing}")
    frame = attach_regime(fills, ts_col=ts_col)
    frame["turnover"] = frame["qty"] * frame["price"]
    return (
        frame.groupby("regime", dropna=False)
        .agg(
            fills=("qty", "size"),
            qty=("qty", "sum"),
            turnover=("turnover", "sum"),
            costs=("cost", "sum"),
            maker_share=("maker", "mean"),
        )
        .reset_index()
    )


def equity_change_by_regime(
    equity: pd.DataFrame,
    *,
    ts_col: str = "ts",
    equity_col: str = "equity",
) -> pd.DataFrame:
    if equity.empty:
        return pd.DataFrame(columns=["regime", "start_equity", "end_equity", "equity_change"])
    for col in (ts_col, equity_col):
        if col not in equity.columns:
            raise ValueError(f"equity missing required column {col}")
    frame = attach_regime(equity.sort_values(ts_col), ts_col=ts_col)
    return (
        frame.groupby("regime", dropna=False)
        .agg(start_equity=(equity_col, "first"), end_equity=(equity_col, "last"))
        .assign(equity_change=lambda x: x["end_equity"] - x["start_equity"])
        .reset_index()
    )
