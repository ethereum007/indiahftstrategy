from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class FillModelCalibrationThresholds:
    tick_size: float = 0.05
    min_orders: int = 1
    min_live_fill_rate: float = 0.0
    max_mismatch_rate: float = 0.0
    max_overfill_rate: float = 0.0
    max_unmatched_fills: int = 0
    max_adverse_slippage_ticks: float | None = None
    latency_quantile: float = 0.95
    fill_ratio_quantile: float = 0.25
    slippage_quantile: float = 0.95
    min_queue_conservatism: float = 1.0
    max_queue_conservatism: float = 10.0
    base_edge_ticks: float = 0.0


@dataclass(frozen=True)
class FillModelCalibrationReport:
    metrics: pd.DataFrame
    recommendations: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_fill_model_calibration(
    reconciliation_orders: pd.DataFrame,
    reconciliation_summary: pd.DataFrame | None = None,
    *,
    thresholds: FillModelCalibrationThresholds | None = None,
) -> FillModelCalibrationReport:
    thresholds = thresholds or FillModelCalibrationThresholds()
    _validate_thresholds(thresholds)
    orders = _normalize_orders(reconciliation_orders)
    summary_input = pd.DataFrame() if reconciliation_summary is None else reconciliation_summary.copy()
    metrics = _metrics(orders, thresholds)
    recommendations = _recommendations(metrics, thresholds)
    checks = _checks(metrics.iloc[0], summary_input, thresholds)
    summary = _summary(metrics.iloc[0], recommendations.iloc[0], checks)
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(recommendations, summary.iloc[0], checks, thresholds, action_queue)
    return FillModelCalibrationReport(metrics, recommendations, checks, summary, config, action_queue=action_queue)


def write_fill_model_calibration(
    *,
    reconciliation_dir: str | Path,
    output_dir: str | Path,
    thresholds: FillModelCalibrationThresholds | None = None,
) -> FillModelCalibrationReport:
    reconciliation = Path(reconciliation_dir)
    orders_path = reconciliation / "order_reconciliation.csv" if reconciliation.is_dir() else reconciliation
    summary_path = reconciliation / "reconciliation_summary.csv" if reconciliation.is_dir() else None
    if not orders_path.exists():
        raise FileNotFoundError(f"order reconciliation file not found: {orders_path}")
    summary = pd.read_csv(summary_path) if summary_path and summary_path.exists() else None
    thresholds = thresholds or FillModelCalibrationThresholds()
    report = evaluate_fill_model_calibration(
        pd.read_csv(orders_path),
        summary,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "fill_model_metrics.csv", index=False)
    report.recommendations.to_csv(out / "fill_model_recommendations.csv", index=False)
    report.checks.to_csv(out / "fill_model_checks.csv", index=False)
    report.summary.to_csv(out / "fill_model_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "fill_model_action_queue.csv", index=False)
    (out / "fill_model_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "fill_model_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="fill_model_calibration",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"reconciliation": reconciliation},
    )
    return FillModelCalibrationReport(
        report.metrics,
        report.recommendations,
        report.checks,
        report.summary,
        report.config,
        out,
        action_queue,
    )


def _normalize_orders(orders: pd.DataFrame) -> pd.DataFrame:
    _require(orders, ["instrument_id", "qty", "live_qty", "filled_live", "fill_status"], "reconciliation_orders")
    frame = orders.copy().reset_index(drop=True)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce").fillna(0.0)
    frame["live_qty"] = pd.to_numeric(frame["live_qty"], errors="coerce").fillna(0.0)
    frame["filled_live"] = frame["filled_live"].map(_to_bool)
    frame["fill_status"] = frame["fill_status"].astype(str).str.strip().str.lower()
    frame["fill_ratio"] = np.where(frame["qty"] > 0, frame["live_qty"] / frame["qty"], 0.0)
    frame["fill_ratio"] = frame["fill_ratio"].clip(lower=0.0)
    frame["latency_ns"] = _numeric_optional(frame, "latency_ns")
    frame["adverse_slippage"] = _numeric_optional(frame, "adverse_slippage")
    frame["mismatch"] = frame["mismatch"].map(_to_bool) if "mismatch" in frame.columns else False
    return frame


def _metrics(orders: pd.DataFrame, thresholds: FillModelCalibrationThresholds) -> pd.DataFrame:
    rows = [_metric_row("ALL", orders, thresholds)]
    for instrument_id, group in orders.groupby("instrument_id", dropna=False):
        rows.append(_metric_row(str(instrument_id), group, thresholds))
    return pd.DataFrame(rows)


def _metric_row(label: str, group: pd.DataFrame, thresholds: FillModelCalibrationThresholds) -> dict[str, object]:
    orders = int(len(group))
    filled = int(group["filled_live"].sum()) if orders else 0
    partial = int((group["fill_status"] == "partial").sum()) if orders else 0
    overfill = int((group["fill_status"] == "overfill").sum()) if orders else 0
    mismatch = int(group["mismatch"].sum()) if orders else 0
    fill_ratio = pd.to_numeric(group["fill_ratio"], errors="coerce")
    latency = pd.to_numeric(group["latency_ns"], errors="coerce")
    adverse = pd.to_numeric(group["adverse_slippage"], errors="coerce")
    adverse_positive = adverse.clip(lower=0.0)
    return {
        "instrument_id": label,
        "orders": orders,
        "filled_orders": filled,
        "partial_orders": partial,
        "overfilled_orders": overfill,
        "mismatched_orders": mismatch,
        "live_fill_rate": filled / orders if orders else 0.0,
        "partial_rate": partial / orders if orders else 0.0,
        "overfill_rate": overfill / orders if orders else 0.0,
        "mismatch_rate": mismatch / orders if orders else 0.0,
        "requested_qty": float(group["qty"].sum()) if orders else 0.0,
        "live_qty": float(group["live_qty"].sum()) if orders else 0.0,
        "avg_fill_ratio": float(fill_ratio.mean(skipna=True)) if fill_ratio.notna().any() else 0.0,
        "fill_ratio_quantile": _quantile(fill_ratio, thresholds.fill_ratio_quantile, default=0.0),
        "avg_latency_ns": float(latency.mean(skipna=True)) if latency.notna().any() else np.nan,
        "latency_quantile_ns": _quantile(latency, thresholds.latency_quantile, default=np.nan),
        "avg_adverse_slippage": float(adverse.mean(skipna=True)) if adverse.notna().any() else np.nan,
        "adverse_slippage_quantile": _quantile(adverse_positive, thresholds.slippage_quantile, default=0.0),
        "max_adverse_slippage": float(adverse.max(skipna=True)) if adverse.notna().any() else 0.0,
    }


def _recommendations(metrics: pd.DataFrame, thresholds: FillModelCalibrationThresholds) -> pd.DataFrame:
    rows = []
    for row in metrics.to_dict("records"):
        fill_ratio_floor = max(float(row["fill_ratio_quantile"]), 1e-9)
        queue_conservatism = min(
            thresholds.max_queue_conservatism,
            max(thresholds.min_queue_conservatism, 1.0 / fill_ratio_floor),
        )
        latency_ns = float(row["latency_quantile_ns"]) if not pd.isna(row["latency_quantile_ns"]) else 0.0
        adverse_ticks = max(0.0, float(row["adverse_slippage_quantile"])) / thresholds.tick_size
        slippage_ticks = float(np.ceil(adverse_ticks - 1e-12))
        rows.append(
            {
                "instrument_id": row["instrument_id"],
                "recommended_queue_conservatism": float(queue_conservatism),
                "recommended_order_latency_us": float(latency_ns / 1_000.0),
                "recommended_slippage_ticks": slippage_ticks,
                "recommended_min_edge_ticks": float(thresholds.base_edge_ticks + slippage_ticks),
                "basis_live_fill_rate": float(row["live_fill_rate"]),
                "basis_fill_ratio_quantile": float(row["fill_ratio_quantile"]),
                "basis_latency_quantile_ns": latency_ns,
                "basis_adverse_slippage_quantile": float(row["adverse_slippage_quantile"]),
            }
        )
    return pd.DataFrame(rows)


def _checks(
    all_metrics: pd.Series,
    reconciliation_summary: pd.DataFrame,
    thresholds: FillModelCalibrationThresholds,
) -> pd.DataFrame:
    unmatched_fills = _unmatched_fills(reconciliation_summary)
    max_adverse_ticks = float(all_metrics["max_adverse_slippage"]) / thresholds.tick_size
    checks = [
        _threshold_check("orders", all_metrics["orders"], ">=", thresholds.min_orders),
        _threshold_check("live_fill_rate", all_metrics["live_fill_rate"], ">=", thresholds.min_live_fill_rate),
        _threshold_check("mismatch_rate", all_metrics["mismatch_rate"], "<=", thresholds.max_mismatch_rate),
        _threshold_check("overfill_rate", all_metrics["overfill_rate"], "<=", thresholds.max_overfill_rate),
        _threshold_check("unmatched_fills", unmatched_fills, "<=", thresholds.max_unmatched_fills),
    ]
    if thresholds.max_adverse_slippage_ticks is not None:
        checks.append(
            _threshold_check(
                "max_adverse_slippage_ticks",
                max_adverse_ticks,
                "<=",
                thresholds.max_adverse_slippage_ticks,
            )
        )
    return pd.DataFrame(checks)


def _summary(all_metrics: pd.Series, all_recommendation: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "orders": int(all_metrics["orders"]),
                "live_fill_rate": float(all_metrics["live_fill_rate"]),
                "avg_fill_ratio": float(all_metrics["avg_fill_ratio"]),
                "recommended_queue_conservatism": float(all_recommendation["recommended_queue_conservatism"]),
                "recommended_order_latency_us": float(all_recommendation["recommended_order_latency_us"]),
                "recommended_slippage_ticks": float(all_recommendation["recommended_slippage_ticks"]),
                "recommended_min_edge_ticks": float(all_recommendation["recommended_min_edge_ticks"]),
                "failed_checks": failed,
                "recommendation": "use_recommended_fill_model" if ready else "collect_more_shadow_data_or_tighten_simulation",
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
    next_gate = "calibrate-fill-model"
    return {
        "queue_status": "blocked",
        "source": "fill_model_checks",
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
    recommendations: pd.DataFrame,
    summary: pd.Series,
    checks: pd.DataFrame,
    thresholds: FillModelCalibrationThresholds,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    global_row = recommendations.iloc[0]
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "tick_size": float(thresholds.tick_size),
        "global": {
            "queue_conservatism": float(global_row["recommended_queue_conservatism"]),
            "order_latency_us": float(global_row["recommended_order_latency_us"]),
            "slippage_ticks": float(global_row["recommended_slippage_ticks"]),
            "min_edge_ticks": float(global_row["recommended_min_edge_ticks"]),
        },
        "by_instrument": [
            {
                "instrument_id": str(row.instrument_id),
                "queue_conservatism": float(row.recommended_queue_conservatism),
                "order_latency_us": float(row.recommended_order_latency_us),
                "slippage_ticks": float(row.recommended_slippage_ticks),
                "min_edge_ticks": float(row.recommended_min_edge_ticks),
            }
            for row in recommendations.iloc[1:].itertuples(index=False)
        ],
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
        "failed_check_count": _int(summary.get("failed_check_count")),
        "failed_check_names": _split_items(summary.get("failed_check_names")),
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
    }


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if bool(summary.get("ready")) else "no"
    lines = [
        "# Fill Model Calibration Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Orders: {_int(summary.get('orders'))}",
        f"- Live fill rate: {_text(summary.get('live_fill_rate'))}",
        f"- Average fill ratio: {_text(summary.get('avg_fill_ratio'))}",
        f"- Queue conservatism: {_text(summary.get('recommended_queue_conservatism'))}",
        f"- Order latency us: {_text(summary.get('recommended_order_latency_us'))}",
        f"- Slippage ticks: {_text(summary.get('recommended_slippage_ticks'))}",
        f"- Minimum edge ticks: {_text(summary.get('recommended_min_edge_ticks'))}",
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
        return "No fill-model calibration actions."
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
    if check == "orders":
        return "sample_size"
    if check in {"live_fill_rate", "overfill_rate"}:
        return "fill_quality"
    if check in {"mismatch_rate", "unmatched_fills"}:
        return "reconciliation_quality"
    if check == "max_adverse_slippage_ticks":
        return "slippage"
    return "fill_model"


def _recommendation(check: str) -> str:
    if check == "orders":
        return "collect_more_shadow_orders_before_replay_calibration"
    if check == "live_fill_rate":
        return "review_route_quality_or_raise_queue_conservatism"
    if check in {"mismatch_rate", "unmatched_fills"}:
        return "repair_broker_reconciliation_before_calibration"
    if check == "overfill_rate":
        return "investigate_duplicate_fills_or_order_controls"
    if check == "max_adverse_slippage_ticks":
        return "increase_replay_slippage_or_tighten_limit_prices"
    return "repair_fill_model_calibration_inputs"


def _unmatched_fills(reconciliation_summary: pd.DataFrame) -> int:
    if reconciliation_summary.empty or "unmatched_fills" not in reconciliation_summary.columns:
        return 0
    value = pd.to_numeric(reconciliation_summary.iloc[0]["unmatched_fills"], errors="coerce")
    return int(value) if not pd.isna(value) else 0


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
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _quantile(values: pd.Series, quantile: float, *, default: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return float(default)
    return float(clean.quantile(quantile))


def _numeric_optional(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([np.nan] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _validate_thresholds(thresholds: FillModelCalibrationThresholds) -> None:
    if thresholds.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")
    for name in ("min_live_fill_rate", "max_mismatch_rate", "max_overfill_rate"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    for name in ("latency_quantile", "fill_ratio_quantile", "slippage_quantile"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if thresholds.max_unmatched_fills < 0:
        raise ValueError("max_unmatched_fills must be non-negative")
    if thresholds.max_adverse_slippage_ticks is not None and thresholds.max_adverse_slippage_ticks < 0:
        raise ValueError("max_adverse_slippage_ticks must be non-negative")
    if thresholds.min_queue_conservatism <= 0:
        raise ValueError("min_queue_conservatism must be positive")
    if thresholds.max_queue_conservatism < thresholds.min_queue_conservatism:
        raise ValueError("max_queue_conservatism must be >= min_queue_conservatism")
    if thresholds.base_edge_ticks < 0:
        raise ValueError("base_edge_ticks must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


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


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
