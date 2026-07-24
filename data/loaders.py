from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Callable, Mapping, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from markets.calendars import MarketCalendar, resolve_market_calendar
from markets.profiles import (
    INDIA_NSE_INDEX_DERIVATIVES,
    calendar_closed_mask as market_calendar_closed_mask,
    calendar_out_of_range_mask as market_calendar_out_of_range_mask,
    get_market_profile,
    session_mask,
    session_time_mask,
    trading_day_mask as market_trading_day_mask,
)


ENGINE_COLUMNS = ["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"]
REQUIRED_COLUMNS = ["ts", "bid", "ask", "bid_qty", "ask_qty"]
IST = ZoneInfo("Asia/Kolkata")
INT64_MIN = int(np.iinfo(np.int64).min)
INT64_MAX = int(np.iinfo(np.int64).max)


@dataclass(frozen=True)
class QuarantineReport:
    total_rows: int
    kept_rows: int
    dropped_null_rows: int = 0
    dropped_nonfinite_rows: int = 0
    dropped_nonintegral_rows: int = 0
    dropped_duplicate_rows: int = 0
    dropped_integer_overflow_rows: int = 0
    dropped_negative_depth_rows: int = 0
    dropped_invalid_trade_rows: int = 0
    dropped_nonpositive_quote_rows: int = 0
    dropped_crossed_quote_rows: int = 0
    dropped_nonmonotonic_rows: int = 0
    dropped_non_trading_day_rows: int = 0
    dropped_calendar_closed_rows: int = 0
    dropped_calendar_out_of_range_rows: int = 0
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
    market_calendar: MarketCalendar | str | Path | None = None,
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
        market_calendar=market_calendar,
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
    market_calendar: MarketCalendar | str | Path | None = None,
    add_regime: bool = True,
) -> NormalizedTicks:
    """Normalize vendor ticks into the engine schema.

    `column_map` maps engine column names to source column names, for example
    {"ts": "exchange_time", "bid": "best_bid"}.
    """

    calendar = resolve_market_calendar(market_calendar, market=market)
    source = _apply_column_map(df, column_map)
    _require_columns(source, REQUIRED_COLUMNS)
    out = source.copy()
    for col in ("last", "last_qty"):
        if col not in out.columns:
            out[col] = np.nan

    total_rows = len(out)
    optional_columns = ["last", "last_qty"]
    optional_values_present = out[optional_columns].notna()
    out["ts"] = _to_ns(out["ts"], unit=timestamp_unit, timestamp_tz=timestamp_tz)
    integer_values = out[["ts", "bid_qty", "ask_qty", "last_qty"]].copy()
    integer_columns = ["bid_qty", "ask_qty", "last_qty"]
    real_columns = ["bid", "ask", "last"]
    out[integer_columns] = out[integer_columns].apply(_coerce_integer_numeric)
    out[real_columns] = out[real_columns].apply(pd.to_numeric, errors="coerce")
    optional_parse_failed = optional_values_present & out[optional_columns].isna()
    null_mask = out[REQUIRED_COLUMNS].isna().any(axis=1)
    out = out.loc[~null_mask].copy()
    finite_mask = _finite_numeric_mask(
        out,
        ENGINE_COLUMNS,
        nullable_columns=optional_columns,
    )
    finite_mask &= ~optional_parse_failed.loc[out.index].any(axis=1)
    nonfinite_count = int((~finite_mask).sum())
    out = out.loc[finite_mask].copy()
    integral_mask = _integral_numeric_mask(
        out,
        ["ts", "bid_qty", "ask_qty", "last_qty"],
        nullable_columns=["last_qty"],
    )
    nonintegral_count = int((~integral_mask).sum())
    out = out.loc[integral_mask].copy()
    int64_mask = _int64_range_mask(
        integer_values.loc[out.index],
        ["ts", "bid_qty", "ask_qty", "last_qty"],
        nullable_columns=["last_qty"],
    )
    integer_overflow_count = int((~int64_mask).sum())
    out = out.loc[int64_mask].copy()
    depth_mask = (out["bid_qty"] > 0) & (out["ask_qty"] > 0)
    negative_depth_count = int((~depth_mask).sum())
    out = out.loc[depth_mask].copy()
    out["ts"] = out["ts"].astype("int64")
    quote_positive_mask = (out["bid"] > 0) & (out["ask"] > 0)
    nonpositive_count = int((~quote_positive_mask).sum())
    out = out.loc[quote_positive_mask].copy()
    crossed_mask = out["ask"] >= out["bid"]
    crossed_count = int((~crossed_mask).sum())
    out = out.loc[crossed_mask].copy()
    trade_mask = (out["last"].isna() | (out["last"] > 0)) & (
        out["last_qty"].isna() | (out["last_qty"] >= 0)
    )
    invalid_trade_count = int((~trade_mask).sum())
    out = out.loc[trade_mask].copy()
    monotonic_mask = _timestamp_at_high_water_mask(out["ts"])
    nonmonotonic_count = int((~monotonic_mask).sum())
    out = out.loc[monotonic_mask].copy()
    out = out.sort_values("ts", kind="mergesort").reset_index(drop=True)

    non_trading_day_count = 0
    calendar_closed_count = 0
    calendar_out_of_range_count = 0
    session_count = 0
    if filter_session and not out.empty:
        trading_days = trading_day_mask(
            out["ts"],
            market=market,
            market_calendar=calendar,
        )
        session_times = trading_session_time_mask(
            out["ts"],
            market=market,
            market_calendar=calendar,
        )
        calendar_closed_count = int(
            calendar_closed_mask(
                out["ts"],
                market=market,
                market_calendar=calendar,
            ).sum()
        )
        calendar_out_of_range_count = int(
            calendar_out_of_range_mask(
                out["ts"],
                market=market,
                market_calendar=calendar,
            ).sum()
        )
        non_trading_day_count = int((~trading_days).sum())
        session_count = int((trading_days & ~session_times).sum())
        out = out.loc[trading_days & session_times].copy()

    duplicate_mask = out.duplicated(subset=ENGINE_COLUMNS, keep="first")
    duplicate_count = int(duplicate_mask.sum())
    out = out.loc[~duplicate_mask].copy()

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
        dropped_nonfinite_rows=nonfinite_count,
        dropped_nonintegral_rows=nonintegral_count,
        dropped_duplicate_rows=duplicate_count,
        dropped_integer_overflow_rows=integer_overflow_count,
        dropped_negative_depth_rows=negative_depth_count,
        dropped_invalid_trade_rows=invalid_trade_count,
        dropped_nonpositive_quote_rows=nonpositive_count,
        dropped_crossed_quote_rows=crossed_count,
        dropped_nonmonotonic_rows=nonmonotonic_count,
        dropped_non_trading_day_rows=non_trading_day_count,
        dropped_calendar_closed_rows=calendar_closed_count,
        dropped_calendar_out_of_range_rows=calendar_out_of_range_count,
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
        dt = pd.to_datetime(values, errors="coerce")
    elif unit == "datetime":
        dt = pd.to_datetime(values, errors="coerce")
    else:
        numeric = _coerce_integer_numeric(values)
        return _scale_numeric_timestamp(
            numeric,
            _unit_multiplier(unit),
            source_values=values,
        )

    if dt.dt.tz is None:
        if timestamp_tz:
            dt = dt.dt.tz_localize(timestamp_tz)
        else:
            dt = dt.dt.tz_localize(IST)
    else:
        dt = dt.dt.tz_convert(IST)
    ns = dt.dt.as_unit("ns").astype("int64")
    return ns.mask(dt.isna()).astype("Int64")


def _finite_numeric_mask(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    nullable_columns: list[str] | tuple[str, ...] = (),
) -> pd.Series:
    nullable = set(nullable_columns)
    mask = pd.Series(True, index=frame.index, dtype=bool)
    for column in columns:
        source_values = frame[column]
        if pd.api.types.is_numeric_dtype(source_values.dtype):
            values = pd.to_numeric(source_values, errors="coerce")
            finite = pd.Series(
                np.isfinite(values.astype("float64").to_numpy()),
                index=frame.index,
                dtype=bool,
            )
        else:
            values = source_values
            finite = source_values.map(_object_numeric_value_is_finite)
        if column in nullable:
            finite |= values.isna()
        mask &= finite
    return mask


def _integral_numeric_mask(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    nullable_columns: list[str] | tuple[str, ...] = (),
) -> pd.Series:
    nullable = set(nullable_columns)
    mask = pd.Series(True, index=frame.index, dtype=bool)
    for column in columns:
        source_values = frame[column]
        if pd.api.types.is_numeric_dtype(source_values.dtype):
            values = pd.to_numeric(source_values, errors="coerce")
            integral = values.mod(1).eq(0).fillna(False)
        else:
            values = source_values
            integral = source_values.map(_object_numeric_value_is_integral)
        if column in nullable:
            integral |= values.isna()
        mask &= integral.astype(bool)
    return mask


def _int64_range_mask(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    nullable_columns: list[str] | tuple[str, ...] = (),
) -> pd.Series:
    nullable = set(nullable_columns)
    mask = pd.Series(True, index=frame.index, dtype=bool)
    for column in columns:
        source_values = frame[column]
        if not pd.api.types.is_numeric_dtype(source_values.dtype):
            in_range = source_values.map(_object_int64_value_in_range)
            values = source_values
        else:
            values = pd.to_numeric(source_values, errors="coerce")
            if pd.api.types.is_float_dtype(values.dtype):
                in_range = values.ge(float(INT64_MIN)) & values.lt(
                    float(INT64_MAX) + 1.0
                )
            else:
                in_range = values.ge(INT64_MIN) & values.le(INT64_MAX)
        if column in nullable:
            in_range |= values.isna()
        mask &= in_range.fillna(False).astype(bool)
    return mask


def _timestamp_at_high_water_mask(values: pd.Series) -> pd.Series:
    """Keep timestamps that equal the greatest value observed so far."""

    return values.eq(values.cummax()).fillna(False).astype(bool)


def _object_int64_value_in_range(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (int, np.integer)):
        return INT64_MIN <= int(value) <= INT64_MAX
    if isinstance(value, (float, np.floating)):
        numeric = float(value)
        return (
            np.isfinite(numeric)
            and numeric.is_integer()
            and numeric >= float(INT64_MIN)
            and numeric < float(INT64_MAX) + 1.0
        )
    try:
        numeric = Decimal(str(value).strip())
    except (DecimalException, ValueError):
        return False
    return (
        numeric.is_finite()
        and numeric == numeric.to_integral_value()
        and Decimal(INT64_MIN) <= numeric <= Decimal(INT64_MAX)
    )


def _scale_numeric_timestamp(
    values: pd.Series,
    multiplier: int,
    *,
    source_values: pd.Series,
) -> pd.Series:
    if (
        not pd.api.types.is_numeric_dtype(source_values.dtype)
        and pd.api.types.is_float_dtype(values.dtype)
    ):
        return _map_object_series(
            source_values,
            lambda value: _scale_object_timestamp_value(value, multiplier),
        )
    if multiplier == 1 or not pd.api.types.is_integer_dtype(values.dtype):
        return values * multiplier

    min_source = -((-INT64_MIN) // multiplier)
    max_source = INT64_MAX // multiplier
    within_range = values.isna() | values.between(min_source, max_source).fillna(False)
    if bool(within_range.all()):
        return values * multiplier

    return _map_object_series(
        values,
        lambda value: value if pd.isna(value) else int(value) * multiplier,
    )


def _scale_object_timestamp_value(value: object, multiplier: int) -> object:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, np.integer)):
        return int(value) * multiplier
    if isinstance(value, (float, np.floating)):
        return float(value) * multiplier
    try:
        return Decimal(str(value).strip()) * multiplier
    except (DecimalException, ValueError):
        return np.nan


def _coerce_integer_numeric(values: pd.Series) -> pd.Series:
    try:
        numeric = pd.to_numeric(values, errors="coerce")
    except OverflowError:
        return _map_object_series(values, _object_numeric_value)
    if (
        not pd.api.types.is_numeric_dtype(values.dtype)
        and pd.api.types.is_float_dtype(numeric.dtype)
    ):
        return _map_object_series(values, _object_numeric_value)
    return numeric


def _map_object_series(
    values: pd.Series,
    function: Callable[[object], object],
) -> pd.Series:
    return pd.Series(
        [function(value) for value in values.array],
        index=values.index,
        dtype="object",
        name=values.name,
    )


def _object_numeric_value(value: object) -> object:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    try:
        return Decimal(str(value).strip())
    except (DecimalException, ValueError):
        return np.nan


def _object_numeric_value_is_finite(value: object) -> bool:
    numeric = _object_numeric_value(value)
    if isinstance(numeric, Decimal):
        return numeric.is_finite()
    if isinstance(numeric, int):
        return True
    if pd.isna(numeric):
        return False
    return bool(np.isfinite(numeric))


def _object_numeric_value_is_integral(value: object) -> bool:
    numeric = _object_numeric_value(value)
    if isinstance(numeric, Decimal):
        return numeric.is_finite() and numeric == numeric.to_integral_value()
    if isinstance(numeric, int):
        return True
    if pd.isna(numeric) or not np.isfinite(numeric):
        return False
    return float(numeric).is_integer()


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
    market_calendar: MarketCalendar | str | Path | None = None,
) -> pd.Series:
    return session_mask(
        ts_ns,
        market=market,
        market_calendar=market_calendar,
    )


def trading_session_time_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> pd.Series:
    return session_time_mask(
        ts_ns,
        market=market,
        market_calendar=market_calendar,
    )


def trading_day_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> pd.Series:
    return market_trading_day_mask(
        ts_ns,
        market=market,
        market_calendar=market_calendar,
    )


def calendar_closed_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> pd.Series:
    return market_calendar_closed_mask(
        ts_ns,
        market=market,
        market_calendar=market_calendar,
    )


def calendar_out_of_range_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> pd.Series:
    return market_calendar_out_of_range_mask(
        ts_ns,
        market=market,
        market_calendar=market_calendar,
    )


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
