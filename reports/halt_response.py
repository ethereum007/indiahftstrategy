from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


PROOF_REFRESH_COLUMNS = [
    "proof_refresh_required",
    "proof_refresh_provided",
    "proof_refresh_ready",
    "proof_refresh_strategy",
    "proof_refresh_market",
    "proof_refresh_mixed_identity",
    "proof_source",
]

BROKER_ROUTE_READINESS_COLUMNS = [
    "broker_route_readiness_required",
    "broker_route_readiness_provided",
    "broker_route_readiness_ready",
    "broker_route_readiness_strategy",
    "broker_route_readiness_market",
    "broker_route_readiness_route_ready_pairs",
    "broker_route_readiness_gap_pairs",
    "broker_route_readiness_recommendation",
    "broker_route_readiness_ops_launch_controls_ready",
    "broker_route_readiness_ops_launch_control_failures",
    "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
    "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
]

CANCEL_COLUMNS = [
    "action_id",
    "action",
    "strategy",
    "market",
    *PROOF_REFRESH_COLUMNS,
    *BROKER_ROUTE_READINESS_COLUMNS,
    "client_order_id",
    "broker_order_id",
    "instrument_id",
    "side",
    "side_text",
    "open_qty",
    "reason",
    "guard_failed_check_names",
    "guard_first_failed_reason",
]

FLATTEN_COLUMNS = [
    "action_id",
    "action",
    "strategy",
    "market",
    *PROOF_REFRESH_COLUMNS,
    *BROKER_ROUTE_READINESS_COLUMNS,
    "instrument_id",
    "side",
    "side_text",
    "qty",
    "price",
    "order_type",
    "time_in_force",
    "reason",
    "guard_failed_check_names",
    "guard_first_failed_reason",
]

TERMINAL_STATUSES = {"filled", "cancelled", "canceled", "rejected", "expired", "complete", "closed"}

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


@dataclass(frozen=True)
class HaltResponseConfig:
    require_guard_halt: bool = True
    require_flatten_prices: bool = True
    default_order_type: str = "LIMIT"
    default_time_in_force: str = "DAY"


@dataclass(frozen=True)
class HaltResponseReport:
    cancel_orders: pd.DataFrame
    flatten_orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_halt_response(
    guard_summary: pd.DataFrame,
    guard_checks: pd.DataFrame | None = None,
    *,
    open_orders: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
    config: HaltResponseConfig | None = None,
) -> HaltResponseReport:
    config = config or HaltResponseConfig()
    guard_summary = _require_guard_summary(guard_summary)
    guard_checks = pd.DataFrame() if guard_checks is None else guard_checks.copy()
    open_orders = pd.DataFrame() if open_orders is None else open_orders.copy()
    positions = pd.DataFrame() if positions is None else positions.copy()

    guard_row = guard_summary.iloc[0]
    guard_context = _guard_halt_context(guard_row, guard_checks)
    cancel_orders = _cancel_actions(open_orders, guard_context)
    flatten_orders = _flatten_actions(positions, config, guard_context)
    checks = _checks(guard_row, cancel_orders, flatten_orders, config)
    action_queue = _action_queue(checks)
    summary = _summary_with_actions(
        _summary(guard_row, cancel_orders, flatten_orders, checks, guard_context),
        checks,
        action_queue,
    )
    failed_check_records = _failed_check_records(checks)
    action_statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    response_config = {
        **asdict(config),
        "strategy": guard_context["strategy"],
        "market": guard_context["market"],
        "failed_check_count": len(failed_check_records),
        "failed_checks": [str(record.get("check", "")) for record in failed_check_records],
        "primary_blocker": failed_check_records[0] if failed_check_records else {},
        "action_queue_count": int(len(action_queue)),
        "ready_action_count": int((action_statuses == "ready").sum()) if not action_statuses.empty else 0,
        "blocked_action_count": int((action_statuses == "blocked").sum()) if not action_statuses.empty else 0,
        "review_action_count": int((action_statuses == "review").sum()) if not action_statuses.empty else 0,
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _first_action_value(action_queue, "queue_status"),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _actions_with_status(action_queue, "ready"),
        "blocked_actions": _actions_with_status(action_queue, "blocked"),
        "review_actions": _actions_with_status(action_queue, "review"),
        "guard_failed_checks": guard_context["failed_check_names"],
        "guard_failed_check_reasons": guard_context["failed_check_reasons"],
        "proof_freshness": _proof_freshness_config(guard_context),
        "broker_route_readiness": _broker_route_readiness_config(guard_context),
    }
    return HaltResponseReport(
        cancel_orders=cancel_orders,
        flatten_orders=flatten_orders,
        checks=checks,
        summary=summary,
        config=response_config,
        action_queue=action_queue,
    )


def write_halt_response_plan(
    *,
    guard_dir: str | Path,
    output_dir: str | Path,
    open_orders_path: str | Path | None = None,
    positions_path: str | Path | None = None,
    config: HaltResponseConfig | None = None,
) -> HaltResponseReport:
    guard = Path(guard_dir)
    guard_summary_path = guard / "runtime_guard_summary.csv" if guard.is_dir() else guard
    guard_checks_path = guard / "runtime_guard_checks.csv" if guard.is_dir() else None
    guard_summary = _read_required(guard_summary_path)
    guard_checks = pd.read_csv(guard_checks_path) if guard_checks_path and guard_checks_path.exists() else None
    open_orders = _read_optional(open_orders_path)
    positions = _read_optional(positions_path)

    config = config or HaltResponseConfig()
    report = evaluate_halt_response(
        guard_summary,
        guard_checks,
        open_orders=open_orders,
        positions=positions,
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.cancel_orders.to_csv(out / "halt_cancel_orders.csv", index=False)
    report.flatten_orders.to_csv(out / "halt_flatten_orders.csv", index=False)
    report.checks.to_csv(out / "halt_response_checks.csv", index=False)
    report.summary.to_csv(out / "halt_response_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "halt_response_action_queue.csv", index=False)
    (out / "halt_response_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    (out / "halt_response_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="halt_response_plan",
        parameters={"config": asdict(config)},
        inputs=_manifest_inputs(
            guard_summary_path=guard_summary_path,
            guard_checks_path=guard_checks_path,
            open_orders_path=open_orders_path,
            positions_path=positions_path,
        ),
    )
    return HaltResponseReport(
        report.cancel_orders,
        report.flatten_orders,
        report.checks,
        report.summary,
        report.config,
        out,
        action_queue,
    )


def _manifest_inputs(
    *,
    guard_summary_path: Path,
    guard_checks_path: Path | None,
    open_orders_path: str | Path | None,
    positions_path: str | Path | None,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {"guard_summary": guard_summary_path}
    if guard_checks_path is not None and guard_checks_path.exists():
        inputs["guard_checks"] = guard_checks_path
    if open_orders_path is not None:
        inputs["open_orders"] = Path(open_orders_path)
    if positions_path is not None:
        inputs["positions"] = Path(positions_path)
    return inputs


def _cancel_actions(open_orders: pd.DataFrame, guard_context: dict[str, object]) -> pd.DataFrame:
    if open_orders.empty:
        return pd.DataFrame(columns=CANCEL_COLUMNS)
    frame = open_orders.copy().reset_index(drop=True)
    frame["client_order_id"] = _column_or_default(frame, "client_order_id", "")
    frame["broker_order_id"] = _column_or_default(frame, "broker_order_id", "")
    frame["instrument_id"] = _column_or_default(frame, "instrument_id", "")
    frame["side"] = _numeric_column(frame, "side", np.nan)
    frame["side_text"] = _side_text(frame)
    frame["status"] = _column_or_default(frame, "status", "open").astype(str).str.strip().str.lower()
    frame["open_qty"] = _open_qty(frame)
    active = frame.loc[(~frame["status"].isin(TERMINAL_STATUSES)) & (frame["open_qty"] > 0)].copy()
    active["action_id"] = [f"CXL-{idx:06d}" for idx in range(len(active))]
    active["action"] = "cancel_order"
    active["strategy"] = guard_context["strategy"]
    active["market"] = guard_context["market"]
    _assign_proof_refresh_columns(active, guard_context)
    _assign_broker_route_readiness_columns(active, guard_context)
    active["reason"] = "guard_halt_open_order"
    active["guard_failed_check_names"] = guard_context["failed_check_names_text"]
    active["guard_first_failed_reason"] = guard_context["first_failed_reason"]
    return active[CANCEL_COLUMNS].reset_index(drop=True)


def _flatten_actions(
    positions: pd.DataFrame,
    config: HaltResponseConfig,
    guard_context: dict[str, object],
) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(columns=FLATTEN_COLUMNS)
    frame = positions.copy().reset_index(drop=True)
    if "instrument_id" not in frame.columns:
        raise ValueError("positions must contain instrument_id")
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["net_qty"] = _net_qty(frame)
    active = frame.loc[frame["net_qty"] != 0].copy()
    active["side"] = np.where(active["net_qty"] > 0, -1, 1)
    active["side_text"] = np.where(active["side"] > 0, "BUY", "SELL")
    active["qty"] = active["net_qty"].abs()
    active["price"] = [_flatten_price(row) for row in active.to_dict("records")]
    active["order_type"] = str(config.default_order_type)
    active["time_in_force"] = str(config.default_time_in_force)
    active["reason"] = "flatten_residual_position"
    active["strategy"] = guard_context["strategy"]
    active["market"] = guard_context["market"]
    _assign_proof_refresh_columns(active, guard_context)
    _assign_broker_route_readiness_columns(active, guard_context)
    active["guard_failed_check_names"] = guard_context["failed_check_names_text"]
    active["guard_first_failed_reason"] = guard_context["first_failed_reason"]
    active["action"] = "flatten_position"
    active["action_id"] = [f"FLT-{idx:06d}" for idx in range(len(active))]
    return active[FLATTEN_COLUMNS].reset_index(drop=True)


def _checks(
    guard_row: pd.Series,
    cancel_orders: pd.DataFrame,
    flatten_orders: pd.DataFrame,
    config: HaltResponseConfig,
) -> pd.DataFrame:
    guard_halted = _to_bool(guard_row.get("halted", False)) or str(guard_row.get("guard_action", "")) == "halt"
    checks = [
        _check(
            "guard_halted",
            guard_halted,
            "is",
            True,
            guard_halted or not config.require_guard_halt,
            "runtime guard has not requested a halt",
        ),
        _check(
            "cancel_actions_available",
            int(len(cancel_orders)),
            ">=",
            0,
            True,
            "",
        ),
    ]
    missing_prices = int(flatten_orders["price"].isna().sum()) if not flatten_orders.empty else 0
    checks.append(
        _check(
            "flatten_prices_available",
            missing_prices,
            "==",
            0,
            missing_prices == 0 or not config.require_flatten_prices,
            "one or more residual positions do not have executable flatten prices",
        )
    )
    checks.append(
        _check(
            "response_plan_coherent",
            int(len(cancel_orders) + len(flatten_orders)),
            ">=",
            0,
            True,
            "",
        )
    )
    return pd.DataFrame(checks)


def _failed_check_records(checks: pd.DataFrame) -> list[dict[str, object]]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool)]
    return [_jsonable_check_record(row) for row in failed.to_dict(orient="records")]


def _jsonable_check_record(row: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable(value) for key, value in row.items()}


def _jsonable(value: object) -> object:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _summary(
    guard_row: pd.Series,
    cancel_orders: pd.DataFrame,
    flatten_orders: pd.DataFrame,
    checks: pd.DataFrame,
    guard_context: dict[str, object],
) -> pd.DataFrame:
    failed_rows = _failed_check_rows(checks)
    primary_blocker = _first_failed_check(failed_rows)
    failed = int(len(failed_rows)) if not checks.empty else 1
    ready = failed == 0
    action_count = int(len(cancel_orders) + len(flatten_orders))
    recommendation = "do_not_execute_response_until_inputs_fixed"
    if ready and action_count:
        recommendation = "submit_cancel_and_flatten"
    elif ready:
        recommendation = "halt_confirmed_no_open_risk"
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": str(guard_row.get("guard_action", "")),
                "strategy": str(guard_context["strategy"]),
                "market": str(guard_context["market"]),
                "cancel_orders": int(len(cancel_orders)),
                "flatten_orders": int(len(flatten_orders)),
                "open_risk_items": action_count,
                "failed_checks": failed,
                "failed_check_count": failed,
                "failed_check_names": _failed_check_names(failed_rows),
                "first_failed_reason": _check_reason(primary_blocker),
                "primary_blocker_check": _check_name(primary_blocker),
                "primary_blocker_value": _check_value(primary_blocker, "value"),
                "primary_blocker_operator": _check_value(primary_blocker, "operator"),
                "primary_blocker_threshold": _check_value(primary_blocker, "threshold"),
                "primary_blocker_reason": _check_reason(primary_blocker),
                "guard_failed_check_names": guard_context["failed_check_names_text"],
                "guard_first_failed_reason": guard_context["first_failed_reason"],
                "guard_failed_check_reasons": guard_context["failed_check_reasons_text"],
                **_proof_refresh_summary_fields(guard_context),
                **_broker_route_readiness_summary_fields(guard_context),
                "scenario_key": str(guard_row.get("scenario_key", "")),
                "adapter": str(guard_row.get("adapter", "")),
                "recommendation": recommendation,
            }
        ]
    )


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
    out["failed_check_names"] = _failed_check_names(failed)
    out["first_failed_reason"] = _check_reason(_first_failed_check(failed))
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _check_name(row)
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "halt_response_checks",
                "component": _component(check),
                "check": check,
                "actual": row.get("value"),
                "operator": _check_value(row, "operator"),
                "expected": row.get("threshold"),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "reason": _check_reason(row),
                "recommendation": _action_recommendation(check),
            }
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _component(check: str) -> str:
    if check == "guard_halted":
        return "runtime_guard"
    if check == "flatten_prices_available":
        return "flatten_price_inputs"
    if check == "cancel_actions_available":
        return "cancel_actions"
    if check == "response_plan_coherent":
        return "halt_response"
    return "halt_response"


def _next_gate(check: str) -> str:
    if check == "guard_halted":
        return "monitor-scaleup-guard"
    if check in {"flatten_prices_available", "cancel_actions_available", "response_plan_coherent"}:
        return "plan-halt-response"
    return "plan-halt-response"


def _action_recommendation(check: str) -> str:
    if check == "guard_halted":
        return "rerun_runtime_guard_or_allow_continue_guard"
    if check == "flatten_prices_available":
        return "supply_executable_flatten_prices_or_allow_missing_flatten_prices"
    if check == "cancel_actions_available":
        return "repair_cancel_action_inputs"
    if check == "response_plan_coherent":
        return "repair_or_rerun_halt_response_plan"
    return "repair_halt_response_inputs"


def _runbook_markdown(summary: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary.get("ready", False)) else "no"
    lines = [
        "# Halt Response Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Strategy: {_clean(summary.get('strategy'))}",
        f"- Market: {_clean(summary.get('market'))}",
        f"- Scenario: {_clean(summary.get('scenario_key'))}",
        f"- Adapter: {_clean(summary.get('adapter'))}",
        f"- Guard action: {_clean(summary.get('guard_action'))}",
        f"- Guard failed checks: {_clean(summary.get('guard_failed_check_names'))}",
        f"- Cancel orders: {_int_value(summary.get('cancel_orders'))}",
        f"- Flatten orders: {_int_value(summary.get('flatten_orders'))}",
        f"- Open risk items: {_int_value(summary.get('open_risk_items'))}",
        f"- Failed checks: {_int_value(summary.get('failed_check_count'))}",
        f"- Blocked actions: {_int_value(summary.get('blocked_action_count'))}",
        f"- Recommendation: {_clean(summary.get('recommendation'))}",
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
        return "No halt-response actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _clean(item.get("priority")),
                    _clean(item.get("queue_status")),
                    _clean(item.get("component")),
                    _clean(item.get("check")),
                    _clean(item.get("actual")),
                    _clean(item.get("expected")),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _clean(item.get("reason")),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_check_record(row) for row in action_queue.to_dict(orient="records")]


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> list[dict[str, object]]:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return []
    rows = action_queue.loc[action_queue["queue_status"].astype(str) == status]
    return [_jsonable_check_record(row) for row in rows.to_dict(orient="records")]


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_check_record(dict(action_queue.iloc[0]))


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _clean(action_queue.iloc[0].get(column))


def _help_command(next_gate: str) -> str:
    gate = _clean(next_gate)
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _clean(value)
    return f"`{text}`" if text else ""


def _int_value(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[:0].copy()
    return checks.loc[~checks["passed"].map(_to_bool)].copy().reset_index(drop=True)


def _first_failed_check(failed_rows: pd.DataFrame) -> pd.Series:
    if failed_rows.empty:
        return pd.Series(dtype=object)
    return failed_rows.iloc[0]


def _failed_check_names(failed_rows: pd.DataFrame) -> str:
    names = [_check_name(row) for _, row in failed_rows.iterrows()]
    return ";".join(name for name in names if name)


def _check_name(row: pd.Series) -> str:
    if row.empty:
        return ""
    return _clean(row.get("check"))


def _check_value(row: pd.Series, column: str) -> str:
    if row.empty:
        return ""
    return _clean(row.get(column))


def _check_reason(row: pd.Series) -> str:
    if row.empty:
        return ""
    return _clean(row.get("reason"))


def _require_guard_summary(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        raise ValueError("guard summary is empty")
    required = {"guard_action"}
    missing = sorted(required - set(summary.columns))
    if missing:
        raise ValueError(f"guard summary missing columns: {', '.join(missing)}")
    return summary.copy().reset_index(drop=True)


def _read_required(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required CSV not found: {file_path}")
    return pd.read_csv(file_path)


def _read_optional(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"optional CSV path was provided but not found: {file_path}")
    return pd.read_csv(file_path)


def _column_or_default(frame: pd.DataFrame, column: str, default: object) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series([default] * len(frame), index=frame.index)


def _numeric_column(frame: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([default] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _open_qty(frame: pd.DataFrame) -> pd.Series:
    for column in ("open_qty", "leaves_qty", "remaining_qty"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    qty = _numeric_column(frame, "qty", 0.0).fillna(0.0)
    filled = _numeric_column(frame, "filled_qty", 0.0).fillna(0.0)
    return (qty - filled).clip(lower=0.0)


def _net_qty(frame: pd.DataFrame) -> pd.Series:
    for column in ("net_qty", "position", "qty"):
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    raise ValueError("positions must contain net_qty, position, or qty")


def _side_text(frame: pd.DataFrame) -> pd.Series:
    if "side_text" in frame.columns:
        return frame["side_text"].astype(str).str.upper()
    side = _numeric_column(frame, "side", np.nan)
    return side.map({1.0: "BUY", -1.0: "SELL"}).fillna("UNKNOWN")


def _flatten_price(row: dict[str, Any]) -> float:
    side = int(row["side"])
    columns = ("market_ask", "ask", "best_ask", "last", "price") if side > 0 else (
        "market_bid",
        "bid",
        "best_bid",
        "last",
        "price",
    )
    for column in columns:
        value = row.get(column, np.nan)
        if not pd.isna(value):
            return float(value)
    return float("nan")


def _failed_guard_checks(guard_checks: pd.DataFrame) -> list[str]:
    if guard_checks.empty or "passed" not in guard_checks.columns or "check" not in guard_checks.columns:
        return []
    failed = guard_checks.loc[~guard_checks["passed"].map(_to_bool), "check"]
    return [str(item) for item in failed.tolist()]


def _guard_halt_context(guard_row: pd.Series, guard_checks: pd.DataFrame) -> dict[str, object]:
    names = _failed_guard_checks(guard_checks)
    if not names:
        names = _split_text_cell(guard_row.get("failed_check_names", ""))
    reasons = _failed_guard_reasons(guard_checks)
    if not reasons:
        reasons = _split_text_cell(guard_row.get("failed_check_reasons", ""))
    first_reason = _clean(guard_row.get("first_failed_reason", ""))
    if not first_reason and reasons:
        first_reason = reasons[0]
    return {
        "strategy": _clean(guard_row.get("strategy", "")),
        "market": _clean(guard_row.get("market", "")),
        "failed_check_names": names,
        "failed_check_names_text": ";".join(names),
        "first_failed_reason": first_reason,
        "failed_check_reasons": reasons,
        "failed_check_reasons_text": ";".join(reasons),
        **_proof_refresh_context(guard_row),
        **_broker_route_readiness_context(guard_row),
    }


def _failed_guard_reasons(guard_checks: pd.DataFrame) -> list[str]:
    if guard_checks.empty or "passed" not in guard_checks.columns:
        return []
    failed = guard_checks.loc[~guard_checks["passed"].map(_to_bool)].copy()
    if failed.empty:
        return []
    names = failed["check"].astype(str) if "check" in failed.columns else pd.Series(["check"] * len(failed))
    reasons = failed["reason"].astype(str) if "reason" in failed.columns else pd.Series([""] * len(failed))
    out: list[str] = []
    for name, reason in zip(names.tolist(), reasons.tolist(), strict=False):
        clean_reason = _clean(reason)
        out.append(f"{name}: {clean_reason}" if clean_reason else str(name))
    return out


def _split_text_cell(value: object) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [item.strip() for item in text.split(";") if item.strip()]


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "halt"}
    return bool(value)


def _proof_refresh_context(guard_row: pd.Series) -> dict[str, object]:
    return {
        "proof_refresh_required": _to_bool(guard_row.get("proof_refresh_required", False)),
        "proof_refresh_provided": _to_bool(guard_row.get("proof_refresh_provided", False)),
        "proof_refresh_ready": _to_bool(guard_row.get("proof_refresh_ready", False)),
        "proof_refresh_strategy": _clean(guard_row.get("proof_refresh_strategy", "")),
        "proof_refresh_market": _clean(guard_row.get("proof_refresh_market", "")),
        "proof_refresh_mixed_identity": _to_bool(guard_row.get("proof_refresh_mixed_identity", False)),
        "proof_source": _clean(guard_row.get("proof_source", "")),
    }


def _assign_proof_refresh_columns(frame: pd.DataFrame, guard_context: dict[str, object]) -> None:
    for column in PROOF_REFRESH_COLUMNS:
        frame[column] = guard_context[column]


def _broker_route_readiness_context(guard_row: pd.Series) -> dict[str, object]:
    return {
        "broker_route_readiness_required": _to_bool(
            guard_row.get("broker_route_readiness_required", False)
        ),
        "broker_route_readiness_provided": _to_bool(
            guard_row.get("broker_route_readiness_provided", False)
        ),
        "broker_route_readiness_ready": _to_bool(guard_row.get("broker_route_readiness_ready", False)),
        "broker_route_readiness_strategy": _clean(guard_row.get("broker_route_readiness_strategy", "")),
        "broker_route_readiness_market": _clean(guard_row.get("broker_route_readiness_market", "")),
        "broker_route_readiness_route_ready_pairs": _int_value(
            guard_row.get("broker_route_readiness_route_ready_pairs", 0)
        ),
        "broker_route_readiness_gap_pairs": _int_value(
            guard_row.get("broker_route_readiness_gap_pairs", 0)
        ),
        "broker_route_readiness_recommendation": _clean(
            guard_row.get("broker_route_readiness_recommendation", "")
        ),
        "broker_route_readiness_ops_launch_controls_ready": _to_bool(
            guard_row.get("broker_route_readiness_ops_launch_controls_ready", False)
        ),
        "broker_route_readiness_ops_launch_control_failures": _clean(
            guard_row.get("broker_route_readiness_ops_launch_control_failures", "")
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _int_value(
            guard_row.get("broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0)
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _int_value(
            guard_row.get("broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0)
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": _int_value(
            guard_row.get(
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0,
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": _int_value(
            guard_row.get(
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0,
            )
        ),
    }


def _assign_broker_route_readiness_columns(frame: pd.DataFrame, guard_context: dict[str, object]) -> None:
    for column in BROKER_ROUTE_READINESS_COLUMNS:
        frame[column] = guard_context[column]


def _proof_refresh_summary_fields(guard_context: dict[str, object]) -> dict[str, object]:
    return {column: guard_context[column] for column in PROOF_REFRESH_COLUMNS}


def _broker_route_readiness_summary_fields(guard_context: dict[str, object]) -> dict[str, object]:
    return {column: guard_context[column] for column in BROKER_ROUTE_READINESS_COLUMNS}


def _proof_freshness_config(guard_context: dict[str, object]) -> dict[str, object]:
    return {
        "required": bool(guard_context["proof_refresh_required"]),
        "provided": bool(guard_context["proof_refresh_provided"]),
        "ready": bool(guard_context["proof_refresh_ready"]),
        "strategy": str(guard_context["proof_refresh_strategy"]),
        "market": str(guard_context["proof_refresh_market"]),
        "mixed_identity": bool(guard_context["proof_refresh_mixed_identity"]),
        "proof_source": str(guard_context["proof_source"]),
    }


def _broker_route_readiness_config(guard_context: dict[str, object]) -> dict[str, object]:
    return {
        "required": bool(guard_context["broker_route_readiness_required"]),
        "provided": bool(guard_context["broker_route_readiness_provided"]),
        "ready": bool(guard_context["broker_route_readiness_ready"]),
        "strategy": str(guard_context["broker_route_readiness_strategy"]),
        "market": str(guard_context["broker_route_readiness_market"]),
        "route_ready_pairs": int(guard_context["broker_route_readiness_route_ready_pairs"]),
        "gap_pairs": int(guard_context["broker_route_readiness_gap_pairs"]),
        "recommendation": str(guard_context["broker_route_readiness_recommendation"]),
        "ops_launch_controls_ready": bool(
            guard_context["broker_route_readiness_ops_launch_controls_ready"]
        ),
        "ops_launch_control_failures": str(
            guard_context["broker_route_readiness_ops_launch_control_failures"]
        ),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            guard_context["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            guard_context["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            guard_context[
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
            ]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            guard_context[
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
            ]
        ),
    }


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
