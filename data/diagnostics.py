from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.loaders import (
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
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES


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


def tick_diagnostics(
    ticks: pd.DataFrame,
    *,
    tick_size: float | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
) -> DiagnosticResult:
    _require(ticks, TICK_REQUIRED, "ticks")
    calendar = resolve_market_calendar(market_calendar, market=market)
    frame = ticks.copy()
    frame["spread"] = frame["ask"] - frame["bid"]
    frame["mid"] = 0.5 * (frame["bid"] + frame["ask"])
    frame["depth"] = frame["bid_qty"] + frame["ask_qty"]
    if tick_size:
        frame["spread_ticks"] = frame["spread"] / tick_size
    else:
        frame["spread_ticks"] = np.nan
    gaps = frame["ts"].sort_values().diff().dropna()
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
                "nonmonotonic_rows": int((ticks["ts"].diff().fillna(0) < 0).sum()),
                "crossed_quote_rows": int((frame["ask"] < frame["bid"]).sum()),
                "nonpositive_quote_rows": int(((frame["bid"] <= 0) | (frame["ask"] <= 0)).sum()),
                "nonpositive_depth_rows": int(((frame["bid_qty"] <= 0) | (frame["ask_qty"] <= 0)).sum()),
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
            non_trading_days=non_trading_days,
            calendar_closed=calendar_closed,
            calendar_out_of_range=calendar_out_of_range,
            out_of_session=out_of_session,
        ),
    )


def chain_diagnostics(
    chain: pd.DataFrame,
    *,
    tick_size: float | None = None,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    market_calendar: MarketCalendar | str | Path | None = None,
    expiry_cycle: str | None = None,
    underlying: str | None = None,
    lot_size: int | None = None,
) -> DiagnosticResult:
    _require(chain, CHAIN_REQUIRED, "chain")
    calendar = resolve_market_calendar(market_calendar, market=market)
    frame = chain.copy()
    frame["call_spread"] = frame["call_ask"] - frame["call_bid"]
    frame["put_spread"] = frame["put_ask"] - frame["put_bid"]
    if tick_size:
        frame["call_spread_ticks"] = frame["call_spread"] / tick_size
        frame["put_spread_ticks"] = frame["put_spread"] / tick_size
    else:
        frame["call_spread_ticks"] = np.nan
        frame["put_spread_ticks"] = np.nan
    non_trading_days, calendar_closed, calendar_out_of_range, out_of_session = _session_issue_masks(
        frame["ts"],
        market=market,
        market_calendar=calendar,
    )
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
        )
        .reset_index()
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
    overall = pd.DataFrame(
        [
            {
                "market": market,
                **market_calendar_summary(calendar),
                **expiry_summary,
                **lot_summary,
                "rows": int(len(frame)),
                "expiries": int(frame["expiry"].nunique()),
                "strikes": int(frame["strike"].nunique()),
                "start_ts": int(frame["ts"].min()) if len(frame) else np.nan,
                "end_ts": int(frame["ts"].max()) if len(frame) else np.nan,
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
    non_trading_days: pd.Series,
    calendar_closed: pd.Series,
    calendar_out_of_range: pd.Series,
    out_of_session: pd.Series,
) -> pd.DataFrame:
    rows = []
    checks = {
        "nonmonotonic_ts": frame["ts"].diff().fillna(0) < 0,
        "crossed_quote": frame["ask"] < frame["bid"],
        "nonpositive_quote": (frame["bid"] <= 0) | (frame["ask"] <= 0),
        "nonpositive_depth": (frame["bid_qty"] <= 0) | (frame["ask_qty"] <= 0),
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


def _chain_issues(
    frame: pd.DataFrame,
    *,
    non_trading_days: pd.Series,
    calendar_closed: pd.Series,
    calendar_out_of_range: pd.Series,
    out_of_session: pd.Series,
    invalid_contract_expiry: pd.Series,
    invalid_contract_lot: pd.Series,
) -> pd.DataFrame:
    rows = []
    checks = {
        "crossed_quote": (frame["call_ask"] < frame["call_bid"]) | (frame["put_ask"] < frame["put_bid"]),
        "nonpositive_quote": (frame["call_bid"] <= 0)
        | (frame["call_ask"] <= 0)
        | (frame["put_bid"] <= 0)
        | (frame["put_ask"] <= 0),
        "nonpositive_depth": (frame["call_bid_qty"] <= 0)
        | (frame["call_ask_qty"] <= 0)
        | (frame["put_bid_qty"] <= 0)
        | (frame["put_ask_qty"] <= 0),
        "calendar_closed": calendar_closed,
        "calendar_out_of_range": calendar_out_of_range,
        "non_trading_day": non_trading_days
        & ~calendar_closed
        & ~calendar_out_of_range,
        "out_of_session": out_of_session,
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
