from __future__ import annotations

import pandas as pd


SIM_REQUIRED = ["client_order_id", "instrument_id", "ts_sent_ns", "side", "qty", "price"]
LIVE_REQUIRED = ["client_order_id", "instrument_id", "ts_fill_ns", "side", "qty", "price"]


def compare_simulated_to_live(
    simulated_orders: pd.DataFrame,
    live_fills: pd.DataFrame,
) -> pd.DataFrame:
    """Compare shadow/simulated orders against broker or exchange fills."""

    _require(simulated_orders, SIM_REQUIRED, "simulated_orders")
    _require(live_fills, LIVE_REQUIRED, "live_fills")
    sim = simulated_orders.copy()
    live = (
        live_fills.sort_values("ts_fill_ns")
        .groupby("client_order_id", as_index=False)
        .agg(
            live_instrument_id=("instrument_id", "first"),
            live_side=("side", "first"),
            live_qty=("qty", "sum"),
            live_avg_price=("price", "mean"),
            first_fill_ts_ns=("ts_fill_ns", "first"),
            last_fill_ts_ns=("ts_fill_ns", "last"),
        )
    )
    joined = sim.merge(live, on="client_order_id", how="left")
    joined["filled_live"] = joined["live_qty"].notna()
    joined["live_qty"] = joined["live_qty"].fillna(0).astype(int)
    joined["fill_qty_diff"] = joined["live_qty"] - joined["qty"]
    joined["latency_error_ns"] = joined["first_fill_ts_ns"] - joined["ts_sent_ns"]
    joined["price_slippage"] = joined["side"] * (joined["live_avg_price"] - joined["price"])
    return joined


def calibration_summary(comparison: pd.DataFrame) -> pd.DataFrame:
    if comparison.empty:
        return pd.DataFrame(
            columns=[
                "instrument_id",
                "orders",
                "live_fill_rate",
                "avg_live_qty",
                "avg_qty_diff",
                "avg_latency_error_ns",
                "avg_price_slippage",
            ]
        )
    required = [
        "instrument_id",
        "filled_live",
        "live_qty",
        "fill_qty_diff",
        "latency_error_ns",
        "price_slippage",
    ]
    _require(comparison, required, "comparison")
    return (
        comparison.groupby("instrument_id", dropna=False)
        .agg(
            orders=("client_order_id", "size"),
            live_fill_rate=("filled_live", "mean"),
            avg_live_qty=("live_qty", "mean"),
            avg_qty_diff=("fill_qty_diff", "mean"),
            avg_latency_error_ns=("latency_error_ns", "mean"),
            avg_price_slippage=("price_slippage", "mean"),
        )
        .reset_index()
    )


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
