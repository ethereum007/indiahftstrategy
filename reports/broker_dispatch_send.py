from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from adapters.broker import get_adapter
from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    broker_dispatch_lineage_fields,
    broker_dispatch_lineage_manifest_inputs,
    empty_broker_dispatch_lineage,
    load_broker_dispatch_lineage,
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
BROKER_DISPATCH_LINEAGE_OUTPUT_COLUMNS = tuple(
    broker_dispatch_lineage_fields(empty_broker_dispatch_lineage()).keys()
)
TARGET_APPLICATION_BATCH_MODE = "per_dataset_verified_target_application"
TARGET_APPLICATION_DATASET_LINEAGE_FIELDS: tuple[str, ...] = (
    "mapping_application_path",
    "mapping_application_id",
    "mapping_application_sha256",
    "mapping_scope_review_id",
    "mapping_scope_review_sha256",
    "target_intake_receipt_id",
    "applied_mapping_sha256",
)
TARGET_APPLICATION_LINEAGE_IDENTITY_FIELDS: tuple[str, ...] = (
    "source_file_sha256",
    "source_header_sha256",
    "mapping_draft_sha256",
    "mapping_source",
    "mapping_application_id",
    "mapping_application_sha256",
    "mapping_scope_review_id",
    "mapping_scope_review_sha256",
    "target_intake_receipt_id",
    "applied_mapping_sha256",
)
DISPATCH_FINAL_LINEAGE_COMPARISON_KEY = (
    "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_FINAL_LINEAGE_FIELD_PREFIX = (
    "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "route_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    "current_application_lineage_sha256",
    "broker_application_lineage_sha256",
    "scaleup_carried_application_lineage_sha256",
    "cutover_carried_application_lineage_sha256",
    "route_carried_application_lineage_sha256",
    "dispatch_carried_application_lineage_sha256",
    "send_carried_application_lineage_sha256",
    "ack_carried_application_lineage_sha256",
    "roundtrip_carried_application_lineage_sha256",
    "readiness_carried_application_lineage_sha256",
    "scaleup_review_carried_application_lineage_sha256",
    "cutover_review_carried_application_lineage_sha256",
    "route_enable_review_carried_application_lineage_sha256",
)
DISPATCH_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "route_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    "current_application_lineage_sha256",
    "broker_application_lineage_sha256",
    "scaleup_carried_application_lineage_sha256",
    "cutover_carried_application_lineage_sha256",
    "route_carried_application_lineage_sha256",
    "dispatch_carried_application_lineage_sha256",
    "send_carried_application_lineage_sha256",
    "ack_carried_application_lineage_sha256",
    "roundtrip_carried_application_lineage_sha256",
    "readiness_carried_application_lineage_sha256",
    "scaleup_review_carried_application_lineage_sha256",
    "cutover_review_carried_application_lineage_sha256",
    "route_enable_review_carried_application_lineage_sha256",
    "dispatch_plan_review_carried_application_lineage_sha256",
    "send_packet_review_carried_application_lineage_sha256",
    "ack_reconciliation_review_carried_application_lineage_sha256",
    "roundtrip_final_review_carried_application_lineage_sha256",
    "broker_readiness_review_carried_application_lineage_sha256",
    "scaleup_final_review_carried_application_lineage_sha256",
    "cutover_final_review_carried_application_lineage_sha256",
    "route_final_review_carried_application_lineage_sha256",
)
SEND_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    *DISPATCH_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "dispatch_final_review_carried_application_lineage_sha256",
    "send_final_review_carried_application_lineage_sha256",
    "ack_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_complete_final_review_carried_application_lineage_sha256",
)
SEND_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_COMPARISON_KEY = (
    "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_FIELD_PREFIX = (
    "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_SUMMARY_FIELD_PREFIX = (
    "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_DIGEST_FIELDS: tuple[str, ...] = (
    *DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "scaleup_complete_final_review_carried_application_lineage_sha256",
    "cutover_complete_final_review_carried_application_lineage_sha256",
    "route_complete_final_review_carried_application_lineage_sha256",
    "dispatch_complete_final_review_carried_application_lineage_sha256",
    "send_complete_final_review_carried_application_lineage_sha256",
    "ack_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
)
SEND_EXTENDED_COMPLETE_FINAL_LINEAGE_39_COMPARISON_KEY = (
    "send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_COMPARISON_KEY = (
    "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_FIELD_PREFIX = (
    "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_SUMMARY_FIELD_PREFIX = (
    "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_DIGEST_FIELDS: tuple[str, ...] = (
    *DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_DIGEST_FIELDS,
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
SEND_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_47_COMPARISON_KEY = (
    "send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)


@dataclass(frozen=True)
class BrokerDispatchSendThresholds:
    target_mode: str = "live_dryrun"
    require_dispatch_ready: bool = True
    require_armed_dispatch: bool = True
    require_dry_run: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    max_requests: int | None = None


@dataclass(frozen=True)
class BrokerDispatchSendReport:
    requests: pd.DataFrame
    expected_acks: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_dispatch_send_packet(
    *,
    dispatch_summary: pd.DataFrame,
    dispatch_orders: pd.DataFrame,
    dispatch_config: dict[str, Any] | None = None,
    broker_dispatch_lineage: dict[str, Any] | None = None,
    thresholds: BrokerDispatchSendThresholds | None = None,
) -> BrokerDispatchSendReport:
    thresholds = thresholds or BrokerDispatchSendThresholds()
    _validate_thresholds(thresholds)
    dispatch_summary = _require_nonempty(dispatch_summary, "dispatch_summary")
    dispatch_orders = _require_nonempty(dispatch_orders, "dispatch_orders")
    dispatch_config = dispatch_config or {}

    summary_row = _dispatch_summary_state(dispatch_summary.iloc[0], dispatch_config)
    for column, value in broker_dispatch_lineage_fields(
        broker_dispatch_lineage or empty_broker_dispatch_lineage()
    ).items():
        summary_row[column] = value
    requests = _request_rows(summary_row, dispatch_orders)
    expected_acks = _expected_ack_template(requests)
    checks = _checks(summary_row, dispatch_orders, requests, thresholds)
    summary = _summary(summary_row, requests, checks, thresholds)
    action_queue = _action_queue(summary.iloc[0], checks)
    summary = _summary_with_actions(summary, checks, action_queue)
    config = _config(summary.iloc[0], requests, thresholds, checks, action_queue)
    return BrokerDispatchSendReport(
        requests=requests,
        expected_acks=expected_acks,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_broker_dispatch_send_packet(
    *,
    dispatch_dir: str | Path,
    output_dir: str | Path,
    thresholds: BrokerDispatchSendThresholds | None = None,
) -> BrokerDispatchSendReport:
    dispatch = Path(dispatch_dir)
    dispatch_config_path = dispatch / "broker_dispatch_config.json"
    dispatch_summary_path = dispatch / "broker_dispatch_summary.csv"
    dispatch_orders_path = dispatch / "broker_dispatch_orders.csv"
    dispatch_manifest_path = dispatch / "manifest.json"
    dispatch_lineage = load_broker_dispatch_lineage(dispatch_config_path)
    dispatch_config = (
        json.loads(dispatch_config_path.read_text(encoding="utf-8"))
        if dispatch_config_path.exists()
        else {}
    )
    route_manifest_path = _manifest_input_path(dispatch_manifest_path, "route_enable_manifest")
    cutover_manifest_path = _manifest_input_path(route_manifest_path, "cutover_manifest")
    broker_readiness_config_path = _manifest_input_path(cutover_manifest_path, "broker_readiness_config")
    if broker_readiness_config_path is not None:
        dispatch_config = _with_broker_readiness_config_vendor_market_data_batch(
            dispatch_config,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=_read_required(dispatch_summary_path, "broker_dispatch_summary"),
        dispatch_orders=_read_required(dispatch_orders_path, "broker_dispatch_orders"),
        dispatch_config=dispatch_config,
        broker_dispatch_lineage=dispatch_lineage,
        thresholds=thresholds,
    )
    out = Path(output_dir).resolve()
    _reject_input_output_collision(out, {"broker dispatch": dispatch_config_path})
    out.mkdir(parents=True, exist_ok=True)
    report.requests.to_csv(out / "broker_dispatch_send_requests.csv", index=False)
    report.expected_acks.to_csv(out / "broker_dispatch_expected_acks.csv", index=False)
    report.checks.to_csv(out / "broker_dispatch_send_checks.csv", index=False)
    report.summary.to_csv(out / "broker_dispatch_send_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(
        report.summary.iloc[0], report.checks
    )
    action_queue.to_csv(out / "broker_dispatch_send_action_queue.csv", index=False)
    (out / "broker_dispatch_send_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "broker_dispatch_send_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = _manifest_inputs(
        dispatch_summary=dispatch_summary_path,
        dispatch_orders=dispatch_orders_path,
        dispatch_config=dispatch_config_path,
        dispatch_manifest=dispatch_manifest_path,
    )
    inputs.update(broker_dispatch_lineage_manifest_inputs(dispatch_lineage))
    write_experiment_manifest(
        out,
        run_type="broker_dispatch_send_packet",
        parameters={"thresholds": asdict(thresholds or BrokerDispatchSendThresholds())},
        inputs=inputs,
        extra={
            "ready": bool(report.ready),
            **broker_dispatch_lineage_fields(dispatch_lineage),
            "submission_enabled": False,
            "authorizes_submission": False,
        },
    )
    return BrokerDispatchSendReport(
        report.requests,
        report.expected_acks,
        report.checks,
        report.summary,
        report.config,
        out,
        action_queue,
    )


def _manifest_inputs(**paths: Path) -> dict[str, Path]:
    return {name: path for name, path in paths.items() if path.exists()}


def _request_rows(dispatch_summary: pd.Series, dispatch_orders: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    adapter = _text(dispatch_summary, "adapter") or _first_order_text(dispatch_orders, "adapter")
    target_mode = _identity_key(_text(dispatch_summary, "target_mode") or _first_order_text(dispatch_orders, "target_mode"))
    lineage_fields = _broker_dispatch_lineage_output_fields(dispatch_summary)
    for index, order in dispatch_orders.reset_index(drop=True).iterrows():
        payload, payload_error = _order_payload(order)
        envelope = {
            "adapter": adapter,
            "target_mode": target_mode,
            "dry_run_only": True,
            "submission_enabled": False,
            **lineage_fields,
            "authorizes_submission": False,
            "dispatch_batch_id": _text(order, "dispatch_batch_id"),
            "dispatch_order_id": _text(order, "dispatch_order_id"),
            "route_dispatch_roundtrip_batch_id": _text(order, "route_dispatch_roundtrip_batch_id")
            or _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "source_order_id": _text(order, "source_order_id"),
            "source_payload_hash": _text(order, "source_payload_hash"),
            "order": payload,
        }
        request_hash = hashlib.sha256(json.dumps(envelope, sort_keys=True).encode("utf-8")).hexdigest()
        rows.append(
            {
                "request_id": f"BDR-{index + 1:06d}-{request_hash[:12]}",
                "dispatch_batch_id": _text(order, "dispatch_batch_id"),
                "dispatch_order_id": _text(order, "dispatch_order_id"),
                "route_dispatch_roundtrip_batch_id": _text(order, "route_dispatch_roundtrip_batch_id")
                or _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
                "source_order_id": _text(order, "source_order_id"),
                "target_mode": target_mode,
                "strategy": _text(order, "strategy") or _text(dispatch_summary, "strategy"),
                "market": _text(order, "market") or _text(dispatch_summary, "market"),
                "scenario_key": _text(order, "scenario_key") or _text(dispatch_summary, "scenario_key"),
                "adapter": adapter,
                "request_action": _text(order, "dispatch_action") or "dry_run_submit",
                "transport": "file_packet",
                "endpoint": f"{adapter}.orders.dry_run_submit",
                "http_method": "POST",
                "submission_enabled": False,
                "dry_run_only": _to_bool(order.get("dry_run_only", False)),
                **lineage_fields,
                "authorizes_submission": False,
                "idempotency_key": f"IDEMP-{request_hash[:24]}",
                "source_payload_hash": _text(order, "source_payload_hash"),
                "request_payload_hash": request_hash,
                "payload_valid": payload_error == "",
                "payload_error": payload_error,
                "request_payload_json": json.dumps(envelope, sort_keys=True),
            }
        )
    return pd.DataFrame(rows)


def _expected_ack_template(requests: pd.DataFrame) -> pd.DataFrame:
    if requests.empty:
        return pd.DataFrame(
            columns=[
                "dispatch_order_id",
                "source_order_id",
                "request_id",
                "idempotency_key",
                "route_dispatch_roundtrip_batch_id",
                "adapter",
                "target_mode",
                "broker_order_id",
                "ack_status",
                "ack_ts_ns",
                "notes",
            ]
        )
    return pd.DataFrame(
        [
            {
                "dispatch_order_id": row.dispatch_order_id,
                "source_order_id": row.source_order_id,
                "request_id": row.request_id,
                "idempotency_key": row.idempotency_key,
                "route_dispatch_roundtrip_batch_id": row.route_dispatch_roundtrip_batch_id,
                "adapter": row.adapter,
                "target_mode": row.target_mode,
                "broker_order_id": "",
                "ack_status": "",
                "ack_ts_ns": "",
                "notes": "fill from Arrow.money/iRage dry-run acknowledgement log",
            }
            for row in requests.itertuples(index=False)
        ]
    )


def _dispatch_summary_state(row: pd.Series, config: dict[str, Any]) -> pd.Series:
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
    (
        broker_vendor_market_data_batch,
        broker_vendor_market_data_batch_prefix,
    ) = _broker_vendor_market_data_batch_source(config)
    broker_vendor_market_data_batch_lineage = (
        _broker_vendor_market_data_batch_lineage_state(state, config)
    )
    broker_vendor_final_lineage = _broker_vendor_final_lineage_state(state, config)
    broker_vendor_complete_final_lineage = (
        _broker_vendor_complete_final_lineage_state(state, config)
    )
    broker_vendor_extended_complete_final_lineage = (
        _broker_vendor_extended_complete_final_lineage_state(state, config)
    )
    broker_vendor_extended_complete_final_lineage_38 = (
        _broker_vendor_extended_complete_final_lineage_38_state(state, config)
    )
    broker_vendor_latest_extended_complete_final_lineage_46 = (
        _broker_vendor_latest_extended_complete_final_lineage_46_state(state, config)
    )
    (
        broker_vendor_data_readiness,
        broker_vendor_data_readiness_prefix,
    ) = _broker_vendor_data_readiness_source(config)
    if broker_vendor_data_readiness:
        _apply_broker_vendor_data_readiness_config(
            state,
            broker_vendor_data_readiness,
            field_prefix="dispatch_broker_vendor_data_readiness",
            fallback_prefix=broker_vendor_data_readiness_prefix,
        )
    else:
        _copy_broker_vendor_data_readiness_fields(
            state,
            source_prefix=broker_vendor_data_readiness_prefix,
            field_prefix="dispatch_broker_vendor_data_readiness",
        )
    if broker_vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            broker_vendor_market_data_batch,
            field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            fallback_prefix=broker_vendor_market_data_batch_prefix,
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefix=broker_vendor_market_data_batch_prefix,
            field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    vendor_market_data_batch = config.get("route_vendor_market_data_batch", {}) or {}
    if vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            state,
            vendor_market_data_batch,
            field_prefix="dispatch_vendor_market_data_batch",
            fallback_prefix="route_vendor_market_data_batch",
        )
    else:
        _copy_vendor_market_data_batch_fields(
            state,
            source_prefix="route_vendor_market_data_batch",
            field_prefix="dispatch_vendor_market_data_batch",
        )
    for field, value in broker_vendor_market_data_batch_lineage.items():
        state[field] = value
    for field, value in broker_vendor_final_lineage.items():
        state[field] = value
    for field, value in broker_vendor_complete_final_lineage.items():
        state[field] = value
    for field, value in broker_vendor_extended_complete_final_lineage.items():
        state[field] = value
    for field, value in broker_vendor_extended_complete_final_lineage_38.items():
        state[field] = value
    for field, value in broker_vendor_latest_extended_complete_final_lineage_46.items():
        state[field] = value
    return state


def _broker_vendor_market_data_batch_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return select_vendor_market_data_batch_source(
        config,
        (
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="route_broker_dispatch_roundtrip_vendor_market_data_batch",
    )


def _broker_vendor_market_data_batch_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
    ):
        comparison = config.get(key)
        if isinstance(comparison, dict) and comparison:
            return comparison
    return {}


def _broker_vendor_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(DISPATCH_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_complete_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(DISPATCH_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_extended_complete_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_extended_complete_final_lineage_38_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_latest_extended_complete_final_lineage_46_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_market_data_batch_lineage_state(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, object]:
    comparison = _broker_vendor_market_data_batch_lineage_comparison_source(config)
    return {
        "dispatch_broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(
                    "dispatch_broker_vendor_market_data_batch_lineage_match_required",
                    row.get(
                        "route_broker_vendor_market_data_batch_lineage_match_required",
                        False,
                    ),
                ),
            )
        ),
        "dispatch_broker_vendor_market_data_batch_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(
                    "dispatch_broker_vendor_market_data_batch_lineage_matches",
                    row.get("route_broker_vendor_market_data_batch_lineage_matches", False),
                ),
            )
        ),
        "dispatch_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("current_application_lineage_sha256", ""),
                row.get("dispatch_vendor_market_data_batch_application_lineage_sha256", ""),
                row.get("route_vendor_market_data_batch_application_lineage_sha256", ""),
            )
        ),
        "dispatch_broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("broker_application_lineage_sha256", ""),
                row.get(
                    "dispatch_broker_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
                row.get(
                    "route_broker_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
            )
        ),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    comparison.get("scaleup_carried_application_lineage_sha256", ""),
                    row.get(
                        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    comparison.get("cutover_carried_application_lineage_sha256", ""),
                    row.get(
                        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    comparison.get("route_carried_application_lineage_sha256", ""),
                    row.get(
                        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    comparison.get("dispatch_carried_application_lineage_sha256", ""),
                    row.get(
                        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
    }


def _broker_vendor_final_lineage_state(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, object]:
    comparison = _broker_vendor_final_lineage_comparison_source(config)
    prefix = DISPATCH_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = DISPATCH_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in DISPATCH_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_complete_final_lineage_state(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, object]:
    comparison = _broker_vendor_complete_final_lineage_comparison_source(config)
    prefix = DISPATCH_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = DISPATCH_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in DISPATCH_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_extended_complete_final_lineage_state(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, object]:
    comparison = _broker_vendor_extended_complete_final_lineage_comparison_source(
        config
    )
    prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "scaleup_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "cutover_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_cutover_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_route_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "route_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_route_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_dispatch_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_extended_complete_final_lineage_38_state(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, object]:
    comparison = _broker_vendor_extended_complete_final_lineage_38_comparison_source(
        config
    )
    prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_FIELD_PREFIX
    summary_prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_SUMMARY_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "cutover_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_route_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "route_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_route_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_dispatch_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_latest_extended_complete_final_lineage_46_state(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, object]:
    comparison = _broker_vendor_latest_extended_complete_final_lineage_46_comparison_source(
        config
    )
    prefix = DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_FIELD_PREFIX
    summary_prefix = (
        DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_SUMMARY_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{summary_prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{summary_prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "route_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
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
    return {}, "route_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    dispatch_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    vendor, _source = _broker_vendor_market_data_batch_source(dispatch_config)
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
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(dispatch_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(broker_readiness_config)
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    existing_lineage = _broker_vendor_market_data_batch_lineage_comparison_source(
        dispatch_config
    )
    sidecar_lineage = (
        dispatch.get("vendor_market_data_batch_lineage_comparison", {}) or {}
        if isinstance(dispatch, dict)
        else {}
    )
    should_hydrate_lineage = (
        not existing_lineage
        and isinstance(sidecar_lineage, dict)
        and bool(sidecar_lineage)
    )
    if (
        not should_hydrate_vendor
        and not should_hydrate_readiness
        and not should_hydrate_lineage
    ):
        return dispatch_config

    out = dict(dispatch_config)
    if should_hydrate_vendor:
        out["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out["route_broker_vendor_data_readiness"] = dict(sidecar_readiness)
    if should_hydrate_lineage:
        out[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
        ] = dict(sidecar_lineage)
    return out


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


def _apply_vendor_market_data_batch_config(
    state: pd.Series,
    vendor: dict[str, Any],
    *,
    field_prefix: str,
    fallback_prefix: str,
) -> None:
    comparison = vendor.get("comparison", {}) or {}
    state[f"{field_prefix}_provided"] = _to_bool(
        vendor.get("provided", state.get(f"{fallback_prefix}_provided", False))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        vendor.get("ready", state.get(f"{fallback_prefix}_ready", False))
    )
    state[f"{field_prefix}_adapter"] = _object_text(
        vendor.get("adapter", state.get(f"{fallback_prefix}_adapter", ""))
    )
    state[f"{field_prefix}_kind"] = _object_text(vendor.get("kind", state.get(f"{fallback_prefix}_kind", "")))
    state[f"{field_prefix}_manifest_run_type"] = _identity_key(
        vendor.get("manifest_run_type", state.get(f"{fallback_prefix}_manifest_run_type", ""))
    )
    state[f"{field_prefix}_market"] = _object_text(
        vendor.get("market", state.get(f"{fallback_prefix}_market", ""))
    )
    state[f"{field_prefix}_dataset_count"] = int(
        _number_value(
            vendor.get("dataset_count"),
            _number(state, f"{fallback_prefix}_dataset_count", 0.0),
        )
    )
    state[f"{field_prefix}_ready_datasets"] = int(
        _number_value(
            vendor.get("ready_datasets"),
            _number(state, f"{fallback_prefix}_ready_datasets", 0.0),
        )
    )
    state[f"{field_prefix}_failed_datasets"] = int(
        _number_value(
            vendor.get("failed_datasets"),
            _number(state, f"{fallback_prefix}_failed_datasets", 0.0),
        )
    )
    state[f"{field_prefix}_ready_rate"] = _number_value(
        vendor.get("ready_rate"),
        _number(state, f"{fallback_prefix}_ready_rate", 0.0),
    )
    state[f"{field_prefix}_unique_source_files"] = int(
        _number_value(
            vendor.get("unique_source_files"),
            _number(state, f"{fallback_prefix}_unique_source_files", 0.0),
        )
    )
    state[f"{field_prefix}_unique_header_fingerprints"] = int(
        _number_value(
            vendor.get("unique_header_fingerprints"),
            _number(state, f"{fallback_prefix}_unique_header_fingerprints", 0.0),
        )
    )
    state[f"{field_prefix}_source_file_fingerprint_coverage"] = _number_value(
        vendor.get("source_file_fingerprint_coverage"),
        _number(state, f"{fallback_prefix}_source_file_fingerprint_coverage", 0.0),
    )
    state[f"{field_prefix}_min_mapping_coverage"] = _number_value(
        vendor.get("min_mapping_coverage"),
        _number(state, f"{fallback_prefix}_min_mapping_coverage", 0.0),
    )
    state[f"{field_prefix}_unique_mapping_drafts"] = int(
        _number_value(
            vendor.get("unique_mapping_drafts"),
            _number(state, f"{fallback_prefix}_unique_mapping_drafts", 0.0),
        )
    )
    state[f"{field_prefix}_mapping_sources"] = _object_text(
        vendor.get("mapping_sources", state.get(f"{fallback_prefix}_mapping_sources", ""))
    )
    state[f"{field_prefix}_mapping_source_mode"] = _identity_key(
        vendor.get("mapping_source_mode", state.get(f"{fallback_prefix}_mapping_source_mode", ""))
    )
    state[f"{field_prefix}_mapping_application_count"] = int(
        _number_value(
            vendor.get("mapping_application_count"),
            _number(state, f"{fallback_prefix}_mapping_application_count", 0.0),
        )
    )
    state[f"{field_prefix}_unique_mapping_applications"] = int(
        _number_value(
            vendor.get("unique_mapping_applications"),
            _number(state, f"{fallback_prefix}_unique_mapping_applications", 0.0),
        )
    )
    state[f"{field_prefix}_target_application_coverage"] = _number_value(
        vendor.get("target_application_coverage"),
        _number(state, f"{fallback_prefix}_target_application_coverage", 0.0),
    )
    state[f"{field_prefix}_application_lineage_consistency_required"] = _to_bool(
        vendor.get(
            "application_lineage_consistency_required",
            state.get(f"{fallback_prefix}_application_lineage_consistency_required", False),
        )
    )
    state[f"{field_prefix}_application_lineage_consistent"] = _to_bool(
        vendor.get(
            "application_lineage_consistent",
            state.get(f"{fallback_prefix}_application_lineage_consistent", False),
        )
    )
    state[f"{field_prefix}_application_lineage_sha256"] = _sha256_text(
        _first_text(
            vendor.get("application_lineage_sha256", ""),
            state.get(f"{fallback_prefix}_application_lineage_sha256", ""),
        )
    )
    state[f"{field_prefix}_comparison_accepted"] = _to_bool(
        comparison.get("accepted", state.get(f"{fallback_prefix}_comparison_accepted", False))
    )
    state[f"{field_prefix}_comparison_failed_checks"] = int(
        _number_value(
            comparison.get("failed_checks"),
            _number(state, f"{fallback_prefix}_comparison_failed_checks", 0.0),
        )
    )
    datasets = vendor.get("datasets")
    state[f"{field_prefix}_datasets_json"] = (
        json.dumps(_vendor_market_data_batch_datasets(datasets), sort_keys=True)
        if isinstance(datasets, list)
        else _text(state, f"{fallback_prefix}_datasets_json")
    )


def _copy_vendor_market_data_batch_fields(
    state: pd.Series,
    *,
    source_prefix: str,
    field_prefix: str,
) -> None:
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
        "mapping_source_mode",
        "mapping_application_count",
        "unique_mapping_applications",
        "target_application_coverage",
        "application_lineage_consistency_required",
        "application_lineage_consistent",
        "application_lineage_sha256",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        state[f"{field_prefix}_{suffix}"] = state.get(f"{source_prefix}_{suffix}", "")


def _apply_broker_vendor_data_readiness_config(
    state: pd.Series,
    readiness: dict[str, Any],
    *,
    field_prefix: str,
    fallback_prefix: str,
) -> None:
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    state[f"{field_prefix}_provided"] = _to_bool(
        readiness.get("provided", state.get(f"{fallback_prefix}_provided", active_config))
    )
    state[f"{field_prefix}_ready"] = _to_bool(
        readiness.get("ready", state.get(f"{fallback_prefix}_ready", False))
    )
    state[f"{field_prefix}_failed_checks"] = _broker_vendor_data_readiness_failed_checks(
        readiness,
        fallback=_number(state, f"{fallback_prefix}_failed_checks", 0.0),
    )


def _copy_broker_vendor_data_readiness_fields(
    state: pd.Series,
    *,
    source_prefix: str,
    field_prefix: str,
) -> None:
    state[f"{field_prefix}_provided"] = state.get(f"{source_prefix}_provided", False)
    state[f"{field_prefix}_ready"] = state.get(f"{source_prefix}_ready", False)
    state[f"{field_prefix}_failed_checks"] = state.get(f"{source_prefix}_failed_checks", 0)


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
    vendor_readiness = readiness.get("broker_vendor_data_readiness", {}) or {}
    route = readiness.get("route_readiness", {}) or {}
    dispatch = readiness.get("dispatch_roundtrip", {}) or {}
    route_dispatch = readiness.get("route_dispatch_roundtrip", {}) or {}
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
    dispatch_orders: pd.DataFrame,
    requests: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
) -> pd.DataFrame:
    orders = int(len(dispatch_orders))
    request_count = int(len(requests))
    max_requests = thresholds.max_requests if thresholds.max_requests is not None else orders
    summary_ready = _to_bool(dispatch_summary.get("ready", False))
    dispatch_state = _identity_key(dispatch_summary.get("dispatch_state", ""))
    target_mode = _identity_key(dispatch_summary.get("target_mode", ""))
    adapter = _text(dispatch_summary, "adapter") or _first_order_text(dispatch_orders, "adapter")
    adapter_known = _adapter_known(adapter)
    dry_run_only = bool(requests["dry_run_only"].astype(bool).all()) if not requests.empty else False
    submission_disabled = bool((~requests["submission_enabled"].astype(bool)).all()) if not requests.empty else False
    requests_non_authorizing = bool(
        (~requests["authorizes_submission"].astype(bool)).all()
    ) if not requests.empty else False
    unique_idempotency = int(requests["idempotency_key"].nunique()) if not requests.empty else 0
    payloads_valid = bool(requests["payload_valid"].astype(bool).all()) if not requests.empty else False
    route_roundtrip_active = _dispatch_roundtrip_required(thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    )
    route_readiness_required = _route_readiness_required(thresholds, dispatch_summary)
    route_readiness_active = bool(
        route_readiness_required or _to_bool(dispatch_summary.get("route_readiness_provided", False))
    )
    route_enable_failed_checks = int(
        _number(dispatch_summary, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
    )
    route_batch_id = _text(dispatch_summary, "route_dispatch_roundtrip_batch_id")
    order_route_batches = _unique_text_values(dispatch_orders, "route_dispatch_roundtrip_batch_id")
    request_route_batches = _unique_text_values(requests, "route_dispatch_roundtrip_batch_id")
    checks = pd.DataFrame(
        [
            _check(
                "dispatch_ready",
                summary_ready,
                "is",
                True,
                summary_ready or not thresholds.require_dispatch_ready,
                "broker dispatch plan is not ready",
            ),
            _check(
                "dispatch_armed_dry_run",
                dispatch_state,
                "==",
                "armed_dry_run",
                dispatch_state == "armed_dry_run" or not thresholds.require_armed_dispatch,
                "dispatch state is not armed for dry-run sending",
            ),
            _check(
                "target_mode_matches",
                target_mode,
                "==",
                thresholds.target_mode,
                target_mode == thresholds.target_mode,
                "sender packet target mode does not match dispatch target",
            ),
            _check(
                "route_dispatch_roundtrip_provided",
                _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("route_dispatch_roundtrip_provided", False))
                or not _dispatch_roundtrip_required(thresholds),
                "sender packet requires dispatch plan with route round-trip proof",
            ),
            _check(
                "route_readiness_provided",
                _to_bool(dispatch_summary.get("route_readiness_provided", False)),
                "is",
                True,
                _to_bool(dispatch_summary.get("route_readiness_provided", False)) or not route_readiness_required,
                "sender packet requires dispatch plan with route-readiness proof",
            ),
            _check("adapter_known", adapter, "in", "known adapters", adapter_known, "dispatch adapter is unknown"),
            _check(
                "request_count_matches_dispatch",
                request_count,
                "==",
                orders,
                request_count == orders,
                "sender packet request count does not match dispatch order count",
            ),
            _check(
                "request_count_within_limit",
                request_count,
                "<=",
                max_requests,
                request_count <= max_requests,
                "sender packet request count exceeds limit",
            ),
            _check(
                "dry_run_only",
                dry_run_only,
                "is",
                True,
                dry_run_only or not thresholds.require_dry_run,
                "sender packet contains non-dry-run requests",
            ),
            _check(
                "submission_disabled",
                submission_disabled,
                "is",
                True,
                submission_disabled,
                "sender packet would enable live submission",
            ),
            _check(
                "requests_non_authorizing",
                requests_non_authorizing,
                "is",
                True,
                requests_non_authorizing,
                "sender packet contains an authorizing claim",
            ),
            _check(
                "unique_idempotency_key",
                unique_idempotency,
                "==",
                request_count,
                unique_idempotency == request_count,
                "sender packet idempotency keys are not unique",
            ),
            _check("payloads_valid", payloads_valid, "is", True, payloads_valid, "dispatch payload JSON is invalid"),
        ]
    )
    if _to_bool(dispatch_summary.get("broker_dispatch_lineage_required", False)):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(
                    [
                        _check(
                            "broker_dispatch_lineage_provided",
                            _to_bool(dispatch_summary.get("broker_dispatch_lineage_provided", False)),
                            "is",
                            True,
                            _to_bool(dispatch_summary.get("broker_dispatch_lineage_provided", False)),
                            "broker-dispatch lineage evidence is required but missing",
                        ),
                        _check(
                            "broker_dispatch_manifest_current",
                            _to_bool(dispatch_summary.get("broker_dispatch_manifest_current", False)),
                            "is",
                            True,
                            _to_bool(dispatch_summary.get("broker_dispatch_manifest_current", False)),
                            "broker-dispatch manifest is missing, stale, or incomplete",
                        ),
                        _check(
                            "broker_dispatch_lineage_contract_consistent",
                            _to_bool(
                                dispatch_summary.get(
                                    "broker_dispatch_lineage_contract_consistent", False
                                )
                            ),
                            "is",
                            True,
                            _to_bool(
                                dispatch_summary.get(
                                    "broker_dispatch_lineage_contract_consistent", False
                                )
                            ),
                            "broker-dispatch orders, summary, config, and manifest disagree",
                        ),
                        _check(
                            "broker_dispatch_non_authorizing",
                            _to_bool(dispatch_summary.get("broker_dispatch_non_authorizing", False)),
                            "is",
                            True,
                            _to_bool(dispatch_summary.get("broker_dispatch_non_authorizing", False)),
                            "broker-dispatch lineage contains an authorizing claim",
                        ),
                        _check(
                            "broker_dispatch_route_enable_lineage_gate_passed",
                            _to_bool(
                                dispatch_summary.get(
                                    "broker_dispatch_route_enable_lineage_gate_passed", False
                                )
                            ),
                            "is",
                            True,
                            _to_bool(
                                dispatch_summary.get(
                                    "broker_dispatch_route_enable_lineage_gate_passed", False
                                )
                            ),
                            "broker-dispatch plan did not retain a valid route-enable lineage gate",
                        ),
                        _check(
                            "broker_dispatch_route_enable_matches_current",
                            _to_bool(
                                dispatch_summary.get(
                                    "broker_dispatch_route_enable_matches_current", False
                                )
                            ),
                            "is",
                            True,
                            _to_bool(
                                dispatch_summary.get(
                                    "broker_dispatch_route_enable_matches_current", False
                                )
                            ),
                            "broker-dispatch route lineage does not match the current route source",
                        ),
                        _check(
                            "broker_dispatch_lineage_gate_passed",
                            _to_bool(dispatch_summary.get("broker_dispatch_lineage_gate_passed", False)),
                            "is",
                            True,
                            _to_bool(dispatch_summary.get("broker_dispatch_lineage_gate_passed", False)),
                            "broker-dispatch operational lineage gate did not pass",
                        ),
                    ]
                ),
            ],
            ignore_index=True,
        )
    if route_readiness_active:
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_route_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    resume_route_checks: list[dict[str, object]] = []
    if _resume_route_readiness_active(dispatch_summary, "route_broker_resume_broker_route_readiness"):
        resume_route_checks.extend(
            _resume_route_readiness_checks(
                dispatch_summary,
                prefix="route_broker_resume_broker_route_readiness",
                label="dispatch broker resume-gate broker route-readiness",
            )
        )
    if _resume_route_readiness_active(dispatch_summary, "route_broker_resume_incident_broker_route_readiness"):
        resume_route_checks.extend(
            _resume_route_readiness_checks(
                dispatch_summary,
                prefix="route_broker_resume_incident_broker_route_readiness",
                label="dispatch broker resume-gate incident route-readiness",
            )
        )
    if resume_route_checks:
        checks = pd.concat([checks, pd.DataFrame(resume_route_checks)], ignore_index=True)
    if _dispatch_roundtrip_required(thresholds) or _to_bool(
        dispatch_summary.get("route_dispatch_roundtrip_provided", False)
    ):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_dispatch_roundtrip_checks(dispatch_summary, target_mode)),
                pd.DataFrame(
                    [
                        _check(
                            "route_enable_dispatch_roundtrip_failed_checks",
                            route_enable_failed_checks,
                            "<=",
                            0,
                            route_enable_failed_checks <= 0,
                            "route-enable dispatch round-trip has failed component checks",
                        ),
                        _check(
                            "dispatch_order_route_roundtrip_batch_matches",
                            "|".join(order_route_batches),
                            "==",
                            route_batch_id,
                            bool(
                                route_batch_id
                                and len(order_route_batches) == 1
                                and order_route_batches[0] == route_batch_id
                            ),
                            "dispatch order route proof batch ids do not match dispatch summary",
                        ),
                        _check(
                            "request_route_roundtrip_batch_matches",
                            "|".join(request_route_batches),
                            "==",
                            route_batch_id,
                            bool(
                                route_batch_id
                                and len(request_route_batches) == 1
                                and request_route_batches[0] == route_batch_id
                            ),
                            "sender request route proof batch ids do not match dispatch summary",
                        ),
                    ]
                )
                if route_roundtrip_active
                else pd.DataFrame(),
            ],
            ignore_index=True,
        )
    if _strategy_portfolio_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_strategy_portfolio_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _shadow_broker_readiness_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_shadow_broker_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _route_broker_shadow_broker_readiness_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_route_broker_shadow_broker_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _broker_vendor_data_readiness_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_broker_vendor_data_readiness_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _vendor_market_data_batch_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_vendor_market_data_batch_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    if _broker_vendor_market_data_batch_active(dispatch_summary):
        checks = pd.concat(
            [
                checks,
                pd.DataFrame(_broker_vendor_market_data_batch_checks(dispatch_summary)),
            ],
            ignore_index=True,
        )
    return checks


def _route_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    checks = [
        _check(
            "route_readiness_ready",
            _to_bool(dispatch_summary.get("route_readiness_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_readiness_ready", False)),
            "dispatch route-readiness proof is not ready",
        ),
        _check(
            "route_readiness_strategy_matches",
            _identity_key(dispatch_summary.get("route_readiness_strategy", "")),
            "==",
            strategy,
            bool(
                _identity_key(dispatch_summary.get("route_readiness_strategy", ""))
                and strategy
                and _identity_key(dispatch_summary.get("route_readiness_strategy", "")) == strategy
            ),
            "dispatch route-readiness strategy does not match sender strategy",
        ),
        _check(
            "route_readiness_market_matches",
            _identity_key(dispatch_summary.get("route_readiness_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get("route_readiness_market", ""))
                and market
                and _identity_key(dispatch_summary.get("route_readiness_market", "")) == market
            ),
            "dispatch route-readiness market does not match sender market",
        ),
        _check(
            "route_readiness_ops_launch_controls_present",
            _to_bool(dispatch_summary.get("route_readiness_ops_launch_controls_present", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_readiness_ops_launch_controls_present", False)),
            "dispatch route-readiness proof is missing launch-grade ops broker controls",
        ),
        _check(
            "route_readiness_ops_launch_controls_blocked_pairs",
            int(_number(dispatch_summary, "route_readiness_ops_launch_controls_blocked_pairs", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_readiness_ops_launch_controls_blocked_pairs", 0.0)) <= 0,
            "dispatch route-readiness proof has blocked launch-control pairs",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
            int(_number(dispatch_summary, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0))
            <= 0,
            "dispatch route-readiness proof has broker round-trip allocation breach pairs",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
            int(
                _number(
                    dispatch_summary,
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    0.0,
                )
            ),
            "<=",
            0,
            int(
                _number(
                    dispatch_summary,
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    0.0,
                )
            )
            <= 0,
            "dispatch route-readiness proof has broker round-trip concentration breach pairs",
        ),
    ]
    if _route_broker_route_readiness_active(dispatch_summary):
        checks.extend(_route_broker_route_readiness_checks(dispatch_summary))
    return checks


def _route_broker_route_readiness_active(dispatch_summary: pd.Series) -> bool:
    return bool(
        _to_bool(dispatch_summary.get("route_broker_route_readiness_required", False))
        or _to_bool(dispatch_summary.get("route_broker_route_readiness_provided", False))
        or _to_bool(dispatch_summary.get("route_broker_route_readiness_ready", False))
        or int(_number(dispatch_summary, "route_broker_route_readiness_route_ready_pairs", 0.0)) > 0
        or int(_number(dispatch_summary, "route_broker_route_readiness_gap_pairs", 0.0)) > 0
        or bool(_text(dispatch_summary, "route_broker_route_readiness_strategy"))
        or bool(_text(dispatch_summary, "route_broker_route_readiness_market"))
        or bool(_text(dispatch_summary, "route_broker_route_readiness_recommendation"))
        or _to_bool(dispatch_summary.get("route_broker_route_readiness_ops_launch_controls_ready", False))
        or bool(_text(dispatch_summary, "route_broker_route_readiness_ops_launch_control_failures"))
        or int(
            _number(dispatch_summary, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        )
        > 0
        or int(
            _number(dispatch_summary, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        )
        > 0
        or int(
            _number(
                dispatch_summary,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        )
        > 0
        or int(
            _number(
                dispatch_summary,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        )
        > 0
    )


def _route_broker_route_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    return [
        _check(
            "route_broker_route_readiness_provided",
            _to_bool(dispatch_summary.get("route_broker_route_readiness_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_broker_route_readiness_provided", False))
            or not _to_bool(dispatch_summary.get("route_broker_route_readiness_required", False)),
            "dispatch broker-carried route proof is required but not provided",
        ),
        _check(
            "route_broker_route_readiness_ready",
            _to_bool(dispatch_summary.get("route_broker_route_readiness_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_broker_route_readiness_ready", False)),
            "dispatch broker-carried route proof is not ready",
        ),
        _check(
            "route_broker_route_readiness_strategy_matches",
            _identity_key(dispatch_summary.get("route_broker_route_readiness_strategy", "")),
            "==",
            strategy,
            bool(
                _identity_key(dispatch_summary.get("route_broker_route_readiness_strategy", ""))
                and strategy
                and _identity_key(dispatch_summary.get("route_broker_route_readiness_strategy", "")) == strategy
            ),
            "dispatch broker-carried route strategy does not match sender strategy",
        ),
        _check(
            "route_broker_route_readiness_market_matches",
            _identity_key(dispatch_summary.get("route_broker_route_readiness_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get("route_broker_route_readiness_market", ""))
                and market
                and _identity_key(dispatch_summary.get("route_broker_route_readiness_market", "")) == market
            ),
            "dispatch broker-carried route market does not match sender market",
        ),
        _check(
            "route_broker_route_readiness_gap_pairs",
            int(_number(dispatch_summary, "route_broker_route_readiness_gap_pairs", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_broker_route_readiness_gap_pairs", 0.0)) <= 0,
            "dispatch broker-carried route proof has route gaps",
        ),
        _check(
            "route_broker_route_readiness_ops_launch_controls_ready",
            _to_bool(dispatch_summary.get("route_broker_route_readiness_ops_launch_controls_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_broker_route_readiness_ops_launch_controls_ready", False)),
            "dispatch broker-carried route proof is missing launch-grade ops broker controls",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    0.0,
                )
            ),
            ">",
            0,
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    0.0,
                )
            )
            > 0,
            "dispatch broker-carried route proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    0.0,
                )
            ),
            "<=",
            0,
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    0.0,
                )
            )
            <= 0,
            "dispatch broker-carried route proof has allocation breach broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                )
            ),
            ">",
            0,
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                )
            )
            > 0,
            "dispatch broker-carried route proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                )
            ),
            "<=",
            0,
            int(
                _number(
                    dispatch_summary,
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                )
            )
            <= 0,
            "dispatch broker-carried route proof has concentration breach broker round-trip runs",
        ),
    ]


def _resume_route_readiness_active(dispatch_summary: pd.Series, prefix: str) -> bool:
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_required", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or int(_number(dispatch_summary, f"{prefix}_route_ready_pairs", 0.0)) > 0
        or int(_number(dispatch_summary, f"{prefix}_gap_pairs", 0.0)) > 0
        or bool(_text(dispatch_summary, f"{prefix}_strategy"))
        or bool(_text(dispatch_summary, f"{prefix}_market"))
        or bool(_text(dispatch_summary, f"{prefix}_recommendation"))
        or _to_bool(dispatch_summary.get(f"{prefix}_ops_launch_controls_ready", False))
        or bool(_text(dispatch_summary, f"{prefix}_ops_launch_control_failures"))
        or int(_number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0
        or int(_number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0))
        > 0
        or int(
            _number(
                dispatch_summary,
                f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        )
        > 0
        or int(
            _number(
                dispatch_summary,
                f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        )
        > 0
    )


def _resume_route_readiness_checks(
    dispatch_summary: pd.Series,
    *,
    prefix: str,
    label: str,
) -> list[dict[str, object]]:
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(dispatch_summary.get(f"{prefix}_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
            or not _to_bool(dispatch_summary.get(f"{prefix}_required", False)),
            f"{label} proof is required but not provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
            f"{label} proof is not ready",
        ),
        _check(
            f"{prefix}_strategy_matches",
            _identity_key(dispatch_summary.get(f"{prefix}_strategy", "")),
            "==",
            strategy,
            bool(
                _identity_key(dispatch_summary.get(f"{prefix}_strategy", ""))
                and strategy
                and _identity_key(dispatch_summary.get(f"{prefix}_strategy", "")) == strategy
            ),
            f"{label} strategy does not match sender strategy",
        ),
        _check(
            f"{prefix}_market_matches",
            _identity_key(dispatch_summary.get(f"{prefix}_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get(f"{prefix}_market", ""))
                and market
                and _identity_key(dispatch_summary.get(f"{prefix}_market", "")) == market
            ),
            f"{label} market does not match sender market",
        ),
        _check(
            f"{prefix}_route_ready_pairs",
            int(_number(dispatch_summary, f"{prefix}_route_ready_pairs", 0.0)),
            ">",
            0,
            int(_number(dispatch_summary, f"{prefix}_route_ready_pairs", 0.0)) > 0,
            f"{label} has no route-ready pairs",
        ),
        _check(
            f"{prefix}_gap_pairs",
            int(_number(dispatch_summary, f"{prefix}_gap_pairs", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, f"{prefix}_gap_pairs", 0.0)) <= 0,
            f"{label} has route gaps",
        ),
        _check(
            f"{prefix}_ops_launch_controls_ready",
            _to_bool(dispatch_summary.get(f"{prefix}_ops_launch_controls_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_ops_launch_controls_ready", False)),
            f"{label} is missing launch-grade ops broker controls",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            int(_number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)),
            ">",
            0,
            int(_number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0,
            f"{label} has no allocation-safe broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            int(_number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)) <= 0,
            f"{label} has allocation breach broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            int(
                _number(
                    dispatch_summary,
                    f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                )
            ),
            ">",
            0,
            int(
                _number(
                    dispatch_summary,
                    f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                )
            )
            > 0,
            f"{label} has no concentration-OK broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            int(
                _number(
                    dispatch_summary,
                    f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                )
            ),
            "<=",
            0,
            int(
                _number(
                    dispatch_summary,
                    f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                )
            )
            <= 0,
            f"{label} has concentration breach broker round-trip runs",
        ),
    ]


def _strategy_portfolio_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    selected_strategy = _identity_key(dispatch_summary.get("strategy_portfolio_selected_strategy", ""))
    selected_market = _identity_key(dispatch_summary.get("strategy_portfolio_selected_market", ""))
    selected_allocation = _number(dispatch_summary, "strategy_portfolio_selected_allocation_notional", 0.0)
    dispatch_total_notional = _number(dispatch_summary, "dispatch_total_notional", 0.0)
    return [
        _check(
            "strategy_portfolio_ready",
            _to_bool(dispatch_summary.get("strategy_portfolio_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("strategy_portfolio_ready", False)),
            "dispatch strategy portfolio allocation is not ready",
        ),
        _check(
            "strategy_portfolio_allocation_eligible",
            _to_bool(dispatch_summary.get("strategy_portfolio_selected_eligible", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("strategy_portfolio_selected_eligible", False)),
            "dispatch strategy portfolio allocation row is not eligible",
        ),
        _check(
            "strategy_portfolio_strategy_matches",
            selected_strategy,
            "==",
            strategy,
            bool(selected_strategy and strategy and selected_strategy == strategy),
            "dispatch strategy portfolio strategy does not match sender strategy",
        ),
        _check(
            "strategy_portfolio_market_matches",
            selected_market,
            "==",
            market,
            bool(selected_market and market and selected_market == market),
            "dispatch strategy portfolio market does not match sender market",
        ),
        _check(
            "strategy_portfolio_allocation_notional",
            selected_allocation,
            ">",
            0.0,
            selected_allocation > 0.0,
            "dispatch strategy portfolio allocation notional must be positive",
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


def _dispatch_roundtrip_checks(dispatch_summary: pd.Series, target_mode: str) -> list[dict[str, object]]:
    strategy = _text(dispatch_summary, "strategy")
    market = _identity_key(dispatch_summary.get("market", ""))
    scenario = _text(dispatch_summary, "scenario_key")
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get("route_dispatch_roundtrip_ready", False)),
            "dispatch route round-trip proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")),
            "==",
            target_mode,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")) == target_mode
            ),
            "dispatch route round-trip target mode does not match sender target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")),
            "==",
            _identity_key(strategy),
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_strategy", "")) == _identity_key(strategy)
            ),
            "dispatch route round-trip strategy does not match sender strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", "")),
            "==",
            market,
            bool(
                _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", ""))
                and _identity_key(dispatch_summary.get("route_dispatch_roundtrip_market", "")) == market
            ),
            "dispatch route round-trip market does not match sender market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key"),
            "==",
            scenario,
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") and scenario)
            and _text(dispatch_summary, "route_dispatch_roundtrip_scenario_key") == scenario,
            "dispatch route round-trip scenario does not match sender scenario",
        ),
        _check(
            "route_dispatch_roundtrip_batch_id_provided",
            _text(dispatch_summary, "route_dispatch_roundtrip_batch_id"),
            "is not",
            "",
            bool(_text(dispatch_summary, "route_dispatch_roundtrip_batch_id")),
            "dispatch route round-trip proof batch id is missing",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)) <= 0,
            "dispatch route round-trip has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)) <= 0,
            "dispatch route round-trip has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            int(_number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)) <= 0,
            "dispatch route round-trip has unmatched acknowledgements",
        ),
    ]


def _shadow_broker_readiness_active(dispatch_summary: pd.Series) -> bool:
    session_columns = (
        "shadow_broker_readiness_sessions",
        "shadow_broker_vendor_data_readiness_sessions",
        "shadow_broker_route_readiness_sessions",
        "shadow_broker_dispatch_roundtrip_sessions",
        "shadow_broker_route_dispatch_roundtrip_sessions",
    )
    return any(int(_number(dispatch_summary, column, 0.0)) > 0 for column in session_columns)


def _shadow_broker_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    strategy = _identity_key(dispatch_summary.get("strategy", ""))
    market = _identity_key(dispatch_summary.get("market", ""))
    adapter = _identity_key(dispatch_summary.get("adapter", ""))
    sessions = int(_number(dispatch_summary, "shadow_broker_readiness_sessions", 0.0))
    if sessions > 0:
        ready_sessions = int(_number(dispatch_summary, "shadow_broker_readiness_ready_sessions", 0.0))
        shadow_adapter = _identity_key(dispatch_summary.get("shadow_broker_adapter", ""))
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_readiness_ready",
                    ready_sessions,
                    "==",
                    sessions,
                    ready_sessions == sessions,
                    "dispatch shadow broker-readiness evidence is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_adapter_matches",
                    shadow_adapter,
                    "==",
                    adapter,
                    bool(shadow_adapter and adapter and shadow_adapter == adapter),
                    "dispatch shadow broker adapter does not match sender adapter",
                ),
                _check(
                    "dispatch_shadow_broker_adapter_consistent",
                    int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)) == 1,
                    "dispatch shadow broker adapter identity is missing or mixed",
                ),
            ]
        )
    vendor_sessions = int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_sessions", 0.0))
    if vendor_sessions > 0:
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
                    vendor_sessions,
                    "==",
                    sessions,
                    vendor_sessions == sessions,
                    "dispatch shadow broker vendor-data wrapper proof is present for only some broker-readiness sessions",
                ),
                _check(
                    "dispatch_shadow_broker_vendor_data_readiness_provided",
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)),
                    "==",
                    sessions,
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0))
                    == sessions,
                    "dispatch shadow broker vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    "dispatch_shadow_broker_vendor_data_readiness_ready",
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)),
                    "==",
                    sessions,
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0))
                    == sessions,
                    "dispatch shadow broker vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _check(
                    "dispatch_shadow_broker_vendor_data_readiness_failed_checks",
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)) <= 0,
                    "dispatch shadow broker vendor-data wrapper proof has failed checks",
                ),
            ]
        )
    route_sessions = int(_number(dispatch_summary, "shadow_broker_route_readiness_sessions", 0.0))
    if route_sessions > 0:
        route_strategy = _identity_key(dispatch_summary.get("shadow_broker_route_readiness_strategy", ""))
        route_market = _identity_key(dispatch_summary.get("shadow_broker_route_readiness_market", ""))
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_route_readiness_ready",
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0)),
                    "==",
                    route_sessions,
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0))
                    == route_sessions,
                    "dispatch shadow broker route-readiness proof is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_route_readiness_strategy_matches",
                    route_strategy,
                    "==",
                    strategy,
                    bool(route_strategy and strategy and route_strategy == strategy),
                    "dispatch shadow broker route-readiness strategy does not match sender strategy",
                ),
                _check(
                    "dispatch_shadow_broker_route_readiness_market_matches",
                    route_market,
                    "==",
                    market,
                    bool(route_market and market and route_market == market),
                    "dispatch shadow broker route-readiness market does not match sender market",
                ),
                _check(
                    "dispatch_shadow_broker_route_readiness_gap_pairs",
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)) <= 0,
                    "dispatch shadow broker route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_sessions", 0.0))
    if dispatch_sessions > 0:
        dispatch_strategy = _identity_key(dispatch_summary.get("shadow_broker_dispatch_roundtrip_strategy", ""))
        dispatch_market = _identity_key(dispatch_summary.get("shadow_broker_dispatch_roundtrip_market", ""))
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_ready",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)),
                    "==",
                    dispatch_sessions,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0))
                    == dispatch_sessions,
                    "dispatch shadow broker dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_strategy_matches",
                    dispatch_strategy,
                    "==",
                    strategy,
                    bool(dispatch_strategy and strategy and dispatch_strategy == strategy),
                    "dispatch shadow broker dispatch round-trip strategy does not match sender strategy",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_market_matches",
                    dispatch_market,
                    "==",
                    market,
                    bool(dispatch_market and market and dispatch_market == market),
                    "dispatch shadow broker dispatch round-trip market does not match sender market",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_scenario_consistent",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)) == 1,
                    "dispatch shadow broker dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_missing_request_acks",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0))
                    <= 0,
                    "dispatch shadow broker dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_rejected_orders",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)) <= 0,
                    "dispatch shadow broker dispatch round-trip has rejected orders",
                ),
                _check(
                    "dispatch_shadow_broker_dispatch_roundtrip_unmatched_acks",
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)),
                    "<=",
                    0,
                    int(_number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)) <= 0,
                    "dispatch shadow broker dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0))
    if route_dispatch_sessions > 0:
        route_dispatch_strategy = _identity_key(
            dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_strategy", "")
        )
        route_dispatch_market = _identity_key(
            dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_market", "")
        )
        checks.extend(
            [
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_ready",
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)),
                    "==",
                    route_dispatch_sessions,
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0))
                    == route_dispatch_sessions,
                    "dispatch shadow broker route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_strategy_matches",
                    route_dispatch_strategy,
                    "==",
                    strategy,
                    bool(route_dispatch_strategy and strategy and route_dispatch_strategy == strategy),
                    "dispatch shadow broker route dispatch round-trip strategy does not match sender strategy",
                ),
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_market_matches",
                    route_dispatch_market,
                    "==",
                    market,
                    bool(route_dispatch_market and market and route_dispatch_market == market),
                    "dispatch shadow broker route dispatch round-trip market does not match sender market",
                ),
                _check(
                    "dispatch_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)),
                    "==",
                    1,
                    int(_number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)) == 1,
                    "dispatch shadow broker route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _route_broker_shadow_broker_readiness_active(dispatch_summary: pd.Series) -> bool:
    prefix = "route_broker_shadow_broker"
    session_columns = (
        f"{prefix}_readiness_sessions",
        f"{prefix}_route_readiness_sessions",
        f"{prefix}_dispatch_roundtrip_sessions",
        f"{prefix}_route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_readiness_provided", False))
        or any(int(_number(dispatch_summary, column, 0.0)) > 0 for column in session_columns)
    )


def _route_broker_shadow_broker_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    source_prefix = "route_broker_shadow_broker"
    checks = [
        _check(
            "dispatch_broker_shadow_broker_readiness_provided",
            _to_bool(dispatch_summary.get(f"{source_prefix}_readiness_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{source_prefix}_readiness_provided", False)),
            "dispatch broker-readiness shadow broker proof is active but not marked provided",
        )
    ]
    mapped = _shadow_broker_projection(dispatch_summary, source_prefix=source_prefix)
    for check in _shadow_broker_readiness_checks(mapped):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "dispatch_shadow_broker",
            "dispatch_broker_shadow_broker",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "dispatch shadow broker",
                "dispatch broker-readiness shadow broker",
            )
        checks.append(renamed)
    return checks


def _vendor_market_data_batch_active(dispatch_summary: pd.Series) -> bool:
    prefix = "dispatch_vendor_market_data_batch"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or _identity_key(dispatch_summary.get(f"{prefix}_adapter", ""))
        or _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
        or int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0)) > 0
    )


def _broker_vendor_data_readiness_active(dispatch_summary: pd.Series) -> bool:
    prefix = "dispatch_broker_vendor_data_readiness"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or int(_number(dispatch_summary, f"{prefix}_failed_checks", 0.0)) > 0
    )


def _broker_vendor_data_readiness_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "dispatch_broker_vendor_data_readiness"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(dispatch_summary.get(f"{prefix}_provided", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_provided", False)),
            "dispatch broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
            "is",
            True,
            _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
            "dispatch broker-vendor readiness wrapper proof is not ready",
        ),
        _check(
            f"{prefix}_failed_checks",
            int(_number(dispatch_summary, f"{prefix}_failed_checks", 0.0)),
            "<=",
            0,
            int(_number(dispatch_summary, f"{prefix}_failed_checks", 0.0)) <= 0,
            "dispatch broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _vendor_market_data_batch_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "dispatch_vendor_market_data_batch"
    manifest_run_type = _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
    return [
        _check(
            f"{prefix}_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "dispatch vendor market-data manifest is not a vendor batch pipeline proof",
        )
    ]


def _broker_vendor_market_data_batch_active(dispatch_summary: pd.Series) -> bool:
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    return bool(
        _to_bool(dispatch_summary.get(f"{prefix}_provided", False))
        or _to_bool(dispatch_summary.get(f"{prefix}_ready", False))
        or _identity_key(dispatch_summary.get(f"{prefix}_adapter", ""))
        or _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
        or int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0)) > 0
    )


def _broker_vendor_market_data_batch_checks(dispatch_summary: pd.Series) -> list[dict[str, object]]:
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    manifest_run_type = _identity_key(dispatch_summary.get(f"{prefix}_manifest_run_type", ""))
    checks = [
        _check(
            f"{prefix}_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "dispatch broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            f"{prefix}_source_file_fingerprint_coverage",
            _number(dispatch_summary, f"{prefix}_source_file_fingerprint_coverage", 0.0),
            ">=",
            1.0,
            _number(dispatch_summary, f"{prefix}_source_file_fingerprint_coverage", 0.0) >= 1.0,
            "dispatch broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            f"{prefix}_min_mapping_coverage",
            _number(dispatch_summary, f"{prefix}_min_mapping_coverage", 0.0),
            ">=",
            1.0,
            _number(dispatch_summary, f"{prefix}_min_mapping_coverage", 0.0) >= 1.0,
            "dispatch broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            f"{prefix}_mapping_drafts",
            int(_number(dispatch_summary, f"{prefix}_unique_mapping_drafts", 0.0)),
            ">",
            0,
            int(_number(dispatch_summary, f"{prefix}_unique_mapping_drafts", 0.0)) > 0,
            "dispatch broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
    ]
    if _target_application_batch_active(dispatch_summary, prefix=prefix):
        dataset_count = int(_number(dispatch_summary, f"{prefix}_dataset_count", 0.0))
        mapping_application_count = int(
            _number(dispatch_summary, f"{prefix}_mapping_application_count", 0.0)
        )
        unique_mapping_applications = int(
            _number(dispatch_summary, f"{prefix}_unique_mapping_applications", 0.0)
        )
        target_application_coverage = _number(
            dispatch_summary, f"{prefix}_target_application_coverage", 0.0
        )
        lineage_datasets = _target_application_lineage_dataset_count(
            dispatch_summary,
            prefix=prefix,
        )
        lineage_consistency_required = _to_bool(
            dispatch_summary.get(
                f"{prefix}_application_lineage_consistency_required",
                False,
            )
        )
        lineage_consistent = _to_bool(
            dispatch_summary.get(f"{prefix}_application_lineage_consistent", False)
        )
        lineage_match_required = _to_bool(
            dispatch_summary.get(
                "dispatch_broker_vendor_market_data_batch_lineage_match_required",
                False,
            )
        )
        lineage_matches = _to_bool(
            dispatch_summary.get(
                "dispatch_broker_vendor_market_data_batch_lineage_matches",
                False,
            )
        )
        current_lineage_sha256 = _sha256_text(
            dispatch_summary.get(
                "dispatch_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        broker_lineage_sha256 = _sha256_text(
            dispatch_summary.get(
                "dispatch_broker_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        scaleup_carried_lineage_sha256 = _sha256_text(
            dispatch_summary.get(
                "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        cutover_carried_lineage_sha256 = _sha256_text(
            dispatch_summary.get(
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        route_carried_lineage_sha256 = _sha256_text(
            dispatch_summary.get(
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        dispatch_carried_lineage_sha256 = _sha256_text(
            dispatch_summary.get(
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        send_carried_lineage_sha256 = _target_application_lineage_sha256(
            dispatch_summary,
            prefix=prefix,
        )
        mapping_source_mode = _identity_key(
            dispatch_summary.get(f"{prefix}_mapping_source_mode", "")
        )
        checks.extend(
            [
                _check(
                    f"{prefix}_mapping_source_mode",
                    mapping_source_mode,
                    "==",
                    TARGET_APPLICATION_BATCH_MODE,
                    mapping_source_mode == TARGET_APPLICATION_BATCH_MODE,
                    "dispatch broker-readiness vendor target applications are missing strict source mode",
                ),
                _check(
                    f"{prefix}_mapping_application_count",
                    mapping_application_count,
                    "==",
                    dataset_count,
                    dataset_count > 0 and mapping_application_count == dataset_count,
                    "dispatch broker-readiness vendor target applications are not aligned one for one",
                ),
                _check(
                    f"{prefix}_unique_mapping_applications",
                    unique_mapping_applications,
                    "==",
                    dataset_count,
                    dataset_count > 0 and unique_mapping_applications == dataset_count,
                    "dispatch broker-readiness vendor target applications are not distinct per dataset",
                ),
                _check(
                    f"{prefix}_target_application_coverage",
                    target_application_coverage,
                    ">=",
                    1.0,
                    target_application_coverage >= 1.0,
                    "dispatch broker-readiness vendor target-application coverage is incomplete",
                ),
                _check(
                    f"{prefix}_application_lineage_datasets",
                    lineage_datasets,
                    "==",
                    dataset_count,
                    dataset_count > 0 and lineage_datasets == dataset_count,
                    "dispatch broker-readiness vendor datasets are missing target-application lineage",
                ),
                _check(
                    f"{prefix}_lineage_match_required",
                    lineage_match_required,
                    "is",
                    True,
                    lineage_match_required,
                    "target-application send preparation requires the dispatch-plan lineage comparison",
                ),
                _check(
                    f"{prefix}_lineage_matches",
                    lineage_matches,
                    "is",
                    True,
                    lineage_match_required and lineage_matches,
                    "dispatch-plan current and final target-application lineages do not match",
                ),
                _check(
                    f"{prefix}_source_lineage_sha256_matches",
                    current_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and current_lineage_sha256
                        and broker_lineage_sha256
                        and current_lineage_sha256 == broker_lineage_sha256
                    ),
                    "dispatch-plan current/final target-lineage digests are missing or disagree",
                ),
                _check(
                    f"{prefix}_scaleup_carried_lineage_sha256_matches",
                    scaleup_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and scaleup_carried_lineage_sha256
                        and broker_lineage_sha256
                        and scaleup_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "dispatch-plan scale-up-carried target lineage does not match broker-readiness proof",
                ),
                _check(
                    f"{prefix}_cutover_carried_lineage_sha256_matches",
                    cutover_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and cutover_carried_lineage_sha256
                        and broker_lineage_sha256
                        and cutover_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "dispatch-plan cutover-carried target lineage does not match broker-readiness proof",
                ),
                _check(
                    f"{prefix}_route_carried_lineage_sha256_matches",
                    route_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and route_carried_lineage_sha256
                        and broker_lineage_sha256
                        and route_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "dispatch-plan route-carried target lineage does not match broker-readiness proof",
                ),
                _check(
                    f"{prefix}_dispatch_carried_lineage_sha256_matches",
                    dispatch_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and dispatch_carried_lineage_sha256
                        and broker_lineage_sha256
                        and dispatch_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "dispatch-plan carried target lineage does not match route-enable proof",
                ),
                _check(
                    f"{prefix}_send_carried_lineage_sha256_matches",
                    send_carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and send_carried_lineage_sha256
                        and broker_lineage_sha256
                        and send_carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "send-packet carried target lineage does not match dispatch-plan proof",
                ),
            ]
        )
        if lineage_consistency_required:
            checks.extend(
                [
                    _check(
                        f"{prefix}_application_lineage_consistent",
                        lineage_consistent,
                        "is",
                        True,
                        lineage_consistent,
                        "dispatch final dispatch/send/ack target lineage was not consistent",
                    ),
                    *_broker_vendor_final_lineage_checks(
                        dispatch_summary,
                        send_lineage_sha256=send_carried_lineage_sha256,
                    ),
                    *_broker_vendor_complete_final_lineage_checks(
                        dispatch_summary,
                        send_lineage_sha256=send_carried_lineage_sha256,
                    ),
                    *_broker_vendor_extended_complete_final_lineage_checks(
                        dispatch_summary,
                        send_lineage_sha256=send_carried_lineage_sha256,
                    ),
                    *_broker_vendor_extended_complete_final_lineage_38_checks(
                        dispatch_summary,
                        send_lineage_sha256=send_carried_lineage_sha256,
                    ),
                    *_broker_vendor_latest_extended_complete_final_lineage_46_checks(
                        dispatch_summary,
                        send_lineage_sha256=send_carried_lineage_sha256,
                    ),
                ]
            )
    return checks


def _broker_vendor_final_lineage_checks(
    dispatch_summary: pd.Series,
    *,
    send_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = DISPATCH_FINAL_LINEAGE_FIELD_PREFIX
    prefix = source_prefix
    lineage_match_required = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_match_required", False)
    )
    lineage_matches = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_matches", False)
    )
    final_broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    final_current_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_current_application_lineage_sha256",
            "",
        )
    )
    dispatch_broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            "dispatch_broker_vendor_market_data_batch_application_lineage_sha256",
            "",
        )
    )
    dispatch_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            "",
        )
    )
    checks = [
        _check(
            f"{prefix}_final_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target send preparation requires broker dispatch's final lineage comparison",
        ),
        _check(
            f"{prefix}_final_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker dispatch did not reconcile every final target-lineage view",
        ),
        _check(
            f"{prefix}_final_source_lineage_sha256_matches",
            final_current_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and final_current_lineage_sha256
                and final_broker_lineage_sha256
                and final_current_lineage_sha256 == final_broker_lineage_sha256
            ),
            "broker dispatch's final source lineage does not match final broker proof",
        ),
        _check(
            f"{prefix}_final_broker_lineage_sha256_matches",
            dispatch_broker_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and dispatch_broker_lineage_sha256
                and final_broker_lineage_sha256
                and dispatch_broker_lineage_sha256 == final_broker_lineage_sha256
            ),
            "broker dispatch's current/final broker digest does not match its final comparison",
        ),
        _check(
            f"{prefix}_final_application_lineage_sha256_matches",
            dispatch_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and dispatch_lineage_sha256
                and final_broker_lineage_sha256
                and dispatch_lineage_sha256 == final_broker_lineage_sha256
            ),
            "broker dispatch's independently recomputed batch digest does not match final comparison",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("prior_cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
        ("scaleup_review", "scaleup_review_carried_application_lineage_sha256"),
        ("cutover_review", "cutover_review_carried_application_lineage_sha256"),
        ("route_enable_review", "route_enable_review_carried_application_lineage_sha256"),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{prefix}_final_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and final_broker_lineage_sha256
                    and carried_sha256 == final_broker_lineage_sha256
                ),
                (
                    f"broker dispatch's {stage.replace('_', '-')} target lineage does not "
                    "match final broker proof"
                ),
            )
        )
    dispatch_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_carried_application_lineage_sha256",
            "",
        )
    )
    checks.extend(
        [
            _check(
                f"{prefix}_final_dispatch_plan_review_carried_lineage_sha256_matches",
                dispatch_review_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and dispatch_review_lineage_sha256
                    and final_broker_lineage_sha256
                    and dispatch_review_lineage_sha256 == final_broker_lineage_sha256
                ),
                "broker dispatch's carried review lineage does not match final broker proof",
            ),
            _check(
                f"{prefix}_send_packet_review_carried_lineage_sha256_matches",
                send_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and send_lineage_sha256
                    and final_broker_lineage_sha256
                    and send_lineage_sha256 == final_broker_lineage_sha256
                ),
                "send preparation's independently recomputed target lineage does not match final broker proof",
            ),
        ]
    )
    return checks


def _broker_vendor_complete_final_lineage_checks(
    dispatch_summary: pd.Series,
    *,
    send_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = DISPATCH_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_dispatch_final"
    lineage_match_required = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_match_required", False)
    )
    lineage_matches = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_matches", False)
    )
    broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    current_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_current_application_lineage_sha256",
            "",
        )
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_broker_application_lineage_sha256",
            "",
        )
    )
    compatibility_dispatch_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_carried_application_lineage_sha256",
            "",
        )
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target send preparation requires broker dispatch's complete final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker dispatch did not match every complete final target-lineage view",
        ),
        _check(
            f"{check_prefix}_source_lineage_sha256_matches",
            current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and current_lineage_sha256
                and broker_lineage_sha256
                and current_lineage_sha256 == broker_lineage_sha256
            ),
            "broker dispatch final source lineage does not match final broker proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
            compatibility_broker_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_broker_lineage_sha256
                and broker_lineage_sha256
                and compatibility_broker_lineage_sha256 == broker_lineage_sha256
            ),
            "send compatibility broker digest does not match dispatch's final proof",
        ),
        _check(
            f"{check_prefix}_compatibility_dispatch_carried_lineage_sha256_matches",
            compatibility_dispatch_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_dispatch_lineage_sha256
                and broker_lineage_sha256
                and compatibility_dispatch_lineage_sha256 == broker_lineage_sha256
            ),
            "send compatibility dispatch digest does not match dispatch's final proof",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("prior_cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
        ("scaleup_review", "scaleup_review_carried_application_lineage_sha256"),
        ("cutover_review", "cutover_review_carried_application_lineage_sha256"),
        (
            "route_enable_review",
            "route_enable_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_plan_review",
            "dispatch_plan_review_carried_application_lineage_sha256",
        ),
        (
            "send_packet_review",
            "send_packet_review_carried_application_lineage_sha256",
        ),
        (
            "ack_reconciliation_review",
            "ack_reconciliation_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_final_review",
            "roundtrip_final_review_carried_application_lineage_sha256",
        ),
        (
            "broker_readiness_review",
            "broker_readiness_review_carried_application_lineage_sha256",
        ),
        (
            "scaleup_final_review",
            "scaleup_final_review_carried_application_lineage_sha256",
        ),
        (
            "cutover_final_review",
            "cutover_final_review_carried_application_lineage_sha256",
        ),
        (
            "route_final_review",
            "route_final_review_carried_application_lineage_sha256",
        ),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{check_prefix}_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and broker_lineage_sha256
                    and carried_sha256 == broker_lineage_sha256
                ),
                (
                    f"broker dispatch's {stage.replace('_', '-')} target lineage "
                    "does not match final broker proof"
                ),
            )
        )
    dispatch_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_carried_application_lineage_sha256",
            "",
        )
    )
    send_final_review_lineage_sha256 = _sha256_text(send_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_dispatch_final_review_carried_lineage_sha256_matches",
                dispatch_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and dispatch_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and dispatch_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's carried final-review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_send_final_review_carried_lineage_sha256_matches",
                send_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and send_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and send_final_review_lineage_sha256 == broker_lineage_sha256
                ),
                "send preparation's independently recomputed target lineage does not match dispatch's final proof",
            ),
        ]
    )
    return checks


def _broker_vendor_extended_complete_final_lineage_checks(
    dispatch_summary: pd.Series,
    *,
    send_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    compatibility_prefix = DISPATCH_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_dispatch_complete_final"
    lineage_match_required = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_match_required", False)
    )
    lineage_matches = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_matches", False)
    )
    broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    current_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_current_application_lineage_sha256",
            "",
        )
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{compatibility_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    compatibility_dispatch_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{compatibility_prefix}_carried_application_lineage_sha256",
            "",
        )
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target send preparation requires broker dispatch's extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker dispatch did not match every extended complete-final target-lineage view",
        ),
        _check(
            f"{check_prefix}_source_lineage_sha256_matches",
            current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and current_lineage_sha256
                and broker_lineage_sha256
                and current_lineage_sha256 == broker_lineage_sha256
            ),
            "broker dispatch complete-final source lineage does not match final broker proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
            compatibility_broker_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_broker_lineage_sha256
                and broker_lineage_sha256
                and compatibility_broker_lineage_sha256 == broker_lineage_sha256
            ),
            "send compatibility broker digest does not match dispatch's extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_dispatch_final_review_carried_lineage_sha256_matches",
            compatibility_dispatch_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_dispatch_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_dispatch_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "send compatibility dispatch final review does not match dispatch's extended proof",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("prior_cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
        ("scaleup_review", "scaleup_review_carried_application_lineage_sha256"),
        ("cutover_review", "cutover_review_carried_application_lineage_sha256"),
        (
            "route_enable_review",
            "route_enable_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_plan_review",
            "dispatch_plan_review_carried_application_lineage_sha256",
        ),
        (
            "send_packet_review",
            "send_packet_review_carried_application_lineage_sha256",
        ),
        (
            "ack_reconciliation_review",
            "ack_reconciliation_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_final_review",
            "roundtrip_final_review_carried_application_lineage_sha256",
        ),
        (
            "broker_readiness_review",
            "broker_readiness_review_carried_application_lineage_sha256",
        ),
        (
            "scaleup_final_review",
            "scaleup_final_review_carried_application_lineage_sha256",
        ),
        (
            "cutover_final_review",
            "cutover_final_review_carried_application_lineage_sha256",
        ),
        (
            "route_final_review",
            "route_final_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_final_review",
            "dispatch_final_review_carried_application_lineage_sha256",
        ),
        (
            "send_final_review",
            "send_final_review_carried_application_lineage_sha256",
        ),
        (
            "ack_complete_final_review",
            "ack_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_complete_final_review",
            "roundtrip_complete_final_review_carried_application_lineage_sha256",
        ),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{check_prefix}_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and broker_lineage_sha256
                    and carried_sha256 == broker_lineage_sha256
                ),
                (
                    f"broker dispatch's {stage.replace('_', '-')} target lineage "
                    "does not match extended complete-final broker proof"
                ),
            )
        )
    scaleup_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    cutover_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_cutover_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    route_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_route_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    dispatch_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_carried_application_lineage_sha256",
            "",
        )
    )
    send_complete_final_review_lineage_sha256 = _sha256_text(send_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_scaleup_complete_final_review_carried_lineage_sha256_matches",
                scaleup_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's carried scale-up complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_complete_final_review_carried_lineage_sha256_matches",
                cutover_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's carried cutover complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_complete_final_review_carried_lineage_sha256_matches",
                route_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and route_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's carried route complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_dispatch_complete_final_review_carried_lineage_sha256_matches",
                dispatch_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and dispatch_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and dispatch_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's carried complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_send_complete_final_review_carried_lineage_sha256_matches",
                send_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and send_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and send_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "send preparation's independently recomputed target lineage does not match dispatch's extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_extended_complete_final_lineage_38_checks(
    dispatch_summary: pd.Series,
    *,
    send_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_FIELD_PREFIX
    compatibility_prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = (
        f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_dispatch_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_match_required", False)
    )
    lineage_matches = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_matches", False)
    )
    broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    current_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_current_application_lineage_sha256",
            "",
        )
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{compatibility_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    compatibility_dispatch_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{compatibility_prefix}_carried_application_lineage_sha256",
            "",
        )
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target send preparation requires broker dispatch's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker dispatch did not match every latest extended complete-final target-lineage view",
        ),
        _check(
            f"{check_prefix}_source_lineage_sha256_matches",
            current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and current_lineage_sha256
                and broker_lineage_sha256
                and current_lineage_sha256 == broker_lineage_sha256
            ),
            "broker dispatch extended complete-final source lineage does not match final broker proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
            compatibility_broker_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_broker_lineage_sha256
                and broker_lineage_sha256
                and compatibility_broker_lineage_sha256 == broker_lineage_sha256
            ),
            "send compatibility broker digest does not match dispatch's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_dispatch_complete_final_review_carried_lineage_sha256_matches",
            compatibility_dispatch_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_dispatch_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_dispatch_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "send compatibility dispatch complete-final review does not match dispatch's latest extended proof",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("prior_cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
        ("scaleup_review", "scaleup_review_carried_application_lineage_sha256"),
        ("cutover_review", "cutover_review_carried_application_lineage_sha256"),
        (
            "route_enable_review",
            "route_enable_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_plan_review",
            "dispatch_plan_review_carried_application_lineage_sha256",
        ),
        (
            "send_packet_review",
            "send_packet_review_carried_application_lineage_sha256",
        ),
        (
            "ack_reconciliation_review",
            "ack_reconciliation_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_final_review",
            "roundtrip_final_review_carried_application_lineage_sha256",
        ),
        (
            "broker_readiness_review",
            "broker_readiness_review_carried_application_lineage_sha256",
        ),
        (
            "scaleup_final_review",
            "scaleup_final_review_carried_application_lineage_sha256",
        ),
        (
            "cutover_final_review",
            "cutover_final_review_carried_application_lineage_sha256",
        ),
        (
            "route_final_review",
            "route_final_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_final_review",
            "dispatch_final_review_carried_application_lineage_sha256",
        ),
        (
            "send_final_review",
            "send_final_review_carried_application_lineage_sha256",
        ),
        (
            "ack_complete_final_review",
            "ack_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_complete_final_review",
            "roundtrip_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "scaleup_complete_final_review",
            "scaleup_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "cutover_complete_final_review",
            "cutover_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "route_complete_final_review",
            "route_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_complete_final_review",
            "dispatch_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "send_complete_final_review",
            "send_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "ack_extended_complete_final_review",
            "ack_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "roundtrip_extended_complete_final_review",
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
        ),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{check_prefix}_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and broker_lineage_sha256
                    and carried_sha256 == broker_lineage_sha256
                ),
                (
                    f"broker dispatch's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    broker_readiness_extended_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    scaleup_extended_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    cutover_extended_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    route_extended_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_route_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    )
    dispatch_extended_complete_final_review_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_carried_application_lineage_sha256",
            "",
        )
    )
    send_extended_complete_final_review_lineage_sha256 = _sha256_text(
        send_lineage_sha256
    )
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
                broker_readiness_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and broker_readiness_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and broker_readiness_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's broker-readiness extended review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
                scaleup_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's scale-up extended review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
                cutover_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's cutover extended review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_extended_complete_final_review_carried_lineage_sha256_matches",
                route_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and route_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's route extended review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
                dispatch_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and dispatch_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and dispatch_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker dispatch's carried extended complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_send_extended_complete_final_review_carried_lineage_sha256_matches",
                send_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and send_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and send_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "send preparation's independently recomputed target lineage does not match dispatch's latest extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_latest_extended_complete_final_lineage_46_checks(
    dispatch_summary: pd.Series,
    *,
    send_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_FIELD_PREFIX
    compatibility_prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_FIELD_PREFIX
    check_prefix = (
        f"{DISPATCH_FINAL_LINEAGE_FIELD_PREFIX}_dispatch_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_match_required", False)
    )
    lineage_matches = _to_bool(
        dispatch_summary.get(f"{source_prefix}_lineage_matches", False)
    )
    broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    current_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{source_prefix}_current_application_lineage_sha256",
            "",
        )
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        dispatch_summary.get(
            f"{compatibility_prefix}_broker_application_lineage_sha256",
            "",
        )
    )
    compatibility_dispatch_extended_complete_final_review_lineage_sha256 = (
        _sha256_text(
            dispatch_summary.get(
                f"{compatibility_prefix}_carried_application_lineage_sha256",
                "",
            )
        )
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target send preparation requires broker dispatch's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker dispatch did not match every latest extended complete-final target-lineage view",
        ),
        _check(
            f"{check_prefix}_source_lineage_sha256_matches",
            current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and current_lineage_sha256
                and broker_lineage_sha256
                and current_lineage_sha256 == broker_lineage_sha256
            ),
            "broker dispatch latest extended complete-final source lineage does not match final broker proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
            compatibility_broker_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_broker_lineage_sha256
                and broker_lineage_sha256
                and compatibility_broker_lineage_sha256 == broker_lineage_sha256
            ),
            "send compatibility broker digest does not match dispatch's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_dispatch_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_dispatch_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_dispatch_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "send compatibility dispatch extended review does not match dispatch's latest extended proof",
        ),
    ]
    for field in DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_DIGEST_FIELDS:
        if field in {
            "current_application_lineage_sha256",
            "broker_application_lineage_sha256",
        }:
            continue
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        carried_sha256 = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{check_prefix}_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and broker_lineage_sha256
                    and carried_sha256 == broker_lineage_sha256
                ),
                (
                    f"broker dispatch's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    for stage, field in (
        (
            "broker_readiness_latest_extended_complete_final_review",
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "scaleup_latest_extended_complete_final_review",
            "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "cutover_latest_extended_complete_final_review",
            "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "route_latest_extended_complete_final_review",
            "route_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        (
            "dispatch_latest_extended_complete_final_review",
            "carried_application_lineage_sha256",
        ),
    ):
        carried_sha256 = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{check_prefix}_{stage}_carried_lineage_sha256_matches",
                carried_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and carried_sha256
                    and broker_lineage_sha256
                    and carried_sha256 == broker_lineage_sha256
                ),
                (
                    f"broker dispatch's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    send_latest_extended_complete_final_review_lineage_sha256 = _sha256_text(
        send_lineage_sha256
    )
    checks.append(
        _check(
            f"{check_prefix}_send_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            send_latest_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and send_latest_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and send_latest_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "send preparation's independently recomputed target lineage does not match dispatch's latest extended proof",
        )
    )
    return checks


def _target_application_batch_active(dispatch_summary: pd.Series, *, prefix: str) -> bool:
    mapping_sources = {
        value.strip().lower()
        for value in _text(dispatch_summary, f"{prefix}_mapping_sources").split(";")
        if value.strip()
    }
    return bool(
        _identity_key(dispatch_summary.get(f"{prefix}_mapping_source_mode", ""))
        == TARGET_APPLICATION_BATCH_MODE
        or "verified_target_application" in mapping_sources
        or int(_number(dispatch_summary, f"{prefix}_mapping_application_count", 0.0)) > 0
        or _number(dispatch_summary, f"{prefix}_target_application_coverage", 0.0) > 0.0
    )


def _target_application_lineage_dataset_count(
    dispatch_summary: pd.Series,
    *,
    prefix: str,
) -> int:
    datasets = _json_list(dispatch_summary.get(f"{prefix}_datasets_json", ""))
    return sum(
        isinstance(dataset, dict)
        and all(_object_text(dataset.get(field, "")) for field in TARGET_APPLICATION_DATASET_LINEAGE_FIELDS)
        for dataset in datasets
    )


def _target_application_lineage_sha256(
    dispatch_summary: pd.Series,
    *,
    prefix: str,
) -> str:
    identities: list[dict[str, str]] = []
    for dataset in _json_list(dispatch_summary.get(f"{prefix}_datasets_json", "")):
        if not isinstance(dataset, dict):
            return ""
        identity = {
            field: _object_text(dataset.get(field))
            for field in TARGET_APPLICATION_LINEAGE_IDENTITY_FIELDS
        }
        if not all(identity.values()):
            return ""
        identities.append(identity)
    if not identities:
        return ""
    canonical = json.dumps(
        sorted(
            identities,
            key=lambda identity: json.dumps(
                identity,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sha256_text(value: object) -> str:
    normalized = _object_text(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return ""
    return normalized


def _shadow_broker_projection(dispatch_summary: pd.Series, *, source_prefix: str) -> pd.Series:
    mapped = dispatch_summary.copy()
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
        mapped[f"shadow_broker_{suffix}"] = dispatch_summary.get(f"{source_prefix}_{suffix}", "")
    return mapped


def _prefixed_shadow_broker_summary_fields(dispatch_summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        f"{field_prefix}_readiness_provided": _to_bool(
            dispatch_summary.get(f"{field_prefix}_readiness_provided", False)
        ),
        f"{field_prefix}_readiness_sessions": int(_number(dispatch_summary, f"{field_prefix}_readiness_sessions", 0.0)),
        f"{field_prefix}_readiness_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_provided_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_failed_checks": int(
            _number(dispatch_summary, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0)
        ),
        f"{field_prefix}_adapter": _identity_key(dispatch_summary.get(f"{field_prefix}_adapter", "")),
        f"{field_prefix}_adapter_count": int(_number(dispatch_summary, f"{field_prefix}_adapter_count", 0.0)),
        f"{field_prefix}_route_readiness_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_readiness_sessions", 0.0)
        ),
        f"{field_prefix}_route_readiness_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_route_readiness_strategy": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_readiness_strategy", "")
        ),
        f"{field_prefix}_route_readiness_market": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_readiness_market", "")
        ),
        f"{field_prefix}_route_readiness_gap_pairs": int(
            _number(dispatch_summary, f"{field_prefix}_route_readiness_gap_pairs", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_strategy": _identity_key(
            dispatch_summary.get(f"{field_prefix}_dispatch_roundtrip_strategy", "")
        ),
        f"{field_prefix}_dispatch_roundtrip_market": _identity_key(
            dispatch_summary.get(f"{field_prefix}_dispatch_roundtrip_market", "")
        ),
        f"{field_prefix}_dispatch_roundtrip_scenario_count": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_missing_request_acks": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_rejected_orders": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_unmatched_acks": int(
            _number(dispatch_summary, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_ready_sessions": int(
            _number(dispatch_summary, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_strategy": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_dispatch_roundtrip_strategy", "")
        ),
        f"{field_prefix}_route_dispatch_roundtrip_market": _identity_key(
            dispatch_summary.get(f"{field_prefix}_route_dispatch_roundtrip_market", "")
        ),
        f"{field_prefix}_route_dispatch_roundtrip_scenario_count": int(
            _number(dispatch_summary, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0)
        ),
    }


def _summary(
    dispatch_summary: pd.Series,
    requests: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "request_state": "dry_run_send_packet_ready" if ready else "disabled",
                "target_mode": _identity_key(dispatch_summary.get("target_mode", "")),
                "strategy": _text(dispatch_summary, "strategy"),
                "market": _text(dispatch_summary, "market"),
                "scenario_key": _text(dispatch_summary, "scenario_key"),
                "adapter": _text(dispatch_summary, "adapter"),
                "broker_schema_status": _text(dispatch_summary, "broker_schema_status"),
                "broker_schema_reviewed": _to_bool(dispatch_summary.get("broker_schema_reviewed", False)),
                "broker_schema_review_mode": _text(dispatch_summary, "broker_schema_review_mode"),
                "dispatch_batch_id": _text(dispatch_summary, "dispatch_batch_id"),
                "dispatch_orders": int(_number(dispatch_summary, "dispatch_orders", len(requests))),
                "dispatch_total_notional": _number(dispatch_summary, "dispatch_total_notional", 0.0),
                "requests": int(len(requests)),
                **_broker_dispatch_lineage_output_fields(dispatch_summary),
                "authorizes_submission": False,
                "strategy_portfolio_required": _to_bool(
                    dispatch_summary.get("strategy_portfolio_required", False)
                ),
                "strategy_portfolio_provided": _to_bool(
                    dispatch_summary.get("strategy_portfolio_provided", False)
                ),
                "strategy_portfolio_ready": _to_bool(dispatch_summary.get("strategy_portfolio_ready", False)),
                "strategy_portfolio_deployment_mode": _text(
                    dispatch_summary, "strategy_portfolio_deployment_mode"
                ),
                "strategy_portfolio_allocation_mode": _text(
                    dispatch_summary, "strategy_portfolio_allocation_mode"
                ),
                "strategy_portfolio_capital_currency": _text(
                    dispatch_summary, "strategy_portfolio_capital_currency"
                ),
                "strategy_portfolio_selected_profile": _text(
                    dispatch_summary, "strategy_portfolio_selected_profile"
                ),
                "strategy_portfolio_selected_strategy": _identity_key(
                    dispatch_summary.get("strategy_portfolio_selected_strategy", "")
                ),
                "strategy_portfolio_selected_market": _identity_key(
                    dispatch_summary.get("strategy_portfolio_selected_market", "")
                ),
                "strategy_portfolio_selected_eligible": _to_bool(
                    dispatch_summary.get("strategy_portfolio_selected_eligible", False)
                ),
                "strategy_portfolio_selected_allocation_weight": _number(
                    dispatch_summary, "strategy_portfolio_selected_allocation_weight", 0.0
                ),
                "strategy_portfolio_selected_allocation_notional": _number(
                    dispatch_summary, "strategy_portfolio_selected_allocation_notional", 0.0
                ),
                "strategy_portfolio_notional_cap_applied": _to_bool(
                    dispatch_summary.get("strategy_portfolio_notional_cap_applied", False)
                ),
                "strategy_portfolio_min_strategy_count": int(
                    _number(dispatch_summary, "strategy_portfolio_min_strategy_count", 0.0)
                ),
                "strategy_portfolio_min_market_count": int(
                    _number(dispatch_summary, "strategy_portfolio_min_market_count", 0.0)
                ),
                "strategy_portfolio_max_strategy_weight": _number(
                    dispatch_summary, "strategy_portfolio_max_strategy_weight", 0.0
                ),
                "strategy_portfolio_max_market_weight": _number(
                    dispatch_summary, "strategy_portfolio_max_market_weight", 0.0
                ),
                "strategy_portfolio_allocated_strategy_count": int(
                    _number(dispatch_summary, "strategy_portfolio_allocated_strategy_count", 0.0)
                ),
                "strategy_portfolio_allocated_market_count": int(
                    _number(dispatch_summary, "strategy_portfolio_allocated_market_count", 0.0)
                ),
                "strategy_portfolio_top_strategy_by_weight": _identity_key(
                    dispatch_summary.get("strategy_portfolio_top_strategy_by_weight", "")
                ),
                "strategy_portfolio_top_market_by_weight": _identity_key(
                    dispatch_summary.get("strategy_portfolio_top_market_by_weight", "")
                ),
                "strategy_portfolio_max_strategy_allocation_weight": _number(
                    dispatch_summary, "strategy_portfolio_max_strategy_allocation_weight", 0.0
                ),
                "strategy_portfolio_max_market_allocation_weight": _number(
                    dispatch_summary, "strategy_portfolio_max_market_allocation_weight", 0.0
                ),
                "pre_portfolio_max_notional_per_session": _number(
                    dispatch_summary, "pre_portfolio_max_notional_per_session", 0.0
                ),
                "route_readiness_required": _route_readiness_required(thresholds, dispatch_summary),
                "route_readiness_provided": _to_bool(dispatch_summary.get("route_readiness_provided", False)),
                "route_readiness_ready": _to_bool(dispatch_summary.get("route_readiness_ready", False)),
                "route_readiness_strategy": _identity_key(dispatch_summary.get("route_readiness_strategy", "")),
                "route_readiness_market": _identity_key(dispatch_summary.get("route_readiness_market", "")),
                "route_readiness_route_ready_pairs": int(
                    _number(dispatch_summary, "route_readiness_route_ready_pairs", 0.0)
                ),
                "route_readiness_gap_pairs": int(_number(dispatch_summary, "route_readiness_gap_pairs", 0.0)),
                "route_readiness_recommendation": _text(dispatch_summary, "route_readiness_recommendation"),
                "route_readiness_ops_launch_controls_present": _to_bool(
                    dispatch_summary.get("route_readiness_ops_launch_controls_present", False)
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": int(
                    _number(dispatch_summary, "route_readiness_ops_launch_controls_blocked_pairs", 0.0)
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    _number(dispatch_summary, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0)
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    _number(
                        dispatch_summary,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                        0.0,
                    )
                ),
                **_route_broker_route_readiness_summary_fields(dispatch_summary),
                **_resume_route_readiness_summary_fields(
                    dispatch_summary,
                    prefix="route_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_summary_fields(
                    dispatch_summary,
                    prefix="route_broker_resume_incident_broker_route_readiness",
                ),
                "shadow_broker_readiness_sessions": int(
                    _number(dispatch_summary, "shadow_broker_readiness_sessions", 0.0)
                ),
                "shadow_broker_readiness_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_sessions": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    _number(dispatch_summary, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)
                ),
                "shadow_broker_adapter": _identity_key(dispatch_summary.get("shadow_broker_adapter", "")),
                "shadow_broker_adapter_count": int(_number(dispatch_summary, "shadow_broker_adapter_count", 0.0)),
                "shadow_broker_route_readiness_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_readiness_sessions", 0.0)
                ),
                "shadow_broker_route_readiness_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_route_readiness_strategy": _identity_key(
                    dispatch_summary.get("shadow_broker_route_readiness_strategy", "")
                ),
                "shadow_broker_route_readiness_market": _identity_key(
                    dispatch_summary.get("shadow_broker_route_readiness_market", "")
                ),
                "shadow_broker_route_readiness_gap_pairs": int(
                    _number(dispatch_summary, "shadow_broker_route_readiness_gap_pairs", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_sessions", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("shadow_broker_dispatch_roundtrip_strategy", "")
                ),
                "shadow_broker_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("shadow_broker_dispatch_roundtrip_market", "")
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_summary, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    _number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_strategy", "")
                ),
                "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("shadow_broker_route_dispatch_roundtrip_market", "")
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    _number(dispatch_summary, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)
                ),
                **_prefixed_shadow_broker_summary_fields(
                    dispatch_summary,
                    field_prefix="route_broker_shadow_broker",
                ),
                **_broker_vendor_data_readiness_summary_fields(
                    dispatch_summary,
                    field_prefix="dispatch_broker_vendor_data_readiness",
                ),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_summary,
                    field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
                ),
                **_broker_vendor_market_data_batch_lineage_summary_fields(
                    dispatch_summary
                ),
                **_broker_vendor_final_lineage_summary_fields(dispatch_summary),
                **_broker_vendor_complete_final_lineage_summary_fields(
                    dispatch_summary
                ),
                **_broker_vendor_extended_complete_final_lineage_summary_fields(
                    dispatch_summary
                ),
                **_broker_vendor_extended_complete_final_lineage_38_summary_fields(
                    dispatch_summary
                ),
                **_broker_vendor_latest_extended_complete_final_lineage_46_summary_fields(
                    dispatch_summary
                ),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_summary,
                    field_prefix="dispatch_vendor_market_data_batch",
                ),
                "route_dispatch_roundtrip_required": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_required", False)
                ),
                "route_dispatch_roundtrip_provided": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_provided", False)
                ),
                "route_dispatch_roundtrip_ready": _to_bool(
                    dispatch_summary.get("route_dispatch_roundtrip_ready", False)
                ),
                "route_dispatch_roundtrip_target_mode": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_target_mode", "")
                ),
                "route_dispatch_roundtrip_strategy": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_strategy", "")
                ),
                "route_dispatch_roundtrip_market": _identity_key(
                    dispatch_summary.get("route_dispatch_roundtrip_market", "")
                ),
                "route_dispatch_roundtrip_scenario_key": _text(
                    dispatch_summary, "route_dispatch_roundtrip_scenario_key"
                ),
                "route_dispatch_roundtrip_batch_id": _text(
                    dispatch_summary, "route_dispatch_roundtrip_batch_id"
                ),
                "route_dispatch_roundtrip_requests": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_requests", 0.0)
                ),
                "route_dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_acked_orders", 0.0)
                ),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "route_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "route_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_summary, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    _number(dispatch_summary, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
                ),
                "dry_run_only": bool(requests["dry_run_only"].astype(bool).all()) if not requests.empty else False,
                "submission_enabled": False,
                "failed_checks": failed,
                "recommendation": "ready_for_non_submitting_broker_sender_review"
                if ready
                else "keep_broker_sender_disabled",
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


def _route_broker_route_readiness_summary_fields(dispatch_summary: pd.Series) -> dict[str, object]:
    return {
        "route_broker_route_readiness_required": _to_bool(
            dispatch_summary.get("route_broker_route_readiness_required", False)
        ),
        "route_broker_route_readiness_provided": _to_bool(
            dispatch_summary.get("route_broker_route_readiness_provided", False)
        ),
        "route_broker_route_readiness_ready": _to_bool(
            dispatch_summary.get("route_broker_route_readiness_ready", False)
        ),
        "route_broker_route_readiness_strategy": _identity_key(
            dispatch_summary.get("route_broker_route_readiness_strategy", "")
        ),
        "route_broker_route_readiness_market": _identity_key(
            dispatch_summary.get("route_broker_route_readiness_market", "")
        ),
        "route_broker_route_readiness_route_ready_pairs": int(
            _number(dispatch_summary, "route_broker_route_readiness_route_ready_pairs", 0.0)
        ),
        "route_broker_route_readiness_gap_pairs": int(
            _number(dispatch_summary, "route_broker_route_readiness_gap_pairs", 0.0)
        ),
        "route_broker_route_readiness_recommendation": _text(
            dispatch_summary, "route_broker_route_readiness_recommendation"
        ),
        "route_broker_route_readiness_ops_launch_controls_ready": _to_bool(
            dispatch_summary.get("route_broker_route_readiness_ops_launch_controls_ready", False)
        ),
        "route_broker_route_readiness_ops_launch_control_failures": _text(
            dispatch_summary, "route_broker_route_readiness_ops_launch_control_failures"
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(dispatch_summary, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(dispatch_summary, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(
                dispatch_summary,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(
                dispatch_summary,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        ),
    }


def _resume_route_readiness_summary_fields(dispatch_summary: pd.Series, *, prefix: str) -> dict[str, object]:
    return {
        f"{prefix}_required": _to_bool(dispatch_summary.get(f"{prefix}_required", False)),
        f"{prefix}_provided": _to_bool(dispatch_summary.get(f"{prefix}_provided", False)),
        f"{prefix}_ready": _to_bool(dispatch_summary.get(f"{prefix}_ready", False)),
        f"{prefix}_strategy": _identity_key(dispatch_summary.get(f"{prefix}_strategy", "")),
        f"{prefix}_market": _identity_key(dispatch_summary.get(f"{prefix}_market", "")),
        f"{prefix}_route_ready_pairs": int(_number(dispatch_summary, f"{prefix}_route_ready_pairs", 0.0)),
        f"{prefix}_gap_pairs": int(_number(dispatch_summary, f"{prefix}_gap_pairs", 0.0)),
        f"{prefix}_recommendation": _text(dispatch_summary, f"{prefix}_recommendation"),
        f"{prefix}_ops_launch_controls_ready": _to_bool(
            dispatch_summary.get(f"{prefix}_ops_launch_controls_ready", False)
        ),
        f"{prefix}_ops_launch_control_failures": _text(
            dispatch_summary, f"{prefix}_ops_launch_control_failures"
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(dispatch_summary, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(
                dispatch_summary,
                f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(
                dispatch_summary,
                f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        ),
    }


def _action_queue(summary: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _object_text(row.get("check")).strip()
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "broker_dispatch_send_checks",
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
    if check.startswith("broker_dispatch_lineage_") or check.startswith(
        ("broker_dispatch_manifest_", "broker_dispatch_non_authorizing", "broker_dispatch_route_enable_")
    ):
        return "broker_dispatch_plan"
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
    if "dispatch_roundtrip" in check or "route_roundtrip" in check:
        return "broker_dispatch_roundtrip"
    if check.startswith("dispatch_broker_shadow_broker") or check.startswith("dispatch_shadow_broker"):
        return "broker_readiness"
    if check in {
        "dispatch_ready",
        "dispatch_armed_dry_run",
        "target_mode_matches",
        "request_count_matches_dispatch",
        "dispatch_order_route_roundtrip_batch_matches",
    }:
        return "broker_dispatch_plan"
    if check in {
        "adapter_known",
        "request_count_within_limit",
        "dry_run_only",
        "submission_disabled",
        "unique_idempotency_key",
        "payloads_valid",
        "request_route_roundtrip_batch_matches",
    }:
        return "broker_dispatch_send"
    return "broker_dispatch_send"


def _next_gate(check: str) -> str:
    component = _component(check)
    if component == "broker_dispatch_plan":
        return "plan-broker-dispatch"
    if component == "strategy_portfolio":
        return "review-cutover-gate"
    if component == "resume_gate":
        return "review-resume-gate"
    if component == "route_readiness":
        return "review-route-readiness"
    if component == "broker_dispatch_roundtrip":
        return "review-broker-dispatch-roundtrip"
    if component == "vendor_market_data":
        return "pipeline-vendor-market-data-batch"
    if component == "broker_vendor_data_readiness":
        return "pipeline-broker-vendor-readiness"
    if component == "broker_readiness":
        return "review-broker-readiness"
    return "prepare-broker-dispatch-send"


def _action_recommendation(check: str) -> str:
    component = _component(check)
    if component == "broker_dispatch_plan":
        return "repair_or_rebuild_broker_dispatch_plan"
    if component == "strategy_portfolio":
        return "repair_strategy_portfolio_cutover_allocation"
    if component == "resume_gate":
        return "repair_broker_resume_route_readiness_before_sender_packet"
    if component == "route_readiness":
        return "rerun_route_readiness_before_sender_packet"
    if component == "broker_dispatch_roundtrip":
        return "rerun_broker_dispatch_roundtrip_before_sender_packet"
    if component == "vendor_market_data":
        return "refresh_vendor_market_data_batch_proof"
    if component == "broker_vendor_data_readiness":
        return "refresh_broker_vendor_data_readiness_wrapper"
    if component == "broker_readiness":
        return "repair_broker_readiness_shadow_proof"
    if check == "adapter_known":
        return "configure_supported_broker_adapter"
    if check == "payloads_valid":
        return "repair_dispatch_order_payload_json"
    if check == "unique_idempotency_key":
        return "rebuild_sender_packet_with_unique_idempotency_keys"
    if check == "request_count_within_limit":
        return "reduce_sender_request_batch_or_raise_limit"
    if check in {"dry_run_only", "submission_disabled"}:
        return "keep_sender_packet_non_submitting"
    return "repair_broker_dispatch_send_inputs"


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


def _vendor_market_data_batch_summary_fields(dispatch_summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        f"{field_prefix}_provided": _to_bool(dispatch_summary.get(f"{field_prefix}_provided", False)),
        f"{field_prefix}_ready": _to_bool(dispatch_summary.get(f"{field_prefix}_ready", False)),
        f"{field_prefix}_adapter": _identity_key(dispatch_summary.get(f"{field_prefix}_adapter", "")),
        f"{field_prefix}_kind": _text(dispatch_summary, f"{field_prefix}_kind"),
        f"{field_prefix}_manifest_run_type": _identity_key(
            dispatch_summary.get(f"{field_prefix}_manifest_run_type", "")
        ),
        f"{field_prefix}_market": _identity_key(dispatch_summary.get(f"{field_prefix}_market", "")),
        f"{field_prefix}_dataset_count": int(_number(dispatch_summary, f"{field_prefix}_dataset_count", 0.0)),
        f"{field_prefix}_ready_datasets": int(_number(dispatch_summary, f"{field_prefix}_ready_datasets", 0.0)),
        f"{field_prefix}_failed_datasets": int(_number(dispatch_summary, f"{field_prefix}_failed_datasets", 0.0)),
        f"{field_prefix}_ready_rate": _number(dispatch_summary, f"{field_prefix}_ready_rate", 0.0),
        f"{field_prefix}_unique_source_files": int(
            _number(dispatch_summary, f"{field_prefix}_unique_source_files", 0.0)
        ),
        f"{field_prefix}_unique_header_fingerprints": int(
            _number(dispatch_summary, f"{field_prefix}_unique_header_fingerprints", 0.0)
        ),
        f"{field_prefix}_source_file_fingerprint_coverage": _number(
            dispatch_summary, f"{field_prefix}_source_file_fingerprint_coverage", 0.0
        ),
        f"{field_prefix}_min_mapping_coverage": _number(
            dispatch_summary, f"{field_prefix}_min_mapping_coverage", 0.0
        ),
        f"{field_prefix}_unique_mapping_drafts": int(
            _number(dispatch_summary, f"{field_prefix}_unique_mapping_drafts", 0.0)
        ),
        f"{field_prefix}_mapping_sources": _text(dispatch_summary, f"{field_prefix}_mapping_sources"),
        f"{field_prefix}_mapping_source_mode": _identity_key(
            dispatch_summary.get(f"{field_prefix}_mapping_source_mode", "")
        ),
        f"{field_prefix}_mapping_application_count": int(
            _number(dispatch_summary, f"{field_prefix}_mapping_application_count", 0.0)
        ),
        f"{field_prefix}_unique_mapping_applications": int(
            _number(dispatch_summary, f"{field_prefix}_unique_mapping_applications", 0.0)
        ),
        f"{field_prefix}_target_application_coverage": _number(
            dispatch_summary, f"{field_prefix}_target_application_coverage", 0.0
        ),
        f"{field_prefix}_application_lineage_consistency_required": _to_bool(
            dispatch_summary.get(
                f"{field_prefix}_application_lineage_consistency_required",
                False,
            )
        ),
        f"{field_prefix}_application_lineage_consistent": _to_bool(
            dispatch_summary.get(f"{field_prefix}_application_lineage_consistent", False)
        ),
        f"{field_prefix}_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(f"{field_prefix}_application_lineage_sha256", "")
        ),
        f"{field_prefix}_comparison_accepted": _to_bool(
            dispatch_summary.get(f"{field_prefix}_comparison_accepted", False)
        ),
        f"{field_prefix}_comparison_failed_checks": int(
            _number(dispatch_summary, f"{field_prefix}_comparison_failed_checks", 0.0)
        ),
        f"{field_prefix}_datasets_json": _text(dispatch_summary, f"{field_prefix}_datasets_json"),
    }


def _broker_vendor_market_data_batch_lineage_summary_fields(
    dispatch_summary: pd.Series,
) -> dict[str, object]:
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "dispatch_broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            dispatch_summary.get(
                "dispatch_broker_vendor_market_data_batch_lineage_match_required",
                False,
            )
        ),
        "dispatch_broker_vendor_market_data_batch_lineage_matches": _to_bool(
            dispatch_summary.get(
                "dispatch_broker_vendor_market_data_batch_lineage_matches",
                False,
            )
        ),
        "dispatch_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                "dispatch_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        ),
        "dispatch_broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                "dispatch_broker_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        ),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                dispatch_summary.get(
                    "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                    "",
                )
            )
        ),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                dispatch_summary.get(
                    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                    "",
                )
            )
        ),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                dispatch_summary.get(
                    "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                    "",
                )
            )
        ),
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _target_application_lineage_sha256(
                dispatch_summary,
                prefix=prefix,
            )
        ),
    }


def _broker_vendor_final_lineage_summary_fields(
    dispatch_summary: pd.Series,
) -> dict[str, object]:
    source_prefix = DISPATCH_FINAL_LINEAGE_FIELD_PREFIX
    field_prefix = DISPATCH_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{field_prefix}_lineage_match_required": _to_bool(
            dispatch_summary.get(
                f"{source_prefix}_lineage_match_required",
                False,
            )
        ),
        f"{field_prefix}_lineage_matches": _to_bool(
            dispatch_summary.get(f"{source_prefix}_lineage_matches", False)
        ),
        f"{field_prefix}_dispatch_plan_review_carried_application_lineage_sha256": (
            _sha256_text(
                dispatch_summary.get(
                    f"{source_prefix}_carried_application_lineage_sha256",
                    "",
                )
            )
        ),
    }
    for field in DISPATCH_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{field_prefix}_{field}"] = _sha256_text(
            dispatch_summary.get(f"{source_prefix}_{field}", "")
        )
    return fields


def _broker_vendor_complete_final_lineage_summary_fields(
    dispatch_summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_match_required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_matches", False)
        ),
        f"{prefix}_dispatch_final_review_carried_application_lineage_sha256": (
            _sha256_text(
                dispatch_summary.get(
                    f"{prefix}_carried_application_lineage_sha256",
                    "",
                )
            )
        ),
    }
    for field in DISPATCH_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            dispatch_summary.get(f"{prefix}_{field}", "")
        )
    return fields


def _broker_vendor_extended_complete_final_lineage_summary_fields(
    dispatch_summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    send_lineage_sha256 = _target_application_lineage_sha256(
        dispatch_summary,
        prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_match_required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_matches", False)
        ),
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_route_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_route_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_dispatch_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_send_complete_final_review_carried_application_lineage_sha256": send_lineage_sha256,
    }
    for field in DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            dispatch_summary.get(f"{prefix}_{field}", "")
        )
    return fields


def _broker_vendor_extended_complete_final_lineage_38_summary_fields(
    dispatch_summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_FIELD_PREFIX
    send_lineage_sha256 = _target_application_lineage_sha256(
        dispatch_summary,
        prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_match_required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_matches", False)
        ),
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_route_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_route_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_dispatch_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_send_extended_complete_final_review_carried_application_lineage_sha256": send_lineage_sha256,
    }
    for field in DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            dispatch_summary.get(f"{prefix}_{field}", "")
        )
    return fields


def _broker_vendor_latest_extended_complete_final_lineage_46_summary_fields(
    dispatch_summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_FIELD_PREFIX
    send_lineage_sha256 = _target_application_lineage_sha256(
        dispatch_summary,
        prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_match_required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            dispatch_summary.get(f"{prefix}_lineage_matches", False)
        ),
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            dispatch_summary.get(
                f"{prefix}_carried_application_lineage_sha256",
                "",
            )
        ),
        f"{prefix}_send_latest_extended_complete_final_review_carried_application_lineage_sha256": send_lineage_sha256,
    }
    for field in DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            dispatch_summary.get(f"{prefix}_{field}", "")
        )
    return fields


def _broker_vendor_data_readiness_summary_fields(
    dispatch_summary: pd.Series,
    *,
    field_prefix: str,
) -> dict[str, object]:
    return {
        f"{field_prefix}_provided": _to_bool(dispatch_summary.get(f"{field_prefix}_provided", False)),
        f"{field_prefix}_ready": _to_bool(dispatch_summary.get(f"{field_prefix}_ready", False)),
        f"{field_prefix}_failed_checks": int(
            _number(dispatch_summary, f"{field_prefix}_failed_checks", 0.0)
        ),
    }


def _vendor_market_data_batch_config(summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
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
        "unique_header_fingerprints": int(summary[f"{field_prefix}_unique_header_fingerprints"]),
        "source_file_fingerprint_coverage": _jsonable(
            summary[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(summary[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(summary[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": _text(summary, f"{field_prefix}_mapping_sources"),
        "mapping_source_mode": _text(summary, f"{field_prefix}_mapping_source_mode"),
        "mapping_application_count": int(summary[f"{field_prefix}_mapping_application_count"]),
        "unique_mapping_applications": int(
            summary[f"{field_prefix}_unique_mapping_applications"]
        ),
        "target_application_coverage": _jsonable(
            summary[f"{field_prefix}_target_application_coverage"]
        ),
        "application_lineage_consistency_required": _to_bool(
            summary[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        "application_lineage_consistent": _to_bool(
            summary[f"{field_prefix}_application_lineage_consistent"]
        ),
        "application_lineage_sha256": _text(
            summary,
            f"{field_prefix}_application_lineage_sha256",
        ),
        "comparison": {
            "accepted": _to_bool(summary[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(summary[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(summary[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_send_final_lineage_config(
    summary: pd.Series,
) -> dict[str, object]:
    field_prefix = DISPATCH_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(summary[f"{field_prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{field_prefix}_lineage_matches"]),
        "dispatch_plan_review_carried_application_lineage_sha256": _text(
            summary,
            f"{field_prefix}_dispatch_plan_review_carried_application_lineage_sha256",
        ),
        "carried_application_lineage_sha256": _text(
            summary,
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ),
    }
    for field in DISPATCH_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = _text(summary, f"{field_prefix}_{field}")
    return config


def _broker_vendor_send_complete_final_lineage_config(
    summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(summary[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{prefix}_lineage_matches"]),
        "dispatch_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_dispatch_final_review_carried_application_lineage_sha256",
        ),
        "carried_application_lineage_sha256": _text(
            summary,
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ),
    }
    for field in DISPATCH_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = _text(summary, f"{prefix}_{field}")
    return config


def _broker_vendor_send_extended_complete_final_lineage_config(
    summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(summary[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{prefix}_lineage_matches"]),
        "scaleup_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
        ),
        "cutover_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256",
        ),
        "route_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_route_complete_final_review_carried_application_lineage_sha256",
        ),
        "dispatch_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_dispatch_complete_final_review_carried_application_lineage_sha256",
        ),
        "carried_application_lineage_sha256": _text(
            summary,
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ),
    }
    for field in DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = _text(summary, f"{prefix}_{field}")
    return config


def _broker_vendor_send_extended_complete_final_lineage_39_config(
    summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(summary[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{prefix}_lineage_matches"]),
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "cutover_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "route_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_route_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_dispatch_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "carried_application_lineage_sha256": _text(
            summary,
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ),
    }
    for field in DISPATCH_EXTENDED_COMPLETE_FINAL_LINEAGE_38_DIGEST_FIELDS:
        config[field] = _text(summary, f"{prefix}_{field}")
    return config


def _broker_vendor_send_latest_extended_complete_final_lineage_47_config(
    summary: pd.Series,
) -> dict[str, object]:
    prefix = DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(summary[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(summary[f"{prefix}_lineage_matches"]),
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "route_latest_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256": _text(
            summary,
            f"{prefix}_dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ),
        "carried_application_lineage_sha256": _text(
            summary,
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ),
    }
    for field in DISPATCH_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_46_DIGEST_FIELDS:
        config[field] = _text(summary, f"{prefix}_{field}")
    return config


def _broker_vendor_data_readiness_config(summary: pd.Series, *, field_prefix: str) -> dict[str, object]:
    return {
        "provided": _to_bool(summary[f"{field_prefix}_provided"]),
        "ready": _to_bool(summary[f"{field_prefix}_ready"]),
        "failed_checks": int(summary[f"{field_prefix}_failed_checks"]),
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


def _broker_dispatch_lineage_output_fields(row: pd.Series) -> dict[str, Any]:
    defaults = broker_dispatch_lineage_fields(empty_broker_dispatch_lineage())
    return {
        column: row.get(column, default)
        for column, default in defaults.items()
    }


def _broker_dispatch_lineage_config(summary: pd.Series) -> dict[str, Any]:
    return {
        column: _jsonable_check_value(summary[column])
        for column in BROKER_DISPATCH_LINEAGE_OUTPUT_COLUMNS
    }


def _config(
    summary: pd.Series,
    requests: pd.DataFrame,
    thresholds: BrokerDispatchSendThresholds,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "ready": _to_bool(summary["ready"]),
        "failed_check_count": len(failed_check_records),
        "request_state": _text(summary, "request_state"),
        "submission_enabled": False,
        "transport": "file_packet",
        "target_mode": _text(summary, "target_mode"),
        "strategy": _text(summary, "strategy"),
        "market": _text(summary, "market"),
        "scenario_key": _text(summary, "scenario_key"),
        "adapter": _text(summary, "adapter"),
        "broker_readiness": {
            "adapter_schema_status": _text(summary, "broker_schema_status"),
            "schema_reviewed": _to_bool(summary["broker_schema_reviewed"]),
            "schema_review_mode": _text(summary, "broker_schema_review_mode"),
        },
        "dispatch_batch_id": _text(summary, "dispatch_batch_id"),
        "dispatch_total_notional": float(summary["dispatch_total_notional"]),
        "requests": int(summary["requests"]),
        "first_request_id": str(requests.iloc[0]["request_id"]) if not requests.empty else "",
        "last_request_id": str(requests.iloc[-1]["request_id"]) if not requests.empty else "",
        "broker_dispatch_lineage": _broker_dispatch_lineage_config(summary),
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
        "shadow_broker_readiness": {
            "provided": int(summary["shadow_broker_readiness_sessions"]) > 0,
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
        "route_broker_shadow_broker_readiness": _prefixed_shadow_broker_config(
            summary,
            field_prefix="route_broker_shadow_broker",
        ),
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
        "dispatch_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(
            summary,
            field_prefix="dispatch_broker_vendor_data_readiness",
        ),
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            summary,
            field_prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": {
            "required": _to_bool(
                summary[
                    "dispatch_broker_vendor_market_data_batch_lineage_match_required"
                ]
            ),
            "matches": _to_bool(
                summary["dispatch_broker_vendor_market_data_batch_lineage_matches"]
            ),
            "current_application_lineage_sha256": _text(
                summary,
                "dispatch_vendor_market_data_batch_application_lineage_sha256",
            ),
            "broker_application_lineage_sha256": _text(
                summary,
                "dispatch_broker_vendor_market_data_batch_application_lineage_sha256",
            ),
            "scaleup_carried_application_lineage_sha256": _text(
                summary,
                "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ),
            "cutover_carried_application_lineage_sha256": _text(
                summary,
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ),
            "route_carried_application_lineage_sha256": _text(
                summary,
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ),
            "dispatch_carried_application_lineage_sha256": _text(
                summary,
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ),
            "send_carried_application_lineage_sha256": _text(
                summary,
                "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ),
        },
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
            _broker_vendor_send_final_lineage_config(summary)
        ),
        SEND_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_send_complete_final_lineage_config(summary)
        ),
        SEND_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_send_extended_complete_final_lineage_config(summary)
        ),
        SEND_EXTENDED_COMPLETE_FINAL_LINEAGE_39_COMPARISON_KEY: (
            _broker_vendor_send_extended_complete_final_lineage_39_config(
                summary
            )
        ),
        SEND_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_47_COMPARISON_KEY: (
            _broker_vendor_send_latest_extended_complete_final_lineage_47_config(
                summary
            )
        ),
        "dispatch_vendor_market_data_batch": _vendor_market_data_batch_config(
            summary,
            field_prefix="dispatch_vendor_market_data_batch",
        ),
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
    return [_jsonable_row(row) for row in failed.to_dict(orient="records")]


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Broker Dispatch Send Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Request state: {_object_text(summary_row.get('request_state')).strip()}",
        f"- Target mode: {_object_text(summary_row.get('target_mode')).strip()}",
        f"- Strategy: {_object_text(summary_row.get('strategy')).strip()}",
        f"- Market: {_object_text(summary_row.get('market')).strip()}",
        f"- Scenario: {_object_text(summary_row.get('scenario_key')).strip()}",
        f"- Adapter: {_object_text(summary_row.get('adapter')).strip()}",
        f"- Dispatch batch: {_object_text(summary_row.get('dispatch_batch_id')).strip()}",
        f"- Requests: {_int_value(summary_row.get('requests'))}",
        f"- Submission enabled: {_object_text(summary_row.get('submission_enabled')).strip()}",
        "- Broker-dispatch lineage current: "
        f"{'yes' if _to_bool(summary_row.get('broker_dispatch_lineage_gate_passed')) else 'no'}",
        f"- Route readiness ready: {_object_text(summary_row.get('route_readiness_ready')).strip()}",
        f"- Resume broker route ready: {_object_text(summary_row.get('route_broker_resume_broker_route_readiness_ready')).strip()}",
        f"- Resume incident route ready: {_object_text(summary_row.get('route_broker_resume_incident_broker_route_readiness_ready')).strip()}",
        f"- Route dispatch round-trip ready: {_object_text(summary_row.get('route_dispatch_roundtrip_ready')).strip()}",
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
        return "No broker dispatch send actions."
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


def _jsonable_check_record(record: dict[str, object]) -> dict[str, object]:
    return {str(key): _jsonable_check_value(value) for key, value in record.items()}


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


def _order_payload(order: pd.Series) -> tuple[dict[str, Any], str]:
    raw = _text(order, "order_payload_json")
    if not raw:
        return {}, "missing order_payload_json"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"invalid order_payload_json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "order_payload_json is not an object"
    return _jsonable_row(payload), ""


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required broker dispatch send input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required broker dispatch send input is empty: {name}")
    return frame


def _reject_input_output_collision(
    output_dir: Path,
    inputs: dict[str, Path],
) -> None:
    for label, value in inputs.items():
        path = Path(value).resolve()
        root = path if path.is_dir() else path.parent
        if output_dir == root or root in output_dir.parents or output_dir in root.parents:
            raise ValueError(
                f"broker-dispatch-send output_dir must not overwrite the {label} source directory"
            )


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: BrokerDispatchSendThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: BrokerDispatchSendThresholds, dispatch_summary: pd.Series | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (
            dispatch_summary is not None
            and _to_bool(dispatch_summary.get("route_readiness_required", False))
        )
    )


def _strategy_portfolio_active(dispatch_summary: pd.Series) -> bool:
    return bool(
        _to_bool(dispatch_summary.get("strategy_portfolio_required", False))
        or _to_bool(dispatch_summary.get("strategy_portfolio_provided", False))
    )


def _validate_thresholds(thresholds: BrokerDispatchSendThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_requests is not None and thresholds.max_requests <= 0:
        raise ValueError("max_requests must be positive")


def _adapter_known(adapter: str) -> bool:
    try:
        get_adapter(adapter)
    except ValueError:
        return False
    return True


def _first_order_text(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = frame[column].dropna().astype(str).str.strip()
    values = values.loc[values != ""]
    return str(values.iloc[0]) if not values.empty else ""


def _unique_text_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).str.strip()
    return sorted(set(values.loc[values != ""]))


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


def _text(row: pd.Series, column: str) -> str:
    if row.empty or column not in row.index:
        return ""
    value = row[column]
    if pd.isna(value):
        return ""
    return str(value).strip()


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
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed", "armed", "accepted"}
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


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in row.items()}


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
                "mapping_application_path": _object_text(item.get("mapping_application_path", "")),
                "mapping_application_id": _object_text(item.get("mapping_application_id", "")),
                "mapping_application_sha256": _object_text(
                    item.get("mapping_application_sha256", "")
                ),
                "mapping_scope_review_id": _object_text(item.get("mapping_scope_review_id", "")),
                "mapping_scope_review_sha256": _object_text(
                    item.get("mapping_scope_review_sha256", "")
                ),
                "target_intake_receipt_id": _object_text(item.get("target_intake_receipt_id", "")),
                "applied_mapping_sha256": _object_text(item.get("applied_mapping_sha256", "")),
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
