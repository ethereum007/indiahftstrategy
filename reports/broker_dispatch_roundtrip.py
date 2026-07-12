from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    broker_dispatch_ack_lineage_fields,
    broker_dispatch_ack_lineage_manifest_inputs,
    empty_broker_dispatch_ack_lineage,
    load_broker_dispatch_ack_lineage,
)
from reports.vendor_market_data import (
    select_vendor_market_data_batch_source,
    vendor_market_data_batch_source_active,
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
    "target_mode",
    "strategy",
    "market",
    "scenario_key",
    "adapter",
    "next_gate",
    "next_gate_help_command",
    "reason",
    "recommendation",
]
BROKER_DISPATCH_ACK_LINEAGE_OUTPUT_COLUMNS = tuple(
    broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage()
    ).keys()
)


@dataclass(frozen=True)
class BrokerDispatchRoundTripThresholds:
    target_mode: str = "live_dryrun"
    require_dispatch_ready: bool = True
    require_send_ready: bool = True
    require_ack_passed: bool = True
    require_identity_match: bool = True
    require_submission_disabled: bool = True
    require_all_requests_acked: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    require_ack_lineage: bool = False
    allow_rejections: bool = False
    max_duplicate_ack_orders: int = 0
    max_unmatched_acks: int = 0
    max_missing_request_acks: int = 0
    max_total_failed_component_checks: int = 0


@dataclass(frozen=True)
class BrokerDispatchRoundTripReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_broker_dispatch_roundtrip(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    send_summary: pd.DataFrame,
    send_requests: pd.DataFrame,
    ack_summary: pd.DataFrame,
    acknowledgements: pd.DataFrame,
    dispatch_config: dict[str, Any] | None = None,
    send_config: dict[str, Any] | None = None,
    ack_config: dict[str, Any] | None = None,
    broker_dispatch_ack_lineage: dict[str, Any] | None = None,
    thresholds: BrokerDispatchRoundTripThresholds | None = None,
) -> BrokerDispatchRoundTripReport:
    thresholds = thresholds or BrokerDispatchRoundTripThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")
    send_summary = _require_nonempty(send_summary, "send_summary")
    send_requests = _require_nonempty(send_requests, "send_requests")
    ack_summary = _require_nonempty(ack_summary, "ack_summary")
    acknowledgements = _require_nonempty(acknowledgements, "acknowledgements")
    dispatch_row = _component_summary_state(dispatch_summary.iloc[0], dispatch_config or {})
    send_row = _component_summary_state(send_summary.iloc[0], send_config or {})
    ack_row = _component_summary_state(ack_summary.iloc[0], ack_config or {})
    ack_lineage_fields = broker_dispatch_ack_lineage_fields(
        broker_dispatch_ack_lineage
        or empty_broker_dispatch_ack_lineage(
            required=thresholds.require_ack_lineage
        )
    )
    for column, value in ack_lineage_fields.items():
        ack_row[column] = value

    orders = _roundtrip_orders(dispatch_orders, send_requests, acknowledgements)
    for column, value in ack_lineage_fields.items():
        orders[column] = value
    orders["authorizes_submission"] = False
    checks = _checks(
        dispatch_row,
        send_row,
        ack_row,
        dispatch_orders,
        send_requests,
        orders,
        thresholds,
    )
    summary = _summary(
        dispatch_row,
        send_row,
        ack_row,
        orders,
        checks,
        thresholds,
    )
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(summary.iloc[0], thresholds, checks, action_queue)
    return BrokerDispatchRoundTripReport(
        orders=orders,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_broker_dispatch_roundtrip(
    *,
    dispatch_dir: str | Path,
    send_dir: str | Path,
    ack_dir: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchRoundTripThresholds | None = None,
) -> BrokerDispatchRoundTripReport:
    thresholds = thresholds or BrokerDispatchRoundTripThresholds()
    _validate_thresholds(thresholds)
    dispatch = Path(dispatch_dir).resolve()
    send = Path(send_dir).resolve()
    ack = Path(ack_dir).resolve()
    dispatch_summary_path = dispatch / "broker_dispatch_summary.csv"
    dispatch_orders_path = dispatch / "broker_dispatch_orders.csv"
    dispatch_config_path = dispatch / "broker_dispatch_config.json"
    dispatch_manifest_path = dispatch / "manifest.json"
    send_summary_path = send / "broker_dispatch_send_summary.csv"
    send_requests_path = send / "broker_dispatch_send_requests.csv"
    send_config_path = send / "broker_dispatch_send_config.json"
    send_manifest_path = send / "manifest.json"
    ack_summary_path = ack / "broker_dispatch_ack_summary.csv"
    acknowledgements_path = ack / "broker_dispatch_acknowledgements.csv"
    ack_config_path = ack / "broker_dispatch_ack_config.json"
    ack_manifest_path = ack / "manifest.json"
    dispatch_config = _read_optional_json(dispatch_config_path)
    send_config = _read_optional_json(send_config_path)
    ack_config = _read_optional_json(ack_config_path)
    ack_lineage = empty_broker_dispatch_ack_lineage(
        required=thresholds.require_ack_lineage
    )
    if thresholds.require_ack_lineage:
        ack_lineage = load_broker_dispatch_ack_lineage(
            ack_config_path,
            expected_broker_dispatch_send_config_path=send_config_path,
            expected_broker_dispatch_config_path=dispatch_config_path,
        )
    send_dispatch_manifest_path = _manifest_input_path(send_manifest_path, "dispatch_manifest")
    ack_dispatch_manifest_path = _manifest_input_path(ack_manifest_path, "dispatch_manifest")
    broker_readiness_config_path = (
        _broker_readiness_config_from_dispatch_manifest(dispatch_manifest_path)
        or _broker_readiness_config_from_dispatch_manifest(send_dispatch_manifest_path)
        or _broker_readiness_config_from_dispatch_manifest(ack_dispatch_manifest_path)
    )
    if broker_readiness_config_path is not None:
        broker_readiness_config = json.loads(broker_readiness_config_path.read_text(encoding="utf-8"))
        dispatch_config = _with_broker_readiness_config_vendor_market_data_batch(
            dispatch_config,
            broker_readiness_config,
            target_key="route_broker_dispatch_roundtrip_vendor_market_data_batch",
            target_readiness_key="route_broker_vendor_data_readiness",
        )
        send_config = _with_broker_readiness_config_vendor_market_data_batch(
            send_config,
            broker_readiness_config,
            target_key="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            target_readiness_key="dispatch_broker_vendor_data_readiness",
        )
        ack_config = _with_broker_readiness_config_vendor_market_data_batch(
            ack_config,
            broker_readiness_config,
            target_key="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            target_readiness_key="ack_broker_vendor_data_readiness",
        )
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=_read_required(dispatch_summary_path, "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch_orders_path, "broker_dispatch_orders"),
        send_summary=_read_required(send_summary_path, "broker_dispatch_send_summary"),
        send_requests=_read_required(send_requests_path, "broker_dispatch_send_requests"),
        ack_summary=_read_required(ack_summary_path, "broker_dispatch_ack_summary"),
        acknowledgements=_read_required(
            acknowledgements_path,
            "broker_dispatch_acknowledgements",
        ),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
        broker_dispatch_ack_lineage=ack_lineage,
        thresholds=thresholds,
    )
    out = Path(output_dir).resolve()
    _reject_input_output_collision(
        out,
        {
            "broker dispatch": dispatch,
            "broker dispatch send": send,
            "broker dispatch acknowledgement": ack,
        },
    )
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / "broker_dispatch_roundtrip_orders.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_roundtrip_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_roundtrip_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(
        report.summary.iloc[0], report.checks
    )
    action_queue.to_csv(out / "broker_dispatch_roundtrip_action_queue.csv", index=False)
    (out / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "broker_dispatch_roundtrip_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    manifest_inputs: dict[str, Any] = _manifest_inputs(
        dispatch_summary=dispatch_summary_path,
        dispatch_orders=dispatch_orders_path,
        dispatch_config=dispatch_config_path,
        dispatch_manifest=dispatch_manifest_path,
        send_summary=send_summary_path,
        send_requests=send_requests_path,
        send_config=send_config_path,
        send_manifest=send_manifest_path,
        ack_summary=ack_summary_path,
        acknowledgements=acknowledgements_path,
        ack_config=ack_config_path,
        ack_manifest=ack_manifest_path,
    )
    manifest_inputs.update(
        broker_dispatch_ack_lineage_manifest_inputs(ack_lineage)
    )
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_roundtrip",
        parameters={"thresholds": asdict(thresholds)},
        inputs=manifest_inputs,
        extra={
            "passed": bool(report.passed),
            **broker_dispatch_ack_lineage_fields(ack_lineage),
            "authorizes_submission": False,
        },
    )
    return BrokerDispatchRoundTripReport(
        report.orders,
        report.checks,
        report.summary,
        report.config,
        out,
        action_queue,
    )


def _manifest_inputs(**paths: Path) -> dict[str, Path]:
    return {name: path for name, path in paths.items() if path.exists()}


def _manifest_input_path(manifest_path: Path | None, input_name: str) -> Path | None:
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = (manifest.get("inputs", {}) or {}).get(input_name)
    raw_path = value.get("path") if isinstance(value, dict) else value
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path if path.exists() else None


def _broker_readiness_config_from_dispatch_manifest(dispatch_manifest_path: Path | None) -> Path | None:
    route_manifest_path = _manifest_input_path(dispatch_manifest_path, "route_enable_manifest")
    cutover_manifest_path = _manifest_input_path(route_manifest_path, "cutover_manifest")
    return _manifest_input_path(cutover_manifest_path, "broker_readiness_config")


def _roundtrip_orders(
    dispatch_orders: pd.DataFrame,
    send_requests: pd.DataFrame,
    acknowledgements: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, dispatch in dispatch_orders.reset_index(drop=True).iterrows():
        dispatch_order_id = _text(dispatch, "dispatch_order_id")
        source_order_id = _text(dispatch, "source_order_id")
        send_matches = _matches(send_requests, "dispatch_order_id", dispatch_order_id)
        ack_matches = _matches(acknowledgements, "dispatch_order_id", dispatch_order_id)
        ack = ack_matches.iloc[-1] if not ack_matches.empty else pd.Series(dtype=object)
        request = send_matches.iloc[-1] if not send_matches.empty else pd.Series(dtype=object)
        rows.append(
            {
                "dispatch_batch_id": _text(dispatch, "dispatch_batch_id"),
                "dispatch_order_id": dispatch_order_id,
                "dispatch_route_roundtrip_batch_id": _text(dispatch, "route_dispatch_roundtrip_batch_id"),
                "source_order_id": source_order_id,
                "target_mode": _text(dispatch, "target_mode"),
                "strategy": _text(dispatch, "strategy"),
                "market": _text(dispatch, "market"),
                "scenario_key": _text(dispatch, "scenario_key"),
                "adapter": _text(dispatch, "adapter"),
                "request_count": int(len(send_matches)),
                "request_id": _text(request, "request_id"),
                "request_route_roundtrip_batch_id": _text(request, "route_dispatch_roundtrip_batch_id"),
                "idempotency_key": _text(request, "idempotency_key"),
                "request_payload_hash": _text(request, "request_payload_hash"),
                "request_payload_valid": _to_bool(request.get("payload_valid", False)) if not request.empty else False,
                "request_submission_enabled": _to_bool(request.get("submission_enabled", False))
                if not request.empty
                else False,
                "request_dry_run_only": _to_bool(request.get("dry_run_only", False)) if not request.empty else False,
                "ack_row_present": not ack.empty,
                "ack_route_roundtrip_batch_id": _text(ack, "route_dispatch_roundtrip_batch_id"),
                "ack_dispatch_order_route_roundtrip_batch_id": _text(
                    ack,
                    "dispatch_order_route_roundtrip_batch_id",
                ),
                "ack_raw_route_roundtrip_batch_ids": _text(ack, "ack_route_dispatch_roundtrip_batch_ids"),
                "ack_count": int(_number(ack, "ack_count", 0.0)) if not ack.empty else 0,
                "ack_status": _text(ack, "ack_status"),
                "broker_order_id": _text(ack, "broker_order_id"),
                "acked": _to_bool(ack.get("acked", False)) if not ack.empty else False,
                "rejected": _to_bool(ack.get("rejected", False)) if not ack.empty else False,
                "duplicate_ack": _to_bool(ack.get("duplicate_ack", False)) if not ack.empty else False,
                "missing_ack": _to_bool(ack.get("missing_ack", True)) if not ack.empty else True,
            }
        )
    return pd.DataFrame(rows)


def _component_summary_state(row: pd.Series, config: dict[str, Any]) -> pd.Series:
    state = row.copy()
    strategy_portfolio = config.get("strategy_portfolio", {}) or {}
    upload = config.get("upload", {}) or {}
    dispatch = config.get("dispatch", {}) or {}
    if strategy_portfolio:
        state["strategy_portfolio_required"] = _to_bool(
            strategy_portfolio.get("required", state.get("strategy_portfolio_required", False))
        )
        state["strategy_portfolio_provided"] = _to_bool(
            strategy_portfolio.get("provided", state.get("strategy_portfolio_provided", False))
        )
        state["strategy_portfolio_ready"] = _to_bool(
            strategy_portfolio.get("ready", state.get("strategy_portfolio_ready", False))
        )
        state["strategy_portfolio_deployment_mode"] = _first_text(
            strategy_portfolio.get("deployment_mode", ""),
            state.get("strategy_portfolio_deployment_mode", ""),
        )
        state["strategy_portfolio_allocation_mode"] = _first_text(
            strategy_portfolio.get("allocation_mode", ""),
            state.get("strategy_portfolio_allocation_mode", ""),
        )
        state["strategy_portfolio_capital_currency"] = _first_text(
            strategy_portfolio.get("capital_currency", ""),
            state.get("strategy_portfolio_capital_currency", ""),
        )
        state["strategy_portfolio_selected_profile"] = _first_text(
            strategy_portfolio.get("selected_profile", ""),
            state.get("strategy_portfolio_selected_profile", ""),
        )
        state["strategy_portfolio_selected_strategy"] = _identity_key(
            _first_text(
                strategy_portfolio.get("selected_strategy", ""),
                state.get("strategy_portfolio_selected_strategy", ""),
            )
        )
        state["strategy_portfolio_selected_market"] = _identity_key(
            _first_text(
                strategy_portfolio.get("selected_market", ""),
                state.get("strategy_portfolio_selected_market", ""),
            )
        )
        state["strategy_portfolio_selected_eligible"] = _to_bool(
            strategy_portfolio.get("selected_eligible", state.get("strategy_portfolio_selected_eligible", False))
        )
        state["strategy_portfolio_selected_allocation_weight"] = _number_value(
            strategy_portfolio.get(
                "selected_allocation_weight",
                state.get("strategy_portfolio_selected_allocation_weight", 0.0),
            ),
            _number(state, "strategy_portfolio_selected_allocation_weight", 0.0),
        )
        state["strategy_portfolio_selected_allocation_notional"] = _number_value(
            strategy_portfolio.get(
                "selected_allocation_notional",
                state.get("strategy_portfolio_selected_allocation_notional", 0.0),
            ),
            _number(state, "strategy_portfolio_selected_allocation_notional", 0.0),
        )
        state["strategy_portfolio_notional_cap_applied"] = _to_bool(
            strategy_portfolio.get(
                "notional_cap_applied",
                state.get("strategy_portfolio_notional_cap_applied", False),
            )
        )
        state["strategy_portfolio_min_strategy_count"] = int(
            _number_value(
                strategy_portfolio.get(
                    "min_strategy_count",
                    state.get("strategy_portfolio_min_strategy_count", 0.0),
                ),
                _number(state, "strategy_portfolio_min_strategy_count", 0.0),
            )
        )
        state["strategy_portfolio_min_market_count"] = int(
            _number_value(
                strategy_portfolio.get(
                    "min_market_count",
                    state.get("strategy_portfolio_min_market_count", 0.0),
                ),
                _number(state, "strategy_portfolio_min_market_count", 0.0),
            )
        )
        state["strategy_portfolio_max_strategy_weight"] = _number_value(
            strategy_portfolio.get(
                "max_strategy_weight",
                state.get("strategy_portfolio_max_strategy_weight", 0.0),
            ),
            _number(state, "strategy_portfolio_max_strategy_weight", 0.0),
        )
        state["strategy_portfolio_max_market_weight"] = _number_value(
            strategy_portfolio.get(
                "max_market_weight",
                state.get("strategy_portfolio_max_market_weight", 0.0),
            ),
            _number(state, "strategy_portfolio_max_market_weight", 0.0),
        )
        state["strategy_portfolio_allocated_strategy_count"] = int(
            _number_value(
                strategy_portfolio.get(
                    "allocated_strategy_count",
                    state.get("strategy_portfolio_allocated_strategy_count", 0.0),
                ),
                _number(state, "strategy_portfolio_allocated_strategy_count", 0.0),
            )
        )
        state["strategy_portfolio_allocated_market_count"] = int(
            _number_value(
                strategy_portfolio.get(
                    "allocated_market_count",
                    state.get("strategy_portfolio_allocated_market_count", 0.0),
                ),
                _number(state, "strategy_portfolio_allocated_market_count", 0.0),
            )
        )
        state["strategy_portfolio_top_strategy_by_weight"] = _identity_key(
            _first_text(
                strategy_portfolio.get("top_strategy_by_weight", ""),
                state.get("strategy_portfolio_top_strategy_by_weight", ""),
            )
        )
        state["strategy_portfolio_top_market_by_weight"] = _identity_key(
            _first_text(
                strategy_portfolio.get("top_market_by_weight", ""),
                state.get("strategy_portfolio_top_market_by_weight", ""),
            )
        )
        state["strategy_portfolio_max_strategy_allocation_weight"] = _number_value(
            strategy_portfolio.get(
                "max_strategy_allocation_weight",
                state.get("strategy_portfolio_max_strategy_allocation_weight", 0.0),
            ),
            _number(state, "strategy_portfolio_max_strategy_allocation_weight", 0.0),
        )
        state["strategy_portfolio_max_market_allocation_weight"] = _number_value(
            strategy_portfolio.get(
                "max_market_allocation_weight",
                state.get("strategy_portfolio_max_market_allocation_weight", 0.0),
            ),
            _number(state, "strategy_portfolio_max_market_allocation_weight", 0.0),
        )
        state["pre_portfolio_max_notional_per_session"] = _number_value(
            strategy_portfolio.get(
                "pre_portfolio_max_notional_per_session",
                state.get("pre_portfolio_max_notional_per_session", 0.0),
            ),
            _number(state, "pre_portfolio_max_notional_per_session", 0.0),
        )
    state["dispatch_total_notional"] = _number_value(
        upload.get(
            "total_notional",
            dispatch.get("total_notional", state.get("dispatch_total_notional", 0.0)),
        ),
        _number(state, "dispatch_total_notional", 0.0),
    )
    broker_readiness = config.get("broker_readiness", {}) or {}
    if "adapter_schema_status" in broker_readiness:
        state["broker_schema_status"] = _object_text(
            broker_readiness.get("adapter_schema_status", _text(state, "broker_schema_status"))
        )
    if "schema_reviewed" in broker_readiness:
        state["broker_schema_reviewed"] = _to_bool(
            broker_readiness.get("schema_reviewed", state.get("broker_schema_reviewed", False))
        )
    if "schema_review_mode" in broker_readiness:
        state["broker_schema_review_mode"] = _object_text(
            broker_readiness.get("schema_review_mode", _text(state, "broker_schema_review_mode"))
        )
    route_enable = config.get("route_enable_dispatch_roundtrip", {}) or {}
    if "failed_checks" in route_enable:
        state["route_enable_dispatch_roundtrip_failed_checks"] = int(
            _number_value(
                route_enable.get("failed_checks"),
                _number(state, "route_enable_dispatch_roundtrip_failed_checks", 0.0),
            )
        )
    route_readiness = config.get("route_readiness", {}) or {}
    if route_readiness:
        state["route_readiness_required"] = _to_bool(
            route_readiness.get("required", state.get("route_readiness_required", False))
        )
        state["route_readiness_provided"] = _to_bool(
            route_readiness.get("provided", state.get("route_readiness_provided", False))
        )
        state["route_readiness_ready"] = _to_bool(
            route_readiness.get("ready", state.get("route_readiness_ready", False))
        )
        state["route_readiness_strategy"] = _object_text(
            route_readiness.get("strategy", _text(state, "route_readiness_strategy"))
        )
        state["route_readiness_market"] = _object_text(
            route_readiness.get("market", _text(state, "route_readiness_market"))
        )
        state["route_readiness_route_ready_pairs"] = int(
            _number_value(
                route_readiness.get("route_ready_pairs"),
                _number(state, "route_readiness_route_ready_pairs", 0.0),
            )
        )
        state["route_readiness_gap_pairs"] = int(
            _number_value(route_readiness.get("gap_pairs"), _number(state, "route_readiness_gap_pairs", 0.0))
        )
        state["route_readiness_recommendation"] = _object_text(
            route_readiness.get("recommendation", _text(state, "route_readiness_recommendation"))
        )
        state["route_readiness_ops_launch_controls_present"] = _to_bool(
            route_readiness.get(
                "ops_launch_controls_present",
                state.get("route_readiness_ops_launch_controls_present", False),
            )
        )
        state["route_readiness_ops_launch_controls_blocked_pairs"] = int(
            _number_value(
                route_readiness.get("ops_launch_controls_blocked_pairs"),
                _number(state, "route_readiness_ops_launch_controls_blocked_pairs", 0.0),
            )
        )
        state["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_breach_pairs"),
                _number(state, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0),
            )
        )
        state["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_concentration_breach_pairs"),
                _number(
                    state,
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    0.0,
                ),
            )
        )
    route_broker_readiness = config.get("route_broker_route_readiness", {}) or {}
    if route_broker_readiness:
        _apply_route_broker_route_readiness_config(state, route_broker_readiness)
    route_broker_resume_gate = config.get("route_broker_resume_gate", {}) or {}
    if not isinstance(route_broker_resume_gate, dict):
        route_broker_resume_gate = {}
    resume_broker_route_readiness = route_broker_resume_gate.get("broker_route_readiness", {}) or {}
    if resume_broker_route_readiness:
        _apply_resume_route_readiness_config(
            state,
            resume_broker_route_readiness,
            field_prefix="route_broker_resume_broker_route_readiness",
        )
    resume_incident_route_readiness = (
        route_broker_resume_gate.get("incident_broker_route_readiness", {}) or {}
    )
    if resume_incident_route_readiness:
        _apply_resume_route_readiness_config(
            state,
            resume_incident_route_readiness,
            field_prefix="route_broker_resume_incident_broker_route_readiness",
        )
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    if shadow_broker:
        _apply_shadow_broker_readiness_config(
            state,
            shadow_broker,
            field_prefix="shadow_broker",
        )
    route_broker_shadow = config.get("route_broker_shadow_broker_readiness", {}) or {}
    if route_broker_shadow:
        _apply_shadow_broker_readiness_config(
            state,
            route_broker_shadow,
            field_prefix="route_broker_shadow_broker",
        )
    broker_vendor_data_readiness, _broker_vendor_readiness_source_prefix = (
        _broker_vendor_data_readiness_source(config)
    )
    if broker_vendor_data_readiness:
        _apply_broker_vendor_data_readiness_config(state, broker_vendor_data_readiness)
    else:
        _copy_broker_vendor_data_readiness_fields(state)
    broker_vendor_market_data_batch, _broker_vendor_source_prefix = _broker_vendor_market_data_batch_source(
        state,
        config,
    )
    if broker_vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            broker_vendor_market_data_batch,
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefixes=(
                "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
                "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
                "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            ),
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    vendor_market_data_batch = (
        config.get("ack_vendor_market_data_batch", {})
        or config.get("dispatch_vendor_market_data_batch", {})
        or config.get("route_vendor_market_data_batch", {})
        or {}
    )
    if vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(state, vendor_market_data_batch)
    else:
        _copy_vendor_market_data_batch_fields(state)
    return state


def _broker_vendor_market_data_batch_source(
    state: pd.Series,
    config: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    candidates = (
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch",
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_vendor_market_data_batch",
    )
    vendor, field_prefix = select_vendor_market_data_batch_source(
        config,
        candidates,
        default_source="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    if vendor:
        return vendor, field_prefix
    for field_prefix in candidates:
        if any(
            f"{field_prefix}_{suffix}" in state
            for suffix in ("provided", "dataset_count", "datasets_json")
        ):
            return {}, field_prefix
    return {}, "ack_broker_dispatch_roundtrip_vendor_market_data_batch"


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
        (config.get("roundtrip_broker_vendor_data_readiness"), "roundtrip_broker_vendor_data_readiness"),
        (config.get("ack_broker_vendor_data_readiness"), "ack_broker_vendor_data_readiness"),
        (config.get("dispatch_broker_vendor_data_readiness"), "dispatch_broker_vendor_data_readiness"),
        (config.get("route_broker_vendor_data_readiness"), "route_broker_vendor_data_readiness"),
        (config.get("cutover_broker_vendor_data_readiness"), "cutover_broker_vendor_data_readiness"),
        (config.get("scaleup_broker_vendor_data_readiness"), "scaleup_broker_vendor_data_readiness"),
        (config.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness"),
    ]
    broker_readiness = config.get("broker_readiness", {}) or {}
    if isinstance(broker_readiness, dict):
        candidates.append(
            (broker_readiness.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
        broker_dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
        if isinstance(broker_dispatch, dict):
            candidates.append(
                (broker_dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
            )
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(
            (dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
    for candidate, source in candidates:
        if isinstance(candidate, dict) and _broker_vendor_data_readiness_source_active(candidate):
            return candidate, source
    return {}, "ack_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    component_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
    *,
    target_key: str,
    target_readiness_key: str,
) -> dict[str, Any]:
    vendor, _source = select_vendor_market_data_batch_source(
        component_config,
        (
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        sidecar_vendor, _source = select_vendor_market_data_batch_source(
            dispatch,
            (
                "broker_dispatch_roundtrip_vendor_market_data_batch",
                "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
                "vendor_market_data_batch",
                "roundtrip_vendor_market_data_batch",
            ),
            default_source="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    else:
        sidecar_vendor = {}
    should_hydrate_vendor = (
        not vendor_market_data_batch_source_active(vendor)
        and vendor_market_data_batch_source_active(sidecar_vendor)
    )
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(component_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(broker_readiness_config)
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    if not should_hydrate_vendor and not should_hydrate_readiness:
        return component_config

    out = dict(component_config)
    if should_hydrate_vendor:
        out[target_key] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out[target_readiness_key] = dict(sidecar_readiness)
    return out


def _apply_vendor_market_data_batch_config(
    state: pd.Series,
    vendor: dict[str, Any],
    *,
    field_prefix: str = "vendor_market_data_batch",
) -> None:
    comparison = vendor.get("comparison", {}) or {}
    state[f"{field_prefix}_provided"] = _to_bool(
        vendor.get("provided", state.get(f"{field_prefix}_provided", False))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        vendor.get("ready", state.get(f"{field_prefix}_ready", False))
    )
    state[f"{field_prefix}_adapter"] = _object_text(
        vendor.get("adapter", state.get(f"{field_prefix}_adapter", ""))
    )
    state[f"{field_prefix}_kind"] = _object_text(
        vendor.get("kind", state.get(f"{field_prefix}_kind", ""))
    )
    state[f"{field_prefix}_manifest_run_type"] = _identity_key(
        vendor.get("manifest_run_type", state.get(f"{field_prefix}_manifest_run_type", ""))
    )
    state[f"{field_prefix}_market"] = _object_text(
        vendor.get("market", state.get(f"{field_prefix}_market", ""))
    )
    state[f"{field_prefix}_dataset_count"] = int(
        _number_value(vendor.get("dataset_count"), _number(state, f"{field_prefix}_dataset_count", 0.0))
    )
    state[f"{field_prefix}_ready_datasets"] = int(
        _number_value(vendor.get("ready_datasets"), _number(state, f"{field_prefix}_ready_datasets", 0.0))
    )
    state[f"{field_prefix}_failed_datasets"] = int(
        _number_value(vendor.get("failed_datasets"), _number(state, f"{field_prefix}_failed_datasets", 0.0))
    )
    state[f"{field_prefix}_ready_rate"] = _number_value(
        vendor.get("ready_rate"),
        _number(state, f"{field_prefix}_ready_rate", 0.0),
    )
    state[f"{field_prefix}_unique_source_files"] = int(
        _number_value(
            vendor.get("unique_source_files"),
            _number(state, f"{field_prefix}_unique_source_files", 0.0),
        )
    )
    state[f"{field_prefix}_unique_header_fingerprints"] = int(
        _number_value(
            vendor.get("unique_header_fingerprints"),
            _number(state, f"{field_prefix}_unique_header_fingerprints", 0.0),
        )
    )
    state[f"{field_prefix}_source_file_fingerprint_coverage"] = _number_value(
        vendor.get("source_file_fingerprint_coverage"),
        _number(state, f"{field_prefix}_source_file_fingerprint_coverage", 0.0),
    )
    state[f"{field_prefix}_min_mapping_coverage"] = _number_value(
        vendor.get("min_mapping_coverage"),
        _number(state, f"{field_prefix}_min_mapping_coverage", 0.0),
    )
    state[f"{field_prefix}_unique_mapping_drafts"] = int(
        _number_value(
            vendor.get("unique_mapping_drafts"),
            _number(state, f"{field_prefix}_unique_mapping_drafts", 0.0),
        )
    )
    state[f"{field_prefix}_mapping_sources"] = _object_text(
        vendor.get("mapping_sources", state.get(f"{field_prefix}_mapping_sources", ""))
    )
    state[f"{field_prefix}_comparison_accepted"] = _to_bool(
        comparison.get("accepted", state.get(f"{field_prefix}_comparison_accepted", False))
    )
    state[f"{field_prefix}_comparison_failed_checks"] = int(
        _number_value(
            comparison.get("failed_checks"),
            _number(state, f"{field_prefix}_comparison_failed_checks", 0.0),
        )
    )
    datasets = vendor.get("datasets")
    state[f"{field_prefix}_datasets_json"] = (
        json.dumps(_vendor_market_data_batch_datasets(datasets), sort_keys=True)
        if isinstance(datasets, list)
        else _text(state, f"{field_prefix}_datasets_json")
    )


def _copy_vendor_market_data_batch_fields(
    state: pd.Series,
    *,
    source_prefixes: tuple[str, ...] = (
        "ack_vendor_market_data_batch",
        "dispatch_vendor_market_data_batch",
        "route_vendor_market_data_batch",
    ),
    field_prefix: str = "vendor_market_data_batch",
) -> None:
    source_prefix = next(
        (
            prefix
            for prefix in source_prefixes
            if _to_bool(state.get(f"{prefix}_provided", False))
            or int(_number(state, f"{prefix}_dataset_count", 0.0)) > 0
        ),
        "",
    )
    for suffix in (
        "provided",
        "ready",
        "adapter",
        "kind",
        "manifest_run_type",
        "market",
        "dataset_count",
        "ready_datasets",
        "failed_datasets",
        "ready_rate",
        "unique_source_files",
        "unique_header_fingerprints",
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
        "unique_mapping_drafts",
        "mapping_sources",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        state[f"{field_prefix}_{suffix}"] = (
            state.get(f"{source_prefix}_{suffix}", "") if source_prefix else ""
        )


def _apply_broker_vendor_data_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str = "broker_vendor_data_readiness",
) -> None:
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    state[f"{field_prefix}_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{field_prefix}_provided", active_config))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        readiness.get("ready", state.get(f"{field_prefix}_ready", False))
    )
    state[f"{field_prefix}_failed_checks"] = _broker_vendor_data_readiness_failed_checks(
        readiness,
        fallback=_number(state, f"{field_prefix}_failed_checks", 0.0),
    )


def _copy_broker_vendor_data_readiness_fields(
    state: pd.Series,
    *,
    source_prefixes: tuple[str, ...] = (
        "roundtrip_broker_vendor_data_readiness",
        "ack_broker_vendor_data_readiness",
        "dispatch_broker_vendor_data_readiness",
        "route_broker_vendor_data_readiness",
    ),
    field_prefix: str = "broker_vendor_data_readiness",
) -> None:
    source_prefix = next(
        (
            prefix
            for prefix in source_prefixes
            if _to_bool(state.get(f"{prefix}_provided", False))
            or _to_bool(state.get(f"{prefix}_ready", False))
            or int(_number(state, f"{prefix}_failed_checks", 0.0)) > 0
        ),
        "",
    )
    for suffix in ("provided", "ready", "failed_checks"):
        state[f"{field_prefix}_{suffix}"] = (
            state.get(f"{source_prefix}_{suffix}", 0 if suffix == "failed_checks" else False)
            if source_prefix
            else 0 if suffix == "failed_checks" else False
        )


def _broker_vendor_data_readiness_failed_checks(
    readiness: dict[str, Any],
    *,
    fallback: float = 0.0,
) -> int:
    failed_checks = readiness.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_value(failed_checks, fallback))
    return int(_number_value(readiness.get("failed_check_count", fallback), fallback))


def _apply_route_broker_route_readiness_config(state: pd.Series, readiness: dict[str, Any]) -> None:
    state["route_broker_route_readiness_required"] = _to_bool(
        readiness.get("required", state.get("route_broker_route_readiness_required", False))
    )
    state["route_broker_route_readiness_provided"] = _to_bool(
        readiness.get("provided", state.get("route_broker_route_readiness_provided", False))
    )
    state["route_broker_route_readiness_ready"] = _to_bool(
        readiness.get("ready", state.get("route_broker_route_readiness_ready", False))
    )
    state["route_broker_route_readiness_strategy"] = _object_text(
        readiness.get("strategy", _text(state, "route_broker_route_readiness_strategy"))
    )
    state["route_broker_route_readiness_market"] = _object_text(
        readiness.get("market", _text(state, "route_broker_route_readiness_market"))
    )
    state["route_broker_route_readiness_route_ready_pairs"] = int(
        _number_value(
            readiness.get("route_ready_pairs"),
            _number(state, "route_broker_route_readiness_route_ready_pairs", 0.0),
        )
    )
    state["route_broker_route_readiness_gap_pairs"] = int(
        _number_value(readiness.get("gap_pairs"), _number(state, "route_broker_route_readiness_gap_pairs", 0.0))
    )
    state["route_broker_route_readiness_recommendation"] = _object_text(
        readiness.get("recommendation", _text(state, "route_broker_route_readiness_recommendation"))
    )
    state["route_broker_route_readiness_ops_launch_controls_ready"] = _to_bool(
        readiness.get(
            "ops_launch_controls_ready",
            state.get("route_broker_route_readiness_ops_launch_controls_ready", False),
        )
    )
    state["route_broker_route_readiness_ops_launch_control_failures"] = _object_text(
        readiness.get(
            "ops_launch_control_failures",
            _text(state, "route_broker_route_readiness_ops_launch_control_failures"),
        )
    )
    state["route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_safe_runs"),
            _number(state, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
        )
    )
    state["route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_breach_runs"),
            _number(state, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
        )
    )
    state["route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_concentration_ok_runs"),
            _number(
                state,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            ),
        )
    )
    state["route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_concentration_breach_runs"),
            _number(
                state,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            ),
        )
    )


def _apply_resume_route_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str,
) -> None:
    state[f"{field_prefix}_required"] = _to_bool(
        readiness.get("required", state.get(f"{field_prefix}_required", False))
    )
    state[f"{field_prefix}_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{field_prefix}_provided", False))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        readiness.get("ready", state.get(f"{field_prefix}_ready", False))
    )
    state[f"{field_prefix}_strategy"] = _identity_key(
        _first_text(readiness.get("strategy", ""), state.get(f"{field_prefix}_strategy", ""))
    )
    state[f"{field_prefix}_market"] = _identity_key(
        _first_text(readiness.get("market", ""), state.get(f"{field_prefix}_market", ""))
    )
    state[f"{field_prefix}_route_ready_pairs"] = int(
        _number_value(
            readiness.get("route_ready_pairs"),
            _number(state, f"{field_prefix}_route_ready_pairs", 0.0),
        )
    )
    state[f"{field_prefix}_gap_pairs"] = int(
        _number_value(readiness.get("gap_pairs"), _number(state, f"{field_prefix}_gap_pairs", 0.0))
    )
    state[f"{field_prefix}_recommendation"] = _object_text(
        _first_text(readiness.get("recommendation", ""), state.get(f"{field_prefix}_recommendation", ""))
    )
    state[f"{field_prefix}_ops_launch_controls_ready"] = _to_bool(
        readiness.get("ops_launch_controls_ready", state.get(f"{field_prefix}_ops_launch_controls_ready", False))
    )
    state[f"{field_prefix}_ops_launch_control_failures"] = _object_text(
        _first_text(
            readiness.get("ops_launch_control_failures", ""),
            state.get(f"{field_prefix}_ops_launch_control_failures", ""),
        )
    )
    state[f"{field_prefix}_ops_broker_roundtrip_portfolio_safe_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_safe_runs"),
            _number(state, f"{field_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
        )
    )
    state[f"{field_prefix}_ops_broker_roundtrip_portfolio_breach_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_breach_runs"),
            _number(state, f"{field_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
        )
    )
    state[f"{field_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_concentration_ok_runs"),
            _number(state, f"{field_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0),
        )
    )
    state[f"{field_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"] = int(
        _number_value(
            readiness.get("ops_broker_roundtrip_portfolio_concentration_breach_runs"),
            _number(
                state,
                f"{field_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            ),
        )
    )


def _apply_shadow_broker_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str,
) -> None:
    route = readiness.get("route_readiness", {}) or {}
    dispatch = readiness.get("dispatch_roundtrip", {}) or {}
    route_dispatch = readiness.get("route_dispatch_roundtrip", {}) or {}
    vendor_readiness = readiness.get("broker_vendor_data_readiness", {}) or {}
    state[f"{field_prefix}_readiness_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{field_prefix}_readiness_provided", False))
    )
    state[f"{field_prefix}_readiness_sessions"] = int(
        _number_value(readiness.get("sessions"), _number(state, f"{field_prefix}_readiness_sessions", 0.0))
    )
    state[f"{field_prefix}_readiness_ready_sessions"] = int(
        _number_value(
            readiness.get("ready_sessions"),
            _number(state, f"{field_prefix}_readiness_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_sessions"] = int(
        _number_value(
            vendor_readiness.get("sessions"),
            _number(state, f"{field_prefix}_vendor_data_readiness_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_provided_sessions"] = int(
        _number_value(
            vendor_readiness.get("provided_sessions"),
            _number(state, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_ready_sessions"] = int(
        _number_value(
            vendor_readiness.get("ready_sessions"),
            _number(state, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_vendor_data_readiness_failed_checks"] = int(
        _number_value(
            vendor_readiness.get("failed_checks"),
            _number(state, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0),
        )
    )
    state[f"{field_prefix}_adapter"] = _object_text(
        readiness.get("adapter", _text(state, f"{field_prefix}_adapter"))
    )
    state[f"{field_prefix}_adapter_count"] = int(
        _number_value(readiness.get("adapter_count"), _number(state, f"{field_prefix}_adapter_count", 0.0))
    )
    state[f"{field_prefix}_route_readiness_sessions"] = int(
        _number_value(route.get("sessions"), _number(state, f"{field_prefix}_route_readiness_sessions", 0.0))
    )
    state[f"{field_prefix}_route_readiness_ready_sessions"] = int(
        _number_value(
            route.get("ready_sessions"),
            _number(state, f"{field_prefix}_route_readiness_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_route_readiness_strategy"] = _object_text(
        route.get("strategy", _text(state, f"{field_prefix}_route_readiness_strategy"))
    )
    state[f"{field_prefix}_route_readiness_market"] = _object_text(
        route.get("market", _text(state, f"{field_prefix}_route_readiness_market"))
    )
    state[f"{field_prefix}_route_readiness_gap_pairs"] = int(
        _number_value(route.get("max_gap_pairs"), _number(state, f"{field_prefix}_route_readiness_gap_pairs", 0.0))
    )
    state[f"{field_prefix}_dispatch_roundtrip_sessions"] = int(
        _number_value(dispatch.get("sessions"), _number(state, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0))
    )
    state[f"{field_prefix}_dispatch_roundtrip_ready_sessions"] = int(
        _number_value(
            dispatch.get("ready_sessions"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_strategy"] = _object_text(
        dispatch.get("strategy", _text(state, f"{field_prefix}_dispatch_roundtrip_strategy"))
    )
    state[f"{field_prefix}_dispatch_roundtrip_market"] = _object_text(
        dispatch.get("market", _text(state, f"{field_prefix}_dispatch_roundtrip_market"))
    )
    state[f"{field_prefix}_dispatch_roundtrip_scenario_count"] = int(
        _number_value(
            dispatch.get("scenario_count"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_missing_request_acks"] = int(
        _number_value(
            dispatch.get("max_missing_request_acks"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_rejected_orders"] = int(
        _number_value(
            dispatch.get("max_rejected_orders"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0),
        )
    )
    state[f"{field_prefix}_dispatch_roundtrip_unmatched_acks"] = int(
        _number_value(
            dispatch.get("max_unmatched_acks"),
            _number(state, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0),
        )
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_sessions"] = int(
        _number_value(
            route_dispatch.get("sessions"),
            _number(state, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_ready_sessions"] = int(
        _number_value(
            route_dispatch.get("ready_sessions"),
            _number(state, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0),
        )
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_strategy"] = _object_text(
        route_dispatch.get("strategy", _text(state, f"{field_prefix}_route_dispatch_roundtrip_strategy"))
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_market"] = _object_text(
        route_dispatch.get("market", _text(state, f"{field_prefix}_route_dispatch_roundtrip_market"))
    )
    state[f"{field_prefix}_route_dispatch_roundtrip_scenario_count"] = int(
        _number_value(
            route_dispatch.get("scenario_count"),
            _number(state, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0),
        )
    )


def _checks(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    dispatch_orders: pd.DataFrame,
    send_requests: pd.DataFrame,
    roundtrip_orders: pd.DataFrame,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> pd.DataFrame:
    component_failed = _component_failed_checks(dispatch_summary, send_summary, ack_summary)
    request_count = int(len(send_requests))
    dispatch_count = int(len(dispatch_orders))
    acked_requests = int(roundtrip_orders["acked"].map(_to_bool).sum()) if not roundtrip_orders.empty else 0
    missing_request_acks = _missing_request_acks(roundtrip_orders)
    rejected = int(_number(ack_summary, "rejected_orders", 0.0))
    duplicate_acks = int(_number(ack_summary, "duplicate_ack_orders", 0.0))
    unmatched_acks = int(_number(ack_summary, "unmatched_acks", 0.0))
    identity_mismatches = _identity_mismatches(dispatch_summary, send_summary, ack_summary)
    route_readiness_required = _route_readiness_required(dispatch_summary, send_summary, ack_summary, thresholds)
    route_readiness_provided = _route_readiness_provided(dispatch_summary, send_summary, ack_summary)
    route_roundtrip_required = _dispatch_roundtrip_required(dispatch_summary, thresholds)
    route_roundtrip_provided = _route_roundtrip_provided(dispatch_summary, send_summary, ack_summary)
    route_enable_failed_checks = _route_enable_failed_checks(dispatch_summary, send_summary, ack_summary)
    submission_enabled = _submission_enabled(send_summary, send_requests)
    dry_run_only = _all_dry_run(dispatch_orders, send_requests, roundtrip_orders)
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                _to_bool(dispatch_summary.get("ready", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("ready", False)) or not thresholds.require_dispatch_ready,
                "dispatch plan is not ready",
            ),
            _check(
                "send_ready",
                _to_bool(send_summary.get("ready", False)),
                "is",
                True,
                _to_bool(send_summary.get("ready", False)) or not thresholds.require_send_ready,
                "broker dispatch send packet is not ready",
            ),
            _check(
                "ack_passed",
                _to_bool(ack_summary.get("passed", False)),
                "is",
                True,
                _to_bool(ack_summary.get("passed", False)) or not thresholds.require_ack_passed,
                "broker dispatch acknowledgements did not pass",
            ),
            _check(
                "target_mode_matches",
                _identity_key(dispatch_summary.get("target_mode", "")),
                "==",
                thresholds.target_mode,
                _identity_key(dispatch_summary.get("target_mode", "")) == thresholds.target_mode,
                "round-trip target mode does not match threshold",
            ),
            _check(
                "identity_match",
                identity_mismatches,
                "==",
                0,
                identity_mismatches == 0 or not thresholds.require_identity_match,
                "dispatch, send, and ack identities do not match",
            ),
            _check(
                "route_dispatch_roundtrip_provided",
                route_roundtrip_provided,
                "is",
                True,
                route_roundtrip_provided or not route_roundtrip_required,
                "round-trip proof requires route dispatch round-trip evidence from dispatch, send, and ack artifacts",
            ),
            _check(
                "route_readiness_provided",
                route_readiness_provided,
                "is",
                True,
                route_readiness_provided or not route_readiness_required,
                "round-trip proof requires route-readiness evidence from dispatch, send, and ack artifacts",
            ),
            _check(
                "request_count_matches_dispatch",
                request_count,
                "==",
                dispatch_count,
                request_count == dispatch_count,
                "send request count does not match dispatch order count",
            ),
            _check(
                "unique_request_per_dispatch_order",
                int(roundtrip_orders["request_count"].eq(1).sum()) if not roundtrip_orders.empty else 0,
                "==",
                dispatch_count,
                bool(roundtrip_orders["request_count"].eq(1).all()) if not roundtrip_orders.empty else False,
                "each dispatch order must have exactly one send request",
            ),
            _check(
                "submission_disabled",
                submission_enabled,
                "is",
                False,
                (not submission_enabled) or not thresholds.require_submission_disabled,
                "round-trip evidence includes live submission enabled",
            ),
            _check("dry_run_only", dry_run_only, "is", True, dry_run_only, "round-trip evidence is not dry-run-only"),
            _check(
                "all_requests_acked",
                acked_requests,
                "==",
                request_count,
                (acked_requests == request_count and missing_request_acks == 0)
                or not thresholds.require_all_requests_acked,
                "not every send request has an accepted acknowledgement",
            ),
            _check(
                "missing_request_acks",
                missing_request_acks,
                "<=",
                thresholds.max_missing_request_acks,
                missing_request_acks <= thresholds.max_missing_request_acks,
                "missing request acknowledgements exceeded threshold",
            ),
            _check(
                "rejected_orders",
                rejected,
                "==",
                0,
                rejected == 0 or thresholds.allow_rejections,
                "acknowledgements include rejected orders",
            ),
            _check(
                "duplicate_ack_orders",
                duplicate_acks,
                "<=",
                thresholds.max_duplicate_ack_orders,
                duplicate_acks <= thresholds.max_duplicate_ack_orders,
                "duplicate acknowledgement rows exceeded threshold",
            ),
            _check(
                "unmatched_acks",
                unmatched_acks,
                "<=",
                thresholds.max_unmatched_acks,
                unmatched_acks <= thresholds.max_unmatched_acks,
                "acknowledgement reconciliation has unmatched rows",
            ),
            _check(
                "component_failed_checks",
                component_failed,
                "<=",
                thresholds.max_total_failed_component_checks,
                component_failed <= thresholds.max_total_failed_component_checks,
                "component reports contain failed checks",
            ),
            _check(
                "route_enable_dispatch_roundtrip_failed_checks",
                route_enable_failed_checks,
                "<=",
                0,
                route_enable_failed_checks <= 0,
                "route-enable dispatch round-trip has failed component checks",
            ),
        ]
    )
    if _to_bool(
        ack_summary.get("broker_dispatch_ack_lineage_required", False)
    ):
        ack_lineage_checks = [
            _check(
                "broker_dispatch_ack_lineage_provided",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_lineage_provided", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_lineage_provided", False
                    )
                ),
                "broker-dispatch acknowledgement lineage is required but missing",
            ),
            _check(
                "broker_dispatch_ack_manifest_current",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_manifest_current", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_manifest_current", False
                    )
                ),
                "broker-dispatch acknowledgement manifest is stale or incomplete",
            ),
            _check(
                "broker_dispatch_ack_lineage_contract_consistent",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_lineage_contract_consistent", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_lineage_contract_consistent", False
                    )
                ),
                "ack rows, summary, config, checks, and manifest disagree",
            ),
            _check(
                "broker_dispatch_ack_non_authorizing",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_non_authorizing", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_non_authorizing", False
                    )
                ),
                "broker-dispatch acknowledgement lineage contains an authorizing claim",
            ),
            _check(
                "broker_dispatch_ack_send_lineage_gate_passed",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_send_lineage_gate_passed", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_send_lineage_gate_passed", False
                    )
                ),
                "acknowledgement bundle did not retain a valid send-lineage gate",
            ),
            _check(
                "broker_dispatch_ack_send_matches_current",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_send_matches_current", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_send_matches_current", False
                    )
                ),
                "acknowledgement bundle does not match its current send source",
            ),
            _check(
                "broker_dispatch_ack_expected_send_matches_current",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_expected_send_matches_current",
                        False,
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_expected_send_matches_current",
                        False,
                    )
                ),
                "acknowledgement source does not match the send packet under review",
            ),
            _check(
                "broker_dispatch_ack_lineage_gate_passed",
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_lineage_gate_passed", False
                    )
                ),
                "is",
                True,
                _to_bool(
                    ack_summary.get(
                        "broker_dispatch_ack_lineage_gate_passed", False
                    )
                ),
                "broker-dispatch acknowledgement lineage gate did not pass",
            ),
        ]
        checks = pd.concat(
            [checks, pd.DataFrame(ack_lineage_checks)],
            ignore_index=True,
        )
    if route_readiness_required or route_readiness_provided:
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _route_readiness_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _shadow_broker_readiness_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_shadow_broker_readiness_checks(dispatch_summary, send_summary, ack_summary)),
            ],
            ignore_index=True,
        )
    if _route_broker_shadow_broker_readiness_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _route_broker_shadow_broker_readiness_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _strategy_portfolio_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_strategy_portfolio_checks(dispatch_summary, send_summary, ack_summary)),
            ],
            ignore_index=True,
        )
    if _broker_vendor_data_readiness_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _broker_vendor_data_readiness_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _vendor_market_data_batch_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _vendor_market_data_batch_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if _broker_vendor_market_data_batch_active(dispatch_summary, send_summary, ack_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _broker_vendor_market_data_batch_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                    )
                ),
            ],
            ignore_index=True,
        )
    if route_roundtrip_required or route_roundtrip_provided:
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    _route_roundtrip_checks(
                        dispatch_summary,
                        send_summary,
                        ack_summary,
                        roundtrip_orders,
                    )
                ),
            ],
            ignore_index=True,
        )
    return checks


def _route_readiness_checks(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
) -> list[dict[str, object]]:
    rows = (dispatch_summary, send_summary, ack_summary)
    ready = all(_to_bool(row.get("route_readiness_ready", False)) for row in rows)
    identity_mismatches = _route_readiness_identity_mismatches(rows)
    gap_pairs = _route_readiness_counter_max(rows, "route_readiness_gap_pairs")
    ops_launch_present = all(
        _to_bool(row.get("route_readiness_ops_launch_controls_present", False)) for row in rows
    )
    ops_blocked_pairs = _route_readiness_counter_max(rows, "route_readiness_ops_launch_controls_blocked_pairs")
    ops_allocation_breach_pairs = _route_readiness_counter_max(
        rows,
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
    )
    ops_concentration_breach_pairs = _route_readiness_counter_max(
        rows,
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
    )
    checks = [
        _check(
            "route_readiness_ready",
            ready,
            "is",
            True,
            ready,
            "route-readiness proof is not ready in all component artifacts",
        ),
        _check(
            "route_readiness_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "route-readiness proof identity does not match component identity",
        ),
        _check(
            "route_readiness_gap_pairs",
            gap_pairs,
            "==",
            0,
            gap_pairs == 0,
            "route-readiness proof still reports market/strategy gaps",
        ),
        _check(
            "route_readiness_ops_launch_controls_present",
            ops_launch_present,
            "is",
            True,
            ops_launch_present,
            "route-readiness proof is missing launch-grade ops broker controls in one or more component artifacts",
        ),
        _check(
            "route_readiness_ops_launch_controls_blocked_pairs",
            ops_blocked_pairs,
            "<=",
            0,
            ops_blocked_pairs <= 0,
            "route-readiness proof has blocked launch-control pairs in a component artifact",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
            ops_allocation_breach_pairs,
            "<=",
            0,
            ops_allocation_breach_pairs <= 0,
            "route-readiness proof has broker round-trip allocation breach pairs in a component artifact",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
            ops_concentration_breach_pairs,
            "<=",
            0,
            ops_concentration_breach_pairs <= 0,
            "route-readiness proof has broker round-trip concentration breach pairs in a component artifact",
        ),
    ]
    if _route_broker_route_readiness_active(rows):
        checks.extend(_route_broker_route_readiness_checks(rows))
    if _resume_route_readiness_active(rows, "route_broker_resume_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                rows,
                prefix="route_broker_resume_broker_route_readiness",
                label="broker resume-gate broker route-readiness",
            )
        )
    if _resume_route_readiness_active(rows, "route_broker_resume_incident_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                rows,
                prefix="route_broker_resume_incident_broker_route_readiness",
                label="broker resume-gate incident route-readiness",
            )
        )
    return checks


def _route_broker_route_readiness_active(rows: tuple[pd.Series, ...]) -> bool:
    return any(
        _to_bool(row.get("route_broker_route_readiness_required", False))
        or _to_bool(row.get("route_broker_route_readiness_provided", False))
        or _to_bool(row.get("route_broker_route_readiness_ready", False))
        or int(_number(row, "route_broker_route_readiness_route_ready_pairs", 0.0)) > 0
        or int(_number(row, "route_broker_route_readiness_gap_pairs", 0.0)) > 0
        or bool(_text(row, "route_broker_route_readiness_strategy"))
        or bool(_text(row, "route_broker_route_readiness_market"))
        or bool(_text(row, "route_broker_route_readiness_recommendation"))
        or _to_bool(row.get("route_broker_route_readiness_ops_launch_controls_ready", False))
        or bool(_text(row, "route_broker_route_readiness_ops_launch_control_failures"))
        or int(_number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0
        or int(_number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)) > 0
        or int(
            _number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)
        )
        > 0
        or int(
            _number(
                row,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        )
        > 0
        for row in rows
    )


def _route_broker_route_readiness_checks(rows: tuple[pd.Series, ...]) -> list[dict[str, object]]:
    provided = all(_to_bool(row.get("route_broker_route_readiness_provided", False)) for row in rows)
    ready = all(_to_bool(row.get("route_broker_route_readiness_ready", False)) for row in rows)
    identity_mismatches = _route_broker_route_readiness_identity_mismatches(rows)
    gap_pairs = _route_readiness_counter_max(rows, "route_broker_route_readiness_gap_pairs")
    ops_launch_ready = all(
        _to_bool(row.get("route_broker_route_readiness_ops_launch_controls_ready", False)) for row in rows
    )
    safe_runs = _route_readiness_counter_min(
        rows,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
    )
    breach_runs = _route_readiness_counter_max(
        rows,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
    )
    concentration_ok_runs = _route_readiness_counter_min(
        rows,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
    )
    concentration_breach_runs = _route_readiness_counter_max(
        rows,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    )
    return [
        _check(
            "route_broker_route_readiness_provided",
            provided,
            "is",
            True,
            provided,
            "broker-carried route proof is active but missing from one or more component artifacts",
        ),
        _check(
            "route_broker_route_readiness_ready",
            ready,
            "is",
            True,
            ready,
            "broker-carried route proof is not ready in all component artifacts",
        ),
        _check(
            "route_broker_route_readiness_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "broker-carried route proof identity does not match component identity",
        ),
        _check(
            "route_broker_route_readiness_gap_pairs",
            gap_pairs,
            "<=",
            0,
            gap_pairs <= 0,
            "broker-carried route proof still reports route gaps",
        ),
        _check(
            "route_broker_route_readiness_ops_launch_controls_ready",
            ops_launch_ready,
            "is",
            True,
            ops_launch_ready,
            "broker-carried route proof is missing launch-grade ops broker controls",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            safe_runs,
            ">",
            0,
            safe_runs > 0,
            "broker-carried route proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            breach_runs,
            "<=",
            0,
            breach_runs <= 0,
            "broker-carried route proof has allocation breach broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            concentration_ok_runs,
            ">",
            0,
            concentration_ok_runs > 0,
            "broker-carried route proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            concentration_breach_runs,
            "<=",
            0,
            concentration_breach_runs <= 0,
            "broker-carried route proof has concentration breach broker round-trip runs",
        ),
    ]


def _resume_route_readiness_active(rows: tuple[pd.Series, ...], prefix: str) -> bool:
    return any(
        _to_bool(row.get(f"{prefix}_required", False))
        or _to_bool(row.get(f"{prefix}_provided", False))
        or _to_bool(row.get(f"{prefix}_ready", False))
        or int(_number(row, f"{prefix}_route_ready_pairs", 0.0)) > 0
        or int(_number(row, f"{prefix}_gap_pairs", 0.0)) > 0
        or bool(_text(row, f"{prefix}_strategy"))
        or bool(_text(row, f"{prefix}_market"))
        or bool(_text(row, f"{prefix}_recommendation"))
        or _to_bool(row.get(f"{prefix}_ops_launch_controls_ready", False))
        or bool(_text(row, f"{prefix}_ops_launch_control_failures"))
        or int(_number(row, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0
        or int(_number(row, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)) > 0
        or int(_number(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)) > 0
        or int(_number(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0)) > 0
        for row in rows
    )


def _resume_route_readiness_checks(
    rows: tuple[pd.Series, ...],
    *,
    prefix: str,
    label: str,
) -> list[dict[str, object]]:
    provided = all(_to_bool(row.get(f"{prefix}_provided", False)) for row in rows)
    ready = all(_to_bool(row.get(f"{prefix}_ready", False)) for row in rows)
    identity_mismatches = _resume_route_readiness_identity_mismatches(rows, prefix)
    route_ready_pairs = _route_readiness_counter_min(rows, f"{prefix}_route_ready_pairs")
    gap_pairs = _route_readiness_counter_max(rows, f"{prefix}_gap_pairs")
    ops_launch_ready = all(_to_bool(row.get(f"{prefix}_ops_launch_controls_ready", False)) for row in rows)
    safe_runs = _route_readiness_counter_min(rows, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs")
    breach_runs = _route_readiness_counter_max(rows, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs")
    concentration_ok_runs = _route_readiness_counter_min(
        rows,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
    )
    concentration_breach_runs = _route_readiness_counter_max(
        rows,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    )
    return [
        _check(
            f"{prefix}_provided",
            provided,
            "is",
            True,
            provided,
            f"{label} proof is active but missing from one or more component artifacts",
        ),
        _check(
            f"{prefix}_ready",
            ready,
            "is",
            True,
            ready,
            f"{label} proof is not ready in all component artifacts",
        ),
        _check(
            f"{prefix}_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            f"{label} proof identity does not match component identity",
        ),
        _check(
            f"{prefix}_route_ready_pairs",
            route_ready_pairs,
            ">",
            0,
            route_ready_pairs > 0,
            f"{label} proof has no route-ready pairs in one or more component artifacts",
        ),
        _check(
            f"{prefix}_gap_pairs",
            gap_pairs,
            "<=",
            0,
            gap_pairs <= 0,
            f"{label} proof still reports route gaps",
        ),
        _check(
            f"{prefix}_ops_launch_controls_ready",
            ops_launch_ready,
            "is",
            True,
            ops_launch_ready,
            f"{label} proof is missing launch-grade ops broker controls",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            safe_runs,
            ">",
            0,
            safe_runs > 0,
            f"{label} proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            breach_runs,
            "<=",
            0,
            breach_runs <= 0,
            f"{label} proof has allocation breach broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            concentration_ok_runs,
            ">",
            0,
            concentration_ok_runs > 0,
            f"{label} proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            concentration_breach_runs,
            "<=",
            0,
            concentration_breach_runs <= 0,
            f"{label} proof has concentration breach broker round-trip runs",
        ),
    ]


def _strategy_portfolio_checks(*rows: pd.Series) -> list[dict[str, object]]:
    dispatch_total_notional = _strategy_portfolio_dispatch_total_notional(rows)
    selected_allocation = _strategy_portfolio_number_min(rows, "strategy_portfolio_selected_allocation_notional")
    return [
        _check(
            "strategy_portfolio_provided",
            _strategy_portfolio_provided(*rows),
            "is",
            True,
            _strategy_portfolio_provided(*rows),
            "strategy portfolio allocation evidence is missing from one or more round-trip artifacts",
        ),
        _check(
            "strategy_portfolio_ready",
            _strategy_portfolio_bool_all(rows, "strategy_portfolio_ready"),
            "is",
            True,
            _strategy_portfolio_bool_all(rows, "strategy_portfolio_ready"),
            "strategy portfolio allocation is not ready in every round-trip artifact",
        ),
        _check(
            "strategy_portfolio_allocation_eligible",
            _strategy_portfolio_bool_all(rows, "strategy_portfolio_selected_eligible"),
            "is",
            True,
            _strategy_portfolio_bool_all(rows, "strategy_portfolio_selected_eligible"),
            "strategy portfolio allocation row is not eligible in every round-trip artifact",
        ),
        _check(
            "strategy_portfolio_strategy_matches",
            _strategy_portfolio_identity_mismatches(rows, "strategy"),
            "==",
            0,
            _strategy_portfolio_identity_mismatches(rows, "strategy") == 0,
            "strategy portfolio strategy does not match round-trip strategy evidence",
        ),
        _check(
            "strategy_portfolio_market_matches",
            _strategy_portfolio_identity_mismatches(rows, "market"),
            "==",
            0,
            _strategy_portfolio_identity_mismatches(rows, "market") == 0,
            "strategy portfolio market does not match round-trip market evidence",
        ),
        _check(
            "strategy_portfolio_profile_consistent",
            _strategy_portfolio_text_unique_count(rows, "strategy_portfolio_selected_profile"),
            "==",
            1,
            _strategy_portfolio_text_unique_count(rows, "strategy_portfolio_selected_profile") == 1,
            "strategy portfolio selected profile is not consistent across round-trip artifacts",
        ),
        _check(
            "strategy_portfolio_allocation_notional",
            selected_allocation,
            ">",
            0.0,
            selected_allocation > 0.0,
            "strategy portfolio allocation notional must be positive",
        ),
        _check(
            "strategy_portfolio_allocation_notional_consistent",
            _strategy_portfolio_number_unique_count(rows, "strategy_portfolio_selected_allocation_notional"),
            "==",
            1,
            _strategy_portfolio_number_unique_count(rows, "strategy_portfolio_selected_allocation_notional") == 1,
            "strategy portfolio allocation notional is not consistent across round-trip artifacts",
        ),
        _check(
            "dispatch_total_notional_consistent",
            _strategy_portfolio_number_unique_count(rows, "dispatch_total_notional"),
            "==",
            1,
            _strategy_portfolio_number_unique_count(rows, "dispatch_total_notional") == 1,
            "dispatch total notional is not consistent across round-trip artifacts",
        ),
        _check(
            "dispatch_notional_within_strategy_portfolio_allocation",
            dispatch_total_notional,
            "<=",
            selected_allocation,
            dispatch_total_notional <= selected_allocation,
            "dispatch notional exceeds selected strategy portfolio allocation",
        ),
    ]


def _route_roundtrip_checks(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    roundtrip_orders: pd.DataFrame,
) -> list[dict[str, object]]:
    rows = (dispatch_summary, send_summary, ack_summary)
    ready = all(_to_bool(row.get("route_dispatch_roundtrip_ready", False)) for row in rows)
    identity_mismatches = _route_roundtrip_identity_mismatches(rows)
    batch_ids = _route_roundtrip_batch_ids(rows, roundtrip_orders)
    batch_consistent = bool(batch_ids) and len(batch_ids) == 1
    request_counts_match = _route_roundtrip_request_counts_match(rows)
    missing = _route_roundtrip_counter_max(rows, "route_dispatch_roundtrip_missing_request_acks")
    rejected = _route_roundtrip_counter_max(rows, "route_dispatch_roundtrip_rejected_orders")
    unmatched = _route_roundtrip_counter_max(rows, "route_dispatch_roundtrip_unmatched_acks")
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            ready,
            "is",
            True,
            ready,
            "route dispatch round-trip proof is not ready in all component artifacts",
        ),
        _check(
            "route_dispatch_roundtrip_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "route dispatch round-trip proof identity does not match component identity",
        ),
        _check(
            "route_dispatch_roundtrip_batch_consistent",
            ",".join(sorted(batch_ids)),
            "has_unique_nonempty",
            True,
            batch_consistent,
            "route dispatch round-trip proof batch is missing or inconsistent across artifacts",
        ),
        _check(
            "route_dispatch_roundtrip_request_counts_match",
            request_counts_match,
            "is",
            True,
            request_counts_match,
            "route dispatch round-trip request and ack counts are inconsistent",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            missing,
            "<=",
            0,
            missing <= 0,
            "route dispatch round-trip proof has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            rejected,
            "<=",
            0,
            rejected <= 0,
            "route dispatch round-trip proof has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            unmatched,
            "<=",
            0,
            unmatched <= 0,
            "route dispatch round-trip proof has unmatched acknowledgements",
        ),
    ]


def _shadow_broker_readiness_active(*rows: pd.Series) -> bool:
    session_columns = (
        "shadow_broker_readiness_sessions",
        "shadow_broker_vendor_data_readiness_sessions",
        "shadow_broker_route_readiness_sessions",
        "shadow_broker_dispatch_roundtrip_sessions",
        "shadow_broker_route_dispatch_roundtrip_sessions",
    )
    return any(_shadow_counter_max(rows, column) > 0 for column in session_columns)


def _shadow_broker_readiness_checks(*rows: pd.Series) -> list[dict[str, object]]:
    sessions = [int(_number(row, "shadow_broker_readiness_sessions", 0.0)) for row in rows]
    ready_sessions = [int(_number(row, "shadow_broker_readiness_ready_sessions", 0.0)) for row in rows]
    provided = all(value > 0 for value in sessions)
    ready = provided and all(ready == session for ready, session in zip(ready_sessions, sessions))
    vendor_sessions = [
        int(_number(row, "shadow_broker_vendor_data_readiness_sessions", 0.0)) for row in rows
    ]
    vendor_provided_sessions = [
        int(_number(row, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)) for row in rows
    ]
    vendor_ready_sessions = [
        int(_number(row, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)) for row in rows
    ]
    vendor_active = any(value > 0 for value in vendor_sessions)
    adapter_match = _shadow_adapter_matches(rows)
    adapter_consistent = _shadow_adapter_consistent(rows)
    route_sessions = [int(_number(row, "shadow_broker_route_readiness_sessions", 0.0)) for row in rows]
    route_ready_sessions = [
        int(_number(row, "shadow_broker_route_readiness_ready_sessions", 0.0)) for row in rows
    ]
    dispatch_sessions = [
        int(_number(row, "shadow_broker_dispatch_roundtrip_sessions", 0.0)) for row in rows
    ]
    dispatch_ready_sessions = [
        int(_number(row, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)) for row in rows
    ]
    route_dispatch_sessions = [
        int(_number(row, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0)) for row in rows
    ]
    route_dispatch_ready_sessions = [
        int(_number(row, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)) for row in rows
    ]
    return [
        _check(
            "shadow_broker_readiness_provided",
            min(sessions) if sessions else 0,
            ">",
            0,
            provided,
            "shadow broker-readiness proof is not present in every component artifact",
        ),
        _check(
            "shadow_broker_readiness_ready",
            "|".join(str(value) for value in ready_sessions),
            "==",
            "|".join(str(value) for value in sessions),
            ready,
            "shadow broker-readiness proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_present_for_broker_sessions",
            "|".join(str(value) for value in vendor_sessions),
            "==",
            "|".join(str(value) for value in sessions),
            (not vendor_active)
            or all(vendor == session for vendor, session in zip(vendor_sessions, sessions)),
            "shadow broker vendor-data wrapper proof is present for only some broker-readiness sessions",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_provided",
            "|".join(str(value) for value in vendor_provided_sessions),
            "==",
            "|".join(str(value) for value in sessions),
            (not vendor_active)
            or all(provided == session for provided, session in zip(vendor_provided_sessions, sessions)),
            "shadow broker vendor-data wrapper proof is missing for some broker-readiness sessions",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_ready",
            "|".join(str(value) for value in vendor_ready_sessions),
            "==",
            "|".join(str(value) for value in sessions),
            (not vendor_active)
            or all(ready == session for ready, session in zip(vendor_ready_sessions, sessions)),
            "shadow broker vendor-data wrapper proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_failed_checks",
            _shadow_counter_max(rows, "shadow_broker_vendor_data_readiness_failed_checks"),
            "<=",
            0,
            (not vendor_active)
            or _shadow_counter_max(rows, "shadow_broker_vendor_data_readiness_failed_checks") <= 0,
            "shadow broker vendor-data wrapper proof has failed checks",
        ),
        _check(
            "shadow_broker_adapter_match",
            _shadow_adapter_value(rows),
            "matches",
            _identity_key(rows[0].get("adapter", "")) if rows else "",
            adapter_match,
            "shadow broker adapter proof does not match component adapter identity",
        ),
        _check(
            "shadow_broker_adapter_consistent",
            _shadow_counter_max(rows, "shadow_broker_adapter_count"),
            "==",
            1,
            adapter_consistent,
            "shadow broker adapter proof is missing or mixed across component artifacts",
        ),
        _check(
            "shadow_broker_route_readiness_ready",
            "|".join(str(value) for value in route_ready_sessions),
            "==",
            "|".join(str(value) for value in route_sessions),
            all(session > 0 for session in route_sessions)
            and all(ready == session for ready, session in zip(route_ready_sessions, route_sessions)),
            "shadow broker route-readiness proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_route_readiness_identity_match",
            _shadow_identity_mismatches(rows, "route_readiness"),
            "==",
            0,
            _shadow_identity_mismatches(rows, "route_readiness") == 0,
            "shadow broker route-readiness proof identity does not match component identity",
        ),
        _check(
            "shadow_broker_route_readiness_gap_pairs",
            _shadow_counter_max(rows, "shadow_broker_route_readiness_gap_pairs"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_route_readiness_gap_pairs") <= 0,
            "shadow broker route-readiness proof reports route gaps",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_ready",
            "|".join(str(value) for value in dispatch_ready_sessions),
            "==",
            "|".join(str(value) for value in dispatch_sessions),
            all(session > 0 for session in dispatch_sessions)
            and all(ready == session for ready, session in zip(dispatch_ready_sessions, dispatch_sessions)),
            "shadow broker dispatch round-trip proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_identity_match",
            _shadow_identity_mismatches(rows, "dispatch_roundtrip"),
            "==",
            0,
            _shadow_identity_mismatches(rows, "dispatch_roundtrip") == 0,
            "shadow broker dispatch round-trip proof identity does not match component identity",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_scenario_consistent",
            "|".join(str(int(_number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0))) for row in rows),
            "==",
            1,
            all(int(_number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)) == 1 for row in rows),
            "shadow broker dispatch round-trip scenario is missing or mixed",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_missing_request_acks",
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_missing_request_acks"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_missing_request_acks") <= 0,
            "shadow broker dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_rejected_orders",
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_rejected_orders"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_rejected_orders") <= 0,
            "shadow broker dispatch round-trip has rejected orders",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_unmatched_acks",
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_unmatched_acks"),
            "<=",
            0,
            _shadow_counter_max(rows, "shadow_broker_dispatch_roundtrip_unmatched_acks") <= 0,
            "shadow broker dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_ready",
            "|".join(str(value) for value in route_dispatch_ready_sessions),
            "==",
            "|".join(str(value) for value in route_dispatch_sessions),
            all(session > 0 for session in route_dispatch_sessions)
            and all(
                ready == session
                for ready, session in zip(route_dispatch_ready_sessions, route_dispatch_sessions)
            ),
            "shadow broker route dispatch round-trip proof is not ready in every component artifact",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_identity_match",
            _shadow_identity_mismatches(rows, "route_dispatch_roundtrip"),
            "==",
            0,
            _shadow_identity_mismatches(rows, "route_dispatch_roundtrip") == 0,
            "shadow broker route dispatch round-trip proof identity does not match component identity",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_scenario_consistent",
            "|".join(
                str(int(_number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)))
                for row in rows
            ),
            "==",
            1,
            all(
                int(_number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)) == 1
                for row in rows
            ),
            "shadow broker route dispatch round-trip scenario is missing or mixed",
        ),
    ]


def _route_broker_shadow_broker_readiness_active(*rows: pd.Series) -> bool:
    prefix = "route_broker_shadow_broker"
    session_columns = (
        f"{prefix}_readiness_sessions",
        f"{prefix}_vendor_data_readiness_sessions",
        f"{prefix}_route_readiness_sessions",
        f"{prefix}_dispatch_roundtrip_sessions",
        f"{prefix}_route_dispatch_roundtrip_sessions",
    )
    return bool(
        any(_to_bool(row.get(f"{prefix}_readiness_provided", False)) for row in rows)
        or any(_shadow_counter_max(rows, column) > 0 for column in session_columns)
    )


def _route_broker_shadow_broker_readiness_checks(*rows: pd.Series) -> list[dict[str, object]]:
    source_prefix = "route_broker_shadow_broker"
    provided = bool(
        rows
        and all(
            _to_bool(row.get(f"{source_prefix}_readiness_provided", False))
            and int(_number(row, f"{source_prefix}_readiness_sessions", 0.0)) > 0
            for row in rows
        )
    )
    checks = [
        _check(
            "broker_shadow_broker_readiness_provided",
            provided,
            "is",
            True,
            provided,
            "broker-readiness shadow broker proof is not provided by every component",
        )
    ]
    projected_rows = tuple(_shadow_broker_projection(row, source_prefix=source_prefix) for row in rows)
    for check in _shadow_broker_readiness_checks(*projected_rows):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "shadow_broker",
            "broker_shadow_broker",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "shadow broker",
                "broker-readiness shadow broker",
            )
        checks.append(renamed)
    return checks


def _vendor_market_data_batch_active(*rows: pd.Series) -> bool:
    return bool(
        any(_to_bool(row.get("vendor_market_data_batch_provided", False)) for row in rows)
        or any(_identity_key(row.get("vendor_market_data_batch_manifest_run_type", "")) for row in rows)
        or any(int(_number(row, "vendor_market_data_batch_dataset_count", 0.0)) > 0 for row in rows)
    )


def _broker_vendor_data_readiness_active(*rows: pd.Series) -> bool:
    return bool(
        any(_to_bool(row.get("broker_vendor_data_readiness_provided", False)) for row in rows)
        or any(_to_bool(row.get("broker_vendor_data_readiness_ready", False)) for row in rows)
        or any(int(_number(row, "broker_vendor_data_readiness_failed_checks", 0.0)) > 0 for row in rows)
    )


def _broker_vendor_data_readiness_checks(*rows: pd.Series) -> list[dict[str, object]]:
    provided = bool(
        rows and all(_to_bool(row.get("broker_vendor_data_readiness_provided", False)) for row in rows)
    )
    ready = bool(
        rows and all(_to_bool(row.get("broker_vendor_data_readiness_ready", False)) for row in rows)
    )
    failed_checks = _broker_vendor_data_readiness_counter_max(
        rows,
        "broker_vendor_data_readiness_failed_checks",
    )
    return [
        _check(
            "broker_vendor_data_readiness_provided",
            provided,
            "is",
            True,
            provided,
            "broker-vendor readiness wrapper proof is not provided by every component",
        ),
        _check(
            "broker_vendor_data_readiness_ready",
            ready,
            "is",
            True,
            ready,
            "broker-vendor readiness wrapper proof is not ready in every component",
        ),
        _check(
            "broker_vendor_data_readiness_failed_checks",
            failed_checks,
            "==",
            0,
            failed_checks == 0,
            "broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _vendor_market_data_batch_checks(*rows: pd.Series) -> list[dict[str, object]]:
    provided = bool(
        rows
        and all(
            _to_bool(row.get("vendor_market_data_batch_provided", False))
            and int(_number(row, "vendor_market_data_batch_dataset_count", 0.0)) > 0
            for row in rows
        )
    )
    ready = bool(rows and all(_to_bool(row.get("vendor_market_data_batch_ready", False)) for row in rows))
    identity_mismatches = _vendor_market_data_batch_identity_mismatches(rows)
    manifest_run_type_valid = _vendor_market_data_batch_manifest_run_type_valid(rows)
    counts_consistent = _vendor_market_data_batch_counts_consistent(rows)
    failed_datasets = _vendor_market_data_batch_counter_max(rows, "vendor_market_data_batch_failed_datasets")
    comparison_failed = _vendor_market_data_batch_counter_max(
        rows,
        "vendor_market_data_batch_comparison_failed_checks",
    )
    source_file_fingerprint_coverage = _vendor_market_data_batch_number_min(
        rows,
        "vendor_market_data_batch_source_file_fingerprint_coverage",
    )
    min_mapping_coverage = _vendor_market_data_batch_number_min(
        rows,
        "vendor_market_data_batch_min_mapping_coverage",
    )
    unique_mapping_drafts = _vendor_market_data_batch_counter_min(
        rows,
        "vendor_market_data_batch_unique_mapping_drafts",
    )
    comparison_accepted = bool(
        rows and all(_to_bool(row.get("vendor_market_data_batch_comparison_accepted", False)) for row in rows)
    )
    return [
        _check(
            "vendor_market_data_batch_provided",
            provided,
            "is",
            True,
            provided,
            "vendor market-data batch proof is not provided by every component",
        ),
        _check(
            "vendor_market_data_batch_ready",
            ready,
            "is",
            True,
            ready,
            "vendor market-data batch proof is not ready in every component",
        ),
        _check(
            "vendor_market_data_batch_identity_match",
            identity_mismatches,
            "==",
            0,
            identity_mismatches == 0,
            "vendor market-data batch adapter/market identity is inconsistent",
        ),
        _check(
            "vendor_market_data_batch_manifest_run_type",
            _vendor_market_data_batch_text_value(rows, "manifest_run_type"),
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type_valid,
            "vendor market-data batch manifest is not a vendor batch pipeline proof",
        ),
        _check(
            "vendor_market_data_batch_dataset_count_consistent",
            counts_consistent,
            "is",
            True,
            counts_consistent,
            "vendor market-data batch dataset counts differ across components",
        ),
        _check(
            "vendor_market_data_batch_failed_datasets",
            failed_datasets,
            "==",
            0,
            failed_datasets == 0,
            "vendor market-data batch still has failed datasets",
        ),
        _check(
            "vendor_market_data_batch_source_file_fingerprint_coverage",
            source_file_fingerprint_coverage,
            ">=",
            1.0,
            source_file_fingerprint_coverage >= 1.0,
            "vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            "vendor_market_data_batch_min_mapping_coverage",
            min_mapping_coverage,
            ">=",
            1.0,
            min_mapping_coverage >= 1.0,
            "vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            "vendor_market_data_batch_mapping_drafts",
            unique_mapping_drafts,
            ">",
            0,
            unique_mapping_drafts > 0,
            "vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            "vendor_market_data_batch_comparison_accepted",
            comparison_accepted,
            "is",
            True,
            comparison_accepted,
            "vendor market-data batch comparison is not accepted by every component",
        ),
        _check(
            "vendor_market_data_batch_comparison_failed_checks",
            comparison_failed,
            "==",
            0,
            comparison_failed == 0,
            "vendor market-data batch comparison has failed checks",
        ),
    ]


def _broker_vendor_market_data_batch_active(*rows: pd.Series) -> bool:
    return _vendor_market_data_batch_active(*_broker_vendor_market_data_batch_rows(rows))


def _broker_vendor_market_data_batch_checks(*rows: pd.Series) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for check in _vendor_market_data_batch_checks(*_broker_vendor_market_data_batch_rows(rows)):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "vendor market-data batch",
                "broker-readiness vendor market-data batch",
            )
        checks.append(renamed)
    return checks


def _broker_vendor_market_data_batch_rows(rows: tuple[pd.Series, ...]) -> tuple[pd.Series, ...]:
    return tuple(
        _vendor_market_data_batch_projection(
            row,
            source_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
        for row in rows
    )


def _vendor_market_data_batch_projection(row: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = row.copy()
    for suffix in (
        "provided",
        "ready",
        "adapter",
        "kind",
        "manifest_run_type",
        "market",
        "dataset_count",
        "ready_datasets",
        "failed_datasets",
        "ready_rate",
        "unique_source_files",
        "unique_header_fingerprints",
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
        "unique_mapping_drafts",
        "mapping_sources",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        mapped[f"vendor_market_data_batch_{suffix}"] = row.get(f"{source_prefix}_{suffix}", "")
    return mapped


def _shadow_broker_projection(row: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = row.copy()
    for suffix in (
        "readiness_sessions",
        "readiness_ready_sessions",
        "vendor_data_readiness_sessions",
        "vendor_data_readiness_provided_sessions",
        "vendor_data_readiness_ready_sessions",
        "vendor_data_readiness_failed_checks",
        "adapter",
        "adapter_count",
        "route_readiness_sessions",
        "route_readiness_ready_sessions",
        "route_readiness_strategy",
        "route_readiness_market",
        "route_readiness_gap_pairs",
        "dispatch_roundtrip_sessions",
        "dispatch_roundtrip_ready_sessions",
        "dispatch_roundtrip_strategy",
        "dispatch_roundtrip_market",
        "dispatch_roundtrip_scenario_count",
        "dispatch_roundtrip_missing_request_acks",
        "dispatch_roundtrip_rejected_orders",
        "dispatch_roundtrip_unmatched_acks",
        "route_dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_ready_sessions",
        "route_dispatch_roundtrip_strategy",
        "route_dispatch_roundtrip_market",
        "route_dispatch_roundtrip_scenario_count",
    ):
        mapped[f"shadow_broker_{suffix}"] = row.get(f"{source_prefix}_{suffix}", "")
    return mapped


def _prefixed_shadow_broker_summary_fields(
    rows: tuple[pd.Series, ...],
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, object]:
    return {
        f"{output_prefix}_readiness_provided": _prefixed_shadow_broker_readiness_provided(
            rows,
            source_prefix=source_prefix,
        ),
        f"{output_prefix}_readiness_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_readiness_sessions",
        ),
        f"{output_prefix}_readiness_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_readiness_ready_sessions",
        ),
        f"{output_prefix}_vendor_data_readiness_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_vendor_data_readiness_sessions",
        ),
        f"{output_prefix}_vendor_data_readiness_provided_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_vendor_data_readiness_provided_sessions",
        ),
        f"{output_prefix}_vendor_data_readiness_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_vendor_data_readiness_ready_sessions",
        ),
        f"{output_prefix}_vendor_data_readiness_failed_checks": _shadow_counter_max(
            rows,
            f"{source_prefix}_vendor_data_readiness_failed_checks",
        ),
        f"{output_prefix}_adapter": _prefixed_shadow_adapter_value(rows, source_prefix=source_prefix),
        f"{output_prefix}_adapter_count": _shadow_counter_max(rows, f"{source_prefix}_adapter_count"),
        f"{output_prefix}_route_readiness_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_readiness_sessions",
        ),
        f"{output_prefix}_route_readiness_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_readiness_ready_sessions",
        ),
        f"{output_prefix}_route_readiness_strategy": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_readiness",
            column="strategy",
        ),
        f"{output_prefix}_route_readiness_market": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_readiness",
            column="market",
        ),
        f"{output_prefix}_route_readiness_gap_pairs": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_readiness_gap_pairs",
        ),
        f"{output_prefix}_dispatch_roundtrip_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_sessions",
        ),
        f"{output_prefix}_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_ready_sessions",
        ),
        f"{output_prefix}_dispatch_roundtrip_strategy": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="dispatch_roundtrip",
            column="strategy",
        ),
        f"{output_prefix}_dispatch_roundtrip_market": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="dispatch_roundtrip",
            column="market",
        ),
        f"{output_prefix}_dispatch_roundtrip_scenario_count": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_scenario_count",
        ),
        f"{output_prefix}_dispatch_roundtrip_missing_request_acks": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_missing_request_acks",
        ),
        f"{output_prefix}_dispatch_roundtrip_rejected_orders": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_rejected_orders",
        ),
        f"{output_prefix}_dispatch_roundtrip_unmatched_acks": _shadow_counter_max(
            rows,
            f"{source_prefix}_dispatch_roundtrip_unmatched_acks",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_dispatch_roundtrip_sessions",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_dispatch_roundtrip_ready_sessions",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_strategy": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_dispatch_roundtrip",
            column="strategy",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_market": _prefixed_shadow_identity_value(
            rows,
            source_prefix=source_prefix,
            proof_name="route_dispatch_roundtrip",
            column="market",
        ),
        f"{output_prefix}_route_dispatch_roundtrip_scenario_count": _shadow_counter_max(
            rows,
            f"{source_prefix}_route_dispatch_roundtrip_scenario_count",
        ),
    }


def _broker_dispatch_ack_lineage_output_fields(row: pd.Series) -> dict[str, Any]:
    defaults = broker_dispatch_ack_lineage_fields(
        empty_broker_dispatch_ack_lineage()
    )
    return {
        column: row.get(column, default)
        for column, default in defaults.items()
    }


def _broker_dispatch_ack_lineage_config(summary: pd.Series) -> dict[str, Any]:
    return {
        column: _jsonable_check_value(summary[column])
        for column in BROKER_DISPATCH_ACK_LINEAGE_OUTPUT_COLUMNS
    }


def _summary(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    roundtrip_orders: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    passed = failed == 0
    proof_rows = (dispatch_summary, send_summary, ack_summary)
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "target_mode": _text(dispatch_summary, "target_mode"),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                **_broker_dispatch_ack_lineage_output_fields(ack_summary),
                "authorizes_submission": False,
                "broker_schema_status": _broker_schema_text(proof_rows, "broker_schema_status"),
                "broker_schema_reviewed": _broker_schema_reviewed(proof_rows),
                "broker_schema_review_mode": _broker_schema_text(proof_rows, "broker_schema_review_mode"),
                "dispatch_batch_id": _text(dispatch_summary, "dispatch_batch_id")
                or _text(send_summary, "dispatch_batch_id"),
                "dispatch_orders": int(_number(dispatch_summary, "dispatch_orders", len(roundtrip_orders))),
                "dispatch_total_notional": _strategy_portfolio_dispatch_total_notional(proof_rows),
                "strategy_portfolio_required": _strategy_portfolio_required(*proof_rows),
                "strategy_portfolio_provided": _strategy_portfolio_provided(*proof_rows),
                "strategy_portfolio_ready": _strategy_portfolio_bool_all(proof_rows, "strategy_portfolio_ready"),
                "strategy_portfolio_deployment_mode": _strategy_portfolio_text_value(
                    proof_rows,
                    "strategy_portfolio_deployment_mode",
                ),
                "strategy_portfolio_allocation_mode": _strategy_portfolio_text_value(
                    proof_rows,
                    "strategy_portfolio_allocation_mode",
                ),
                "strategy_portfolio_capital_currency": _strategy_portfolio_text_value(
                    proof_rows,
                    "strategy_portfolio_capital_currency",
                ),
                "strategy_portfolio_selected_profile": _strategy_portfolio_text_value(
                    proof_rows,
                    "strategy_portfolio_selected_profile",
                ),
                "strategy_portfolio_selected_strategy": _strategy_portfolio_identity_value(
                    proof_rows,
                    "strategy",
                ),
                "strategy_portfolio_selected_market": _strategy_portfolio_identity_value(
                    proof_rows,
                    "market",
                ),
                "strategy_portfolio_selected_eligible": _strategy_portfolio_bool_all(
                    proof_rows,
                    "strategy_portfolio_selected_eligible",
                ),
                "strategy_portfolio_selected_allocation_weight": _strategy_portfolio_number_max(
                    proof_rows,
                    "strategy_portfolio_selected_allocation_weight",
                ),
                "strategy_portfolio_selected_allocation_notional": _strategy_portfolio_number_min(
                    proof_rows,
                    "strategy_portfolio_selected_allocation_notional",
                ),
                "strategy_portfolio_notional_cap_applied": _strategy_portfolio_bool_all(
                    proof_rows,
                    "strategy_portfolio_notional_cap_applied",
                ),
                "strategy_portfolio_min_strategy_count": int(
                    _strategy_portfolio_number_max(proof_rows, "strategy_portfolio_min_strategy_count")
                ),
                "strategy_portfolio_min_market_count": int(
                    _strategy_portfolio_number_max(proof_rows, "strategy_portfolio_min_market_count")
                ),
                "strategy_portfolio_max_strategy_weight": _strategy_portfolio_number_max(
                    proof_rows,
                    "strategy_portfolio_max_strategy_weight",
                ),
                "strategy_portfolio_max_market_weight": _strategy_portfolio_number_max(
                    proof_rows,
                    "strategy_portfolio_max_market_weight",
                ),
                "strategy_portfolio_allocated_strategy_count": int(
                    _strategy_portfolio_number_max(proof_rows, "strategy_portfolio_allocated_strategy_count")
                ),
                "strategy_portfolio_allocated_market_count": int(
                    _strategy_portfolio_number_max(proof_rows, "strategy_portfolio_allocated_market_count")
                ),
                "strategy_portfolio_top_strategy_by_weight": _strategy_portfolio_text_value(
                    proof_rows,
                    "strategy_portfolio_top_strategy_by_weight",
                ),
                "strategy_portfolio_top_market_by_weight": _strategy_portfolio_text_value(
                    proof_rows,
                    "strategy_portfolio_top_market_by_weight",
                ),
                "strategy_portfolio_max_strategy_allocation_weight": _strategy_portfolio_number_max(
                    proof_rows,
                    "strategy_portfolio_max_strategy_allocation_weight",
                ),
                "strategy_portfolio_max_market_allocation_weight": _strategy_portfolio_number_max(
                    proof_rows,
                    "strategy_portfolio_max_market_allocation_weight",
                ),
                "pre_portfolio_max_notional_per_session": _strategy_portfolio_number_max(
                    proof_rows,
                    "pre_portfolio_max_notional_per_session",
                ),
                "send_requests": int(_number(send_summary, "requests", 0.0)),
                "acked_orders": int(_number(ack_summary, "acked_orders", 0.0)),
                "missing_request_acks": _missing_request_acks(roundtrip_orders),
                "rejected_orders": int(_number(ack_summary, "rejected_orders", 0.0)),
                "duplicate_ack_orders": int(_number(ack_summary, "duplicate_ack_orders", 0.0)),
                "unmatched_acks": int(_number(ack_summary, "unmatched_acks", 0.0)),
                "route_readiness_required": _route_readiness_required(
                    dispatch_summary,
                    send_summary,
                    ack_summary,
                    thresholds,
                ),
                "route_readiness_provided": _route_readiness_provided(*proof_rows),
                "route_readiness_ready": all(
                    _to_bool(row.get("route_readiness_ready", False)) for row in proof_rows
                ),
                "route_readiness_strategy": _route_readiness_identity_value(dispatch_summary, "strategy")
                or _route_readiness_identity_value(send_summary, "strategy")
                or _route_readiness_identity_value(ack_summary, "strategy"),
                "route_readiness_market": _route_readiness_identity_value(dispatch_summary, "market")
                or _route_readiness_identity_value(send_summary, "market")
                or _route_readiness_identity_value(ack_summary, "market"),
                "route_readiness_route_ready_pairs": _route_readiness_counter_max(
                    proof_rows,
                    "route_readiness_route_ready_pairs",
                ),
                "route_readiness_gap_pairs": _route_readiness_counter_max(
                    proof_rows,
                    "route_readiness_gap_pairs",
                ),
                "route_readiness_recommendation": _route_readiness_recommendation(*proof_rows),
                "route_readiness_ops_launch_controls_present": all(
                    _to_bool(row.get("route_readiness_ops_launch_controls_present", False))
                    for row in proof_rows
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": _route_readiness_counter_max(
                    proof_rows,
                    "route_readiness_ops_launch_controls_blocked_pairs",
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": _route_readiness_counter_max(
                    proof_rows,
                    "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    _route_readiness_counter_max(
                        proof_rows,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    )
                ),
                **_route_broker_route_readiness_summary_fields(proof_rows),
                **_resume_route_readiness_summary_fields(
                    proof_rows,
                    prefix="route_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_summary_fields(
                    proof_rows,
                    prefix="route_broker_resume_incident_broker_route_readiness",
                ),
                "shadow_broker_readiness_provided": _shadow_broker_readiness_provided(*proof_rows),
                "shadow_broker_readiness_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_readiness_sessions",
                ),
                "shadow_broker_readiness_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_readiness_ready_sessions",
                ),
                "shadow_broker_vendor_data_readiness_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_vendor_data_readiness_sessions",
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_vendor_data_readiness_provided_sessions",
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_vendor_data_readiness_ready_sessions",
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_vendor_data_readiness_failed_checks",
                ),
                "shadow_broker_adapter": _shadow_adapter_value(proof_rows),
                "shadow_broker_adapter_count": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_adapter_count",
                ),
                "shadow_broker_route_readiness_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_readiness_sessions",
                ),
                "shadow_broker_route_readiness_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_readiness_ready_sessions",
                ),
                "shadow_broker_route_readiness_strategy": _shadow_identity_value(
                    proof_rows,
                    "route_readiness",
                    "strategy",
                ),
                "shadow_broker_route_readiness_market": _shadow_identity_value(
                    proof_rows,
                    "route_readiness",
                    "market",
                ),
                "shadow_broker_route_readiness_gap_pairs": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_readiness_gap_pairs",
                ),
                "shadow_broker_dispatch_roundtrip_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_sessions",
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_ready_sessions",
                ),
                "shadow_broker_dispatch_roundtrip_strategy": _shadow_identity_value(
                    proof_rows,
                    "dispatch_roundtrip",
                    "strategy",
                ),
                "shadow_broker_dispatch_roundtrip_market": _shadow_identity_value(
                    proof_rows,
                    "dispatch_roundtrip",
                    "market",
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_scenario_count",
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_missing_request_acks",
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_rejected_orders",
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_dispatch_roundtrip_unmatched_acks",
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_dispatch_roundtrip_sessions",
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions",
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": _shadow_identity_value(
                    proof_rows,
                    "route_dispatch_roundtrip",
                    "strategy",
                ),
                "shadow_broker_route_dispatch_roundtrip_market": _shadow_identity_value(
                    proof_rows,
                    "route_dispatch_roundtrip",
                    "market",
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": _shadow_counter_max(
                    proof_rows,
                    "shadow_broker_route_dispatch_roundtrip_scenario_count",
                ),
                **_prefixed_shadow_broker_summary_fields(
                    proof_rows,
                    source_prefix="route_broker_shadow_broker",
                    output_prefix="broker_shadow_broker",
                ),
                **_broker_vendor_data_readiness_summary_fields(proof_rows),
                **_vendor_market_data_batch_summary_fields(proof_rows),
                **_broker_vendor_market_data_batch_summary_fields(proof_rows),
                "route_dispatch_roundtrip_required": _dispatch_roundtrip_required(dispatch_summary, thresholds),
                "route_dispatch_roundtrip_provided": _route_roundtrip_provided(*proof_rows),
                "route_dispatch_roundtrip_ready": all(
                    _to_bool(row.get("route_dispatch_roundtrip_ready", False)) for row in proof_rows
                ),
                "route_dispatch_roundtrip_target_mode": _route_identity_value(dispatch_summary, "target_mode")
                or _route_identity_value(send_summary, "target_mode")
                or _route_identity_value(ack_summary, "target_mode"),
                "route_dispatch_roundtrip_strategy": _route_identity_value(dispatch_summary, "strategy")
                or _route_identity_value(send_summary, "strategy")
                or _route_identity_value(ack_summary, "strategy"),
                "route_dispatch_roundtrip_market": _route_identity_value(dispatch_summary, "market")
                or _route_identity_value(send_summary, "market")
                or _route_identity_value(ack_summary, "market"),
                "route_dispatch_roundtrip_scenario_key": _route_identity_value(dispatch_summary, "scenario_key")
                or _route_identity_value(send_summary, "scenario_key")
                or _route_identity_value(ack_summary, "scenario_key"),
                "route_dispatch_roundtrip_batch_id": _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
                or _text(send_summary, "route_dispatch_roundtrip_batch_id")
                or _text(ack_summary, "route_dispatch_roundtrip_batch_id"),
                "route_dispatch_roundtrip_requests": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_requests",
                ),
                "route_dispatch_roundtrip_acked_orders": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_acked_orders",
                ),
                "route_dispatch_roundtrip_missing_request_acks": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_missing_request_acks",
                ),
                "route_dispatch_roundtrip_rejected_orders": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_rejected_orders",
                ),
                "route_dispatch_roundtrip_unmatched_acks": _route_roundtrip_counter_max(
                    proof_rows,
                    "route_dispatch_roundtrip_unmatched_acks",
                ),
                "route_enable_dispatch_roundtrip_failed_checks": _route_enable_failed_checks(*proof_rows),
                "total_failed_component_checks": _component_failed_checks(
                    dispatch_summary,
                    send_summary,
                    ack_summary,
                ),
                "failed_checks": failed,
                "recommendation": "broker_dry_run_roundtrip_proved"
                if passed
                else "investigate_broker_dry_run_roundtrip",
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
    out["failed_check_names"] = ";".join(failed["check"].astype(str).tolist()) if not failed.empty else ""
    out["first_failed_reason"] = _object_text(failed.iloc[0].get("reason")).strip() if not failed.empty else ""
    out["primary_blocker_check"] = _object_text(failed.iloc[0].get("check")).strip() if not failed.empty else ""
    out["primary_blocker_value"] = _object_text(failed.iloc[0].get("value")).strip() if not failed.empty else ""
    out["primary_blocker_operator"] = _object_text(failed.iloc[0].get("operator")).strip() if not failed.empty else ""
    out["primary_blocker_threshold"] = _object_text(failed.iloc[0].get("threshold")).strip() if not failed.empty else ""
    out["primary_blocker_reason"] = _object_text(failed.iloc[0].get("reason")).strip() if not failed.empty else ""
    out["action_queue_count"] = int(len(action_queue))
    out["ready_action_count"] = int((statuses == "ready").sum()) if not statuses.empty else 0
    out["blocked_action_count"] = int((statuses == "blocked").sum()) if not statuses.empty else 0
    out["review_action_count"] = int((statuses == "review").sum()) if not statuses.empty else 0
    out["next_gate"] = next_gate
    out["next_gate_help_command"] = _help_command(next_gate)
    out["primary_action_status"] = _first_action_value(action_queue, "queue_status")
    return out


def _action_queue(summary: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _object_text(row.get("check")).strip()
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "broker_dispatch_roundtrip_checks",
                "component": _component(check),
                "check": check,
                "actual": row.get("value"),
                "operator": _object_text(row.get("operator")).strip(),
                "expected": row.get("threshold"),
                "target_mode": _object_text(summary.get("target_mode")).strip(),
                "strategy": _object_text(summary.get("strategy")).strip(),
                "market": _object_text(summary.get("market")).strip(),
                "scenario_key": _object_text(summary.get("scenario_key")).strip(),
                "adapter": _object_text(summary.get("adapter")).strip(),
                "next_gate": next_gate,
                "next_gate_help_command": _help_command(next_gate),
                "reason": _object_text(row.get("reason")).strip(),
                "recommendation": _action_recommendation(check),
            }
        )
    ordered_rows = []
    for priority, row in enumerate(rows, start=1):
        item = {column: row.get(column, "") for column in ACTION_QUEUE_COLUMNS}
        item["priority"] = priority
        ordered_rows.append(item)
    return pd.DataFrame(ordered_rows, columns=ACTION_QUEUE_COLUMNS)


def _failed_check_rows(checks: pd.DataFrame) -> pd.DataFrame:
    if checks.empty or "passed" not in checks.columns:
        return checks.iloc[0:0].copy()
    return checks.loc[~checks["passed"].astype(bool)].copy()


def _component(check: str) -> str:
    if check.startswith("broker_dispatch_ack_"):
        return "broker_dispatch_ack"
    if check.startswith("strategy_portfolio_") or "strategy_portfolio" in check:
        return "strategy_portfolio"
    if "vendor_market_data_batch" in check:
        return "vendor_market_data"
    if "broker_vendor_data_readiness" in check or "vendor_data_readiness" in check:
        return "broker_vendor_data_readiness"
    if check.startswith("route_broker_resume_"):
        return "resume_gate"
    if "route_readiness" in check:
        return "route_readiness"
    if check.startswith("shadow_broker") or check.startswith("broker_shadow_broker"):
        return "broker_readiness"
    if (
        "dispatch_roundtrip" in check
        or "route_roundtrip" in check
        or check == "route_enable_dispatch_roundtrip_failed_checks"
    ):
        return "broker_dispatch_roundtrip"
    if check in {"dispatch_ready", "target_mode_matches"}:
        return "broker_dispatch_plan"
    if check in {
        "send_ready",
        "request_count_matches_dispatch",
        "unique_request_per_dispatch_order",
        "submission_disabled",
        "dry_run_only",
    }:
        return "broker_dispatch_send"
    if check in {
        "ack_passed",
        "all_requests_acked",
        "missing_request_acks",
        "rejected_orders",
        "duplicate_ack_orders",
        "unmatched_acks",
    }:
        return "broker_dispatch_ack"
    return "broker_dispatch_roundtrip"


def _next_gate(check: str) -> str:
    component = _component(check)
    if component == "broker_dispatch_plan":
        return "plan-broker-dispatch"
    if component == "broker_dispatch_send":
        return "prepare-broker-dispatch-send"
    if component == "broker_dispatch_ack":
        return "reconcile-broker-dispatch"
    if component == "strategy_portfolio":
        return "review-cutover-gate"
    if component == "resume_gate":
        return "review-resume-gate"
    if component == "route_readiness":
        return "review-route-readiness"
    if component == "vendor_market_data":
        return "pipeline-vendor-market-data-batch"
    if component == "broker_vendor_data_readiness":
        return "pipeline-broker-vendor-readiness"
    if component == "broker_readiness":
        return "review-broker-readiness"
    return "review-broker-dispatch-roundtrip"


def _action_recommendation(check: str) -> str:
    component = _component(check)
    if component == "broker_dispatch_plan":
        return "repair_or_rebuild_broker_dispatch_plan"
    if component == "broker_dispatch_send":
        return "repair_non_submitting_broker_sender_packet"
    if component == "broker_dispatch_ack":
        return "repair_broker_acknowledgement_reconciliation"
    if component == "strategy_portfolio":
        return "repair_strategy_portfolio_cutover_allocation"
    if component == "resume_gate":
        return "repair_broker_resume_route_readiness_before_roundtrip_review"
    if component == "route_readiness":
        return "rerun_route_readiness_before_roundtrip_review"
    if component == "vendor_market_data":
        return "refresh_vendor_market_data_batch_proof"
    if component == "broker_vendor_data_readiness":
        return "refresh_broker_vendor_data_readiness_wrapper"
    if component == "broker_readiness":
        return "repair_broker_readiness_shadow_proof"
    if check == "identity_match":
        return "align_dispatch_send_ack_identity_before_roundtrip_review"
    if check == "component_failed_checks":
        return "repair_failed_component_reports_before_roundtrip_review"
    return "repair_broker_dispatch_roundtrip_inputs"


def _vendor_market_data_batch_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    return {
        "roundtrip_vendor_market_data_batch_provided": bool(
            rows and all(_to_bool(row.get("vendor_market_data_batch_provided", False)) for row in rows)
        ),
        "roundtrip_vendor_market_data_batch_ready": bool(
            rows and all(_to_bool(row.get("vendor_market_data_batch_ready", False)) for row in rows)
        ),
        "roundtrip_vendor_market_data_batch_adapter": _vendor_market_data_batch_identity_value(rows, "adapter"),
        "roundtrip_vendor_market_data_batch_kind": _vendor_market_data_batch_text_value(rows, "kind"),
        "roundtrip_vendor_market_data_batch_manifest_run_type": _vendor_market_data_batch_identity_value(
            rows,
            "manifest_run_type",
        ),
        "roundtrip_vendor_market_data_batch_market": _vendor_market_data_batch_identity_value(rows, "market"),
        "roundtrip_vendor_market_data_batch_dataset_count": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_dataset_count",
        ),
        "roundtrip_vendor_market_data_batch_ready_datasets": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_ready_datasets",
        ),
        "roundtrip_vendor_market_data_batch_failed_datasets": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_failed_datasets",
        ),
        "roundtrip_vendor_market_data_batch_ready_rate": _vendor_market_data_batch_number_min(
            rows,
            "vendor_market_data_batch_ready_rate",
        ),
        "roundtrip_vendor_market_data_batch_unique_source_files": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_unique_source_files",
        ),
        "roundtrip_vendor_market_data_batch_unique_header_fingerprints": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_unique_header_fingerprints",
        ),
        "roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage": (
            _vendor_market_data_batch_number_min(
                rows,
                "vendor_market_data_batch_source_file_fingerprint_coverage",
            )
        ),
        "roundtrip_vendor_market_data_batch_min_mapping_coverage": _vendor_market_data_batch_number_min(
            rows,
            "vendor_market_data_batch_min_mapping_coverage",
        ),
        "roundtrip_vendor_market_data_batch_unique_mapping_drafts": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_unique_mapping_drafts",
        ),
        "roundtrip_vendor_market_data_batch_mapping_sources": _vendor_market_data_batch_text_value(
            rows,
            "mapping_sources",
        ),
        "roundtrip_vendor_market_data_batch_comparison_accepted": bool(
            rows
            and all(_to_bool(row.get("vendor_market_data_batch_comparison_accepted", False)) for row in rows)
        ),
        "roundtrip_vendor_market_data_batch_comparison_failed_checks": _vendor_market_data_batch_counter_max(
            rows,
            "vendor_market_data_batch_comparison_failed_checks",
        ),
        "roundtrip_vendor_market_data_batch_datasets_json": _vendor_market_data_batch_datasets_json(rows),
    }


def _broker_vendor_market_data_batch_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    fields = _vendor_market_data_batch_summary_fields(
        _broker_vendor_market_data_batch_rows(rows)
    )
    return {
        key.replace(
            "roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        ): value
        for key, value in fields.items()
    }


def _broker_vendor_data_readiness_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    return {
        "roundtrip_broker_vendor_data_readiness_provided": bool(
            rows and all(_to_bool(row.get("broker_vendor_data_readiness_provided", False)) for row in rows)
        ),
        "roundtrip_broker_vendor_data_readiness_ready": bool(
            rows and all(_to_bool(row.get("broker_vendor_data_readiness_ready", False)) for row in rows)
        ),
        "roundtrip_broker_vendor_data_readiness_failed_checks": _broker_vendor_data_readiness_counter_max(
            rows,
            "broker_vendor_data_readiness_failed_checks",
        ),
    }


def _route_broker_route_readiness_summary_fields(rows: tuple[pd.Series, ...]) -> dict[str, object]:
    return {
        "route_broker_route_readiness_required": any(
            _to_bool(row.get("route_broker_route_readiness_required", False)) for row in rows
        ),
        "route_broker_route_readiness_provided": bool(
            rows and all(_to_bool(row.get("route_broker_route_readiness_provided", False)) for row in rows)
        ),
        "route_broker_route_readiness_ready": bool(
            rows and all(_to_bool(row.get("route_broker_route_readiness_ready", False)) for row in rows)
        ),
        "route_broker_route_readiness_strategy": _route_broker_route_readiness_identity_value(
            rows,
            "strategy",
        ),
        "route_broker_route_readiness_market": _route_broker_route_readiness_identity_value(
            rows,
            "market",
        ),
        "route_broker_route_readiness_route_ready_pairs": _route_readiness_counter_max(
            rows,
            "route_broker_route_readiness_route_ready_pairs",
        ),
        "route_broker_route_readiness_gap_pairs": _route_readiness_counter_max(
            rows,
            "route_broker_route_readiness_gap_pairs",
        ),
        "route_broker_route_readiness_recommendation": _route_broker_route_readiness_recommendation(*rows),
        "route_broker_route_readiness_ops_launch_controls_ready": bool(
            rows
            and all(_to_bool(row.get("route_broker_route_readiness_ops_launch_controls_ready", False)) for row in rows)
        ),
        "route_broker_route_readiness_ops_launch_control_failures": (
            _route_broker_route_readiness_launch_control_failures(rows)
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": _route_readiness_counter_min(
            rows,
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": _route_readiness_counter_max(
            rows,
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
            _route_readiness_counter_min(
                rows,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            )
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
            _route_readiness_counter_max(
                rows,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            )
        ),
    }


def _resume_route_readiness_summary_fields(rows: tuple[pd.Series, ...], *, prefix: str) -> dict[str, object]:
    return {
        f"{prefix}_required": any(_to_bool(row.get(f"{prefix}_required", False)) for row in rows),
        f"{prefix}_provided": bool(
            rows and all(_to_bool(row.get(f"{prefix}_provided", False)) for row in rows)
        ),
        f"{prefix}_ready": bool(rows and all(_to_bool(row.get(f"{prefix}_ready", False)) for row in rows)),
        f"{prefix}_strategy": _resume_route_readiness_identity_value(rows, prefix, "strategy"),
        f"{prefix}_market": _resume_route_readiness_identity_value(rows, prefix, "market"),
        f"{prefix}_route_ready_pairs": _route_readiness_counter_max(rows, f"{prefix}_route_ready_pairs"),
        f"{prefix}_gap_pairs": _route_readiness_counter_max(rows, f"{prefix}_gap_pairs"),
        f"{prefix}_recommendation": _resume_route_readiness_recommendation(rows, prefix),
        f"{prefix}_ops_launch_controls_ready": bool(
            rows and all(_to_bool(row.get(f"{prefix}_ops_launch_controls_ready", False)) for row in rows)
        ),
        f"{prefix}_ops_launch_control_failures": _resume_route_readiness_launch_control_failures(rows, prefix),
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": _route_readiness_counter_min(
            rows,
            f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs",
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": _route_readiness_counter_max(
            rows,
            f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs",
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": _route_readiness_counter_min(
            rows,
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": _route_readiness_counter_max(
            rows,
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
        ),
    }


def _prefixed_shadow_broker_config(summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        "provided": _to_bool(summary[f"{field_prefix}_readiness_provided"]),
        "sessions": int(summary[f"{field_prefix}_readiness_sessions"]),
        "ready_sessions": int(summary[f"{field_prefix}_readiness_ready_sessions"]),
        "adapter": _text(summary, f"{field_prefix}_adapter"),
        "adapter_count": int(summary[f"{field_prefix}_adapter_count"]),
        "broker_vendor_data_readiness": {
            "sessions": int(summary[f"{field_prefix}_vendor_data_readiness_sessions"]),
            "provided_sessions": int(summary[f"{field_prefix}_vendor_data_readiness_provided_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_vendor_data_readiness_ready_sessions"]),
            "failed_checks": int(summary[f"{field_prefix}_vendor_data_readiness_failed_checks"]),
        },
        "route_readiness": {
            "sessions": int(summary[f"{field_prefix}_route_readiness_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_route_readiness_ready_sessions"]),
            "strategy": _text(summary, f"{field_prefix}_route_readiness_strategy"),
            "market": _text(summary, f"{field_prefix}_route_readiness_market"),
            "max_gap_pairs": int(summary[f"{field_prefix}_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(summary[f"{field_prefix}_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_dispatch_roundtrip_ready_sessions"]),
            "strategy": _text(summary, f"{field_prefix}_dispatch_roundtrip_strategy"),
            "market": _text(summary, f"{field_prefix}_dispatch_roundtrip_market"),
            "scenario_count": int(summary[f"{field_prefix}_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(summary[f"{field_prefix}_dispatch_roundtrip_missing_request_acks"]),
            "max_rejected_orders": int(summary[f"{field_prefix}_dispatch_roundtrip_rejected_orders"]),
            "max_unmatched_acks": int(summary[f"{field_prefix}_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(summary[f"{field_prefix}_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(summary[f"{field_prefix}_route_dispatch_roundtrip_ready_sessions"]),
            "strategy": _text(summary, f"{field_prefix}_route_dispatch_roundtrip_strategy"),
            "market": _text(summary, f"{field_prefix}_route_dispatch_roundtrip_market"),
            "scenario_count": int(summary[f"{field_prefix}_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _vendor_market_data_batch_config(
    summary: pd.Series,
    *,
    field_prefix: str = "roundtrip_vendor_market_data_batch",
) -> dict[str, object]:
    return {
        "provided": _to_bool(summary[f"{field_prefix}_provided"]),
        "ready": _to_bool(summary[f"{field_prefix}_ready"]),
        "adapter": _text(summary, f"{field_prefix}_adapter"),
        "kind": _text(summary, f"{field_prefix}_kind"),
        "manifest_run_type": _text(summary, f"{field_prefix}_manifest_run_type"),
        "market": _text(summary, f"{field_prefix}_market"),
        "dataset_count": int(summary[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(summary[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(summary[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(summary[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(summary[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(
            summary[f"{field_prefix}_unique_header_fingerprints"]
        ),
        "source_file_fingerprint_coverage": _jsonable(
            summary[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(summary[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(summary[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": _text(summary, f"{field_prefix}_mapping_sources"),
        "comparison": {
            "accepted": _to_bool(summary[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(summary[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_data_readiness_config(summary: pd.Series) -> dict[str, object]:
    return {
        "provided": _to_bool(summary["roundtrip_broker_vendor_data_readiness_provided"]),
        "ready": _to_bool(summary["roundtrip_broker_vendor_data_readiness_ready"]),
        "failed_checks": int(summary["roundtrip_broker_vendor_data_readiness_failed_checks"]),
    }


def _route_broker_route_readiness_config(summary: pd.Series) -> dict[str, object]:
    return {
        "required": _to_bool(summary["route_broker_route_readiness_required"]),
        "provided": _to_bool(summary["route_broker_route_readiness_provided"]),
        "ready": _to_bool(summary["route_broker_route_readiness_ready"]),
        "strategy": _text(summary, "route_broker_route_readiness_strategy"),
        "market": _text(summary, "route_broker_route_readiness_market"),
        "route_ready_pairs": int(summary["route_broker_route_readiness_route_ready_pairs"]),
        "gap_pairs": int(summary["route_broker_route_readiness_gap_pairs"]),
        "recommendation": _text(summary, "route_broker_route_readiness_recommendation"),
        "ops_launch_controls_ready": _to_bool(
            summary["route_broker_route_readiness_ops_launch_controls_ready"]
        ),
        "ops_launch_control_failures": _text(
            summary, "route_broker_route_readiness_ops_launch_control_failures"
        ),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _resume_route_readiness_config(summary: pd.Series, *, prefix: str) -> dict[str, object]:
    return {
        "required": _to_bool(summary[f"{prefix}_required"]),
        "provided": _to_bool(summary[f"{prefix}_provided"]),
        "ready": _to_bool(summary[f"{prefix}_ready"]),
        "strategy": _text(summary, f"{prefix}_strategy"),
        "market": _text(summary, f"{prefix}_market"),
        "route_ready_pairs": int(summary[f"{prefix}_route_ready_pairs"]),
        "gap_pairs": int(summary[f"{prefix}_gap_pairs"]),
        "recommendation": _text(summary, f"{prefix}_recommendation"),
        "ops_launch_controls_ready": _to_bool(summary[f"{prefix}_ops_launch_controls_ready"]),
        "ops_launch_control_failures": _text(summary, f"{prefix}_ops_launch_control_failures"),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            summary[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _config(
    summary: pd.Series,
    thresholds: BrokerDispatchRoundTripThresholds,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "passed": _to_bool(summary["passed"]),
        "failed_check_count": len(failed_check_records),
        "target_mode": _text(summary, "target_mode"),
        "strategy": _text(summary, "strategy"),
        "market": _text(summary, "market"),
        "scenario_key": _text(summary, "scenario_key"),
        "adapter": _text(summary, "adapter"),
        "broker_dispatch_ack_lineage": _broker_dispatch_ack_lineage_config(
            summary
        ),
        "broker_readiness": {
            "adapter_schema_status": _text(summary, "broker_schema_status"),
            "schema_reviewed": _to_bool(summary["broker_schema_reviewed"]),
            "schema_review_mode": _text(summary, "broker_schema_review_mode"),
        },
        "dispatch_batch_id": _text(summary, "dispatch_batch_id"),
        "dispatch_orders": int(summary["dispatch_orders"]),
        "dispatch_total_notional": float(summary["dispatch_total_notional"]),
        "strategy_portfolio": {
            "required": _to_bool(summary["strategy_portfolio_required"]),
            "provided": _to_bool(summary["strategy_portfolio_provided"]),
            "ready": _to_bool(summary["strategy_portfolio_ready"]),
            "deployment_mode": _text(summary, "strategy_portfolio_deployment_mode"),
            "allocation_mode": _text(summary, "strategy_portfolio_allocation_mode"),
            "capital_currency": _text(summary, "strategy_portfolio_capital_currency"),
            "selected_profile": _text(summary, "strategy_portfolio_selected_profile"),
            "selected_strategy": _text(summary, "strategy_portfolio_selected_strategy"),
            "selected_market": _text(summary, "strategy_portfolio_selected_market"),
            "selected_eligible": _to_bool(summary["strategy_portfolio_selected_eligible"]),
            "selected_allocation_weight": float(summary["strategy_portfolio_selected_allocation_weight"]),
            "selected_allocation_notional": float(summary["strategy_portfolio_selected_allocation_notional"]),
            "notional_cap_applied": _to_bool(summary["strategy_portfolio_notional_cap_applied"]),
            "min_strategy_count": int(summary["strategy_portfolio_min_strategy_count"]),
            "min_market_count": int(summary["strategy_portfolio_min_market_count"]),
            "max_strategy_weight": float(summary["strategy_portfolio_max_strategy_weight"]),
            "max_market_weight": float(summary["strategy_portfolio_max_market_weight"]),
            "allocated_strategy_count": int(summary["strategy_portfolio_allocated_strategy_count"]),
            "allocated_market_count": int(summary["strategy_portfolio_allocated_market_count"]),
            "top_strategy_by_weight": _text(summary, "strategy_portfolio_top_strategy_by_weight"),
            "top_market_by_weight": _text(summary, "strategy_portfolio_top_market_by_weight"),
            "max_strategy_allocation_weight": float(
                summary["strategy_portfolio_max_strategy_allocation_weight"]
            ),
            "max_market_allocation_weight": float(summary["strategy_portfolio_max_market_allocation_weight"]),
            "pre_portfolio_max_notional_per_session": float(summary["pre_portfolio_max_notional_per_session"]),
        },
        "send_requests": int(summary["send_requests"]),
        "acked_orders": int(summary["acked_orders"]),
        "missing_request_acks": int(summary["missing_request_acks"]),
        "rejected_orders": int(summary["rejected_orders"]),
        "duplicate_ack_orders": int(summary["duplicate_ack_orders"]),
        "unmatched_acks": int(summary["unmatched_acks"]),
        "route_readiness": {
            "required": _to_bool(summary["route_readiness_required"]),
            "provided": _to_bool(summary["route_readiness_provided"]),
            "ready": _to_bool(summary["route_readiness_ready"]),
            "strategy": _text(summary, "route_readiness_strategy"),
            "market": _text(summary, "route_readiness_market"),
            "route_ready_pairs": int(summary["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(summary["route_readiness_gap_pairs"]),
            "ops_launch_controls_present": _to_bool(summary["route_readiness_ops_launch_controls_present"]),
            "ops_launch_controls_blocked_pairs": int(summary["route_readiness_ops_launch_controls_blocked_pairs"]),
            "ops_broker_roundtrip_portfolio_breach_pairs": int(
                summary["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                summary["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]
            ),
            "recommendation": _text(summary, "route_readiness_recommendation"),
        },
        "route_broker_route_readiness": _route_broker_route_readiness_config(summary),
        "route_broker_resume_gate": {
            "broker_route_readiness": _resume_route_readiness_config(
                summary,
                prefix="route_broker_resume_broker_route_readiness",
            ),
            "incident_broker_route_readiness": _resume_route_readiness_config(
                summary,
                prefix="route_broker_resume_incident_broker_route_readiness",
            ),
        },
        "shadow_broker_readiness": {
            "provided": _to_bool(summary["shadow_broker_readiness_provided"]),
            "sessions": int(summary["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(summary["shadow_broker_readiness_ready_sessions"]),
            "adapter": _text(summary, "shadow_broker_adapter"),
            "adapter_count": int(summary["shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(summary["shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(summary["shadow_broker_vendor_data_readiness_provided_sessions"]),
                "ready_sessions": int(summary["shadow_broker_vendor_data_readiness_ready_sessions"]),
                "failed_checks": int(summary["shadow_broker_vendor_data_readiness_failed_checks"]),
            },
            "route_readiness": {
                "sessions": int(summary["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": _text(summary, "shadow_broker_route_readiness_strategy"),
                "market": _text(summary, "shadow_broker_route_readiness_market"),
                "max_gap_pairs": int(summary["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": _text(summary, "shadow_broker_dispatch_roundtrip_strategy"),
                "market": _text(summary, "shadow_broker_dispatch_roundtrip_market"),
                "scenario_count": int(summary["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    summary["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(summary["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(summary["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(summary["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(summary["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": _text(summary, "shadow_broker_route_dispatch_roundtrip_strategy"),
                "market": _text(summary, "shadow_broker_route_dispatch_roundtrip_market"),
                "scenario_count": int(summary["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "broker_shadow_broker_readiness": _prefixed_shadow_broker_config(
            summary,
            field_prefix="broker_shadow_broker",
        ),
        "roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(summary),
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _vendor_market_data_batch_config(
                summary,
                field_prefix="roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            )
        ),
        "roundtrip_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(summary),
        "route_dispatch_roundtrip": {
            "required": _to_bool(summary["route_dispatch_roundtrip_required"]),
            "provided": _to_bool(summary["route_dispatch_roundtrip_provided"]),
            "ready": _to_bool(summary["route_dispatch_roundtrip_ready"]),
            "target_mode": _text(summary, "route_dispatch_roundtrip_target_mode"),
            "strategy": _text(summary, "route_dispatch_roundtrip_strategy"),
            "market": _text(summary, "route_dispatch_roundtrip_market"),
            "scenario_key": _text(summary, "route_dispatch_roundtrip_scenario_key"),
            "dispatch_batch_id": _text(summary, "route_dispatch_roundtrip_batch_id"),
            "requests": int(summary["route_dispatch_roundtrip_requests"]),
            "acked_orders": int(summary["route_dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(summary["route_dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(summary["route_dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(summary["route_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": int(summary["route_enable_dispatch_roundtrip_failed_checks"]),
        },
        "thresholds": asdict(thresholds),
        "failed_checks": [str(record.get("check", "")) for record in failed_check_records],
        "primary_blocker": failed_check_records[0] if failed_check_records else {},
        "action_queue_count": int(len(action_queue)),
        "ready_action_count": int((statuses == "ready").sum()) if not statuses.empty else 0,
        "blocked_action_count": int((statuses == "blocked").sum()) if not statuses.empty else 0,
        "review_action_count": int((statuses == "review").sum()) if not statuses.empty else 0,
        "next_gate": next_gate,
        "next_gate_help_command": _help_command(next_gate),
        "primary_action_status": _first_action_value(action_queue, "queue_status"),
        "primary_action": _first_action_record(action_queue),
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(_actions_with_status(action_queue, "ready")),
        "blocked_actions": _action_records(_actions_with_status(action_queue, "blocked")),
        "review_actions": _action_records(_actions_with_status(action_queue, "review")),
    }


def _failed_check_records(checks: pd.DataFrame) -> list[dict[str, object]]:
    if checks.empty or "passed" not in checks.columns:
        return []
    failed = checks.loc[~checks["passed"].astype(bool)]
    return [_jsonable_check_record(row) for row in failed.to_dict(orient="records")]


def _jsonable_check_record(row: dict[str, Any]) -> dict[str, object]:
    return {str(key): _jsonable_check_value(value) for key, value in row.items()}


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    passed_label = "yes" if _to_bool(summary_row.get("passed", False)) else "no"
    ack_lineage_label = (
        "yes"
        if _to_bool(
            summary_row.get("broker_dispatch_ack_lineage_gate_passed")
        )
        else "no"
    )
    lines = [
        "# Broker Dispatch Round-Trip Runbook",
        "",
        f"- Passed: {passed_label}",
        f"- Target mode: {_object_text(summary_row.get('target_mode')).strip()}",
        f"- Strategy: {_object_text(summary_row.get('strategy')).strip()}",
        f"- Market: {_object_text(summary_row.get('market')).strip()}",
        f"- Scenario: {_object_text(summary_row.get('scenario_key')).strip()}",
        f"- Adapter: {_object_text(summary_row.get('adapter')).strip()}",
        f"- Dispatch batch: {_object_text(summary_row.get('dispatch_batch_id')).strip()}",
        f"- Dispatch orders: {_int_value(summary_row.get('dispatch_orders'))}",
        f"- Send requests: {_int_value(summary_row.get('send_requests'))}",
        f"- Acked orders: {_int_value(summary_row.get('acked_orders'))}",
        f"- Missing request acknowledgements: {_int_value(summary_row.get('missing_request_acks'))}",
        f"- Rejected orders: {_int_value(summary_row.get('rejected_orders'))}",
        f"- Acknowledgement lineage current: {ack_lineage_label}",
        f"- Route readiness ready: {_object_text(summary_row.get('route_readiness_ready')).strip()}",
        f"- Resume broker route ready: {_object_text(summary_row.get('route_broker_resume_broker_route_readiness_ready')).strip()}",
        f"- Resume incident route ready: {_object_text(summary_row.get('route_broker_resume_incident_broker_route_readiness_ready')).strip()}",
        f"- Route dispatch round-trip ready: {_object_text(summary_row.get('route_dispatch_roundtrip_ready')).strip()}",
        f"- Total failed component checks: {_int_value(summary_row.get('total_failed_component_checks'))}",
        f"- Failed checks: {_int_value(summary_row.get('failed_check_count'))}",
        f"- Blocked actions: {_int_value(summary_row.get('blocked_action_count'))}",
        f"- Recommendation: {_object_text(summary_row.get('recommendation')).strip()}",
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
        return "No broker dispatch round-trip actions."
    rows = [
        "| priority | status | component | check | actual | expected | next gate | help | reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in action_queue.to_dict(orient="records"):
        rows.append(
            "| "
            + " | ".join(
                [
                    _object_text(item.get("priority")).strip(),
                    _object_text(item.get("queue_status")).strip(),
                    _object_text(item.get("component")).strip(),
                    _object_text(item.get("check")).strip(),
                    _object_text(item.get("actual")).strip(),
                    _object_text(item.get("expected")).strip(),
                    _code(item.get("next_gate")),
                    _code(item.get("next_gate_help_command")),
                    _object_text(item.get("reason")).strip(),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _object_text(action_queue.iloc[0].get(column)).strip()


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _first_action_record(action_queue: pd.DataFrame) -> dict[str, object]:
    if action_queue.empty:
        return {}
    return _jsonable_check_record(action_queue.iloc[0].to_dict())


def _action_records(action_queue: pd.DataFrame) -> list[dict[str, object]]:
    if action_queue.empty:
        return []
    return [_jsonable_check_record(row) for row in action_queue.to_dict(orient="records")]


def _jsonable_check_value(value: object) -> object:
    value = _jsonable(value)
    if hasattr(value, "item"):
        try:
            return value.item()  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError):
            pass
    return value


def _help_command(next_gate: str) -> str:
    gate = _object_text(next_gate).strip()
    return f"python -m hft_cli {gate} --help" if gate else ""


def _code(value: object) -> str:
    text = _object_text(value).strip()
    return f"`{text}`" if text else ""


def _int_value(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _matches(frame: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    if frame.empty or not value or column not in frame.columns:
        return frame.iloc[:0]
    return frame.loc[frame[column].astype(str).str.strip() == value].reset_index(drop=True)


def _missing_request_acks(roundtrip_orders: pd.DataFrame) -> int:
    if roundtrip_orders.empty:
        return 0
    requested = roundtrip_orders["request_count"].astype(int) > 0
    acked = roundtrip_orders["acked"].map(_to_bool)
    return int((requested & ~acked).sum())


def _submission_enabled(send_summary: pd.Series, send_requests: pd.DataFrame) -> bool:
    summary_enabled = _to_bool(send_summary.get("submission_enabled", False))
    request_enabled = (
        bool(send_requests["submission_enabled"].map(_to_bool).any())
        if "submission_enabled" in send_requests.columns and not send_requests.empty
        else False
    )
    return summary_enabled or request_enabled


def _all_dry_run(
    dispatch_orders: pd.DataFrame,
    send_requests: pd.DataFrame,
    roundtrip_orders: pd.DataFrame,
) -> bool:
    dispatch_dry_run = (
        bool(dispatch_orders["dry_run_only"].map(_to_bool).all())
        if "dry_run_only" in dispatch_orders.columns and not dispatch_orders.empty
        else False
    )
    send_dry_run = (
        bool(send_requests["dry_run_only"].map(_to_bool).all())
        if "dry_run_only" in send_requests.columns and not send_requests.empty
        else False
    )
    linked_dry_run = (
        bool(roundtrip_orders["request_dry_run_only"].map(_to_bool).all()) if not roundtrip_orders.empty else False
    )
    return dispatch_dry_run and send_dry_run and linked_dry_run


def _dispatch_roundtrip_required(
    dispatch_summary: pd.Series,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> bool:
    return bool(
        thresholds.require_dispatch_roundtrip
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
    )


def _route_readiness_required(
    dispatch_summary: pd.Series,
    send_summary: pd.Series,
    ack_summary: pd.Series,
    thresholds: BrokerDispatchRoundTripThresholds,
) -> bool:
    return bool(
        thresholds.require_route_readiness
        or _identity_key(dispatch_summary.get("target_mode", "")) == "live_dryrun"
        or any(
            _to_bool(row.get("route_readiness_required", False))
            for row in (dispatch_summary, send_summary, ack_summary)
        )
    )


def _route_readiness_provided(*rows: pd.Series) -> bool:
    return all(_to_bool(row.get("route_readiness_provided", False)) for row in rows)


def _route_roundtrip_provided(*rows: pd.Series) -> bool:
    return all(_to_bool(row.get("route_dispatch_roundtrip_provided", False)) for row in rows)


def _strategy_portfolio_active(*rows: pd.Series) -> bool:
    return any(
        _to_bool(row.get("strategy_portfolio_required", False))
        or _to_bool(row.get("strategy_portfolio_provided", False))
        for row in rows
    )


def _strategy_portfolio_required(*rows: pd.Series) -> bool:
    return any(_to_bool(row.get("strategy_portfolio_required", False)) for row in rows)


def _strategy_portfolio_provided(*rows: pd.Series) -> bool:
    return bool(
        rows
        and _strategy_portfolio_active(*rows)
        and all(_to_bool(row.get("strategy_portfolio_provided", False)) for row in rows)
    )


def _strategy_portfolio_bool_all(rows: tuple[pd.Series, ...], column: str) -> bool:
    return bool(rows and all(_to_bool(row.get(column, False)) for row in rows))


def _strategy_portfolio_identity_mismatches(rows: tuple[pd.Series, ...], column: str) -> int:
    selected_column = f"strategy_portfolio_selected_{column}"
    component_values = {
        _identity_value(row, column)
        for row in rows
        if not row.empty and _identity_value(row, column)
    }
    proof_values = [_identity_key(row.get(selected_column, "")) for row in rows if not row.empty]
    if any(not value for value in proof_values):
        return 1
    return 0 if len(component_values | set(proof_values)) == 1 else 1


def _strategy_portfolio_identity_value(rows: tuple[pd.Series, ...], column: str) -> str:
    selected_column = f"strategy_portfolio_selected_{column}"
    for row in rows:
        value = _identity_key(row.get(selected_column, ""))
        if value:
            return value
    return ""


def _strategy_portfolio_text_value(rows: tuple[pd.Series, ...], column: str) -> str:
    for row in rows:
        value = _text(row, column)
        if value:
            return value
    return ""


def _strategy_portfolio_text_unique_count(rows: tuple[pd.Series, ...], column: str) -> int:
    return len({_text(row, column) for row in rows})


def _strategy_portfolio_number_unique_count(rows: tuple[pd.Series, ...], column: str) -> int:
    return len({round(_number(row, column, 0.0), 8) for row in rows})


def _strategy_portfolio_number_min(rows: tuple[pd.Series, ...], column: str) -> float:
    values = [_number(row, column, 0.0) for row in rows]
    return min(values) if values else 0.0


def _strategy_portfolio_number_max(rows: tuple[pd.Series, ...], column: str) -> float:
    values = [_number(row, column, 0.0) for row in rows]
    return max(values) if values else 0.0


def _strategy_portfolio_dispatch_total_notional(rows: tuple[pd.Series, ...]) -> float:
    return _strategy_portfolio_number_max(rows, "dispatch_total_notional")


def _route_readiness_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("strategy", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _route_readiness_identity_value(row, column)
            for row in rows
            if not row.empty and _route_readiness_identity_value(row, column)
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_broker_route_readiness_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("strategy", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _route_broker_route_readiness_identity_value(row, column)
            for row in rows
            if not row.empty and _route_broker_route_readiness_identity_value(row, column)
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _resume_route_readiness_identity_mismatches(rows: tuple[pd.Series, ...], prefix: str) -> int:
    mismatches = 0
    for column in ("strategy", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _resume_route_readiness_identity_value(row, prefix, column)
            for row in rows
            if not row.empty and _resume_route_readiness_identity_value(row, prefix, column)
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_roundtrip_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("target_mode", "strategy", "market", "scenario_key"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _route_identity_value(row, column)
            for row in rows
            if not row.empty and _route_identity_value(row, column)
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_roundtrip_batch_ids(rows: tuple[pd.Series, ...], roundtrip_orders: pd.DataFrame) -> set[str]:
    batch_ids = {
        _text(row, "route_dispatch_roundtrip_batch_id")
        for row in rows
        if _text(row, "route_dispatch_roundtrip_batch_id")
    }
    for column in (
        "dispatch_route_roundtrip_batch_id",
        "request_route_roundtrip_batch_id",
        "ack_route_roundtrip_batch_id",
        "ack_dispatch_order_route_roundtrip_batch_id",
        "ack_raw_route_roundtrip_batch_ids",
    ):
        if column in roundtrip_orders.columns:
            for value in roundtrip_orders[column].dropna().astype(str):
                batch_ids.update(_split_batch_ids(value))
    return batch_ids


def _split_batch_ids(value: object) -> set[str]:
    if pd.isna(value):
        return set()
    return {item.strip() for item in str(value).split("|") if item.strip()}


def _route_roundtrip_request_counts_match(rows: tuple[pd.Series, ...]) -> bool:
    request_counts = [
        int(_number(row, "route_dispatch_roundtrip_requests", 0.0))
        for row in rows
    ]
    acked_counts = [
        int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0))
        for row in rows
    ]
    counts = set(request_counts + acked_counts)
    return bool(counts and 0 not in counts and len(counts) == 1)


def _route_roundtrip_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows)


def _route_readiness_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows)


def _route_readiness_counter_min(rows: tuple[pd.Series, ...], column: str) -> int:
    return min(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _shadow_broker_readiness_provided(*rows: pd.Series) -> bool:
    return bool(rows and all(int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0 for row in rows))


def _prefixed_shadow_broker_readiness_provided(rows: tuple[pd.Series, ...], *, source_prefix: str) -> bool:
    return bool(
        rows
        and all(
            _to_bool(row.get(f"{source_prefix}_readiness_provided", False))
            and int(_number(row, f"{source_prefix}_readiness_sessions", 0.0)) > 0
            for row in rows
        )
    )


def _shadow_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _vendor_market_data_batch_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _vendor_market_data_batch_counter_min(rows: tuple[pd.Series, ...], column: str) -> int:
    values = [int(_number(row, column, 0.0)) for row in rows]
    return min(values) if values else 0


def _broker_vendor_data_readiness_counter_max(rows: tuple[pd.Series, ...], column: str) -> int:
    return max(int(_number(row, column, 0.0)) for row in rows) if rows else 0


def _vendor_market_data_batch_number_min(rows: tuple[pd.Series, ...], column: str) -> float:
    values = [float(_number(row, column, 0.0)) for row in rows]
    return min(values) if values else 0.0


def _vendor_market_data_batch_identity_mismatches(rows: tuple[pd.Series, ...]) -> int:
    mismatches = 0
    for column in ("adapter", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _identity_key(row.get(f"vendor_market_data_batch_{column}", ""))
            for row in rows
            if not row.empty and _identity_key(row.get(f"vendor_market_data_batch_{column}", ""))
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _vendor_market_data_batch_manifest_run_type_valid(rows: tuple[pd.Series, ...]) -> bool:
    values = {
        _identity_key(row.get("vendor_market_data_batch_manifest_run_type", ""))
        for row in rows
        if not row.empty and _identity_key(row.get("vendor_market_data_batch_manifest_run_type", ""))
    }
    return values == {"vendor_market_data_batch_pipeline"}


def _vendor_market_data_batch_counts_consistent(rows: tuple[pd.Series, ...]) -> bool:
    counts = {
        int(_number(row, "vendor_market_data_batch_dataset_count", 0.0))
        for row in rows
        if not row.empty and int(_number(row, "vendor_market_data_batch_dataset_count", 0.0)) > 0
    }
    return bool(counts and len(counts) == 1)


def _vendor_market_data_batch_text_value(rows: tuple[pd.Series, ...], column: str) -> str:
    for row in rows:
        value = _text(row, f"vendor_market_data_batch_{column}")
        if value:
            return value
    return ""


def _vendor_market_data_batch_identity_value(rows: tuple[pd.Series, ...], column: str) -> str:
    return _identity_key(_vendor_market_data_batch_text_value(rows, column))


def _vendor_market_data_batch_datasets_json(rows: tuple[pd.Series, ...]) -> str:
    for row in rows:
        value = _text(row, "vendor_market_data_batch_datasets_json")
        if value:
            return value
    return ""


def _shadow_adapter_matches(rows: tuple[pd.Series, ...]) -> bool:
    adapters = {
        _identity_key(row.get("adapter", ""))
        for row in rows
        if not row.empty and _identity_key(row.get("adapter", ""))
    }
    shadow_adapters = {
        _identity_key(row.get("shadow_broker_adapter", ""))
        for row in rows
        if int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0
        and _identity_key(row.get("shadow_broker_adapter", ""))
    }
    return bool(adapters and shadow_adapters and len(adapters | shadow_adapters) == 1)


def _shadow_adapter_consistent(rows: tuple[pd.Series, ...]) -> bool:
    adapters = {
        _identity_key(row.get("shadow_broker_adapter", ""))
        for row in rows
        if int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0
        and _identity_key(row.get("shadow_broker_adapter", ""))
    }
    return bool(
        adapters
        and len(adapters) == 1
        and _shadow_counter_max(rows, "shadow_broker_adapter_count") == 1
    )


def _shadow_adapter_value(rows: tuple[pd.Series, ...]) -> str:
    for row in rows:
        adapter = _identity_key(row.get("shadow_broker_adapter", ""))
        if adapter:
            return adapter
    return ""


def _prefixed_shadow_adapter_value(rows: tuple[pd.Series, ...], *, source_prefix: str) -> str:
    for row in rows:
        adapter = _identity_key(row.get(f"{source_prefix}_adapter", ""))
        if adapter:
            return adapter
    return ""


def _shadow_identity_value(rows: tuple[pd.Series, ...], proof_name: str, column: str) -> str:
    proof_column = f"shadow_broker_{proof_name}_{column}"
    for row in rows:
        value = _identity_key(row.get(proof_column, ""))
        if value:
            return value
    return ""


def _prefixed_shadow_identity_value(
    rows: tuple[pd.Series, ...],
    *,
    source_prefix: str,
    proof_name: str,
    column: str,
) -> str:
    proof_column = f"{source_prefix}_{proof_name}_{column}"
    for row in rows:
        value = _identity_key(row.get(proof_column, ""))
        if value:
            return value
    return ""


def _shadow_identity_mismatches(rows: tuple[pd.Series, ...], proof_name: str) -> int:
    mismatches = 0
    for column in ("strategy", "market"):
        component_values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        proof_values = {
            _identity_key(row.get(f"shadow_broker_{proof_name}_{column}", ""))
            for row in rows
            if int(_number(row, f"shadow_broker_{proof_name}_sessions", 0.0)) > 0
            and _identity_key(row.get(f"shadow_broker_{proof_name}_{column}", ""))
        }
        if len(component_values | proof_values) > 1:
            mismatches += 1
    return mismatches


def _route_enable_failed_checks(*rows: pd.Series) -> int:
    return max(int(_number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)) for row in rows)


def _route_readiness_recommendation(*rows: pd.Series) -> str:
    for row in rows:
        text = _text(row, "route_readiness_recommendation")
        if text:
            return text
    return ""


def _route_broker_route_readiness_recommendation(*rows: pd.Series) -> str:
    for row in rows:
        text = _text(row, "route_broker_route_readiness_recommendation")
        if text:
            return text
    return ""


def _resume_route_readiness_recommendation(rows: tuple[pd.Series, ...], prefix: str) -> str:
    for row in rows:
        text = _text(row, f"{prefix}_recommendation")
        if text:
            return text
    return ""


def _route_broker_route_readiness_launch_control_failures(rows: tuple[pd.Series, ...]) -> str:
    values = [
        _text(row, "route_broker_route_readiness_ops_launch_control_failures")
        for row in rows
        if _text(row, "route_broker_route_readiness_ops_launch_control_failures")
    ]
    return "|".join(dict.fromkeys(values))


def _resume_route_readiness_launch_control_failures(rows: tuple[pd.Series, ...], prefix: str) -> str:
    values = [
        _text(row, f"{prefix}_ops_launch_control_failures")
        for row in rows
        if _text(row, f"{prefix}_ops_launch_control_failures")
    ]
    return "|".join(dict.fromkeys(values))


def _broker_schema_text(rows: tuple[pd.Series, ...], column: str) -> str:
    for row in rows:
        text = _text(row, column)
        if text:
            return text
    return ""


def _broker_schema_reviewed(rows: tuple[pd.Series, ...]) -> bool:
    values = [_to_bool(row.get("broker_schema_reviewed", False)) for row in rows if not row.empty]
    return bool(values and all(values))


def _route_identity_value(row: pd.Series, column: str) -> str:
    proof_column = f"route_dispatch_roundtrip_{column}"
    if column == "scenario_key":
        return _text(row, proof_column)
    return _identity_key(row.get(proof_column, ""))


def _route_readiness_identity_value(row: pd.Series, column: str) -> str:
    return _identity_key(row.get(f"route_readiness_{column}", ""))


def _route_broker_route_readiness_identity_value(row_or_rows: pd.Series | tuple[pd.Series, ...], column: str) -> str:
    if isinstance(row_or_rows, tuple):
        for row in row_or_rows:
            value = _identity_key(row.get(f"route_broker_route_readiness_{column}", ""))
            if value:
                return value
        return ""
    return _identity_key(row_or_rows.get(f"route_broker_route_readiness_{column}", ""))


def _resume_route_readiness_identity_value(
    row_or_rows: pd.Series | tuple[pd.Series, ...],
    prefix: str,
    column: str,
) -> str:
    if isinstance(row_or_rows, tuple):
        for row in row_or_rows:
            value = _identity_key(row.get(f"{prefix}_{column}", ""))
            if value:
                return value
        return ""
    return _identity_key(row_or_rows.get(f"{prefix}_{column}", ""))


def _identity_mismatches(*rows: pd.Series) -> int:
    mismatches = 0
    for column in ("target_mode", "strategy", "market", "scenario_key", "adapter"):
        values = {
            _identity_value(row, column)
            for row in rows
            if not row.empty and _identity_value(row, column)
        }
        if len(values) > 1:
            mismatches += 1
    return mismatches


def _identity_value(row: pd.Series, column: str) -> str:
    if column == "scenario_key":
        return _text(row, column)
    return _identity_key(row.get(column, ""))


def _component_failed_checks(*rows: pd.Series) -> int:
    return int(sum(int(_number(row, "failed_checks", 0.0)) for row in rows))


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch round-trip input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch round-trip input is empty: {name}")
    return frame


def _read_optional_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def _reject_input_output_collision(
    output_dir: Path,
    inputs: dict[str, Path],
) -> None:
    for label, value in inputs.items():
        root = Path(value).resolve()
        if output_dir == root or root in output_dir.parents or output_dir in root.parents:
            raise ValueError(
                "broker-dispatch-roundtrip output_dir must not overwrite "
                f"the {label} source directory"
            )


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _validate_thresholds(thresholds: BrokerDispatchRoundTripThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    for name in (
        "max_duplicate_ack_orders",
        "max_unmatched_acks",
        "max_missing_request_acks",
        "max_total_failed_component_checks",
    ):
        if getattr(thresholds, name) < 0:
            raise ValueError(f"{name} must be non-negative")


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


def _object_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _first_text(*values: object) -> str:
    for value in values:
        text = _object_text(value)
        if text:
            return text
    return ""


def _identity_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_value(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "ready", "accepted"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
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


def _vendor_market_data_batch_datasets(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "dataset": _object_text(item.get("dataset", "")),
                "ready": _to_bool(item.get("ready", False)),
                "source_file_sha256": _object_text(item.get("source_file_sha256", "")),
                "source_header_sha256": _object_text(item.get("source_header_sha256", "")),
                "mapping_draft_sha256": _object_text(item.get("mapping_draft_sha256", "")),
                "mapping_source": _object_text(item.get("mapping_source", "")),
            }
        )
    return rows


def _json_list(value: object) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


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
