from __future__ import annotations

from collections import deque

import pandas as pd


FILL_REQUIRED = ["ts_ns", "instrument_id", "side", "qty", "price", "cost"]


def pair_round_trips(fills: pd.DataFrame) -> pd.DataFrame:
    """FIFO-pair opposite-side fills per instrument into round-trip lots."""

    if fills.empty:
        return _empty_pairs()
    _require(fills, FILL_REQUIRED, "fills")
    rows = []
    inventory: dict[str, deque[dict]] = {}
    for fill in fills.sort_values("ts_ns").itertuples(index=False):
        inst = str(fill.instrument_id)
        queue = inventory.setdefault(inst, deque())
        remaining = int(fill.qty)
        while remaining > 0 and queue and queue[0]["side"] != fill.side:
            opener = queue[0]
            matched_qty = min(remaining, opener["remaining_qty"])
            open_cost = opener["cost_per_unit"] * matched_qty
            close_cost = float(fill.cost) * matched_qty / int(fill.qty)
            if opener["side"] > 0:
                buy_price, sell_price = opener["price"], float(fill.price)
                open_ts, close_ts = opener["ts_ns"], int(fill.ts_ns)
            else:
                buy_price, sell_price = float(fill.price), opener["price"]
                open_ts, close_ts = opener["ts_ns"], int(fill.ts_ns)
            gross_spread = (sell_price - buy_price) * matched_qty
            rows.append(
                {
                    "instrument_id": inst,
                    "open_ts_ns": int(open_ts),
                    "close_ts_ns": int(close_ts),
                    "open_side": int(opener["side"]),
                    "qty": int(matched_qty),
                    "buy_price": float(buy_price),
                    "sell_price": float(sell_price),
                    "gross_spread": float(gross_spread),
                    "costs": float(open_cost + close_cost),
                    "net_spread": float(gross_spread - open_cost - close_cost),
                    "holding_ns": int(close_ts - open_ts),
                }
            )
            remaining -= matched_qty
            opener["remaining_qty"] -= matched_qty
            if opener["remaining_qty"] == 0:
                queue.popleft()
        if remaining > 0:
            queue.append(
                {
                    "ts_ns": int(fill.ts_ns),
                    "side": int(fill.side),
                    "remaining_qty": int(remaining),
                    "price": float(fill.price),
                    "cost_per_unit": float(fill.cost) / int(fill.qty),
                }
            )
    if not rows:
        return _empty_pairs()
    return pd.DataFrame(rows)


def spread_capture_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    if pairs.empty:
        return pd.DataFrame(
            columns=[
                "instrument_id",
                "round_trips",
                "qty",
                "gross_spread",
                "costs",
                "net_spread",
                "avg_holding_ns",
            ]
        )
    required = ["instrument_id", "qty", "gross_spread", "costs", "net_spread", "holding_ns"]
    _require(pairs, required, "pairs")
    return (
        pairs.groupby("instrument_id", dropna=False)
        .agg(
            round_trips=("qty", "size"),
            qty=("qty", "sum"),
            gross_spread=("gross_spread", "sum"),
            costs=("costs", "sum"),
            net_spread=("net_spread", "sum"),
            avg_holding_ns=("holding_ns", "mean"),
        )
        .reset_index()
    )


def residual_inventory(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(columns=["instrument_id", "position", "avg_price"])
    _require(fills, FILL_REQUIRED, "fills")
    rows = []
    for inst, group in fills.sort_values("ts_ns").groupby("instrument_id"):
        signed_qty = group["side"] * group["qty"]
        position = int(signed_qty.sum())
        if position == 0:
            avg_price = 0.0
        else:
            same_side = group.loc[group["side"] == (1 if position > 0 else -1)]
            avg_price = float((same_side["qty"] * same_side["price"]).sum() / same_side["qty"].sum())
        rows.append({"instrument_id": inst, "position": position, "avg_price": avg_price})
    return pd.DataFrame(rows)


def _empty_pairs() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "instrument_id",
            "open_ts_ns",
            "close_ts_ns",
            "open_side",
            "qty",
            "buy_price",
            "sell_price",
            "gross_spread",
            "costs",
            "net_spread",
            "holding_ns",
        ]
    )


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
