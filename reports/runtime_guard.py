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
) -> RuntimeGuardReport:
    if telemetry.empty:
        raise ValueError("runtime telemetry is empty")
    metrics = _metrics(scaleup_config, telemetry)
    checks = _checks(metrics.iloc[0], scaleup_config)
    summary = _summary(metrics.iloc[0], checks)
    return RuntimeGuardReport(metrics=metrics, checks=checks, summary=summary)


def write_runtime_guard_report(
    *,
    scaleup_dir: str | Path,
    telemetry_path: str | Path,
    output_dir: str | Path,
) -> RuntimeGuardReport:
    scaleup_file = _scaleup_config_path(scaleup_dir)
    telemetry_file = Path(telemetry_path)
    if not telemetry_file.exists():
        raise FileNotFoundError(f"runtime telemetry file not found: {telemetry_file}")
    scaleup_config = json.loads(scaleup_file.read_text(encoding="utf-8"))
    report = evaluate_runtime_guard(scaleup_config, pd.read_csv(telemetry_file))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "runtime_guard_metrics.csv", index=False)
    report.checks.to_csv(out / "runtime_guard_checks.csv", index=False)
    report.summary.to_csv(out / "runtime_guard_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="runtime_guard",
        parameters={"scaleup_ready": bool(scaleup_config.get("ready", False))},
        inputs={"scaleup": scaleup_file, "telemetry": telemetry_file},
    )
    return RuntimeGuardReport(report.metrics, report.checks, report.summary, out)


def _metrics(scaleup_config: dict[str, Any], telemetry: pd.DataFrame) -> pd.DataFrame:
    latest = telemetry.iloc[-1]
    limits = scaleup_config.get("limits", {}) or {}
    kill_switches = scaleup_config.get("kill_switches", {}) or {}
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
                "orders_sent": _number(latest, "orders_sent", fallback=_number(latest, "orders")),
                "session_notional": _number(latest, "session_notional", fallback=_number(latest, "total_notional")),
                "realized_pnl": _number(latest, "realized_pnl", fallback=_number(latest, "net_pnl")),
                "total_failed_component_checks": _number(latest, "total_failed_component_checks"),
                "unmatched_fills": _number(latest, "unmatched_fills"),
                "mismatched_orders": _number(latest, "mismatched_orders"),
                "overfilled_orders": _number(latest, "overfilled_orders"),
                "worst_adverse_slippage": _number(
                    latest,
                    "worst_adverse_slippage",
                    fallback=_number(latest, "max_adverse_slippage"),
                ),
                "max_orders_per_session": _number_from(limits, "max_orders_per_session"),
                "max_notional_per_session": _number_from(limits, "max_notional_per_session"),
                "stop_loss": _number_from(limits, "stop_loss"),
                "max_total_failed_component_checks": _number_from(kill_switches, "max_total_failed_component_checks"),
                "max_total_unmatched_fills": _number_from(kill_switches, "max_total_unmatched_fills"),
                "max_total_mismatched_orders": _number_from(kill_switches, "max_total_mismatched_orders"),
                "max_total_overfilled_orders": _number_from(kill_switches, "max_total_overfilled_orders"),
                "max_worst_adverse_slippage": _number_from(kill_switches, "max_worst_adverse_slippage"),
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
