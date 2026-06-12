from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


SUMMARY_FILES = {
    "schema_audit": "adapter_schema_summary.csv",
    "mapped_data": "mapped_data_summary.csv",
    "tick_diagnostics": "diagnostic_summary.csv",
    "chain_diagnostics": "diagnostic_summary.csv",
    "market_profile": "market_profile_summary.csv",
    "instrument_metadata": "instrument_metadata_summary.csv",
}


@dataclass(frozen=True)
class DataReadinessThresholds:
    require_schema_audit: bool = False
    require_mapped_data: bool = False
    require_tick_diagnostics: bool = True
    require_chain_diagnostics: bool = False
    require_market_profile: bool = False
    require_explicit_fee_model: bool = False
    require_instrument_metadata: bool = False
    min_tick_rows: int = 1
    min_chain_rows: int = 1
    min_chain_expiries: int = 1
    min_chain_strikes: int = 1
    max_nonmonotonic_rows: int = 0
    max_crossed_quote_rows: int = 0
    max_nonpositive_quote_rows: int = 0
    max_nonpositive_depth_rows: int = 0
    max_out_of_session_rows: int = 0
    max_tick_p99_gap_ns: float | None = None
    max_tick_median_spread_ticks: float | None = None
    max_chain_median_spread_ticks: float | None = None


@dataclass(frozen=True)
class DataReadinessReport:
    items: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_data_readiness(
    *,
    schema_audit_summary: pd.DataFrame | None = None,
    mapped_data_summary: pd.DataFrame | None = None,
    tick_diagnostic_summary: pd.DataFrame | None = None,
    chain_diagnostic_summary: pd.DataFrame | None = None,
    market_profile_summary: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    thresholds: DataReadinessThresholds | None = None,
) -> DataReadinessReport:
    thresholds = thresholds or DataReadinessThresholds()
    _validate_thresholds(thresholds)
    summaries = {
        "schema_audit": _optional_frame(schema_audit_summary),
        "mapped_data": _optional_frame(mapped_data_summary),
        "tick_diagnostics": _optional_frame(tick_diagnostic_summary),
        "chain_diagnostics": _optional_frame(chain_diagnostic_summary),
        "market_profile": _optional_frame(market_profile_summary),
        "instrument_metadata": _optional_frame(instrument_metadata_summary),
    }
    items = _items(summaries, thresholds)
    checks = _checks(summaries, items, thresholds)
    summary = _summary(items, checks, thresholds)
    return DataReadinessReport(items=items, checks=checks, summary=summary)


def write_data_readiness_report(
    *,
    output_dir: str | Path,
    schema_audit_dir: str | Path | None = None,
    mapped_data_dir: str | Path | None = None,
    tick_diagnostics_dir: str | Path | None = None,
    chain_diagnostics_dir: str | Path | None = None,
    market_profile_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    thresholds: DataReadinessThresholds | None = None,
) -> DataReadinessReport:
    thresholds = thresholds or DataReadinessThresholds()
    _validate_thresholds(thresholds)
    report = evaluate_data_readiness(
        schema_audit_summary=_read_optional_summary(schema_audit_dir, "schema_audit"),
        mapped_data_summary=_read_optional_summary(mapped_data_dir, "mapped_data"),
        tick_diagnostic_summary=_read_optional_summary(tick_diagnostics_dir, "tick_diagnostics"),
        chain_diagnostic_summary=_read_optional_summary(chain_diagnostics_dir, "chain_diagnostics"),
        market_profile_summary=_read_optional_summary(market_profile_dir, "market_profile"),
        instrument_metadata_summary=_read_optional_summary(instrument_metadata_dir, "instrument_metadata"),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.items.to_csv(out / "data_readiness_items.csv", index=False)
    report.checks.to_csv(out / "data_readiness_checks.csv", index=False)
    report.summary.to_csv(out / "data_readiness_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="data_readiness",
        parameters={"thresholds": asdict(thresholds)},
        inputs={
            "schema_audit": schema_audit_dir,
            "mapped_data": mapped_data_dir,
            "tick_diagnostics": tick_diagnostics_dir,
            "chain_diagnostics": chain_diagnostics_dir,
            "market_profile": market_profile_dir,
            "instrument_metadata": instrument_metadata_dir,
        },
    )
    return DataReadinessReport(report.items, report.checks, report.summary, out)


def _items(summaries: dict[str, pd.DataFrame], thresholds: DataReadinessThresholds) -> pd.DataFrame:
    return pd.DataFrame([_item(name, frame, thresholds) for name, frame in summaries.items()])


def _item(component: str, frame: pd.DataFrame, thresholds: DataReadinessThresholds) -> dict[str, Any]:
    provided = not frame.empty
    required = _component_required(component, thresholds)
    ready = _component_ready(component, frame) if provided else False
    row = _overall_row(frame) if provided else pd.Series(dtype=object)
    return {
        "component": component,
        "required": required,
        "provided": provided,
        "ready": ready,
        "rows": int(_number(row, "rows", fallback=_number(row, "output_rows", fallback=0.0))),
        "failed_checks": int(_number(row, "failed_mappings", fallback=0.0)),
        "source_file": SUMMARY_FILES[component],
        "recommendation": _component_recommendation(component, provided, ready, required),
    }


def _checks(
    summaries: dict[str, pd.DataFrame],
    items: pd.DataFrame,
    thresholds: DataReadinessThresholds,
) -> pd.DataFrame:
    checks = []
    for row in items.itertuples(index=False):
        if bool(row.required):
            checks.append(
                _check(
                    f"{row.component}_provided",
                    bool(row.provided),
                    "is",
                    True,
                    bool(row.provided),
                    f"{row.component} summary is required but missing",
                )
            )
        if bool(row.required) or bool(row.provided):
            checks.append(
                _check(
                    f"{row.component}_ready",
                    bool(row.ready),
                    "is",
                    True,
                    bool(row.ready),
                    f"{row.component} is not ready",
                )
            )

    if not summaries["tick_diagnostics"].empty:
        checks.extend(_tick_checks(summaries["tick_diagnostics"], thresholds))
    if not summaries["chain_diagnostics"].empty:
        checks.extend(_chain_checks(summaries["chain_diagnostics"], thresholds))
    if not summaries["market_profile"].empty and thresholds.require_explicit_fee_model:
        row = summaries["market_profile"].iloc[0]
        explicit_fee = _to_bool(row.get("explicit_fee_model", False))
        checks.append(
            _check(
                "explicit_fee_model",
                explicit_fee,
                "is",
                True,
                explicit_fee,
                "market profile does not include explicit fee assumptions",
            )
        )
    return pd.DataFrame(checks)


def _tick_checks(summary: pd.DataFrame, thresholds: DataReadinessThresholds) -> list[dict[str, Any]]:
    row = summary.iloc[0]
    checks = [
        _threshold_check("tick_rows", _number(row, "rows"), ">=", thresholds.min_tick_rows),
        _threshold_check("tick_nonmonotonic_rows", _number(row, "nonmonotonic_rows"), "<=", thresholds.max_nonmonotonic_rows),
        _threshold_check("tick_crossed_quote_rows", _number(row, "crossed_quote_rows"), "<=", thresholds.max_crossed_quote_rows),
        _threshold_check(
            "tick_nonpositive_quote_rows",
            _number(row, "nonpositive_quote_rows"),
            "<=",
            thresholds.max_nonpositive_quote_rows,
        ),
        _threshold_check(
            "tick_nonpositive_depth_rows",
            _number(row, "nonpositive_depth_rows"),
            "<=",
            thresholds.max_nonpositive_depth_rows,
        ),
        _threshold_check("tick_out_of_session_rows", _number(row, "out_of_session_rows"), "<=", thresholds.max_out_of_session_rows),
    ]
    if thresholds.max_tick_p99_gap_ns is not None:
        checks.append(_threshold_check("tick_p99_gap_ns", _number(row, "p99_gap_ns"), "<=", thresholds.max_tick_p99_gap_ns))
    if thresholds.max_tick_median_spread_ticks is not None:
        checks.append(
            _threshold_check(
                "tick_median_spread_ticks",
                _number(row, "median_spread_ticks"),
                "<=",
                thresholds.max_tick_median_spread_ticks,
            )
        )
    return checks


def _chain_checks(summary: pd.DataFrame, thresholds: DataReadinessThresholds) -> list[dict[str, Any]]:
    row = _overall_row(summary)
    checks = [
        _threshold_check("chain_rows", _number(row, "rows"), ">=", thresholds.min_chain_rows),
        _threshold_check("chain_expiries", _number(row, "expiries"), ">=", thresholds.min_chain_expiries),
        _threshold_check("chain_strikes", _number(row, "strikes"), ">=", thresholds.min_chain_strikes),
        _threshold_check("chain_crossed_quote_rows", _number(row, "crossed_quote_rows"), "<=", thresholds.max_crossed_quote_rows),
        _threshold_check(
            "chain_nonpositive_quote_rows",
            _number(row, "nonpositive_quote_rows"),
            "<=",
            thresholds.max_nonpositive_quote_rows,
        ),
        _threshold_check(
            "chain_nonpositive_depth_rows",
            _number(row, "nonpositive_depth_rows"),
            "<=",
            thresholds.max_nonpositive_depth_rows,
        ),
        _threshold_check("chain_out_of_session_rows", _number(row, "out_of_session_rows"), "<=", thresholds.max_out_of_session_rows),
    ]
    if thresholds.max_chain_median_spread_ticks is not None:
        expiry_rows = summary.loc[summary.get("scope", "") == "expiry"] if "scope" in summary.columns else pd.DataFrame()
        call_spread = _max_number(expiry_rows, "median_call_spread_ticks")
        put_spread = _max_number(expiry_rows, "median_put_spread_ticks")
        checks.append(
            _threshold_check(
                "chain_median_spread_ticks",
                max(call_spread, put_spread),
                "<=",
                thresholds.max_chain_median_spread_ticks,
            )
        )
    return checks


def _summary(
    items: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: DataReadinessThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    required = items.loc[items["required"].astype(bool)] if not items.empty else pd.DataFrame()
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "components": int(len(items)),
                "required_components": int(len(required)),
                "provided_components": int(items["provided"].astype(bool).sum()) if not items.empty else 0,
                "ready_components": int(items["ready"].astype(bool).sum()) if not items.empty else 0,
                "failed_checks": failed,
                "require_explicit_fee_model": bool(thresholds.require_explicit_fee_model),
                "recommendation": "feed_strategy_research" if ready else "fix_data_readiness_gaps",
            }
        ]
    )


def _component_required(component: str, thresholds: DataReadinessThresholds) -> bool:
    return bool(
        {
            "schema_audit": thresholds.require_schema_audit,
            "mapped_data": thresholds.require_mapped_data,
            "tick_diagnostics": thresholds.require_tick_diagnostics,
            "chain_diagnostics": thresholds.require_chain_diagnostics,
            "market_profile": thresholds.require_market_profile,
            "instrument_metadata": thresholds.require_instrument_metadata,
        }[component]
    )


def _component_ready(component: str, frame: pd.DataFrame) -> bool:
    row = _overall_row(frame)
    if component == "schema_audit":
        return _to_bool(row.get("all_required_present", False))
    if component == "mapped_data":
        return _to_bool(row.get("ready", False))
    if component == "instrument_metadata":
        return _to_bool(row.get("passed", False))
    if component == "market_profile":
        return int(_number(row, "markets", fallback=0.0)) > 0
    if component in {"tick_diagnostics", "chain_diagnostics"}:
        return int(_number(row, "rows", fallback=0.0)) > 0
    return False


def _component_recommendation(component: str, provided: bool, ready: bool, required: bool) -> str:
    if not provided and required:
        return f"run_{component}"
    if not provided:
        return "optional_not_supplied"
    if not ready:
        return f"fix_{component}"
    return "accepted"


def _overall_row(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=object)
    if "scope" in frame.columns:
        overall = frame.loc[frame["scope"].astype(str) == "overall"]
        if not overall.empty:
            return overall.iloc[0]
    return frame.iloc[0]


def _read_optional_summary(path: str | Path | None, component: str) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / SUMMARY_FILES[component]
    if not candidate.exists():
        raise FileNotFoundError(f"{component} summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"{component} summary is empty: {candidate}")
    return frame


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float) or np.isnan(threshold_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} or threshold is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _max_number(frame: pd.DataFrame, column: str) -> float:
    if frame.empty or column not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.max(skipna=True)) if values.notna().any() else np.nan


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _validate_thresholds(thresholds: DataReadinessThresholds) -> None:
    for name in (
        "min_tick_rows",
        "min_chain_rows",
        "min_chain_expiries",
        "min_chain_strikes",
        "max_nonmonotonic_rows",
        "max_crossed_quote_rows",
        "max_nonpositive_quote_rows",
        "max_nonpositive_depth_rows",
        "max_out_of_session_rows",
    ):
        if getattr(thresholds, name) < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in ("max_tick_p99_gap_ns", "max_tick_median_spread_ticks", "max_chain_median_spread_ticks"):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
