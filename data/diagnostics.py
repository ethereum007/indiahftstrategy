from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from data.loaders import (
    _timestamp_at_high_water_mask,
    calendar_closed_mask,
    calendar_out_of_range_mask,
    trading_day_mask,
    trading_session_time_mask,
)
from markets.calendars import (
    MarketCalendar,
    market_calendar_summary,
    resolve_market_calendar,
)
from markets.expiries import (
    NseFoExpiryRule,
    NseFoExpiryValidation,
    expiry_rule_summary,
    load_nse_fo_expiry_rule,
    validate_nse_fo_expiry,
)
from markets.lot_sizes import (
    NseIndexLotRule,
    NseIndexLotValidation,
    index_lot_rule_summary,
    load_nse_index_lot_rule,
    validate_nse_index_lot_size,
)
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES, get_market_profile


TICK_REQUIRED = ["ts", "bid", "ask", "bid_qty", "ask_qty"]
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
CONTRACT_KEY_COLUMNS = ["ts", "expiry", "strike"]
CONTRACT_STATE_COLUMNS = [
    "call_bid",
    "call_ask",
    "call_bid_qty",
    "call_ask_qty",
    "put_bid",
    "put_ask",
    "put_bid_qty",
    "put_ask_qty",
]
PRICE_GRID_ATOL_TICKS = 1e-7


@dataclass(frozen=True)
class DiagnosticResult:
    summary: pd.DataFrame
    issues: pd.DataFrame
    output_dir: Path | None = None


@dataclass(frozen=True)
class _ContractExpiryDiagnostics:
    enabled: bool
    cycle: str
    rule: NseFoExpiryRule | None
    validations: dict[str, NseFoExpiryValidation]
    row_valid: pd.Series
    row_covered: pd.Series


@dataclass(frozen=True)
class _ContractLotDiagnostics:
    enabled: bool
    underlying: str
    lot_size: object
    cycle: str
    rule: NseIndexLotRule | None
    validations: dict[str, NseIndexLotValidation]
    row_valid: pd.Series
    row_covered: pd.Series


@dataclass(frozen=True)
class _ContractHorizonDiagnostics:
    market_timezone: str
    observation_dates: pd.Series
    expiry_dates: pd.Series
    calendar_dte_days: pd.Series
    row_parseable: pd.Series
    row_expired: pd.Series
    row_zero_dte: pd.Series


@dataclass(frozen=True)
class _ContractKeyDiagnostics:
    row_duplicate: pd.Series
    row_duplicate_excess: pd.Series
    row_exact_duplicate: pd.Series
    row_conflicting: pd.Series
    duplicate_group_head: pd.Series
    exact_duplicate_group_head: pd.Series
    conflicting_group_head: pd.Series


@dataclass(frozen=True)
class _ChainSnapshotDiagnostics:
    snapshots: pd.DataFrame
    by_expiry: pd.DataFrame


def tick_diagnostics(
    ticks: pd.DataFrame,
    *,
    tick_size: float | None = None,
    max_quote_spread_ticks: float | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> DiagnosticResult:
    _require(ticks, TICK_REQUIRED, "ticks")
    _validate_tick_size(tick_size)
    _validate_quote_spread_limit(
        tick_size=tick_size,
        max_quote_spread_ticks=max_quote_spread_ticks,
    )
    calendar = resolve_market_calendar(market_calendar, market=market)
    frame = ticks.copy()
    frame["spread"] = frame["ask"] - frame["bid"]
    frame["mid"] = 0.5 * (frame["bid"] + frame["ask"])
    frame["depth"] = frame["bid_qty"] + frame["ask_qty"]
    if tick_size is not None:
        frame["spread_ticks"] = frame["spread"] / tick_size
    else:
        frame["spread_ticks"] = np.nan
    wide_spread = _wide_spread_mask(
        frame["spread_ticks"],
        max_quote_spread_ticks=max_quote_spread_ticks,
    )
    gaps = frame["ts"].sort_values().diff().dropna()
    nonmonotonic = ~_timestamp_at_high_water_mask(frame["ts"])
    invalid_trade = _invalid_trade_mask(frame)
    off_tick_price = _off_tick_price_mask(
        frame,
        ("bid", "ask", "last"),
        tick_size=tick_size,
    )
    non_trading_days, calendar_closed, calendar_out_of_range, out_of_session = _session_issue_masks(
        frame["ts"],
        market=market,
        market_calendar=calendar,
    )
    summary = pd.DataFrame(
        [
            {
                "market": market,
                **market_calendar_summary(calendar),
                "rows": int(len(frame)),
                "start_ts": int(frame["ts"].min()) if len(frame) else np.nan,
                "end_ts": int(frame["ts"].max()) if len(frame) else np.nan,
                "nonmonotonic_rows": int(nonmonotonic.sum()),
                "crossed_quote_rows": int((frame["ask"] < frame["bid"]).sum()),
                "nonpositive_quote_rows": int(((frame["bid"] <= 0) | (frame["ask"] <= 0)).sum()),
                "nonpositive_depth_rows": int(((frame["bid_qty"] <= 0) | (frame["ask_qty"] <= 0)).sum()),
                "invalid_trade_rows": int(invalid_trade.sum()),
                "price_grid_validation_enabled": tick_size is not None,
                "price_grid_tick_size": float(tick_size) if tick_size is not None else np.nan,
                "off_tick_price_rows": int(off_tick_price.sum()),
                "quote_spread_validation_enabled": (
                    max_quote_spread_ticks is not None
                ),
                "max_quote_spread_ticks": (
                    float(max_quote_spread_ticks)
                    if max_quote_spread_ticks is not None
                    else np.nan
                ),
                "wide_spread_rows": int(wide_spread.sum()),
                "non_trading_day_rows": int(non_trading_days.sum()),
                "calendar_closed_rows": int(calendar_closed.sum()),
                "calendar_out_of_range_rows": int(calendar_out_of_range.sum()),
                "out_of_session_rows": int(out_of_session.sum()),
                "median_gap_ns": float(gaps.median()) if len(gaps) else 0.0,
                "p99_gap_ns": float(gaps.quantile(0.99)) if len(gaps) else 0.0,
                "median_spread": float(frame["spread"].median()) if len(frame) else 0.0,
                "median_spread_ticks": float(frame["spread_ticks"].median()) if tick_size and len(frame) else np.nan,
                "median_depth": float(frame["depth"].median()) if len(frame) else 0.0,
            }
        ]
    )
    return DiagnosticResult(
        summary=summary,
        issues=_tick_issues(
            frame,
            nonmonotonic=nonmonotonic,
            non_trading_days=non_trading_days,
            calendar_closed=calendar_closed,
            calendar_out_of_range=calendar_out_of_range,
            out_of_session=out_of_session,
            invalid_trade=invalid_trade,
            off_tick_price=off_tick_price,
            wide_spread=wide_spread,
        ),
    )


def chain_diagnostics(
    chain: pd.DataFrame,
    *,
    tick_size: float | None = None,
    max_quote_spread_ticks: float | None = None,
    strike_step: float | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
    expiry_cycle: str | None = None,
    underlying: str | None = None,
    lot_size: int | None = None,
) -> DiagnosticResult:
    _require(chain, CHAIN_REQUIRED, "chain")
    _validate_tick_size(tick_size)
    _validate_quote_spread_limit(
        tick_size=tick_size,
        max_quote_spread_ticks=max_quote_spread_ticks,
    )
    _validate_strike_step(strike_step)
    calendar = resolve_market_calendar(market_calendar, market=market)
    frame = chain.copy()
    frame["call_spread"] = frame["call_ask"] - frame["call_bid"]
    frame["put_spread"] = frame["put_ask"] - frame["put_bid"]
    if tick_size is not None:
        frame["call_spread_ticks"] = frame["call_spread"] / tick_size
        frame["put_spread_ticks"] = frame["put_spread"] / tick_size
    else:
        frame["call_spread_ticks"] = np.nan
        frame["put_spread_ticks"] = np.nan
    frame["wide_spread"] = (
        _wide_spread_mask(
            frame["call_spread_ticks"],
            max_quote_spread_ticks=max_quote_spread_ticks,
        )
        | _wide_spread_mask(
            frame["put_spread_ticks"],
            max_quote_spread_ticks=max_quote_spread_ticks,
        )
    )
    frame["off_tick_price"] = _off_tick_price_mask(
        frame,
        ("call_bid", "call_ask", "put_bid", "put_ask"),
        tick_size=tick_size,
    )
    frame["nonmonotonic_ts"] = ~_timestamp_at_high_water_mask(frame["ts"])
    frame["nonpositive_strike"] = frame["strike"] <= 0
    frame["off_grid_strike"] = _off_grid_value_mask(
        frame["strike"],
        step=strike_step,
    )
    non_trading_days, calendar_closed, calendar_out_of_range, out_of_session = _session_issue_masks(
        frame["ts"],
        market=market,
        market_calendar=calendar,
    )
    horizon_diagnostics = _contract_horizon_diagnostics(
        frame["ts"],
        frame["expiry"],
        market=market,
    )
    frame["calendar_dte_days"] = horizon_diagnostics.calendar_dte_days
    frame["contract_expiry_parseable"] = horizon_diagnostics.row_parseable
    frame["unparseable_contract_expiry"] = ~horizon_diagnostics.row_parseable
    frame["expired_contract"] = horizon_diagnostics.row_expired
    frame["zero_dte_contract"] = horizon_diagnostics.row_zero_dte
    key_diagnostics = _contract_key_diagnostics(frame)
    frame["duplicate_contract_key"] = key_diagnostics.row_duplicate
    frame["duplicate_contract_key_excess"] = (
        key_diagnostics.row_duplicate_excess
    )
    frame["exact_duplicate_contract_key"] = (
        key_diagnostics.row_exact_duplicate
    )
    frame["conflicting_contract_key"] = key_diagnostics.row_conflicting
    frame["duplicate_contract_key_group_head"] = (
        key_diagnostics.duplicate_group_head
    )
    frame["exact_duplicate_contract_key_group_head"] = (
        key_diagnostics.exact_duplicate_group_head
    )
    frame["conflicting_contract_key_group_head"] = (
        key_diagnostics.conflicting_group_head
    )
    snapshot_diagnostics = _chain_snapshot_diagnostics(frame)
    expiry_diagnostics = _contract_expiry_diagnostics(
        frame["expiry"],
        cycle=expiry_cycle,
        market_calendar=calendar,
    )
    lot_diagnostics = _contract_lot_diagnostics(
        frame["expiry"],
        underlying=underlying,
        lot_size=lot_size,
        cycle=expiry_cycle,
    )
    by_expiry = (
        frame.groupby("expiry", dropna=False)
        .agg(
            rows=("strike", "size"),
            strikes=("strike", "nunique"),
            min_strike=("strike", "min"),
            max_strike=("strike", "max"),
            median_call_spread=("call_spread", "median"),
            median_put_spread=("put_spread", "median"),
            median_call_spread_ticks=("call_spread_ticks", "median"),
            median_put_spread_ticks=("put_spread_ticks", "median"),
            off_tick_price_rows=("off_tick_price", "sum"),
            wide_spread_rows=("wide_spread", "sum"),
            nonmonotonic_rows=("nonmonotonic_ts", "sum"),
            nonpositive_strike_rows=("nonpositive_strike", "sum"),
            off_grid_strike_rows=("off_grid_strike", "sum"),
            parseable_contract_expiry_rows=(
                "contract_expiry_parseable",
                "sum",
            ),
            unparseable_contract_expiry_rows=(
                "unparseable_contract_expiry",
                "sum",
            ),
            expired_contract_rows=("expired_contract", "sum"),
            zero_dte_rows=("zero_dte_contract", "sum"),
            min_calendar_dte_days=("calendar_dte_days", "min"),
            median_calendar_dte_days=("calendar_dte_days", "median"),
            max_calendar_dte_days=("calendar_dte_days", "max"),
            duplicate_contract_key_rows=("duplicate_contract_key", "sum"),
            duplicate_contract_key_excess_rows=(
                "duplicate_contract_key_excess",
                "sum",
            ),
            duplicate_contract_key_groups=(
                "duplicate_contract_key_group_head",
                "sum",
            ),
            exact_duplicate_contract_key_rows=(
                "exact_duplicate_contract_key",
                "sum",
            ),
            exact_duplicate_contract_key_groups=(
                "exact_duplicate_contract_key_group_head",
                "sum",
            ),
            conflicting_contract_key_rows=(
                "conflicting_contract_key",
                "sum",
            ),
            conflicting_contract_key_groups=(
                "conflicting_contract_key_group_head",
                "sum",
            ),
        )
        .reset_index()
    )
    by_expiry = by_expiry.merge(
        snapshot_diagnostics.by_expiry,
        on="expiry",
        how="left",
        validate="one_to_one",
    )
    if expiry_diagnostics.enabled:
        validations = [
            expiry_diagnostics.validations[_expiry_key(value)]
            for value in by_expiry["expiry"]
        ]
        by_expiry["contract_expiry_valid"] = [
            validation.valid for validation in validations
        ]
        by_expiry["contract_expiry_covered"] = [
            validation.covered for validation in validations
        ]
        by_expiry["contract_expiry_expected"] = [
            _optional_date(validation.expected_expiry)
            for validation in validations
        ]
        by_expiry["contract_expiry_nominal"] = [
            _optional_date(validation.nominal_expiry)
            for validation in validations
        ]
        by_expiry["contract_expiry_adjusted"] = [
            bool(validation.decision and validation.decision.adjusted)
            for validation in validations
        ]
        by_expiry["contract_expiry_rollback_days"] = [
            (
                int(validation.decision.rollback_days)
                if validation.decision is not None
                else np.nan
            )
            for validation in validations
        ]
        by_expiry["contract_expiry_reason"] = [
            validation.reason for validation in validations
        ]
    if lot_diagnostics.enabled:
        lot_validations = [
            lot_diagnostics.validations[_expiry_key(value)]
            for value in by_expiry["expiry"]
        ]
        by_expiry["contract_lot_valid"] = [
            validation.valid for validation in lot_validations
        ]
        by_expiry["contract_lot_covered"] = [
            validation.covered for validation in lot_validations
        ]
        by_expiry["contract_lot_expected"] = [
            (
                int(validation.expected_lot_size)
                if validation.expected_lot_size is not None
                else np.nan
            )
            for validation in lot_validations
        ]
        by_expiry["contract_lot_first_expiry"] = [
            (
                validation.decision.first_expiry.isoformat()
                if validation.decision is not None
                else ""
            )
            for validation in lot_validations
        ]
        by_expiry["contract_lot_reason"] = [
            validation.reason for validation in lot_validations
        ]
    expiry_summary = _contract_expiry_summary(expiry_diagnostics)
    lot_summary = _contract_lot_summary(lot_diagnostics)
    horizon_summary = _contract_horizon_summary(horizon_diagnostics)
    key_summary = _contract_key_summary(key_diagnostics)
    snapshot_summary = _chain_snapshot_summary(snapshot_diagnostics)
    overall = pd.DataFrame(
        [
            {
                "market": market,
                **market_calendar_summary(calendar),
                **horizon_summary,
                **key_summary,
                **snapshot_summary,
                **expiry_summary,
                **lot_summary,
                "rows": int(len(frame)),
                "expiries": int(frame["expiry"].nunique()),
                "strikes": int(frame["strike"].nunique()),
                "start_ts": int(frame["ts"].min()) if len(frame) else np.nan,
                "end_ts": int(frame["ts"].max()) if len(frame) else np.nan,
                "nonmonotonic_rows": int(frame["nonmonotonic_ts"].sum()),
                "nonpositive_strike_rows": int(
                    frame["nonpositive_strike"].sum()
                ),
                "strike_grid_validation_enabled": strike_step is not None,
                "strike_grid_step": (
                    float(strike_step)
                    if strike_step is not None
                    else np.nan
                ),
                "off_grid_strike_rows": int(
                    frame["off_grid_strike"].sum()
                ),
                "crossed_quote_rows": int(((frame["call_ask"] < frame["call_bid"]) | (frame["put_ask"] < frame["put_bid"])).sum()),
                "nonpositive_quote_rows": int(
                    (
                        (frame["call_bid"] <= 0)
                        | (frame["call_ask"] <= 0)
                        | (frame["put_bid"] <= 0)
                        | (frame["put_ask"] <= 0)
                    ).sum()
                ),
                "nonpositive_depth_rows": int(
                    (
                        (frame["call_bid_qty"] <= 0)
                        | (frame["call_ask_qty"] <= 0)
                        | (frame["put_bid_qty"] <= 0)
                        | (frame["put_ask_qty"] <= 0)
                    ).sum()
                ),
                "price_grid_validation_enabled": tick_size is not None,
                "price_grid_tick_size": float(tick_size) if tick_size is not None else np.nan,
                "off_tick_price_rows": int(frame["off_tick_price"].sum()),
                "quote_spread_validation_enabled": (
                    max_quote_spread_ticks is not None
                ),
                "max_quote_spread_ticks": (
                    float(max_quote_spread_ticks)
                    if max_quote_spread_ticks is not None
                    else np.nan
                ),
                "wide_spread_rows": int(frame["wide_spread"].sum()),
                "non_trading_day_rows": int(non_trading_days.sum()),
                "calendar_closed_rows": int(calendar_closed.sum()),
                "calendar_out_of_range_rows": int(calendar_out_of_range.sum()),
                "out_of_session_rows": int(out_of_session.sum()),
            }
        ]
    )
    summary = pd.concat([overall.assign(scope="overall"), by_expiry.assign(scope="expiry")], ignore_index=True, sort=False)
    return DiagnosticResult(
        summary=summary,
        issues=_chain_issues(
            frame,
            nonmonotonic=frame["nonmonotonic_ts"],
            nonpositive_strike=frame["nonpositive_strike"],
            off_grid_strike=frame["off_grid_strike"],
            non_trading_days=non_trading_days,
            calendar_closed=calendar_closed,
            calendar_out_of_range=calendar_out_of_range,
            out_of_session=out_of_session,
            invalid_contract_expiry=(
                ~expiry_diagnostics.row_valid
                if expiry_diagnostics.enabled
                else pd.Series(False, index=frame.index, dtype=bool)
            ),
            invalid_contract_lot=(
                ~lot_diagnostics.row_valid
                if lot_diagnostics.enabled
                else pd.Series(False, index=frame.index, dtype=bool)
            ),
            unparseable_contract_expiry=(
                ~horizon_diagnostics.row_parseable
            ),
            expired_contract=horizon_diagnostics.row_expired,
            exact_duplicate_contract=(
                key_diagnostics.row_exact_duplicate
            ),
            conflicting_contract=key_diagnostics.row_conflicting,
            off_tick_price=frame["off_tick_price"],
            wide_spread=frame["wide_spread"],
        ),
    )


def write_diagnostics(result: DiagnosticResult, output_dir: str | Path) -> DiagnosticResult:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.summary.to_csv(out / "diagnostic_summary.csv", index=False)
    result.issues.to_csv(out / "diagnostic_issues.csv", index=False)
    return DiagnosticResult(result.summary, result.issues, out)


def _tick_issues(
    frame: pd.DataFrame,
    *,
    nonmonotonic: pd.Series,
    non_trading_days: pd.Series,
    calendar_closed: pd.Series,
    calendar_out_of_range: pd.Series,
    out_of_session: pd.Series,
    invalid_trade: pd.Series,
    off_tick_price: pd.Series,
    wide_spread: pd.Series,
) -> pd.DataFrame:
    rows = []
    checks = {
        "nonmonotonic_ts": nonmonotonic,
        "crossed_quote": frame["ask"] < frame["bid"],
        "nonpositive_quote": (frame["bid"] <= 0) | (frame["ask"] <= 0),
        "nonpositive_depth": (frame["bid_qty"] <= 0) | (frame["ask_qty"] <= 0),
        "invalid_trade": invalid_trade,
        "off_tick_price": off_tick_price,
        "wide_spread": wide_spread,
        "calendar_closed": calendar_closed,
        "calendar_out_of_range": calendar_out_of_range,
        "non_trading_day": non_trading_days
        & ~calendar_closed
        & ~calendar_out_of_range,
        "out_of_session": out_of_session,
    }
    for issue, mask in checks.items():
        for idx in frame.index[mask]:
            rows.append({"row_index": int(idx), "ts": int(frame.loc[idx, "ts"]), "issue": issue})
    return pd.DataFrame(rows, columns=["row_index", "ts", "issue"])


def _invalid_trade_mask(frame: pd.DataFrame) -> pd.Series:
    invalid = pd.Series(False, index=frame.index, dtype=bool)
    if "last" in frame.columns:
        last = pd.to_numeric(frame["last"], errors="coerce")
        invalid |= frame["last"].notna() & last.le(0)
    if "last_qty" in frame.columns:
        last_qty = pd.to_numeric(frame["last_qty"], errors="coerce")
        invalid |= frame["last_qty"].notna() & last_qty.lt(0)
    return invalid


def _off_tick_price_mask(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    *,
    tick_size: float | None,
) -> pd.Series:
    off_tick = pd.Series(False, index=frame.index, dtype=bool)
    if tick_size is None:
        return off_tick
    for column in columns:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        finite = values.notna() & np.isfinite(values)
        scaled = values / float(tick_size)
        on_grid = pd.Series(
            np.isclose(
                scaled,
                np.rint(scaled),
                rtol=0.0,
                atol=PRICE_GRID_ATOL_TICKS,
                equal_nan=False,
            ),
            index=frame.index,
            dtype=bool,
        )
        off_tick |= finite & ~on_grid
    return off_tick


def _off_grid_value_mask(
    values: pd.Series,
    *,
    step: float | None,
) -> pd.Series:
    off_grid = pd.Series(False, index=values.index, dtype=bool)
    if step is None:
        return off_grid
    numeric = pd.to_numeric(values, errors="coerce")
    finite = numeric.notna() & np.isfinite(numeric)
    scaled = numeric / float(step)
    on_grid = pd.Series(
        np.isclose(
            scaled,
            np.rint(scaled),
            rtol=0.0,
            atol=PRICE_GRID_ATOL_TICKS,
            equal_nan=False,
        ),
        index=values.index,
        dtype=bool,
    )
    return finite & ~on_grid


def _wide_spread_mask(
    spread_ticks: pd.Series,
    *,
    max_quote_spread_ticks: float | None,
) -> pd.Series:
    wide = pd.Series(False, index=spread_ticks.index, dtype=bool)
    if max_quote_spread_ticks is None:
        return wide
    numeric = pd.to_numeric(spread_ticks, errors="coerce")
    finite = numeric.notna() & np.isfinite(numeric)
    return finite & (
        numeric
        > float(max_quote_spread_ticks) + PRICE_GRID_ATOL_TICKS
    )


def _validate_tick_size(tick_size: float | None) -> None:
    if tick_size is None:
        return
    value = float(tick_size)
    if not np.isfinite(value) or value <= 0:
        raise ValueError("tick_size must be positive and finite")


def _validate_quote_spread_limit(
    *,
    tick_size: float | None,
    max_quote_spread_ticks: float | None,
) -> None:
    if max_quote_spread_ticks is None:
        return
    value = float(max_quote_spread_ticks)
    if not np.isfinite(value) or value < 0:
        raise ValueError(
            "max_quote_spread_ticks must be non-negative and finite"
        )
    if tick_size is None:
        raise ValueError(
            "tick_size is required when max_quote_spread_ticks is set"
        )


def _validate_strike_step(strike_step: float | None) -> None:
    if strike_step is None:
        return
    value = float(strike_step)
    if not np.isfinite(value) or value <= 0:
        raise ValueError("strike_step must be positive and finite")


def _chain_issues(
    frame: pd.DataFrame,
    *,
    nonmonotonic: pd.Series,
    nonpositive_strike: pd.Series,
    off_grid_strike: pd.Series,
    non_trading_days: pd.Series,
    calendar_closed: pd.Series,
    calendar_out_of_range: pd.Series,
    out_of_session: pd.Series,
    invalid_contract_expiry: pd.Series,
    invalid_contract_lot: pd.Series,
    unparseable_contract_expiry: pd.Series,
    expired_contract: pd.Series,
    exact_duplicate_contract: pd.Series,
    conflicting_contract: pd.Series,
    off_tick_price: pd.Series,
    wide_spread: pd.Series,
) -> pd.DataFrame:
    rows = []
    checks = {
        "nonmonotonic_ts": nonmonotonic,
        "nonpositive_strike": nonpositive_strike,
        "off_grid_strike": off_grid_strike,
        "crossed_quote": (frame["call_ask"] < frame["call_bid"]) | (frame["put_ask"] < frame["put_bid"]),
        "nonpositive_quote": (frame["call_bid"] <= 0)
        | (frame["call_ask"] <= 0)
        | (frame["put_bid"] <= 0)
        | (frame["put_ask"] <= 0),
        "nonpositive_depth": (frame["call_bid_qty"] <= 0)
        | (frame["call_ask_qty"] <= 0)
        | (frame["put_bid_qty"] <= 0)
        | (frame["put_ask_qty"] <= 0),
        "off_tick_price": off_tick_price,
        "wide_spread": wide_spread,
        "calendar_closed": calendar_closed,
        "calendar_out_of_range": calendar_out_of_range,
        "non_trading_day": non_trading_days
        & ~calendar_closed
        & ~calendar_out_of_range,
        "out_of_session": out_of_session,
        "unparseable_contract_expiry": unparseable_contract_expiry,
        "expired_contract_observation": expired_contract,
        "duplicate_contract_observation": exact_duplicate_contract,
        "conflicting_contract_observation": conflicting_contract,
        "invalid_contract_expiry": invalid_contract_expiry,
        "invalid_contract_lot_size": invalid_contract_lot,
    }
    for issue, mask in checks.items():
        for idx in frame.index[mask]:
            rows.append(
                {
                    "row_index": int(idx),
                    "ts": int(frame.loc[idx, "ts"]),
                    "expiry": frame.loc[idx, "expiry"],
                    "strike": float(frame.loc[idx, "strike"]),
                    "issue": issue,
                }
            )
    return pd.DataFrame(rows, columns=["row_index", "ts", "expiry", "strike", "issue"])


def _contract_expiry_diagnostics(
    expiries: pd.Series,
    *,
    cycle: str | None,
    market_calendar: MarketCalendar | None,
) -> _ContractExpiryDiagnostics:
    if cycle is None or not str(cycle).strip():
        return _ContractExpiryDiagnostics(
            enabled=False,
            cycle="",
            rule=None,
            validations={},
            row_valid=pd.Series(True, index=expiries.index, dtype=bool),
            row_covered=pd.Series(True, index=expiries.index, dtype=bool),
        )
    if market_calendar is None:
        raise ValueError(
            "market_calendar is required when contract expiry validation is enabled"
        )
    rule = load_nse_fo_expiry_rule()
    validations: dict[str, NseFoExpiryValidation] = {}
    row_valid: list[bool] = []
    row_covered: list[bool] = []
    for value in expiries:
        key = _expiry_key(value)
        if key not in validations:
            validations[key] = validate_nse_fo_expiry(
                value,
                cycle=str(cycle),
                market_calendar=market_calendar,
                rule=rule,
            )
        validation = validations[key]
        row_valid.append(validation.valid)
        row_covered.append(validation.covered)
    return _ContractExpiryDiagnostics(
        enabled=True,
        cycle=str(cycle).strip().lower(),
        rule=rule,
        validations=validations,
        row_valid=pd.Series(row_valid, index=expiries.index, dtype=bool),
        row_covered=pd.Series(
            row_covered,
            index=expiries.index,
            dtype=bool,
        ),
    )


def _contract_expiry_summary(
    diagnostics: _ContractExpiryDiagnostics,
) -> dict[str, object]:
    if not diagnostics.enabled or diagnostics.rule is None:
        return {
            "contract_expiry_validation_enabled": False,
            "contract_expiry_cycle": "",
            "invalid_contract_expiry_rows": 0,
            "uncovered_contract_expiry_rows": 0,
            "invalid_contract_expiries": 0,
            "validated_contract_expiries": 0,
            "contract_expiry_rule_id": "",
            "contract_expiry_rule_effective_from": "",
            "contract_expiry_rule_publisher": "",
            "contract_expiry_rule_source_url": "",
            "contract_expiry_rule_circular_id": "",
            "contract_expiry_rule_circular_date": "",
            "contract_expiry_rule_path": "",
            "contract_expiry_rule_sha256": "",
            "contract_expiry_authority_source_path": "",
            "contract_expiry_authority_source_sha256": "",
        }
    return {
        "contract_expiry_validation_enabled": True,
        "contract_expiry_cycle": diagnostics.cycle,
        "invalid_contract_expiry_rows": int((~diagnostics.row_valid).sum()),
        "uncovered_contract_expiry_rows": int(
            (~diagnostics.row_covered).sum()
        ),
        "invalid_contract_expiries": int(
            sum(
                not validation.valid
                for validation in diagnostics.validations.values()
            )
        ),
        "validated_contract_expiries": int(len(diagnostics.validations)),
        **expiry_rule_summary(diagnostics.rule),
    }


def _contract_horizon_diagnostics(
    ts_ns: pd.Series,
    expiries: pd.Series,
    *,
    market: str,
) -> _ContractHorizonDiagnostics:
    timezone = get_market_profile(market).session.timezone
    observation_dates = (
        pd.to_datetime(ts_ns, unit="ns", utc=True, errors="coerce")
        .dt.tz_convert(timezone)
        .dt.date
    )
    expiry_dates = pd.Series(
        [_parse_contract_expiry_date(value) for value in expiries],
        index=expiries.index,
        dtype=object,
    )
    calendar_dte_days = pd.Series(
        [
            (
                float((expiry_date - observation_date).days)
                if expiry_date is not None
                and observation_date is not None
                and not pd.isna(observation_date)
                else np.nan
            )
            for observation_date, expiry_date in zip(
                observation_dates,
                expiry_dates,
            )
        ],
        index=expiries.index,
        dtype="float64",
    )
    row_parseable = expiry_dates.notna().astype(bool)
    row_expired = calendar_dte_days.lt(0).fillna(False).astype(bool)
    row_zero_dte = calendar_dte_days.eq(0).fillna(False).astype(bool)
    return _ContractHorizonDiagnostics(
        market_timezone=timezone,
        observation_dates=observation_dates,
        expiry_dates=expiry_dates,
        calendar_dte_days=calendar_dte_days,
        row_parseable=row_parseable,
        row_expired=row_expired,
        row_zero_dte=row_zero_dte,
    )


def _contract_horizon_summary(
    diagnostics: _ContractHorizonDiagnostics,
) -> dict[str, object]:
    dte = diagnostics.calendar_dte_days.dropna()
    return {
        "contract_horizon_validation_enabled": True,
        "contract_horizon_market_timezone": diagnostics.market_timezone,
        "parseable_contract_expiry_rows": int(
            diagnostics.row_parseable.sum()
        ),
        "unparseable_contract_expiry_rows": int(
            (~diagnostics.row_parseable).sum()
        ),
        "expired_contract_rows": int(diagnostics.row_expired.sum()),
        "zero_dte_rows": int(diagnostics.row_zero_dte.sum()),
        "min_calendar_dte_days": float(dte.min()) if len(dte) else np.nan,
        "median_calendar_dte_days": (
            float(dte.median()) if len(dte) else np.nan
        ),
        "max_calendar_dte_days": float(dte.max()) if len(dte) else np.nan,
    }


def _contract_key_diagnostics(
    frame: pd.DataFrame,
) -> _ContractKeyDiagnostics:
    row_duplicate = frame.duplicated(
        CONTRACT_KEY_COLUMNS,
        keep=False,
    )
    row_duplicate_excess = frame.duplicated(
        CONTRACT_KEY_COLUMNS,
        keep="first",
    )
    row_conflicting = pd.Series(False, index=frame.index, dtype=bool)
    if bool(row_duplicate.any()):
        state_variants = (
            frame.groupby(
                CONTRACT_KEY_COLUMNS,
                dropna=False,
                sort=False,
            )[CONTRACT_STATE_COLUMNS]
            .nunique(dropna=False)
            .gt(1)
            .any(axis=1)
        )
        conflicting_keys = state_variants.index[state_variants]
        row_keys = pd.MultiIndex.from_frame(
            frame[CONTRACT_KEY_COLUMNS]
        )
        row_conflicting = pd.Series(
            row_keys.isin(conflicting_keys),
            index=frame.index,
            dtype=bool,
        )
    row_conflicting &= row_duplicate
    row_exact_duplicate = row_duplicate & ~row_conflicting
    first_key_row = ~frame.duplicated(
        CONTRACT_KEY_COLUMNS,
        keep="first",
    )
    duplicate_group_head = row_duplicate & first_key_row
    exact_duplicate_group_head = row_exact_duplicate & first_key_row
    conflicting_group_head = row_conflicting & first_key_row
    return _ContractKeyDiagnostics(
        row_duplicate=row_duplicate.astype(bool),
        row_duplicate_excess=row_duplicate_excess.astype(bool),
        row_exact_duplicate=row_exact_duplicate.astype(bool),
        row_conflicting=row_conflicting.astype(bool),
        duplicate_group_head=duplicate_group_head.astype(bool),
        exact_duplicate_group_head=exact_duplicate_group_head.astype(bool),
        conflicting_group_head=conflicting_group_head.astype(bool),
    )


def _contract_key_summary(
    diagnostics: _ContractKeyDiagnostics,
) -> dict[str, object]:
    return {
        "contract_key_validation_enabled": True,
        "duplicate_contract_key_rows": int(
            diagnostics.row_duplicate.sum()
        ),
        "duplicate_contract_key_excess_rows": int(
            diagnostics.row_duplicate_excess.sum()
        ),
        "duplicate_contract_key_groups": int(
            diagnostics.duplicate_group_head.sum()
        ),
        "exact_duplicate_contract_key_rows": int(
            diagnostics.row_exact_duplicate.sum()
        ),
        "exact_duplicate_contract_key_groups": int(
            diagnostics.exact_duplicate_group_head.sum()
        ),
        "conflicting_contract_key_rows": int(
            diagnostics.row_conflicting.sum()
        ),
        "conflicting_contract_key_groups": int(
            diagnostics.conflicting_group_head.sum()
        ),
    }


def _chain_snapshot_diagnostics(
    frame: pd.DataFrame,
) -> _ChainSnapshotDiagnostics:
    snapshots = (
        frame.groupby(
            ["ts", "expiry"],
            dropna=False,
            sort=False,
        )
        .agg(
            snapshot_rows=("strike", "size"),
            snapshot_strikes=("strike", "nunique"),
        )
        .reset_index()
        .sort_values(["expiry", "ts"], kind="mergesort")
        .reset_index(drop=True)
    )
    if snapshots.empty:
        snapshots["snapshot_gap_ns"] = pd.Series(dtype="float64")
    else:
        snapshots["snapshot_gap_ns"] = snapshots.groupby(
            "expiry",
            dropna=False,
            sort=False,
        )["ts"].diff()
    rows: list[dict[str, object]] = []
    for expiry, group in snapshots.groupby(
        "expiry",
        dropna=False,
        sort=False,
    ):
        strikes = group["snapshot_strikes"]
        gaps = group["snapshot_gap_ns"].dropna()
        rows.append(
            {
                "expiry": expiry,
                "expiry_snapshots": int(len(group)),
                "min_snapshot_strikes": int(strikes.min()),
                "median_snapshot_strikes": float(strikes.median()),
                "max_snapshot_strikes": int(strikes.max()),
                "snapshot_gap_observations": int(len(gaps)),
                "median_snapshot_gap_ns": (
                    float(gaps.median()) if len(gaps) else 0.0
                ),
                "p99_snapshot_gap_ns": (
                    float(gaps.quantile(0.99)) if len(gaps) else 0.0
                ),
                "max_snapshot_gap_ns": (
                    float(gaps.max()) if len(gaps) else 0.0
                ),
            }
        )
    by_expiry = pd.DataFrame(
        rows,
        columns=[
            "expiry",
            "expiry_snapshots",
            "min_snapshot_strikes",
            "median_snapshot_strikes",
            "max_snapshot_strikes",
            "snapshot_gap_observations",
            "median_snapshot_gap_ns",
            "p99_snapshot_gap_ns",
            "max_snapshot_gap_ns",
        ],
    )
    return _ChainSnapshotDiagnostics(
        snapshots=snapshots,
        by_expiry=by_expiry,
    )


def _chain_snapshot_summary(
    diagnostics: _ChainSnapshotDiagnostics,
) -> dict[str, object]:
    snapshots = diagnostics.snapshots
    by_expiry = diagnostics.by_expiry
    strikes = snapshots["snapshot_strikes"]
    gaps = snapshots["snapshot_gap_ns"].dropna()
    expiry_snapshot_counts = by_expiry["expiry_snapshots"]
    return {
        "chain_snapshot_validation_enabled": True,
        "observation_timestamps": int(snapshots["ts"].nunique()),
        "expiry_snapshots": int(len(snapshots)),
        "min_snapshots_per_expiry": (
            int(expiry_snapshot_counts.min())
            if len(expiry_snapshot_counts)
            else 0
        ),
        "median_snapshots_per_expiry": (
            float(expiry_snapshot_counts.median())
            if len(expiry_snapshot_counts)
            else 0.0
        ),
        "max_snapshots_per_expiry": (
            int(expiry_snapshot_counts.max())
            if len(expiry_snapshot_counts)
            else 0
        ),
        "min_snapshot_strikes": (
            int(strikes.min()) if len(strikes) else 0
        ),
        "median_snapshot_strikes": (
            float(strikes.median()) if len(strikes) else 0.0
        ),
        "max_snapshot_strikes": (
            int(strikes.max()) if len(strikes) else 0
        ),
        "snapshot_gap_observations": int(len(gaps)),
        "median_snapshot_gap_ns": (
            float(gaps.median()) if len(gaps) else 0.0
        ),
        "p99_snapshot_gap_ns": (
            float(gaps.quantile(0.99)) if len(gaps) else 0.0
        ),
        "max_snapshot_gap_ns": (
            float(gaps.max()) if len(gaps) else 0.0
        ),
    }


def _parse_contract_expiry_date(value: object) -> date | None:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, np.datetime64):
        return pd.Timestamp(value).date()
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def _contract_lot_diagnostics(
    expiries: pd.Series,
    *,
    underlying: str | None,
    lot_size: int | None,
    cycle: str | None,
) -> _ContractLotDiagnostics:
    if underlying is None and lot_size is None:
        return _ContractLotDiagnostics(
            enabled=False,
            underlying="",
            lot_size="",
            cycle="",
            rule=None,
            validations={},
            row_valid=pd.Series(True, index=expiries.index, dtype=bool),
            row_covered=pd.Series(True, index=expiries.index, dtype=bool),
        )
    if underlying is None or not str(underlying).strip():
        raise ValueError(
            "underlying is required when contract lot-size validation is enabled"
        )
    if lot_size is None:
        raise ValueError(
            "lot_size is required when contract lot-size validation is enabled"
        )
    if cycle is None or not str(cycle).strip():
        raise ValueError(
            "expiry_cycle is required when contract lot-size validation is enabled"
        )
    rule = load_nse_index_lot_rule()
    validations: dict[str, NseIndexLotValidation] = {}
    row_valid: list[bool] = []
    row_covered: list[bool] = []
    for value in expiries:
        key = _expiry_key(value)
        if key not in validations:
            validations[key] = validate_nse_index_lot_size(
                underlying,
                value,
                lot_size,
                cycle=str(cycle),
                rule=rule,
            )
        validation = validations[key]
        row_valid.append(validation.valid)
        row_covered.append(validation.covered)
    return _ContractLotDiagnostics(
        enabled=True,
        underlying=str(underlying).strip().upper(),
        lot_size=lot_size,
        cycle=str(cycle).strip().lower(),
        rule=rule,
        validations=validations,
        row_valid=pd.Series(row_valid, index=expiries.index, dtype=bool),
        row_covered=pd.Series(
            row_covered,
            index=expiries.index,
            dtype=bool,
        ),
    )


def _contract_lot_summary(
    diagnostics: _ContractLotDiagnostics,
) -> dict[str, object]:
    if not diagnostics.enabled or diagnostics.rule is None:
        return {
            "contract_lot_validation_enabled": False,
            "contract_lot_underlying": "",
            "contract_lot_size": 0,
            "contract_lot_cycle": "",
            "invalid_contract_lot_rows": 0,
            "uncovered_contract_lot_rows": 0,
            "invalid_contract_lot_expiries": 0,
            "validated_contract_lot_expiries": 0,
            "contract_lot_rule_id": "",
            "contract_lot_rule_publisher": "",
            "contract_lot_rule_source_url": "",
            "contract_lot_rule_circular_id": "",
            "contract_lot_rule_circular_date": "",
            "contract_lot_rule_path": "",
            "contract_lot_rule_sha256": "",
            "contract_lot_authority_source_path": "",
            "contract_lot_authority_source_sha256": "",
            "contract_lot_snapshot_source_url": "",
            "contract_lot_snapshot_as_of": "",
            "contract_lot_snapshot_path": "",
            "contract_lot_snapshot_sha256": "",
        }
    return {
        "contract_lot_validation_enabled": True,
        "contract_lot_underlying": diagnostics.underlying,
        "contract_lot_size": diagnostics.lot_size,
        "contract_lot_cycle": diagnostics.cycle,
        "invalid_contract_lot_rows": int((~diagnostics.row_valid).sum()),
        "uncovered_contract_lot_rows": int(
            (~diagnostics.row_covered).sum()
        ),
        "invalid_contract_lot_expiries": int(
            sum(
                not validation.valid
                for validation in diagnostics.validations.values()
            )
        ),
        "validated_contract_lot_expiries": int(
            len(diagnostics.validations)
        ),
        **index_lot_rule_summary(diagnostics.rule),
    }


def _expiry_key(value: object) -> str:
    try:
        if pd.isna(value):
            return "<null>"
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return str(value).strip()


def _optional_date(value) -> str:
    return "" if value is None else value.isoformat()


def _session_issue_masks(
    ts_ns: pd.Series,
    *,
    market: str,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    calendar = resolve_market_calendar(market_calendar, market=market)
    trading_days = trading_day_mask(
        ts_ns,
        market=market,
        market_calendar=calendar,
    )
    session_times = trading_session_time_mask(
        ts_ns,
        market=market,
        market_calendar=calendar,
    )
    calendar_closed = calendar_closed_mask(
        ts_ns,
        market=market,
        market_calendar=calendar,
    )
    calendar_out_of_range = calendar_out_of_range_mask(
        ts_ns,
        market=market,
        market_calendar=calendar,
    )
    return (
        ~trading_days,
        calendar_closed,
        calendar_out_of_range,
        trading_days & ~session_times,
    )


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
