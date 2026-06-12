from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument


CHAIN_REQUIRED = [
    "ts",
    "expiry",
    "strike",
    "call_bid",
    "call_ask",
    "call_bid_qty",
    "call_ask_qty",
    "put_bid",
    "put_ask",
    "put_bid_qty",
    "put_ask_qty",
]

FUTURES_REQUIRED = ["ts", "bid", "ask", "bid_qty", "ask_qty"]


@dataclass(frozen=True)
class ScannerCosts:
    option: IndianCostModel
    future: IndianCostModel


@dataclass(frozen=True)
class ScannerInstruments:
    option: Instrument
    future: Instrument


def scan_parity(
    chain: pd.DataFrame,
    futures: pd.DataFrame,
    *,
    instruments: ScannerInstruments,
    costs: ScannerCosts,
    asof_latency_ns: int,
    tolerance_ns: Optional[int] = None,
    depth_fraction: float = 0.25,
    carry_adjustment: float = 0.0,
) -> pd.DataFrame:
    _validate(chain, CHAIN_REQUIRED, "chain")
    _validate(futures, FUTURES_REQUIRED, "futures")
    if asof_latency_ns < 0:
        raise ValueError("asof_latency_ns must be non-negative")
    if not 0 < depth_fraction <= 1:
        raise ValueError("depth_fraction must be in (0, 1]")

    quotes = _join_futures(
        chain,
        futures,
        asof_latency_ns=asof_latency_ns,
        tolerance_ns=tolerance_ns,
    )
    rows: list[dict] = []
    for row in quotes.itertuples(index=False):
        strike = float(row.strike)
        fair_strike = strike + carry_adjustment

        buy_synth = row.call_ask - row.put_bid + fair_strike
        sell_future = row.future_bid
        qty = _executable_qty(
            [row.call_ask_qty, row.put_bid_qty, row.future_bid_qty],
            instruments.option.lot_size,
            depth_fraction,
        )
        if qty > 0:
            raw_edge = sell_future - buy_synth
            total_cost = (
                costs.option.cost(+1, row.call_ask, qty, instruments.option)
                + costs.option.cost(-1, row.put_bid, qty, instruments.option)
                + costs.future.cost(-1, row.future_bid, qty, instruments.future)
            )
            rows.append(
                _opportunity_row(
                    row,
                    "buy_synthetic_sell_future",
                    qty,
                    raw_edge,
                    total_cost,
                    instruments.option,
                )
            )

        sell_synth = row.call_bid - row.put_ask + fair_strike
        buy_future = row.future_ask
        qty = _executable_qty(
            [row.call_bid_qty, row.put_ask_qty, row.future_ask_qty],
            instruments.option.lot_size,
            depth_fraction,
        )
        if qty > 0:
            raw_edge = sell_synth - buy_future
            total_cost = (
                costs.option.cost(-1, row.call_bid, qty, instruments.option)
                + costs.option.cost(+1, row.put_ask, qty, instruments.option)
                + costs.future.cost(+1, row.future_ask, qty, instruments.future)
            )
            rows.append(
                _opportunity_row(
                    row,
                    "sell_synthetic_buy_future",
                    qty,
                    raw_edge,
                    total_cost,
                    instruments.option,
                )
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return _empty_opportunities()
    out = _add_persistence(out, ["expiry", "strike", "direction"])
    out = out.loc[out["net_edge"] > 0].sort_values(["ts", "strike", "direction"])
    if out.empty:
        return _empty_opportunities()
    return out.reset_index(drop=True)


def scan_boxes(
    chain: pd.DataFrame,
    *,
    option_instrument: Instrument,
    option_costs: IndianCostModel,
    depth_fraction: float = 0.25,
    fair_value_adjustment: float = 0.0,
) -> pd.DataFrame:
    _validate(chain, CHAIN_REQUIRED, "chain")
    if not 0 < depth_fraction <= 1:
        raise ValueError("depth_fraction must be in (0, 1]")

    rows: list[dict] = []
    for (ts, expiry), group in chain.sort_values(["ts", "strike"]).groupby(["ts", "expiry"]):
        by_strike = {float(row.strike): row for row in group.itertuples(index=False)}
        for low, high in combinations(sorted(by_strike), 2):
            low_row = by_strike[low]
            high_row = by_strike[high]
            fair_box = (high - low) + fair_value_adjustment

            debit = low_row.call_ask - low_row.put_bid - high_row.call_bid + high_row.put_ask
            qty = _executable_qty(
                [
                    low_row.call_ask_qty,
                    low_row.put_bid_qty,
                    high_row.call_bid_qty,
                    high_row.put_ask_qty,
                ],
                option_instrument.lot_size,
                depth_fraction,
            )
            if qty > 0:
                raw_edge = fair_box - debit
                total_cost = (
                    option_costs.cost(+1, low_row.call_ask, qty, option_instrument)
                    + option_costs.cost(-1, low_row.put_bid, qty, option_instrument)
                    + option_costs.cost(-1, high_row.call_bid, qty, option_instrument)
                    + option_costs.cost(+1, high_row.put_ask, qty, option_instrument)
                )
                rows.append(
                    _box_row(
                        ts,
                        expiry,
                        low,
                        high,
                        getattr(low_row, "regime", "unknown"),
                        "buy_box",
                        qty,
                        raw_edge,
                        total_cost,
                        option_instrument,
                    )
                )

            credit = low_row.call_bid - low_row.put_ask - high_row.call_ask + high_row.put_bid
            qty = _executable_qty(
                [
                    low_row.call_bid_qty,
                    low_row.put_ask_qty,
                    high_row.call_ask_qty,
                    high_row.put_bid_qty,
                ],
                option_instrument.lot_size,
                depth_fraction,
            )
            if qty > 0:
                raw_edge = credit - fair_box
                total_cost = (
                    option_costs.cost(-1, low_row.call_bid, qty, option_instrument)
                    + option_costs.cost(+1, low_row.put_ask, qty, option_instrument)
                    + option_costs.cost(+1, high_row.call_ask, qty, option_instrument)
                    + option_costs.cost(-1, high_row.put_bid, qty, option_instrument)
                )
                rows.append(
                    _box_row(
                        ts,
                        expiry,
                        low,
                        high,
                        getattr(low_row, "regime", "unknown"),
                        "sell_box",
                        qty,
                        raw_edge,
                        total_cost,
                        option_instrument,
                    )
                )

    out = pd.DataFrame(rows)
    if out.empty:
        return _empty_box_opportunities()
    out = _add_persistence(out, ["expiry", "low_strike", "high_strike", "direction"])
    out = out.loc[out["net_edge"] > 0].sort_values(["ts", "low_strike", "high_strike", "direction"])
    if out.empty:
        return _empty_box_opportunities()
    return out.reset_index(drop=True)


def opportunity_report(opportunities: pd.DataFrame) -> pd.DataFrame:
    if opportunities.empty:
        return pd.DataFrame(
            columns=[
                "regime",
                "direction",
                "count",
                "net_edge_sum",
                "net_edge_median",
                "persistence_ticks_median",
            ]
        )
    frame = opportunities.copy()
    if "regime" not in frame.columns:
        frame["regime"] = "unknown"
    return (
        frame.groupby(["regime", "direction"], dropna=False)
        .agg(
            count=("net_edge", "size"),
            net_edge_sum=("net_edge", "sum"),
            net_edge_median=("net_edge", "median"),
            persistence_ticks_median=("persistence_ticks", "median"),
        )
        .reset_index()
    )


def _join_futures(
    chain: pd.DataFrame,
    futures: pd.DataFrame,
    *,
    asof_latency_ns: int,
    tolerance_ns: Optional[int],
) -> pd.DataFrame:
    left = chain.sort_values("ts").copy()
    left["futures_lookup_ts"] = left["ts"] - asof_latency_ns
    right = futures.sort_values("ts").copy()
    joined = pd.merge_asof(
        left,
        right,
        left_on="futures_lookup_ts",
        right_on="ts",
        direction="backward",
        tolerance=tolerance_ns,
        suffixes=("", "_future"),
    )
    joined = joined.dropna(subset=["bid", "ask", "bid_qty", "ask_qty"]).copy()
    return joined.rename(
        columns={
            "bid": "future_bid",
            "ask": "future_ask",
            "bid_qty": "future_bid_qty",
            "ask_qty": "future_ask_qty",
            "ts_future": "future_ts",
        }
    )


def _executable_qty(depths: list[float], lot_size: int, depth_fraction: float) -> int:
    displayed = int(np.floor(min(depths) * depth_fraction))
    lots = displayed // lot_size
    return lots * lot_size


def _opportunity_row(row, direction, qty, raw_edge, total_cost, instrument):
    gross_edge = raw_edge * qty * instrument.multiplier
    return {
        "ts": int(row.ts),
        "expiry": row.expiry,
        "strike": float(row.strike),
        "direction": direction,
        "qty": int(qty),
        "edge_per_unit": float(raw_edge),
        "gross_edge": float(gross_edge),
        "total_cost": float(total_cost),
        "net_edge": float(gross_edge - total_cost),
        "displayed_depth": int(qty),
        "future_ts": int(row.future_ts),
        "regime": getattr(row, "regime", "unknown"),
    }


def _box_row(ts, expiry, low, high, regime, direction, qty, raw_edge, total_cost, instrument):
    gross_edge = raw_edge * qty * instrument.multiplier
    return {
        "ts": int(ts),
        "expiry": expiry,
        "low_strike": float(low),
        "high_strike": float(high),
        "direction": direction,
        "qty": int(qty),
        "edge_per_unit": float(raw_edge),
        "gross_edge": float(gross_edge),
        "total_cost": float(total_cost),
        "net_edge": float(gross_edge - total_cost),
        "displayed_depth": int(qty),
        "regime": regime,
    }


def _add_persistence(opportunities: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    sort_cols = [col for col in group_cols if col in opportunities.columns]
    if "ts" in opportunities.columns:
        sort_cols.append("ts")
    out = opportunities.sort_values(sort_cols).copy()
    out["persistence_ticks"] = 0
    for _, idx in out.groupby(group_cols, dropna=False).groups.items():
        ordered = list(idx)
        nets = out.loc[ordered, "net_edge"].to_numpy()
        persistence = []
        for i in range(len(nets)):
            ticks = 0
            for j in range(i + 1, len(nets)):
                if nets[j] <= 0:
                    break
                ticks += 1
            persistence.append(ticks)
        out.loc[ordered, "persistence_ticks"] = persistence
    return out.reset_index(drop=True)


def _validate(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _empty_opportunities() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ts",
            "expiry",
            "strike",
            "direction",
            "qty",
            "edge_per_unit",
            "gross_edge",
            "total_cost",
            "net_edge",
            "displayed_depth",
            "future_ts",
            "regime",
            "persistence_ticks",
        ]
    )


def _empty_box_opportunities() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ts",
            "expiry",
            "low_strike",
            "high_strike",
            "direction",
            "qty",
            "edge_per_unit",
            "gross_edge",
            "total_cost",
            "net_edge",
            "displayed_depth",
            "regime",
            "persistence_ticks",
        ]
    )
