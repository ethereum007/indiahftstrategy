from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class RuntimeGuardReport:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def halted(self) -> bool:
        if self.summary.empty:
            return True
        return str(self.summary.iloc[0]["guard_action"]) == "halt"


def evaluate_runtime_guard(
    scaleup_config: dict[str, Any],
    telemetry: pd.DataFrame,
    *,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
) -> RuntimeGuardReport:
    if telemetry.empty:
        raise ValueError("runtime telemetry is empty")
    metrics = _metrics(
        scaleup_config,
        telemetry,
        as_of_ts_ns=as_of_ts_ns,
        max_telemetry_age_ns=max_telemetry_age_ns,
    )
    checks = _checks(metrics.iloc[0], scaleup_config)
    summary = _summary(metrics.iloc[0], checks)
    return RuntimeGuardReport(metrics=metrics, checks=checks, summary=summary)


def write_runtime_guard_report(
    *,
    scaleup_dir: str | Path,
    telemetry_path: str | Path,
    output_dir: str | Path,
    as_of_ts_ns: int | float | None = None,
    max_telemetry_age_ns: int | float | None = None,
) -> RuntimeGuardReport:
    scaleup_file = _scaleup_config_path(scaleup_dir)
    telemetry_file = _telemetry_path(telemetry_path)
    if not telemetry_file.exists():
        raise FileNotFoundError(f"runtime telemetry file not found: {telemetry_file}")
    scaleup_config = json.loads(scaleup_file.read_text(encoding="utf-8"))
    report = evaluate_runtime_guard(
        scaleup_config,
        pd.read_csv(telemetry_file),
        as_of_ts_ns=as_of_ts_ns,
        max_telemetry_age_ns=max_telemetry_age_ns,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "runtime_guard_metrics.csv", index=False)
    report.checks.to_csv(out / "runtime_guard_checks.csv", index=False)
    report.summary.to_csv(out / "runtime_guard_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="runtime_guard",
        parameters={
            "scaleup_ready": bool(scaleup_config.get("ready", False)),
            "as_of_ts_ns": as_of_ts_ns,
            "max_telemetry_age_ns": max_telemetry_age_ns,
        },
        inputs={"scaleup": scaleup_file, "telemetry": telemetry_file},
    )
    return RuntimeGuardReport(report.metrics, report.checks, report.summary, out)


def _metrics(
    scaleup_config: dict[str, Any],
    telemetry: pd.DataFrame,
    *,
    as_of_ts_ns: int | float | None,
    max_telemetry_age_ns: int | float | None,
) -> pd.DataFrame:
    latest = telemetry.iloc[-1]
    limits = scaleup_config.get("limits", {}) or {}
    kill_switches = scaleup_config.get("kill_switches", {}) or {}
    instrument_metadata = scaleup_config.get("instrument_metadata", {}) or {}
    metadata_min_coverage = _number_from(instrument_metadata, "min_parse_coverage")
    snapshot_ts_ns = _number(latest, "snapshot_ts_ns", fallback=_number(latest, "ts_ns"))
    guard_as_of_ts_ns = _first_number(as_of_ts_ns, _number(latest, "guard_as_of_ts_ns"), np.nan)
    telemetry_age_ns = guard_as_of_ts_ns - snapshot_ts_ns if not np.isnan(guard_as_of_ts_ns) and not np.isnan(snapshot_ts_ns) else np.nan
    max_age_ns = _first_number(max_telemetry_age_ns, _number_from(kill_switches, "max_telemetry_age_ns"), np.nan)
    return pd.DataFrame(
        [
            {
                "scaleup_ready": bool(scaleup_config.get("ready", False)),
                "target_mode": str(scaleup_config.get("target_mode", "")),
                "scenario_key": str(_value(latest, "scenario_key", scaleup_config.get("scenario_key", ""))),
                "expected_scenario_key": str(scaleup_config.get("scenario_key", "")),
                "adapter": str(_value(latest, "adapter", scaleup_config.get("adapter", ""))),
                "expected_adapter": str(scaleup_config.get("adapter", "")),
                "snapshot_count": int(len(telemetry)),
                "snapshot_ts_ns": snapshot_ts_ns,
                "guard_as_of_ts_ns": guard_as_of_ts_ns,
                "runtime_telemetry_age_ns": telemetry_age_ns,
                "max_telemetry_age_ns": max_age_ns,
                "orders_sent": _number(latest, "orders_sent", fallback=_number(latest, "orders")),
                "session_notional": _number(latest, "session_notional", fallback=_number(latest, "total_notional")),
                "realized_pnl": _number(latest, "realized_pnl", fallback=_number(latest, "net_pnl")),
                "open_order_count": _number(latest, "open_order_count"),
                "open_order_qty": _number(latest, "open_order_qty"),
                "gross_position_qty": _number(latest, "gross_position_qty"),
                "abs_net_position_qty": _number(latest, "abs_net_position_qty"),
                "total_failed_component_checks": _number(latest, "total_failed_component_checks"),
                "unmatched_fills": _number(latest, "unmatched_fills"),
                "mismatched_orders": _number(latest, "mismatched_orders"),
                "overfilled_orders": _number(latest, "overfilled_orders"),
                "worst_adverse_slippage": _number(
                    latest,
                    "worst_adverse_slippage",
                    fallback=_number(latest, "max_adverse_slippage"),
                ),
                "instrument_metadata_required": _bool_from(instrument_metadata, "required"),
                "scaleup_instrument_metadata_provided": _bool_from(instrument_metadata, "provided"),
                "scaleup_instrument_metadata_passed": _bool_from(instrument_metadata, "passed"),
                "scaleup_instrument_parse_coverage": _number_from(instrument_metadata, "parse_coverage"),
                "scaleup_unparsed_instruments": _number_from(instrument_metadata, "unparsed_instruments"),
                "runtime_instrument_metadata_provided": _bool_value(latest, "instrument_metadata_provided", fallback=False),
                "runtime_instrument_metadata_passed": _bool_value(latest, "instrument_metadata_passed", fallback=False),
                "runtime_instrument_parse_coverage": _number(latest, "instrument_parse_coverage"),
                "runtime_unparsed_instruments": _number(latest, "unparsed_instruments"),
                "min_instrument_parse_coverage": _number(
                    latest,
                    "min_instrument_parse_coverage",
                    fallback=metadata_min_coverage,
                ),
                "max_orders_per_session": _number_from(limits, "max_orders_per_session"),
                "max_notional_per_session": _number_from(limits, "max_notional_per_session"),
                "stop_loss": _number_from(limits, "stop_loss"),
                "max_total_failed_component_checks": _number_from(kill_switches, "max_total_failed_component_checks"),
                "max_total_unmatched_fills": _number_from(kill_switches, "max_total_unmatched_fills"),
                "max_total_mismatched_orders": _number_from(kill_switches, "max_total_mismatched_orders"),
                "max_total_overfilled_orders": _number_from(kill_switches, "max_total_overfilled_orders"),
                "max_worst_adverse_slippage": _number_from(kill_switches, "max_worst_adverse_slippage"),
                "max_open_order_count": _number_from(kill_switches, "max_open_order_count"),
                "max_open_order_qty": _number_from(kill_switches, "max_open_order_qty"),
                "max_gross_position_qty": _number_from(kill_switches, "max_gross_position_qty"),
                "max_abs_net_position_qty": _number_from(kill_switches, "max_abs_net_position_qty"),
            }
        ]
    )


def _checks(row: pd.Series, scaleup_config: dict[str, Any]) -> pd.DataFrame:
    checks = [
        _check(
            "scaleup_ready",
            bool(row["scaleup_ready"]),
            "is",
            True,
            bool(row["scaleup_ready"]),
            "scale-up config is not ready",
        ),
        _check(
            "scenario_match",
            row["scenario_key"],
            "==",
            row["expected_scenario_key"],
            str(row["scenario_key"]) == str(row["expected_scenario_key"]),
            "telemetry scenario does not match scale-up config",
        ),
        _check(
            "adapter_match",
            row["adapter"],
            "==",
            row["expected_adapter"],
            str(row["adapter"]) == str(row["expected_adapter"]),
            "telemetry adapter does not match scale-up config",
        ),
        _threshold_check("orders_sent", row["orders_sent"], "<=", row["max_orders_per_session"]),
        _threshold_check("session_notional", row["session_notional"], "<=", row["max_notional_per_session"]),
        _threshold_check(
            "total_failed_component_checks",
            row["total_failed_component_checks"],
            "<=",
            row["max_total_failed_component_checks"],
        ),
        _threshold_check("unmatched_fills", row["unmatched_fills"], "<=", row["max_total_unmatched_fills"]),
        _threshold_check("mismatched_orders", row["mismatched_orders"], "<=", row["max_total_mismatched_orders"]),
        _threshold_check("overfilled_orders", row["overfilled_orders"], "<=", row["max_total_overfilled_orders"]),
    ]
    if not pd.isna(row["stop_loss"]):
        checks.append(_threshold_check("realized_pnl", row["realized_pnl"], ">=", -abs(float(row["stop_loss"]))))
    if not pd.isna(row["max_worst_adverse_slippage"]):
        checks.append(
            _threshold_check(
                "worst_adverse_slippage",
                row["worst_adverse_slippage"],
                "<=",
                row["max_worst_adverse_slippage"],
            )
        )
    for value_column, threshold_column in (
        ("open_order_count", "max_open_order_count"),
        ("open_order_qty", "max_open_order_qty"),
        ("gross_position_qty", "max_gross_position_qty"),
        ("abs_net_position_qty", "max_abs_net_position_qty"),
    ):
        if not pd.isna(row[threshold_column]):
            checks.append(_threshold_check(value_column, row[value_column], "<=", row[threshold_column]))
    if not pd.isna(row["max_telemetry_age_ns"]):
        checks.extend(
            [
                _threshold_check(
                    "runtime_telemetry_age_nonnegative",
                    row["runtime_telemetry_age_ns"],
                    ">=",
                    0,
                ),
                _threshold_check(
                    "runtime_telemetry_age_ns",
                    row["runtime_telemetry_age_ns"],
                    "<=",
                    row["max_telemetry_age_ns"],
                ),
            ]
        )
    metadata_required = bool(row["instrument_metadata_required"])
    metadata_provided = bool(row["runtime_instrument_metadata_provided"])
    if metadata_required:
        checks.extend(
            [
                _check(
                    "scaleup_instrument_metadata_provided",
                    bool(row["scaleup_instrument_metadata_provided"]),
                    "is",
                    True,
                    bool(row["scaleup_instrument_metadata_provided"]),
                    "scale-up config requires instrument metadata but does not record supplied evidence",
                ),
                _check(
                    "scaleup_instrument_metadata_passed",
                    bool(row["scaleup_instrument_metadata_passed"]),
                    "is",
                    True,
                    bool(row["scaleup_instrument_metadata_passed"]),
                    "scale-up config requires instrument metadata but the gate did not pass",
                ),
                _check(
                    "runtime_instrument_metadata_provided",
                    metadata_provided,
                    "is",
                    True,
                    metadata_provided,
                    "runtime telemetry is missing required instrument metadata evidence",
                ),
            ]
        )
    if metadata_required or metadata_provided:
        checks.extend(
            [
                _check(
                    "runtime_instrument_metadata_passed",
                    bool(row["runtime_instrument_metadata_passed"]),
                    "is",
                    True,
                    bool(row["runtime_instrument_metadata_passed"]),
                    "runtime instrument metadata did not pass",
                ),
                _threshold_check(
                    "runtime_instrument_parse_coverage",
                    row["runtime_instrument_parse_coverage"],
                    ">=",
                    row["min_instrument_parse_coverage"],
                ),
                _threshold_check(
                    "runtime_unparsed_instruments",
                    row["runtime_unparsed_instruments"],
                    "<=",
                    0,
                ),
            ]
        )
    manual_halt = _manual_halt(scaleup_config)
    if manual_halt:
        checks.append(_check("manual_halt", True, "is", False, False, "scale-up config contains a manual halt"))
    return pd.DataFrame(checks)


def _summary(row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    halted = bool((~checks["passed"].astype(bool)).any()) if not checks.empty else True
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "guard_action": "halt" if halted else "continue",
                "halted": halted,
                "failed_checks": failed,
                "scenario_key": row["scenario_key"],
                "adapter": row["adapter"],
                "orders_sent": row["orders_sent"],
                "session_notional": row["session_notional"],
                "realized_pnl": row["realized_pnl"],
                "recommendation": "stop_routing_and_investigate" if halted else "continue_with_controls",
            }
        ]
    )


def _scaleup_config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "scaleup_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"scale-up config not found: {candidate}")
    return candidate


def _telemetry_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "runtime_telemetry.csv"
    return candidate


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
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
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _manual_halt(scaleup_config: dict[str, Any]) -> bool:
    value = scaleup_config.get("manual_halt", False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _value(row: pd.Series, column: str, fallback: object = "") -> object:
    value = row.get(column, fallback)
    if pd.isna(value):
        return fallback
    return value


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_from(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key, np.nan)
    if value is None or pd.isna(value):
        return np.nan
    return float(value)


def _first_number(*values: object) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isnan(number):
            return number
    return np.nan


def _bool_from(mapping: dict[str, Any], key: str) -> bool:
    return _to_bool(mapping.get(key, False))


def _bool_value(row: pd.Series, column: str, fallback: bool = False) -> bool:
    return _to_bool(row.get(column, fallback))


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready"}
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)
