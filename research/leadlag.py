from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument


BOOK_REQUIRED = ["ts", "bid", "ask", "bid_qty", "ask_qty"]
MEASUREMENT_RUN_TYPE = "leadlag_measurement"
MEASUREMENT_REQUIRED_ARTIFACTS = (
    "cross_correlation.csv",
    "lag_profile.csv",
    "latency_curve.csv",
    "leadlag_measure_summary.csv",
    "leadlag_measure_config.json",
    "leadlag_measure_runbook.md",
)
LATENCY_CURVE_COLUMNS = (
    "latency_ns",
    "events",
    "fills",
    "fill_rate",
    "profitable_fills",
    "win_rate",
    "gross_pnl",
    "round_trip_cost",
    "net_pnl",
    "avg_edge",
    "avg_gross_edge",
    "avg_round_trip_cost",
    "avg_net_edge",
    "cost_drag_ratio",
    "entry_turnover",
    "net_edge_bps",
)


@dataclass(frozen=True)
class LeadLagSummary:
    cross_correlation: pd.DataFrame
    lag_profile: pd.DataFrame
    latency_curve: pd.DataFrame


def summarize_pair(
    leader: pd.DataFrame,
    laggard: pd.DataFrame,
    *,
    leader_tick_size: float,
    laggard_tick_size: float,
    laggard_instrument: Instrument,
    laggard_costs: IndianCostModel,
    delta: float,
    innovation_ticks: float,
    lags_ns: Iterable[int],
    latency_sweep_ns: Iterable[int],
    max_lag_ns: int,
    depth_fraction: float = 0.25,
    correlation_tolerance_ns: int | None = None,
) -> LeadLagSummary:
    return LeadLagSummary(
        cross_correlation=cross_correlation(
            leader,
            laggard,
            lags_ns=lags_ns,
            tolerance_ns=correlation_tolerance_ns,
        ),
        lag_profile=event_lag_profile(
            leader,
            laggard,
            leader_tick_size=leader_tick_size,
            innovation_ticks=innovation_ticks,
            max_lag_ns=max_lag_ns,
        ),
        latency_curve=latency_viability_curve(
            leader,
            laggard,
            leader_tick_size=leader_tick_size,
            laggard_tick_size=laggard_tick_size,
            instrument=laggard_instrument,
            costs=laggard_costs,
            delta=delta,
            innovation_ticks=innovation_ticks,
            latency_sweep_ns=latency_sweep_ns,
            depth_fraction=depth_fraction,
        ),
    )


def cross_correlation(
    leader: pd.DataFrame,
    laggard: pd.DataFrame,
    *,
    lags_ns: Iterable[int],
    tolerance_ns: int | None = None,
) -> pd.DataFrame:
    leader_state = _returns_frame(leader, "leader_ret")
    laggard_state = _returns_frame(laggard, "laggard_ret")
    rows = []
    for lag_ns in lags_ns:
        left = leader_state.copy()
        left["lookup_ts"] = left["ts"] + int(lag_ns)
        joined = pd.merge_asof(
            left.sort_values("lookup_ts"),
            laggard_state.sort_values("ts"),
            left_on="lookup_ts",
            right_on="ts",
            direction="nearest",
            tolerance=tolerance_ns,
            suffixes=("_leader", "_laggard"),
        ).dropna(subset=["laggard_ret"])
        if len(joined) < 2:
            corr = np.nan
            samples = len(joined)
        else:
            corr = float(joined["leader_ret"].corr(joined["laggard_ret"]))
            samples = len(joined)
        rows.append({"lag_ns": int(lag_ns), "correlation": corr, "samples": samples})
    return pd.DataFrame(rows)


def event_lag_profile(
    leader: pd.DataFrame,
    laggard: pd.DataFrame,
    *,
    leader_tick_size: float,
    innovation_ticks: float,
    max_lag_ns: int,
) -> pd.DataFrame:
    events = _events_with_laggard_state(leader, laggard, leader_tick_size, innovation_ticks)
    laggard_mid = _mid_frame(laggard)
    rows = []
    for event in events.itertuples(index=False):
        after = laggard_mid.loc[
            (laggard_mid["ts"] > event.ts)
            & (laggard_mid["ts"] <= event.ts + max_lag_ns)
        ]
        update = after.loc[after["mid"] != event.laggard_mid_at_event]
        if update.empty:
            rows.append(
                {
                    "event_ts": int(event.ts),
                    "leader_move": float(event.leader_move),
                    "time_to_update_ns": np.nan,
                    "updated_within_window": False,
                }
            )
        else:
            first = update.iloc[0]
            rows.append(
                {
                    "event_ts": int(event.ts),
                    "leader_move": float(event.leader_move),
                    "time_to_update_ns": int(first["ts"] - event.ts),
                    "updated_within_window": True,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(
            columns=[
                "event_ts",
                "leader_move",
                "time_to_update_ns",
                "updated_within_window",
                "cdf",
            ]
        )
    valid = out["time_to_update_ns"].dropna().sort_values()
    cdf = {value: (i + 1) / len(valid) for i, value in enumerate(valid)}
    out["cdf"] = out["time_to_update_ns"].map(cdf)
    return out


def latency_viability_curve(
    leader: pd.DataFrame,
    laggard: pd.DataFrame,
    *,
    leader_tick_size: float,
    laggard_tick_size: float,
    instrument: Instrument,
    costs: IndianCostModel,
    delta: float,
    innovation_ticks: float,
    latency_sweep_ns: Iterable[int],
    depth_fraction: float = 0.25,
) -> pd.DataFrame:
    if not 0 < depth_fraction <= 1:
        raise ValueError("depth_fraction must be in (0, 1]")
    events = _events_with_laggard_state(leader, laggard, leader_tick_size, innovation_ticks)
    if events.empty:
        return pd.DataFrame(columns=LATENCY_CURVE_COLUMNS)

    laggard_book = laggard.sort_values("ts").copy()
    rows = []
    for latency_ns in latency_sweep_ns:
        fills = 0
        profitable_fills = 0
        gross_pnl = 0.0
        round_trip_cost = 0.0
        entry_turnover = 0.0
        for event in events.itertuples(index=False):
            arrival_ts = int(event.ts + int(latency_ns))
            book = _book_at(laggard_book, arrival_ts)
            if book is None:
                continue
            expected_move = event.leader_move * delta
            qty = _qty_at_touch(book, instrument.lot_size, depth_fraction, expected_move)
            if qty <= 0:
                continue
            if expected_move > 0:
                fill_price = book["ask"]
                exit_price = event.laggard_bid_at_event + expected_move
                side = +1
            else:
                fill_price = book["bid"]
                exit_price = event.laggard_ask_at_event + expected_move
                side = -1
            raw_edge = side * (exit_price - fill_price)
            if exit_price <= 0:
                continue
            if raw_edge < laggard_tick_size:
                continue
            entry_cost = costs.cost(side, fill_price, qty, instrument)
            exit_cost = costs.cost(-side, exit_price, qty, instrument)
            cost = entry_cost + exit_cost
            gross_edge = raw_edge * qty * instrument.multiplier
            net_edge = gross_edge - cost
            gross_pnl += gross_edge
            round_trip_cost += cost
            entry_turnover += fill_price * qty * instrument.multiplier
            fills += 1
            profitable_fills += int(net_edge > 0)
        net_pnl = gross_pnl - round_trip_cost
        rows.append(
            {
                "latency_ns": int(latency_ns),
                "events": int(len(events)),
                "fills": int(fills),
                "fill_rate": fills / len(events),
                "profitable_fills": int(profitable_fills),
                "win_rate": profitable_fills / fills if fills else 0.0,
                "gross_pnl": float(gross_pnl),
                "round_trip_cost": float(round_trip_cost),
                "net_pnl": float(net_pnl),
                "avg_edge": float(gross_pnl / max(fills, 1)),
                "avg_gross_edge": float(gross_pnl / max(fills, 1)),
                "avg_round_trip_cost": float(round_trip_cost / max(fills, 1)),
                "avg_net_edge": float(net_pnl / max(fills, 1)),
                "cost_drag_ratio": (
                    float(round_trip_cost / gross_pnl)
                    if gross_pnl > 0
                    else np.nan
                ),
                "entry_turnover": float(entry_turnover),
                "net_edge_bps": (
                    float(1e4 * net_pnl / entry_turnover)
                    if entry_turnover > 0
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows, columns=LATENCY_CURVE_COLUMNS)


def _leader_events(
    leader: pd.DataFrame,
    leader_tick_size: float,
    innovation_ticks: float,
) -> pd.DataFrame:
    _validate_book(leader, "leader")
    leader_mid = _mid_frame(leader)
    leader_mid["leader_move"] = leader_mid["mid"].diff().fillna(0)
    events = leader_mid.loc[leader_mid["leader_move"].abs() >= leader_tick_size * innovation_ticks].copy()
    return events[["ts", "mid", "leader_move"]]


def _events_with_laggard_state(
    leader: pd.DataFrame,
    laggard: pd.DataFrame,
    leader_tick_size: float,
    innovation_ticks: float,
) -> pd.DataFrame:
    events = _leader_events(leader, leader_tick_size, innovation_ticks)
    if events.empty:
        return events.assign(
            laggard_bid_at_event=pd.Series(dtype="float64"),
            laggard_ask_at_event=pd.Series(dtype="float64"),
            laggard_mid_at_event=pd.Series(dtype="float64"),
        )
    laggard_state = _mid_frame(laggard)[["ts", "bid", "ask", "mid"]]
    joined = pd.merge_asof(
        events.sort_values("ts"),
        laggard_state.sort_values("ts"),
        on="ts",
        direction="backward",
    ).dropna(subset=["bid", "ask", "mid_y"])
    return joined.rename(
        columns={
            "bid": "laggard_bid_at_event",
            "ask": "laggard_ask_at_event",
            "mid_y": "laggard_mid_at_event",
            "mid_x": "leader_mid",
        }
    )


def _returns_frame(df: pd.DataFrame, ret_col: str) -> pd.DataFrame:
    state = _mid_frame(df)
    state[ret_col] = state["mid"].diff().fillna(0.0)
    return state[["ts", ret_col]]


def _mid_frame(df: pd.DataFrame) -> pd.DataFrame:
    _validate_book(df, "book")
    state = df.sort_values("ts").copy()
    state["mid"] = 0.5 * (state["bid"] + state["ask"])
    return state


def _book_at(book: pd.DataFrame, ts_ns: int) -> dict | None:
    idx = book["ts"].searchsorted(ts_ns, side="right") - 1
    if idx < 0:
        return None
    return book.iloc[int(idx)].to_dict()


def _qty_at_touch(book: dict, lot_size: int, depth_fraction: float, expected_move: float) -> int:
    depth = book["ask_qty"] if expected_move > 0 else book["bid_qty"]
    lots = int(np.floor(depth * depth_fraction)) // lot_size
    return lots * lot_size


def _validate_book(df: pd.DataFrame, name: str):
    missing = [col for col in BOOK_REQUIRED if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
