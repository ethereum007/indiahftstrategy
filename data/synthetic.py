from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SyntheticMarket:
    futures: pd.DataFrame
    options: dict[str, pd.DataFrame]
    deltas: dict[str, float]


def correlated_futures_options(
    *,
    n_ticks: int = 1_000,
    n_options: int = 5,
    start_ts_ns: int = 1_779_419_700_000_000_000,
    step_ns: int = 1_000_000,
    futures_start: float = 25_000.0,
    option_base_price: float = 150.0,
    tick_size: float = 0.05,
    lag_ticks: int | list[int] = 3,
    seed: int = 7,
) -> SyntheticMarket:
    """Generate a leader futures book and lagged option books.

    The option mids follow lagged futures innovations scaled by per-strike
    delta. This is deliberately simple and deterministic so lead-lag and engine
    tests can plant known latency relationships.
    """

    if n_ticks <= 0:
        raise ValueError("n_ticks must be positive")
    if n_options <= 0:
        raise ValueError("n_options must be positive")

    rng = np.random.default_rng(seed)
    ts = start_ts_ns + np.arange(n_ticks, dtype=np.int64) * step_ns
    innovations = rng.normal(0, 0.35, n_ticks)
    futures_mid = futures_start + np.cumsum(innovations)
    futures = _book_from_mid(
        ts,
        futures_mid,
        tick_size=tick_size,
        spread_ticks=1,
        lot_size=75,
        rng=rng,
    )

    lags = _expand_lags(lag_ticks, n_options)
    deltas = {
        f"OPT{i:02d}": float(np.linspace(0.25, 0.75, n_options)[i])
        for i in range(n_options)
    }
    options: dict[str, pd.DataFrame] = {}
    centered_leader = futures_mid - futures_mid[0]
    for i, (symbol, delta) in enumerate(deltas.items()):
        lag = lags[i]
        lagged_move = np.concatenate(
            [np.zeros(lag), centered_leader[: max(n_ticks - lag, 0)]]
        )[:n_ticks]
        micro_noise = rng.normal(0, 0.03, n_ticks)
        mid = option_base_price + i * 5.0 + delta * lagged_move + micro_noise
        mid = np.maximum(mid, tick_size)
        options[symbol] = _book_from_mid(
            ts,
            mid,
            tick_size=tick_size,
            spread_ticks=1 + (i % 3),
            lot_size=75,
            rng=rng,
        )

    return SyntheticMarket(futures=futures, options=options, deltas=deltas)


def _expand_lags(lag_ticks: int | list[int], n_options: int) -> list[int]:
    if isinstance(lag_ticks, int):
        if lag_ticks < 0:
            raise ValueError("lag_ticks must be non-negative")
        return [lag_ticks] * n_options
    if len(lag_ticks) != n_options:
        raise ValueError("lag_ticks list must match n_options")
    if any(lag < 0 for lag in lag_ticks):
        raise ValueError("lag_ticks must be non-negative")
    return list(lag_ticks)


def _book_from_mid(
    ts: np.ndarray,
    mid: np.ndarray,
    *,
    tick_size: float,
    spread_ticks: int,
    lot_size: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    spread = spread_ticks * tick_size
    bid = np.floor((mid - spread / 2) / tick_size) * tick_size
    ask = bid + spread
    bid_qty = rng.integers(5, 40, len(ts)) * lot_size
    ask_qty = rng.integers(5, 40, len(ts)) * lot_size
    last = np.where(rng.random(len(ts)) < 0.5, bid, ask)
    last_qty = rng.integers(1, 5, len(ts)) * lot_size
    return pd.DataFrame(
        {
            "ts": ts.astype("int64"),
            "bid": np.round(bid, 10),
            "ask": np.round(ask, 10),
            "bid_qty": bid_qty.astype("int64"),
            "ask_qty": ask_qty.astype("int64"),
            "last": np.round(last, 10),
            "last_qty": last_qty.astype("int64"),
        }
    )
