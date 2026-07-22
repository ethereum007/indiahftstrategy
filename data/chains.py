from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from data.loaders import (
    _apply_column_map,
    _to_ns,
    tag_regime,
    trading_day_mask,
    trading_session_time_mask,
)
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES


CHAIN_COLUMNS = [
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

REQUIRED_CHAIN_COLUMNS = CHAIN_COLUMNS


@dataclass(frozen=True)
class ChainQuarantineReport:
    total_rows: int
    kept_rows: int
    dropped_null_rows: int = 0
    dropped_nonpositive_quote_rows: int = 0
    dropped_crossed_quote_rows: int = 0
    dropped_negative_depth_rows: int = 0
    dropped_non_trading_day_rows: int = 0
    dropped_out_of_session_rows: int = 0

    @property
    def dropped_rows(self) -> int:
        return self.total_rows - self.kept_rows


@dataclass(frozen=True)
class NormalizedOptionChain:
    data: pd.DataFrame
    quarantine: ChainQuarantineReport


def load_option_chain_csv(
    path: str | Path,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    add_regime: bool = True,
) -> NormalizedOptionChain:
    raw = pd.read_csv(path)
    return normalize_option_chain(
        raw,
        column_map=column_map,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
        add_regime=add_regime,
    )


def normalize_option_chain(
    df: pd.DataFrame,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    add_regime: bool = True,
) -> NormalizedOptionChain:
    source = _apply_column_map(df, column_map)
    _require_columns(source, REQUIRED_CHAIN_COLUMNS)
    out = source.copy()
    out["ts"] = _to_ns(out["ts"], unit=timestamp_unit, timestamp_tz=timestamp_tz)
    out["strike"] = out["strike"].astype("float64")

    total_rows = len(out)
    null_mask = out[REQUIRED_CHAIN_COLUMNS].isna().any(axis=1)
    out = out.loc[~null_mask].copy()

    positive_quote_mask = (
        (out["call_bid"] > 0)
        & (out["call_ask"] > 0)
        & (out["put_bid"] > 0)
        & (out["put_ask"] > 0)
    )
    nonpositive_quote_count = int((~positive_quote_mask).sum())
    out = out.loc[positive_quote_mask].copy()

    crossed_mask = (out["call_ask"] >= out["call_bid"]) & (out["put_ask"] >= out["put_bid"])
    crossed_count = int((~crossed_mask).sum())
    out = out.loc[crossed_mask].copy()

    depth_cols = ["call_bid_qty", "call_ask_qty", "put_bid_qty", "put_ask_qty"]
    depth_mask = (out[depth_cols] > 0).all(axis=1)
    negative_depth_count = int((~depth_mask).sum())
    out = out.loc[depth_mask].copy()

    non_trading_day_count = 0
    session_count = 0
    if filter_session and not out.empty:
        trading_days = trading_day_mask(out["ts"], market=market)
        session_times = trading_session_time_mask(out["ts"], market=market)
        non_trading_day_count = int((~trading_days).sum())
        session_count = int((trading_days & ~session_times).sum())
        out = out.loc[trading_days & session_times].copy()

    if add_regime:
        out["regime"] = tag_regime(out["ts"], market=market)

    for col in depth_cols:
        out[col] = out[col].astype("int64")
    out = out.sort_values(["ts", "expiry", "strike"], kind="mergesort").reset_index(drop=True)

    report = ChainQuarantineReport(
        total_rows=total_rows,
        kept_rows=len(out),
        dropped_null_rows=int(null_mask.sum()),
        dropped_nonpositive_quote_rows=nonpositive_quote_count,
        dropped_crossed_quote_rows=crossed_count,
        dropped_negative_depth_rows=negative_depth_count,
        dropped_non_trading_day_rows=non_trading_day_count,
        dropped_out_of_session_rows=session_count,
    )
    return NormalizedOptionChain(out, report)


def _require_columns(df: pd.DataFrame, columns: list[str]):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"missing required option-chain columns: {missing}")
