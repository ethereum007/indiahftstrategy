from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES, get_market_profile, session_mask


ENGINE_COLUMNS = ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
REQUIRED_COLUMNS = ["ts", "bid", "ask", "bid_qty", "ask_qty"]
IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class QuarantineReport:
    total_rows: int
    kept_rows: int
    dropped_null_rows: int = 0
    dropped_nonpositive_quote_rows: int = 0
    dropped_crossed_quote_rows: int = 0
    dropped_nonmonotonic_rows: int = 0
    dropped_out_of_session_rows: int = 0

    @property
    def dropped_rows(self) -> int:
        return self.total_rows - self.kept_rows


@dataclass(frozen=True)
class NormalizedTicks:
    data: pd.DataFrame
    quarantine: QuarantineReport


def load_tick_csv(
    path: str | Path,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    add_regime: bool = True,
) -> NormalizedTicks:
    raw = pd.read_csv(path)
    return normalize_ticks(
        raw,
        column_map=column_map,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
        add_regime=add_regime,
    )


def normalize_ticks(
    df: pd.DataFrame,
    *,
    column_map: Optional[Mapping[str, str]] = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    add_regime: bool = True,
) -> NormalizedTicks:
    """Normalize vendor ticks into the engine schema.

    `column_map` maps engine column names to source column names, for example
    {"ts": "exchange_time", "bid": "best_bid"}.
    """

    source = _apply_column_map(df, column_map)
    _require_columns(source, REQUIRED_COLUMNS)
    out = source.copy()
    out["ts"] = _to_ns(out["ts"], unit=timestamp_unit, timestamp_tz=timestamp_tz)
    for col in ("last", "last_qty"):
        if col not in out.columns:
            out[col] = np.nan

    total_rows = len(out)
    null_mask = out[REQUIRED_COLUMNS].isna().any(axis=1)
    out = out.loc[~null_mask].copy()
    quote_positive_mask = (out["bid"] > 0) & (out["ask"] > 0)
    nonpositive_count = int((~quote_positive_mask).sum())
    out = out.loc[quote_positive_mask].copy()
    crossed_mask = out["ask"] >= out["bid"]
    crossed_count = int((~crossed_mask).sum())
    out = out.loc[crossed_mask].copy()
    monotonic_mask = out["ts"].diff().fillna(0) >= 0
    nonmonotonic_count = int((~monotonic_mask).sum())
    out = out.loc[monotonic_mask].copy()
    out = out.sort_values("ts", kind="mergesort").reset_index(drop=True)

    session_count = 0
    if filter_session and not out.empty:
        session = trading_session_mask(out["ts"], market=market)
        session_count = int((~session).sum())
        out = out.loc[session].copy()

    if add_regime:
        out["regime"] = tag_regime(out["ts"], market=market)

    for col in ("bid_qty", "ask_qty"):
        out[col] = out[col].astype("int64")
    out["last_qty"] = out["last_qty"].fillna(0).astype("int64")
    out = out.reset_index(drop=True)

    report = QuarantineReport(
        total_rows=total_rows,
        kept_rows=len(out),
        dropped_null_rows=int(null_mask.sum()),
        dropped_nonpositive_quote_rows=nonpositive_count,
        dropped_crossed_quote_rows=crossed_count,
        dropped_nonmonotonic_rows=nonmonotonic_count,
        dropped_out_of_session_rows=session_count,
    )
    return NormalizedTicks(out, report)


def _apply_column_map(
    df: pd.DataFrame,
    column_map: Optional[Mapping[str, str]],
) -> pd.DataFrame:
    if not column_map:
        return df.copy()
    missing_sources = [src for src in column_map.values() if src not in df.columns]
    if missing_sources:
        raise ValueError(f"source columns missing from vendor data: {missing_sources}")
    rename = {src: dst for dst, src in column_map.items()}
    return df.rename(columns=rename)


def _require_columns(df: pd.DataFrame, columns: list[str]):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"missing required normalized columns: {missing}")


def _to_ns(
    values: pd.Series,
    *,
    unit: str,
    timestamp_tz: str | None,
) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(values):
        dt = pd.to_datetime(values)
    elif unit == "datetime":
        dt = pd.to_datetime(values)
    else:
        return values.astype("int64") * _unit_multiplier(unit)

    if dt.dt.tz is None:
        if timestamp_tz:
            dt = dt.dt.tz_localize(timestamp_tz)
        else:
            dt = dt.dt.tz_localize(IST)
    else:
        dt = dt.dt.tz_convert(IST)
    return dt.dt.as_unit("ns").astype("int64")


def _unit_multiplier(unit: str) -> int:
    units = {
        "ns": 1,
        "us": 1_000,
        "ms": 1_000_000,
        "s": 1_000_000_000,
    }
    try:
        return units[unit]
    except KeyError as exc:
        raise ValueError(f"unsupported timestamp_unit {unit!r}") from exc


def trading_session_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> pd.Series:
    return session_mask(ts_ns, market=market)


def tag_regime(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> pd.Series:
    profile = get_market_profile(market)
    dt = pd.to_datetime(ts_ns, unit="ns", utc=True).dt.tz_convert(ZoneInfo(profile.session.timezone))
    if profile.name != INDIA_NSE_INDEX_DERIVATIVES.name:
        return pd.Series(np.full(len(dt), "baseline_market_structure", dtype=object), index=ts_ns.index)
    dates = dt.dt.date.astype(str)
    labels = np.full(len(dt), "pre_weekly_consolidation", dtype=object)
    labels[dates >= "2024-11-20"] = "weekly_consolidated"
    labels[dates >= "2025-09-01"] = "expiry_swap"
    labels[dates >= "2026-04-01"] = "post_stt_hike"
    return pd.Series(labels, index=ts_ns.index)
