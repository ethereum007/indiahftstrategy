from __future__ import annotations

import math
from typing import Any, Mapping


def microprice_features(
    tick: Mapping[str, Any],
    tick_size: float,
) -> dict[str, float] | None:
    if not math.isfinite(float(tick_size)) or tick_size <= 0:
        raise ValueError("tick_size must be positive and finite")
    bid = float(tick["bid"])
    ask = float(tick["ask"])
    bid_qty = float(tick["bid_qty"])
    ask_qty = float(tick["ask_qty"])
    if not all(math.isfinite(value) for value in (bid, ask, bid_qty, ask_qty)):
        return None
    if bid <= 0 or ask <= 0 or ask < bid or bid_qty <= 0 or ask_qty <= 0:
        return None
    depth = bid_qty + ask_qty
    mid = 0.5 * (bid + ask)
    microprice = (ask * bid_qty + bid * ask_qty) / depth
    return {
        "spread_ticks": (ask - bid) / tick_size,
        "imbalance": (bid_qty - ask_qty) / depth,
        "microprice": microprice,
        "microprice_edge_ticks": (microprice - mid) / tick_size,
    }


def microprice_entry_side(
    features: Mapping[str, float],
    *,
    entry_imbalance: float,
    min_microprice_edge_ticks: float,
) -> int:
    imbalance = float(features["imbalance"])
    edge_ticks = float(features["microprice_edge_ticks"])
    if (
        imbalance >= entry_imbalance
        and edge_ticks >= min_microprice_edge_ticks
    ):
        return 1
    if (
        imbalance <= -entry_imbalance
        and edge_ticks <= -min_microprice_edge_ticks
    ):
        return -1
    return 0


def microprice_exit_action(
    features: Mapping[str, float],
    *,
    position_lots: int,
    entry_ts_ns: int | None,
    now_ns: int,
    hold_ns: int,
    exit_imbalance: float,
) -> str:
    if position_lots == 0:
        return ""
    hold_expired = (
        entry_ts_ns is not None and now_ns - entry_ts_ns >= hold_ns
    )
    imbalance = float(features["imbalance"])
    signal_decayed = (
        (position_lots > 0 and imbalance <= exit_imbalance)
        or (position_lots < 0 and imbalance >= -exit_imbalance)
    )
    if hold_expired:
        return "exit_hold"
    if signal_decayed:
        return "exit_decay"
    return ""
