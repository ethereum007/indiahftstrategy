from __future__ import annotations

import pandas as pd


def pnl_decomposition(
    fills: pd.DataFrame,
    *,
    strategy_order_ids: list[int] | None = None,
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(
            columns=[
                "source",
                "fills",
                "qty",
                "turnover",
                "gross_cash_flow",
                "costs",
                "net_cash_flow",
                "maker_share",
            ]
        )
    required = ["oid", "side", "qty", "price", "cost", "maker"]
    missing = [col for col in required if col not in fills.columns]
    if missing:
        raise ValueError(f"fills missing required columns: {missing}")
    frame = fills.copy()
    if strategy_order_ids is None:
        frame["source"] = "all"
    else:
        strategy_ids = set(strategy_order_ids)
        frame["source"] = frame["oid"].map(
            lambda oid: "strategy" if oid in strategy_ids else "terminal_flatten"
        )
    frame["turnover"] = frame["qty"] * frame["price"]
    frame["gross_cash_flow"] = -frame["side"] * frame["qty"] * frame["price"]
    groups = ["source"] + (group_cols or [])
    return (
        frame.groupby(groups, dropna=False)
        .agg(
            fills=("qty", "size"),
            qty=("qty", "sum"),
            turnover=("turnover", "sum"),
            gross_cash_flow=("gross_cash_flow", "sum"),
            costs=("cost", "sum"),
            maker_share=("maker", "mean"),
        )
        .assign(net_cash_flow=lambda x: x["gross_cash_flow"] - x["costs"])
        .reset_index()
    )


def pnl_totals(fills: pd.DataFrame, *, strategy_order_ids: list[int] | None = None) -> pd.DataFrame:
    return pnl_decomposition(fills, strategy_order_ids=strategy_order_ids, group_cols=None)
