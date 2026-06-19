from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from adapters.broker import normalize_live_fills
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ReconciliationThresholds:
    min_order_fill_rate: float = 0.0
    max_unfilled_orders: int | None = None
    max_partial_orders: int | None = None
    max_overfilled_orders: int = 0
    max_mismatched_orders: int = 0
    max_unmatched_fills: int = 0
    max_adverse_slippage: float | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    orders: pd.DataFrame
    unmatched_fills: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None
    config: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_order_reconciliation(
    exported_orders: pd.DataFrame,
    live_fills: pd.DataFrame,
    *,
    thresholds: ReconciliationThresholds | None = None,
) -> ReconciliationReport:
    thresholds = thresholds or ReconciliationThresholds()
    _validate_thresholds(thresholds)
    orders = _normalize_orders(exported_orders)
    fills = _normalize_fills(live_fills)
    matched = _reconcile_orders(orders, fills)
    unmatched = fills.loc[~fills["client_order_id"].isin(orders["client_order_id"])].reset_index(drop=True)
    summary = _summary(matched, unmatched)
    checks = _checks(summary.iloc[0], thresholds)
    summary["passed"] = bool(checks["passed"].all()) if not checks.empty else False
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    return ReconciliationReport(
        orders=matched,
        unmatched_fills=unmatched,
        checks=checks,
        summary=summary,
        action_queue=action_queue,
    )


def write_order_reconciliation(
    *,
    export_dir: str | Path,
    fills_path: str | Path,
    output_dir: str | Path,
    adapter: str = "normalized",
    thresholds: ReconciliationThresholds | None = None,
) -> ReconciliationReport:
    export_path = Path(export_dir)
    orders_path = export_path / "broker_orders.csv"
    if not orders_path.exists():
        raise FileNotFoundError(f"broker_orders.csv not found: {orders_path}")
    fills_file = Path(fills_path)
    if not fills_file.exists():
        raise FileNotFoundError(f"live fills file not found: {fills_file}")
    thresholds = thresholds or ReconciliationThresholds()
    report = evaluate_order_reconciliation(
        pd.read_csv(orders_path),
        normalize_live_fills(fills_file, adapter=adapter),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / "order_reconciliation.csv", index=False)
    report.unmatched_fills.to_csv(out / "unmatched_fills.csv", index=False)
    report.checks.to_csv(out / "reconciliation_checks.csv", index=False)
    report.summary.to_csv(out / "reconciliation_summary.csv", index=False)
    action_queue = (
        report.action_queue
        if report.action_queue is not None
        else _action_queue(report.summary.iloc[0], report.checks)
    )
    action_queue.to_csv(out / "reconciliation_action_queue.csv", index=False)
    config_payload = _config(report.summary.iloc[0], action_queue, thresholds, export_path, fills_file, adapter)
    (out / "reconciliation_config.json").write_text(
        json.dumps(config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "reconciliation_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="order_reconciliation",
        parameters={"adapter": adapter, "thresholds": asdict(thresholds)},
        inputs={"export": export_path, "fills": fills_file},
    )
    return ReconciliationReport(
        report.orders,
        report.unmatched_fills,
        report.checks,
        report.summary,
        out,
        action_queue,
        config_payload,
    )


def _normalize_orders(orders: pd.DataFrame) -> pd.DataFrame:
    _require(orders, ["client_order_id", "instrument_id", "side", "qty", "price"], "exported_orders")
    frame = orders.copy().reset_index(drop=True)
    frame["client_order_id"] = frame["client_order_id"].astype(str)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side).astype("int64")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    if "ts_signal_ns" not in frame.columns:
        frame["ts_signal_ns"] = np.nan
    frame["ts_signal_ns"] = pd.to_numeric(frame["ts_signal_ns"], errors="coerce")
    return frame


def _normalize_fills(fills: pd.DataFrame) -> pd.DataFrame:
    _require(fills, ["client_order_id", "instrument_id", "ts_fill_ns", "side", "qty", "price"], "live_fills")
    frame = fills.copy().reset_index(drop=True)
    frame["client_order_id"] = frame["client_order_id"].astype(str)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side).astype("int64")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["ts_fill_ns"] = pd.to_numeric(frame["ts_fill_ns"], errors="coerce")
    frame["fill_notional"] = frame["qty"] * frame["price"]
    return frame


def _reconcile_orders(orders: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        out = orders.copy()
        return _attach_empty_fill_metrics(out)

    fill_groups = []
    for client_order_id, group in fills.sort_values("ts_fill_ns").groupby("client_order_id", dropna=False):
        live_qty = float(group["qty"].sum())
        live_notional = float(group["fill_notional"].sum())
        avg_price = live_notional / live_qty if live_qty > 0 else np.nan
        instruments = sorted(group["instrument_id"].dropna().astype(str).unique())
        sides = sorted(group["side"].dropna().astype(int).unique())
        fill_groups.append(
            {
                "client_order_id": str(client_order_id),
                "live_qty": live_qty,
                "live_avg_price": avg_price,
                "fill_count": int(len(group)),
                "live_instrument_id": instruments[0] if len(instruments) == 1 else "MULTIPLE",
                "live_side": sides[0] if len(sides) == 1 else 0,
                "first_fill_ts_ns": float(group["ts_fill_ns"].min()),
                "last_fill_ts_ns": float(group["ts_fill_ns"].max()),
                "live_notional": live_notional,
            }
        )
    live = pd.DataFrame(fill_groups)
    out = orders.merge(live, on="client_order_id", how="left")
    out["live_qty"] = out["live_qty"].fillna(0.0)
    out["fill_count"] = out["fill_count"].fillna(0).astype("int64")
    out["filled_live"] = out["live_qty"] > 0
    out["fill_qty_diff"] = out["live_qty"] - out["qty"]
    out["fill_status"] = np.select(
        [
            out["live_qty"] <= 0,
            out["live_qty"] < out["qty"],
            out["live_qty"] == out["qty"],
            out["live_qty"] > out["qty"],
        ],
        ["unfilled", "partial", "full", "overfill"],
        default="unknown",
    )
    out["instrument_match"] = (~out["filled_live"]) | (out["live_instrument_id"] == out["instrument_id"])
    out["side_match"] = (~out["filled_live"]) | (out["live_side"] == out["side"])
    out["mismatch"] = out["filled_live"] & (~out["instrument_match"] | ~out["side_match"])
    out["latency_ns"] = out["first_fill_ts_ns"] - out["ts_signal_ns"]
    out["adverse_slippage"] = out["side"] * (out["live_avg_price"] - out["price"])
    out.loc[~out["filled_live"], ["latency_ns", "adverse_slippage"]] = np.nan
    return out


def _attach_empty_fill_metrics(orders: pd.DataFrame) -> pd.DataFrame:
    out = orders.copy()
    out["live_qty"] = 0.0
    out["live_avg_price"] = np.nan
    out["fill_count"] = 0
    out["live_instrument_id"] = np.nan
    out["live_side"] = np.nan
    out["first_fill_ts_ns"] = np.nan
    out["last_fill_ts_ns"] = np.nan
    out["live_notional"] = 0.0
    out["filled_live"] = False
    out["fill_qty_diff"] = -out["qty"]
    out["fill_status"] = "unfilled"
    out["instrument_match"] = True
    out["side_match"] = True
    out["mismatch"] = False
    out["latency_ns"] = np.nan
    out["adverse_slippage"] = np.nan
    return out


def _summary(orders: pd.DataFrame, unmatched_fills: pd.DataFrame) -> pd.DataFrame:
    order_count = int(len(orders))
    filled_orders = int(orders["filled_live"].sum()) if order_count else 0
    partial_orders = int((orders["fill_status"] == "partial").sum()) if order_count else 0
    overfilled_orders = int((orders["fill_status"] == "overfill").sum()) if order_count else 0
    unfilled_orders = int((orders["fill_status"] == "unfilled").sum()) if order_count else 0
    mismatched_orders = int(orders["mismatch"].sum()) if order_count else 0
    adverse = pd.to_numeric(orders["adverse_slippage"], errors="coerce")
    return pd.DataFrame(
        [
            {
                "orders": order_count,
                "filled_orders": filled_orders,
                "partial_orders": partial_orders,
                "overfilled_orders": overfilled_orders,
                "unfilled_orders": unfilled_orders,
                "mismatched_orders": mismatched_orders,
                "unmatched_fills": int(len(unmatched_fills)),
                "order_fill_rate": filled_orders / order_count if order_count else 0.0,
                "requested_qty": float(pd.to_numeric(orders["qty"], errors="coerce").sum()) if order_count else 0.0,
                "live_qty": float(pd.to_numeric(orders["live_qty"], errors="coerce").sum()) if order_count else 0.0,
                "avg_adverse_slippage": float(adverse.mean(skipna=True)) if adverse.notna().any() else np.nan,
                "max_adverse_slippage": float(adverse.max(skipna=True)) if adverse.notna().any() else np.nan,
                "avg_latency_ns": float(pd.to_numeric(orders["latency_ns"], errors="coerce").mean(skipna=True))
                if pd.to_numeric(orders["latency_ns"], errors="coerce").notna().any()
                else np.nan,
            }
        ]
    )


def _checks(row: pd.Series, thresholds: ReconciliationThresholds) -> pd.DataFrame:
    checks = [
        _threshold_check("order_fill_rate", row["order_fill_rate"], ">=", thresholds.min_order_fill_rate),
        _threshold_check("overfilled_orders", row["overfilled_orders"], "<=", thresholds.max_overfilled_orders),
        _threshold_check("mismatched_orders", row["mismatched_orders"], "<=", thresholds.max_mismatched_orders),
        _threshold_check("unmatched_fills", row["unmatched_fills"], "<=", thresholds.max_unmatched_fills),
    ]
    if thresholds.max_unfilled_orders is not None:
        checks.append(_threshold_check("unfilled_orders", row["unfilled_orders"], "<=", thresholds.max_unfilled_orders))
    if thresholds.max_partial_orders is not None:
        checks.append(_threshold_check("partial_orders", row["partial_orders"], "<=", thresholds.max_partial_orders))
    if thresholds.max_adverse_slippage is not None:
        checks.append(
            _threshold_check("max_adverse_slippage", row["max_adverse_slippage"], "<=", thresholds.max_adverse_slippage)
        )
    return pd.DataFrame(checks)


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
    out["recommendation"] = (
        "promote_reconciliation_to_broker_readiness"
        if bool(out.iloc[0].get("passed"))
        else "repair_reconciliation_before_broker_readiness"
    )
    return out


def _action_queue(summary_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
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
    next_gate = "reconcile-broker-fills"
    return {
        "queue_status": "blocked",
        "source": "reconciliation_checks",
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
    summary_row: pd.Series,
    action_queue: pd.DataFrame,
    thresholds: ReconciliationThresholds,
    export_path: Path,
    fills_file: Path,
    adapter: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "passed": _to_bool(summary_row.get("passed")),
        "adapter": adapter,
        "inputs": {
            "export": str(export_path),
            "fills": str(fills_file),
        },
        "thresholds": asdict(thresholds),
        "metrics": {
            "orders": _int(summary_row.get("orders")),
            "filled_orders": _int(summary_row.get("filled_orders")),
            "partial_orders": _int(summary_row.get("partial_orders")),
            "overfilled_orders": _int(summary_row.get("overfilled_orders")),
            "unfilled_orders": _int(summary_row.get("unfilled_orders")),
            "mismatched_orders": _int(summary_row.get("mismatched_orders")),
            "unmatched_fills": _int(summary_row.get("unmatched_fills")),
            "order_fill_rate": _float(summary_row.get("order_fill_rate")),
            "requested_qty": _float(summary_row.get("requested_qty")),
            "live_qty": _float(summary_row.get("live_qty")),
            "avg_adverse_slippage": _float(summary_row.get("avg_adverse_slippage")),
            "max_adverse_slippage": _float(summary_row.get("max_adverse_slippage")),
            "avg_latency_ns": _float(summary_row.get("avg_latency_ns")),
        },
        "failed_check_count": _int(summary_row.get("failed_check_count")),
        "failed_check_names": _split_items(summary_row.get("failed_check_names")),
        "first_failed_reason": _text(summary_row.get("first_failed_reason")),
        "primary_blocker": {
            "check": _text(summary_row.get("primary_blocker_check")),
            "value": _text(summary_row.get("primary_blocker_value")),
            "operator": _text(summary_row.get("primary_blocker_operator")),
            "threshold": _text(summary_row.get("primary_blocker_threshold")),
            "reason": _text(summary_row.get("primary_blocker_reason")),
        },
        "action_queue_count": _int(summary_row.get("action_queue_count")),
        "ready_action_count": _int(summary_row.get("ready_action_count")),
        "blocked_action_count": _int(summary_row.get("blocked_action_count")),
        "review_action_count": _int(summary_row.get("review_action_count")),
        "next_gate": _text(summary_row.get("next_gate")),
        "next_gate_help_command": _text(summary_row.get("next_gate_help_command")),
        "primary_action_status": _text(summary_row.get("primary_action_status")),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
        "recommendation": _text(summary_row.get("recommendation")),
    }


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    passed_label = "yes" if _to_bool(summary_row.get("passed")) else "no"
    lines = [
        "# Broker Fill Reconciliation Runbook",
        "",
        f"- Passed: {passed_label}",
        f"- Orders: {_int(summary_row.get('orders'))}",
        f"- Filled orders: {_int(summary_row.get('filled_orders'))}",
        f"- Unfilled orders: {_int(summary_row.get('unfilled_orders'))}",
        f"- Partial orders: {_int(summary_row.get('partial_orders'))}",
        f"- Overfilled orders: {_int(summary_row.get('overfilled_orders'))}",
        f"- Mismatched orders: {_int(summary_row.get('mismatched_orders'))}",
        f"- Unmatched fills: {_int(summary_row.get('unmatched_fills'))}",
        f"- Order fill rate: {_text(summary_row.get('order_fill_rate'))}",
        f"- Max adverse slippage: {_text(summary_row.get('max_adverse_slippage'))}",
        f"- Blocked actions: {_int(summary_row.get('blocked_action_count'))}",
        f"- Recommendation: {_text(summary_row.get('recommendation'))}",
        f"- Primary next gate: {_code(summary_row.get('next_gate'))}",
        f"- Primary next gate help: {_code(summary_row.get('next_gate_help_command'))}",
        "",
        "## Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "No reconciliation actions."
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
    if check == "order_fill_rate":
        return "fill_rate"
    if check in {"unfilled_orders", "partial_orders", "overfilled_orders"}:
        return "fill_quality"
    if check == "mismatched_orders":
        return "execution_match"
    if check == "unmatched_fills":
        return "drop_copy"
    if check == "max_adverse_slippage":
        return "slippage"
    return "reconciliation"


def _recommendation(check: str) -> str:
    if check in {"order_fill_rate", "unfilled_orders", "partial_orders"}:
        return "review_order_acceptance_fill_model_or_route_quality"
    if check == "overfilled_orders":
        return "investigate_duplicate_fills_or_order_qty_controls"
    if check == "mismatched_orders":
        return "inspect_client_order_id_instrument_side_mapping"
    if check == "unmatched_fills":
        return "reconcile_broker_ids_or_filter_external_orders"
    if check == "max_adverse_slippage":
        return "tighten_limit_prices_or_update_fill_model"
    return "repair_reconciliation_inputs"


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _validate_thresholds(thresholds: ReconciliationThresholds) -> None:
    if not 0 <= thresholds.min_order_fill_rate <= 1:
        raise ValueError("min_order_fill_rate must be between 0 and 1")
    for name in ("max_unfilled_orders", "max_partial_orders", "max_overfilled_orders", "max_mismatched_orders", "max_unmatched_fills"):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    if thresholds.max_adverse_slippage is not None and thresholds.max_adverse_slippage < 0:
        raise ValueError("max_adverse_slippage must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
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


def _to_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


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


def _normalize_side(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return 0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return 0
