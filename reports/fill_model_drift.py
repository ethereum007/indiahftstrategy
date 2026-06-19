from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class FillModelDriftThresholds:
    require_baseline_ready: bool = True
    require_latest_ready: bool = True
    require_same_instruments: bool = False
    max_queue_conservatism_increase_pct: float | None = 0.25
    max_order_latency_increase_us: float | None = 100.0
    max_slippage_tick_increase: float | None = 1.0
    max_min_edge_tick_increase: float | None = 1.0


@dataclass(frozen=True)
class FillModelDriftReport:
    drift: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    config: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_fill_model_drift(
    baseline_config: dict[str, Any],
    latest_config: dict[str, Any],
    *,
    thresholds: FillModelDriftThresholds | None = None,
) -> FillModelDriftReport:
    thresholds = thresholds or FillModelDriftThresholds()
    _validate_thresholds(thresholds)
    drift = _drift_frame(baseline_config, latest_config)
    checks = _checks(baseline_config, latest_config, drift, thresholds)
    summary = _summary(drift, checks)
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(baseline_config, latest_config, drift, summary.iloc[0], thresholds, action_queue)
    return FillModelDriftReport(
        drift=drift,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
        config=config,
    )


def write_fill_model_drift_report(
    *,
    baseline_path: str | Path,
    latest_path: str | Path,
    output_dir: str | Path,
    thresholds: FillModelDriftThresholds | None = None,
) -> FillModelDriftReport:
    baseline_file = _config_path(baseline_path)
    latest_file = _config_path(latest_path)
    thresholds = thresholds or FillModelDriftThresholds()
    report = evaluate_fill_model_drift(
        json.loads(baseline_file.read_text(encoding="utf-8")),
        json.loads(latest_file.read_text(encoding="utf-8")),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.drift.to_csv(out / "fill_model_drift.csv", index=False)
    report.checks.to_csv(out / "fill_model_drift_checks.csv", index=False)
    report.summary.to_csv(out / "fill_model_drift_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "fill_model_drift_action_queue.csv", index=False)
    config_payload = report.config or _config(
        json.loads(baseline_file.read_text(encoding="utf-8")),
        json.loads(latest_file.read_text(encoding="utf-8")),
        report.drift,
        report.summary.iloc[0],
        thresholds,
        action_queue,
    )
    (out / "fill_model_drift_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "fill_model_drift_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="fill_model_drift",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"baseline_fill_model": baseline_file, "latest_fill_model": latest_file},
    )
    return FillModelDriftReport(
        report.drift,
        report.checks,
        report.summary,
        out,
        action_queue,
        config_payload,
    )


def _drift_frame(baseline_config: dict[str, Any], latest_config: dict[str, Any]) -> pd.DataFrame:
    baseline_models = _models_by_scope(baseline_config)
    latest_models = _models_by_scope(latest_config)
    scopes = sorted(set(baseline_models) | set(latest_models), key=lambda item: (item != "GLOBAL", item))
    rows = []
    for scope in scopes:
        baseline = baseline_models.get(scope, {})
        latest = latest_models.get(scope, {})
        rows.append(
            {
                "scope": "global" if scope == "GLOBAL" else "instrument",
                "instrument_id": "" if scope == "GLOBAL" else scope,
                "baseline_present": bool(baseline),
                "latest_present": bool(latest),
                **_metric_drift("queue_conservatism", baseline, latest),
                **_metric_drift("order_latency_us", baseline, latest),
                **_metric_drift("slippage_ticks", baseline, latest),
                **_metric_drift("min_edge_ticks", baseline, latest),
            }
        )
    return pd.DataFrame(rows)


def _checks(
    baseline_config: dict[str, Any],
    latest_config: dict[str, Any],
    drift: pd.DataFrame,
    thresholds: FillModelDriftThresholds,
) -> pd.DataFrame:
    checks = [
        _check(
            "baseline_ready",
            _to_bool(baseline_config.get("ready", False)),
            "is",
            True,
            _to_bool(baseline_config.get("ready", False)) or not thresholds.require_baseline_ready,
            "baseline fill-model config is not ready",
        ),
        _check(
            "latest_ready",
            _to_bool(latest_config.get("ready", False)),
            "is",
            True,
            _to_bool(latest_config.get("ready", False)) or not thresholds.require_latest_ready,
            "latest fill-model config is not ready",
        ),
    ]
    missing_latest = int((~drift["latest_present"].astype(bool)).sum()) if not drift.empty else 0
    missing_baseline = int((~drift["baseline_present"].astype(bool)).sum()) if not drift.empty else 0
    checks.append(
        _check(
            "instrument_set_unchanged",
            missing_latest + missing_baseline,
            "==",
            0,
            (missing_latest + missing_baseline == 0) or not thresholds.require_same_instruments,
            "baseline and latest fill-model instrument sets differ",
        )
    )
    checks.extend(_metric_checks(drift, "queue_conservatism_delta_pct", thresholds.max_queue_conservatism_increase_pct))
    checks.extend(_metric_checks(drift, "order_latency_us_delta", thresholds.max_order_latency_increase_us))
    checks.extend(_metric_checks(drift, "slippage_ticks_delta", thresholds.max_slippage_tick_increase))
    checks.extend(_metric_checks(drift, "min_edge_ticks_delta", thresholds.max_min_edge_tick_increase))
    return pd.DataFrame(checks)


def _metric_checks(drift: pd.DataFrame, column: str, threshold: float | None) -> list[dict[str, object]]:
    if threshold is None:
        return []
    usable = pd.to_numeric(drift[column], errors="coerce") if column in drift.columns else pd.Series(dtype=float)
    max_increase = float(usable.max(skipna=True)) if usable.notna().any() else 0.0
    return [
        _check(
            column,
            max_increase,
            "<=",
            threshold,
            max_increase <= float(threshold) + 1e-12,
            f"{column} {max_increase:.6g} exceeded {float(threshold):.6g}",
        )
    ]


def _summary(drift: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    global_row = drift.loc[drift["scope"] == "global"].iloc[0] if not drift.empty else pd.Series(dtype=object)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "rows": int(len(drift)),
                "new_instruments": int((~drift["baseline_present"].astype(bool)).sum()) if not drift.empty else 0,
                "missing_latest_instruments": int((~drift["latest_present"].astype(bool)).sum()) if not drift.empty else 0,
                "global_queue_conservatism_delta_pct": _number(global_row, "queue_conservatism_delta_pct"),
                "global_order_latency_us_delta": _number(global_row, "order_latency_us_delta"),
                "global_slippage_ticks_delta": _number(global_row, "slippage_ticks_delta"),
                "global_min_edge_ticks_delta": _number(global_row, "min_edge_ticks_delta"),
                "failed_checks": failed,
                "recommendation": "reuse_existing_proof_assumptions" if passed else "rerun_calibrated_proof_before_promotion",
            }
        ]
    )


ACTION_QUEUE_COLUMNS = [
    "priority",
    "queue_status",
    "source",
    "component",
    "check",
    "actual",
    "operator",
    "expected",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]


def _summary_with_actions(
    summary: pd.DataFrame,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> pd.DataFrame:
    out = summary.copy()
    failed = _failed_check_rows(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    out["failed_check_count"] = int(len(failed))
    out["failed_check_names"] = ";".join(failed["check"].astype(str).tolist()) if not failed.empty else ""
    out["first_failed_reason"] = _text(failed.iloc[0].get("reason")) if not failed.empty else ""
    out["primary_blocker_check"] = _text(failed.iloc[0].get("check")) if not failed.empty else ""
    out["primary_blocker_value"] = _text(failed.iloc[0].get("value")) if not failed.empty else ""
    out["primary_blocker_operator"] = _text(failed.iloc[0].get("operator")) if not failed.empty else ""
    out["primary_blocker_threshold"] = _text(failed.iloc[0].get("threshold")) if not failed.empty else ""
    out["primary_blocker_reason"] = _text(failed.iloc[0].get("reason")) if not failed.empty else ""
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _text(row.get("check"))
        rows.append(
            _action_row(
                component=_component(check),
                check=check,
                actual=row.get("value"),
                operator=_text(row.get("operator")),
                expected=row.get("threshold"),
                reason=_text(row.get("reason")),
                recommendation=_recommendation(check),
            )
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _action_row(
    *,
    component: str,
    check: str,
    actual: object,
    operator: str,
    expected: object,
    reason: str,
    recommendation: str,
) -> dict[str, object]:
    next_gate = "compare-fill-models"
    return {
        "queue_status": "blocked",
        "source": "fill_model_drift_checks",
        "component": component,
        "check": check,
        "actual": actual,
        "operator": operator,
        "expected": expected,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "reason": reason,
        "recommendation": recommendation,
    }


def _config(
    baseline_config: dict[str, Any],
    latest_config: dict[str, Any],
    drift: pd.DataFrame,
    summary: pd.Series,
    thresholds: FillModelDriftThresholds,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": _to_bool(summary.get("passed")),
        "baseline_ready": _to_bool(baseline_config.get("ready", False)),
        "latest_ready": _to_bool(latest_config.get("ready", False)),
        "thresholds": asdict(thresholds),
        "drift": {
            "rows": _int(summary.get("rows")),
            "new_instruments": _int(summary.get("new_instruments")),
            "missing_latest_instruments": _int(summary.get("missing_latest_instruments")),
            "global_queue_conservatism_delta_pct": _float(summary.get("global_queue_conservatism_delta_pct")),
            "global_order_latency_us_delta": _float(summary.get("global_order_latency_us_delta")),
            "global_slippage_ticks_delta": _float(summary.get("global_slippage_ticks_delta")),
            "global_min_edge_ticks_delta": _float(summary.get("global_min_edge_ticks_delta")),
        },
        "scopes": _action_records(drift) if not drift.empty else [],
        "failed_checks": _split_items(summary.get("failed_check_names")),
        "failed_check_count": _int(summary.get("failed_check_count")),
        "first_failed_reason": _text(summary.get("first_failed_reason")),
        "primary_blocker": {
            "check": _text(summary.get("primary_blocker_check")),
            "value": _text(summary.get("primary_blocker_value")),
            "operator": _text(summary.get("primary_blocker_operator")),
            "threshold": _text(summary.get("primary_blocker_threshold")),
            "reason": _text(summary.get("primary_blocker_reason")),
        },
        "action_queue_count": _int(summary.get("action_queue_count")),
        "ready_action_count": _int(summary.get("ready_action_count")),
        "blocked_action_count": _int(summary.get("blocked_action_count")),
        "review_action_count": _int(summary.get("review_action_count")),
        "next_gate": _text(summary.get("next_gate")),
        "next_gate_help_command": _text(summary.get("next_gate_help_command")),
        "primary_action_status": _text(summary.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
        "recommendation": _text(summary.get("recommendation")),
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    passed_label = "yes" if _to_bool(summary.get("passed")) else "no"
    lines = [
        "# Fill Model Drift Runbook",
        "",
        f"- Passed: {passed_label}",
        f"- Drift rows: {_int(summary.get('rows'))}",
        f"- New instruments: {_int(summary.get('new_instruments'))}",
        f"- Missing latest instruments: {_int(summary.get('missing_latest_instruments'))}",
        f"- Global queue delta pct: {_text(summary.get('global_queue_conservatism_delta_pct'))}",
        f"- Global latency delta us: {_text(summary.get('global_order_latency_us_delta'))}",
        f"- Global slippage delta ticks: {_text(summary.get('global_slippage_ticks_delta'))}",
        f"- Global min edge delta ticks: {_text(summary.get('global_min_edge_ticks_delta'))}",
        f"- Failed checks: {_int(summary.get('failed_check_count'))}",
        f"- Blocked actions: {_int(summary.get('blocked_action_count'))}",
        f"- Recommendation: {_text(summary.get('recommendation'))}",
        f"- Primary next gate: {_code(summary.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No fill-model drift actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _text(item.get("priority")),
                    _text(item.get("queue_status")),
                    _text(item.get("component")),
                    _text(item.get("check")),
                    _text(item.get("actual")),
                    _text(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _text(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].copy()


def _component(check: str) -> str:
    if check in {"baseline_ready", "latest_ready"}:
        return "fill_model_readiness"
    if check == "instrument_set_unchanged":
        return "instrument_coverage"
    if check == "queue_conservatism_delta_pct":
        return "queue_model"
    if check == "order_latency_us_delta":
        return "latency_model"
    if check == "slippage_ticks_delta":
        return "slippage_model"
    if check == "min_edge_ticks_delta":
        return "edge_buffer"
    return "fill_model_drift"


def _recommendation(check: str) -> str:
    if check in {"baseline_ready", "latest_ready"}:
        return "rerun_fill_model_calibration_before_proof_reuse"
    if check == "instrument_set_unchanged":
        return "review_instrument_specific_fill_models_or_disable_strict_instrument_match"
    if check == "queue_conservatism_delta_pct":
        return "rerun_calibrated_proof_with_latest_queue_assumptions"
    if check == "order_latency_us_delta":
        return "rerun_calibrated_proof_with_latest_latency_assumptions"
    if check == "slippage_ticks_delta":
        return "rerun_calibrated_proof_with_latest_slippage_assumptions"
    if check == "min_edge_ticks_delta":
        return "rerun_calibrated_proof_with_latest_edge_buffer"
    return "review_fill_model_drift"


def _models_by_scope(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    models = {"GLOBAL": config.get("global", {}) or {}}
    for row in config.get("by_instrument", []) or []:
        instrument_id = str(row.get("instrument_id", "")).strip()
        if instrument_id:
            models[instrument_id] = row
    return models


def _metric_drift(metric: str, baseline: dict[str, Any], latest: dict[str, Any]) -> dict[str, float]:
    baseline_value = _mapping_number(baseline, metric)
    latest_value = _mapping_number(latest, metric)
    delta = latest_value - baseline_value if not pd.isna(latest_value) and not pd.isna(baseline_value) else np.nan
    if pd.isna(delta) or pd.isna(baseline_value) or abs(baseline_value) <= 1e-12:
        delta_pct = np.nan
    else:
        delta_pct = delta / abs(baseline_value)
    return {
        f"baseline_{metric}": baseline_value,
        f"latest_{metric}": latest_value,
        f"{metric}_delta": delta,
        f"{metric}_delta_pct": delta_pct,
    }


def _config_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "fill_model_config.json"
    if not candidate.exists():
        raise FileNotFoundError(f"fill-model config not found: {candidate}")
    return candidate


def _validate_thresholds(thresholds: FillModelDriftThresholds) -> None:
    for name in (
        "max_queue_conservatism_increase_pct",
        "max_order_latency_increase_us",
        "max_slippage_tick_increase",
        "max_min_edge_tick_increase",
    ):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")


def _mapping_number(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key, np.nan)
    if value is None or pd.isna(value):
        return np.nan
    return float(value)


def _number(row: pd.Series, column: str) -> float:
    if row.empty or column not in row.index:
        return np.nan
    value = pd.to_numeric(row[column], errors="coerce")
    return float(value) if not pd.isna(value) else np.nan


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _text(action_queue.iloc[0].get(column))


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_value(value) for key, value in row.items()}


def _jsonable_value(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _split_items(value: object) -> list[str]:
    text = _text(value)
    if not text:
        return []
    normalized = text.replace(",", ";")
    return [item.strip() for item in normalized.split(";") if item.strip()]


def _help_command(next_gate: str) -> str:
    gate = _text(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _text(value)
    return f"`{text}`" if text else ""


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _int(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


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
