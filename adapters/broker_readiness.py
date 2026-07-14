from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from adapters.broker import adapter_schema_status, get_adapter
from reports.manifest import write_experiment_manifest
from reports.vendor_market_data import select_vendor_market_data_batch_source


SUMMARY_FILES = {
    "schema_audit": "adapter_schema_summary.csv",
    "order_export": "broker_order_summary.csv",
    "mapping_draft": "order_mapping_draft_summary.csv",
    "mapped_orders": "mapped_order_summary.csv",
    "upload_pack": "broker_upload_summary.csv",
    "halt_export": "halt_response_export_summary.csv",
    "reconciliation": "reconciliation_summary.csv",
    "runtime_session": "runtime_session_summary.csv",
    "resume_gate": "resume_summary.csv",
    "dispatch_roundtrip": "broker_dispatch_roundtrip_summary.csv",
}
SCHEMA_REVIEW_CHECKLIST_FILE = "adapter_schema_review_checklist.csv"
BROKER_READINESS_NEXT_GATES = {
    "schema_audit": "audit-adapter-schema",
    "order_export": "export-launch-orders",
    "mapping_draft": "draft-order-mapping",
    "mapped_orders": "map-broker-orders",
    "upload_pack": "pack-broker-upload",
    "halt_export": "export-halt-response",
    "reconciliation": "reconcile-broker-fills",
    "runtime_session": "monitor-runtime-session",
    "resume_gate": "review-resume-gate",
    "dispatch_roundtrip": "review-broker-dispatch-roundtrip",
    "route_readiness": "review-route-readiness",
    "route_enable": "review-route-enable",
    "broker_dispatch": "plan-broker-dispatch",
    "dispatch_send": "prepare-broker-dispatch-send",
    "dispatch_ack": "reconcile-broker-dispatch",
    "vendor_market_data": "pipeline-broker-vendor-readiness",
    "broker_readiness": "review-broker-readiness",
}

SUMMARY_FALLBACK_DIRS = {
    "order_export": ("04_export", "03_export"),
    "upload_pack": ("05_upload_pack", "04_upload_pack"),
}
TARGET_APPLICATION_BATCH_MODE = "per_dataset_verified_target_application"


@dataclass(frozen=True)
class BrokerReadinessThresholds:
    adapter: str = "arrow_money"
    expected_market: str = ""
    expected_vendor_data_kind: str = ""
    require_reviewed_schema: bool = True
    require_schema_audit: bool = True
    require_order_export: bool = True
    require_mapping_draft: bool = False
    require_mapped_orders: bool = False
    require_upload_pack: bool = True
    require_halt_export: bool = False
    require_reconciliation: bool = False
    require_runtime_session: bool = False
    require_resume_gate: bool = False
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    require_adapter_match: bool = True


@dataclass(frozen=True)
class BrokerReadinessReport:
    items: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None
    config: dict[str, Any] | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_broker_readiness(
    *,
    schema_audit_summary: pd.DataFrame | None = None,
    schema_review_checklist: pd.DataFrame | None = None,
    order_export_summary: pd.DataFrame | None = None,
    mapping_draft_summary: pd.DataFrame | None = None,
    mapped_order_summary: pd.DataFrame | None = None,
    upload_pack_summary: pd.DataFrame | None = None,
    halt_export_summary: pd.DataFrame | None = None,
    reconciliation_summary: pd.DataFrame | None = None,
    runtime_session_summary: pd.DataFrame | None = None,
    resume_summary: pd.DataFrame | None = None,
    dispatch_roundtrip_summary: pd.DataFrame | None = None,
    dispatch_roundtrip_config: dict[str, Any] | None = None,
    thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerReadinessReport:
    thresholds = thresholds or BrokerReadinessThresholds()
    _validate_thresholds(thresholds)
    dispatch_roundtrip = _dispatch_roundtrip_frame(
        dispatch_roundtrip_summary,
        dispatch_roundtrip_config or {},
    )
    summaries = {
        "schema_audit": _optional_frame(schema_audit_summary),
        "order_export": _optional_frame(order_export_summary),
        "mapping_draft": _optional_frame(mapping_draft_summary),
        "mapped_orders": _optional_frame(mapped_order_summary),
        "upload_pack": _optional_frame(upload_pack_summary),
        "halt_export": _optional_frame(halt_export_summary),
        "reconciliation": _optional_frame(reconciliation_summary),
        "runtime_session": _optional_frame(runtime_session_summary),
        "resume_gate": _optional_frame(resume_summary),
        "dispatch_roundtrip": dispatch_roundtrip,
    }
    items = _items(summaries, thresholds, schema_review_checklist=schema_review_checklist)
    checks = _checks(items, thresholds)
    summary = _summary(items, checks, thresholds)
    action_queue = _action_queue(checks)
    config = _config(items, checks, summary, action_queue, thresholds)
    return BrokerReadinessReport(
        items=items,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_broker_readiness_report(
    *,
    output_dir: str | Path,
    schema_audit_dir: str | Path | None = None,
    order_export_dir: str | Path | None = None,
    mapping_draft_dir: str | Path | None = None,
    mapped_orders_dir: str | Path | None = None,
    upload_pack_dir: str | Path | None = None,
    halt_export_dir: str | Path | None = None,
    reconciliation_dir: str | Path | None = None,
    runtime_session_dir: str | Path | None = None,
    resume_dir: str | Path | None = None,
    dispatch_roundtrip_dir: str | Path | None = None,
    vendor_market_data_batch_dir: str | Path | None = None,
    thresholds: BrokerReadinessThresholds | None = None,
) -> BrokerReadinessReport:
    thresholds = thresholds or BrokerReadinessThresholds()
    _validate_thresholds(thresholds)
    vendor_market_data_batch_root_dir = vendor_market_data_batch_dir
    broker_vendor_data_readiness_config_path = _manifest_config_input(
        vendor_market_data_batch_root_dir,
        "broker_vendor_data_readiness_config.json",
    )
    broker_vendor_data_readiness_config = _read_optional_config(
        vendor_market_data_batch_root_dir,
        "broker_vendor_data_readiness_config.json",
    )
    vendor_market_data_batch_dir = _resolve_vendor_market_data_batch_dir(vendor_market_data_batch_dir)
    dispatch_roundtrip_config_path = _manifest_config_input(
        dispatch_roundtrip_dir,
        "broker_dispatch_roundtrip_config.json",
    )
    dispatch_roundtrip_manifest_path = _manifest_config_input(
        dispatch_roundtrip_dir,
        "manifest.json",
    )
    vendor_market_data_batch_config_path = _manifest_config_input(
        vendor_market_data_batch_dir,
        "vendor_market_data_batch_config.json",
    )
    vendor_market_data_batch_manifest_path = _manifest_config_input(
        vendor_market_data_batch_dir,
        "manifest.json",
    )
    schema_review_checklist_path = _manifest_config_input(
        schema_audit_dir,
        SCHEMA_REVIEW_CHECKLIST_FILE,
    )
    input_paths = {
        "schema_audit": _manifest_summary_input(schema_audit_dir, "schema_audit"),
        "order_export": _manifest_summary_input(order_export_dir, "order_export"),
        "mapping_draft": _manifest_summary_input(mapping_draft_dir, "mapping_draft"),
        "mapped_orders": _manifest_summary_input(mapped_orders_dir, "mapped_orders"),
        "upload_pack": _manifest_summary_input(upload_pack_dir, "upload_pack"),
        "halt_export": _manifest_summary_input(halt_export_dir, "halt_export"),
        "reconciliation": _manifest_summary_input(reconciliation_dir, "reconciliation"),
        "runtime_session": _manifest_summary_input(runtime_session_dir, "runtime_session"),
        "resume_gate": _manifest_summary_input(resume_dir, "resume_gate"),
        "dispatch_roundtrip": _manifest_summary_input(dispatch_roundtrip_dir, "dispatch_roundtrip"),
    }
    if dispatch_roundtrip_config_path is not None:
        input_paths["dispatch_roundtrip_config"] = dispatch_roundtrip_config_path
    if dispatch_roundtrip_manifest_path is not None:
        input_paths["dispatch_roundtrip_manifest"] = dispatch_roundtrip_manifest_path
    if vendor_market_data_batch_config_path is not None:
        input_paths["vendor_market_data_batch_config"] = vendor_market_data_batch_config_path
    if vendor_market_data_batch_manifest_path is not None:
        input_paths["vendor_market_data_batch_manifest"] = vendor_market_data_batch_manifest_path
    if schema_review_checklist_path is not None:
        input_paths["schema_review_checklist"] = schema_review_checklist_path
    if broker_vendor_data_readiness_config_path is not None:
        input_paths["broker_vendor_data_readiness_config"] = broker_vendor_data_readiness_config_path
    dispatch_roundtrip_config = _dispatch_roundtrip_config_with_vendor_market_data_batch(
        _read_optional_config(
            dispatch_roundtrip_dir,
            "broker_dispatch_roundtrip_config.json",
        ),
        _read_vendor_market_data_batch_config(
            vendor_market_data_batch_dir,
            "vendor_market_data_batch_config.json",
        ),
        broker_vendor_data_readiness_config,
    )
    report = evaluate_broker_readiness(
        schema_audit_summary=_read_optional_summary(schema_audit_dir, "schema_audit"),
        schema_review_checklist=_read_optional_schema_review_checklist(schema_audit_dir),
        order_export_summary=_read_optional_summary(order_export_dir, "order_export"),
        mapping_draft_summary=_read_optional_summary(mapping_draft_dir, "mapping_draft"),
        mapped_order_summary=_read_optional_summary(mapped_orders_dir, "mapped_orders"),
        upload_pack_summary=_read_optional_summary(upload_pack_dir, "upload_pack"),
        halt_export_summary=_read_optional_summary(halt_export_dir, "halt_export"),
        reconciliation_summary=_read_optional_summary(reconciliation_dir, "reconciliation"),
        runtime_session_summary=_read_optional_summary(runtime_session_dir, "runtime_session"),
        resume_summary=_read_optional_summary(resume_dir, "resume_gate"),
        dispatch_roundtrip_summary=_read_optional_summary(dispatch_roundtrip_dir, "dispatch_roundtrip"),
        dispatch_roundtrip_config=dispatch_roundtrip_config,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.items.to_csv(out / "broker_readiness_items.csv", index=False)
    report.checks.to_csv(out / "broker_readiness_checks.csv", index=False)
    report.summary.to_csv(out / "broker_readiness_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(report.checks)
    action_queue.to_csv(out / "broker_readiness_action_queue.csv", index=False)
    (out / "broker_readiness_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "broker_readiness_runbook.md").write_text(
        _runbook_markdown(report.summary, report.items, action_queue),
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="broker_readiness",
        parameters={"thresholds": asdict(thresholds)},
        inputs=input_paths,
    )
    return BrokerReadinessReport(
        items=report.items,
        checks=report.checks,
        summary=report.summary,
        output_dir=out,
        config=report.config,
        action_queue=action_queue,
    )


def _items(
    summaries: dict[str, pd.DataFrame],
    thresholds: BrokerReadinessThresholds,
    *,
    schema_review_checklist: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            _item(
                component,
                frame,
                thresholds,
                schema_review_checklist=schema_review_checklist if component == "schema_audit" else None,
            )
            for component, frame in summaries.items()
        ]
    )


def _dispatch_roundtrip_frame(summary: pd.DataFrame | None, config: dict[str, Any]) -> pd.DataFrame:
    frame = _optional_frame(summary)
    if frame.empty:
        vendor_market_data_batch = config.get("roundtrip_vendor_market_data_batch", {}) or {}
        broker_vendor_market_data_batch, _ = _broker_vendor_market_data_batch_config(config)
        broker_vendor_data_readiness, _ = _broker_vendor_data_readiness_config(config)
        if (
            not vendor_market_data_batch
            and not broker_vendor_market_data_batch
            and not broker_vendor_data_readiness
        ):
            return frame
        frame = pd.DataFrame([{"vendor_market_data_batch_only": True}])
    dispatch_config = config.get("dispatch_roundtrip", {}) or {}
    route_readiness = config.get("route_readiness", {}) or dispatch_config.get("route_readiness", {}) or {}
    if route_readiness:
        legacy_ops_columns = (
            "route_readiness_ops_launch_controls_ready",
            "route_readiness_ops_launch_control_failures",
            "route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            "route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
        )
        legacy_ops_present = any(
            key in route_readiness
            for key in (
                "ops_launch_controls_ready",
                "ops_controls_ready",
                "ops_launch_control_failures",
                "ops_control_failures",
                "ops_broker_roundtrip_portfolio_safe_runs",
                "ops_broker_roundtrip_portfolio_breach_runs",
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                "ops_broker_roundtrip_portfolio_concentration_breach_runs",
            )
        ) or any(
            _route_readiness_legacy_value_present(frame.iloc[0].get(column))
            for column in legacy_ops_columns
            if column in frame.columns
        )
        for text_column in (
            "route_readiness_strategy",
            "route_readiness_market",
            "route_readiness_recommendation",
            "route_readiness_ops_launch_control_failures",
        ):
            if text_column in frame.columns:
                frame[text_column] = frame[text_column].astype("object")
        frame.loc[0, "route_readiness_required"] = _to_bool(
            route_readiness.get("required", frame.iloc[0].get("route_readiness_required", False))
        )
        frame.loc[0, "route_readiness_provided"] = _to_bool(
            route_readiness.get("provided", frame.iloc[0].get("route_readiness_provided", False))
        )
        frame.loc[0, "route_readiness_ready"] = _to_bool(
            route_readiness.get("ready", frame.iloc[0].get("route_readiness_ready", False))
        )
        frame.loc[0, "route_readiness_strategy"] = _object_text(
            route_readiness.get("strategy", frame.iloc[0].get("route_readiness_strategy", ""))
        )
        frame.loc[0, "route_readiness_market"] = _object_text(
            route_readiness.get("market", frame.iloc[0].get("route_readiness_market", ""))
        )
        frame.loc[0, "route_readiness_route_ready_pairs"] = int(
            _number_value(
                route_readiness.get("route_ready_pairs"),
                _number(frame.iloc[0], "route_readiness_route_ready_pairs", 0.0),
            )
        )
        frame.loc[0, "route_readiness_gap_pairs"] = int(
            _number_value(route_readiness.get("gap_pairs"), _number(frame.iloc[0], "route_readiness_gap_pairs", 0.0))
        )
        frame.loc[0, "route_readiness_recommendation"] = _object_text(
            route_readiness.get("recommendation", frame.iloc[0].get("route_readiness_recommendation", ""))
        )
        legacy_ops_launch_controls_ready = _to_bool(
            route_readiness.get(
                "ops_launch_controls_ready",
                route_readiness.get(
                    "ops_controls_ready",
                    frame.iloc[0].get("route_readiness_ops_launch_controls_ready", False),
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_legacy_counts_present"] = bool(legacy_ops_present)
        frame.loc[0, "route_readiness_ops_launch_controls_present"] = _to_bool(
            route_readiness.get(
                "ops_launch_controls_present",
                frame.iloc[0].get(
                    "route_readiness_ops_launch_controls_present",
                    legacy_ops_launch_controls_ready,
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_launch_controls_blocked_pairs"] = int(
            _number_value(
                route_readiness.get("ops_launch_controls_blocked_pairs"),
                _number(
                    frame.iloc[0],
                    "route_readiness_ops_launch_controls_blocked_pairs",
                    0.0,
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_breach_pairs"),
                _number(
                    frame.iloc[0],
                    "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
                    _number_value(route_readiness.get("ops_broker_roundtrip_portfolio_breach_runs"), 0.0),
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_concentration_breach_pairs"),
                _number(
                    frame.iloc[0],
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    _number_value(
                        route_readiness.get(
                            "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        ),
                        0.0,
                    ),
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_launch_controls_ready"] = legacy_ops_launch_controls_ready
        frame.loc[0, "route_readiness_ops_launch_control_failures"] = _object_text(
            route_readiness.get(
                "ops_launch_control_failures",
                route_readiness.get(
                    "ops_control_failures",
                    frame.iloc[0].get("route_readiness_ops_launch_control_failures", ""),
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_safe_runs"),
                _number(frame.iloc[0], "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        )
        frame.loc[0, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_breach_runs"),
                _number(frame.iloc[0], "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        )
        frame.loc[0, "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_concentration_ok_runs"),
                _number(
                    frame.iloc[0],
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                ),
            )
        )
        frame.loc[0, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"] = int(
            _number_value(
                route_readiness.get("ops_broker_roundtrip_portfolio_concentration_breach_runs"),
                _number(
                    frame.iloc[0],
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                ),
            )
        )
    route_broker_route_readiness = (
        config.get("route_broker_route_readiness", {})
        or dispatch_config.get("route_broker_route_readiness", {})
        or {}
    )
    if route_broker_route_readiness:
        for text_column in (
            "route_broker_route_readiness_strategy",
            "route_broker_route_readiness_market",
            "route_broker_route_readiness_recommendation",
            "route_broker_route_readiness_ops_launch_control_failures",
        ):
            if text_column in frame.columns:
                frame[text_column] = frame[text_column].astype("object")
        frame.loc[0, "route_broker_route_readiness_required"] = _to_bool(
            route_broker_route_readiness.get(
                "required",
                frame.iloc[0].get("route_broker_route_readiness_required", False),
            )
        )
        frame.loc[0, "route_broker_route_readiness_provided"] = _to_bool(
            route_broker_route_readiness.get(
                "provided",
                frame.iloc[0].get("route_broker_route_readiness_provided", False),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ready"] = _to_bool(
            route_broker_route_readiness.get(
                "ready",
                frame.iloc[0].get("route_broker_route_readiness_ready", False),
            )
        )
        frame.loc[0, "route_broker_route_readiness_strategy"] = _object_text(
            route_broker_route_readiness.get(
                "strategy",
                frame.iloc[0].get("route_broker_route_readiness_strategy", ""),
            )
        )
        frame.loc[0, "route_broker_route_readiness_market"] = _object_text(
            route_broker_route_readiness.get(
                "market",
                frame.iloc[0].get("route_broker_route_readiness_market", ""),
            )
        )
        frame.loc[0, "route_broker_route_readiness_route_ready_pairs"] = int(
            _number_value(
                route_broker_route_readiness.get("route_ready_pairs"),
                _number(frame.iloc[0], "route_broker_route_readiness_route_ready_pairs", 0.0),
            )
        )
        frame.loc[0, "route_broker_route_readiness_gap_pairs"] = int(
            _number_value(
                route_broker_route_readiness.get("gap_pairs"),
                _number(frame.iloc[0], "route_broker_route_readiness_gap_pairs", 0.0),
            )
        )
        frame.loc[0, "route_broker_route_readiness_recommendation"] = _object_text(
            route_broker_route_readiness.get(
                "recommendation",
                frame.iloc[0].get("route_broker_route_readiness_recommendation", ""),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ops_launch_controls_ready"] = _to_bool(
            route_broker_route_readiness.get(
                "ops_launch_controls_ready",
                frame.iloc[0].get("route_broker_route_readiness_ops_launch_controls_ready", False),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ops_launch_control_failures"] = _object_text(
            route_broker_route_readiness.get(
                "ops_launch_control_failures",
                frame.iloc[0].get("route_broker_route_readiness_ops_launch_control_failures", ""),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"] = int(
            _number_value(
                route_broker_route_readiness.get("ops_broker_roundtrip_portfolio_safe_runs"),
                _number(
                    frame.iloc[0],
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    0.0,
                ),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"] = int(
            _number_value(
                route_broker_route_readiness.get("ops_broker_roundtrip_portfolio_breach_runs"),
                _number(
                    frame.iloc[0],
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    0.0,
                ),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"] = int(
            _number_value(
                route_broker_route_readiness.get(
                    "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                ),
                _number(
                    frame.iloc[0],
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                ),
            )
        )
        frame.loc[0, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"] = int(
            _number_value(
                route_broker_route_readiness.get(
                    "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                ),
                _number(
                    frame.iloc[0],
                    "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                ),
            )
        )
    route_enable = config.get("route_enable_dispatch_roundtrip", {}) or {}
    if "failed_checks" in route_enable:
        frame.loc[0, "route_enable_dispatch_roundtrip_failed_checks"] = int(
            _number_value(
                route_enable.get("failed_checks"),
                _number(frame.iloc[0], "route_enable_dispatch_roundtrip_failed_checks", 0.0),
            )
        )
    broker_vendor_data_readiness, _broker_vendor_data_readiness_source = _broker_vendor_data_readiness_config(config)
    if broker_vendor_data_readiness:
        frame.loc[0, "broker_vendor_data_readiness_provided"] = _to_bool(
            broker_vendor_data_readiness.get("provided", True)
        )
        frame.loc[0, "broker_vendor_data_readiness_ready"] = _to_bool(
            broker_vendor_data_readiness.get("ready", False)
        )
        frame.loc[0, "broker_vendor_data_readiness_failed_checks"] = int(
            _broker_vendor_data_readiness_failed_checks(broker_vendor_data_readiness)
        )
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    if shadow_broker:
        _apply_shadow_broker_readiness_config(
            frame,
            shadow_broker,
            field_prefix="shadow_broker",
        )
    broker_shadow_broker = config.get("broker_shadow_broker_readiness", {}) or {}
    if broker_shadow_broker:
        _apply_shadow_broker_readiness_config(
            frame,
            broker_shadow_broker,
            field_prefix="broker_shadow_broker",
        )
    vendor_market_data_batch = config.get("roundtrip_vendor_market_data_batch", {}) or {}
    if vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(frame, vendor_market_data_batch)
    broker_vendor_market_data_batch, broker_vendor_source_prefix = _broker_vendor_market_data_batch_config(config)
    if broker_vendor_market_data_batch:
        _apply_vendor_market_data_batch_config(
            frame,
            broker_vendor_market_data_batch,
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
            source_prefix=broker_vendor_source_prefix,
        )
    return frame


def _broker_vendor_market_data_batch_config(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return select_vendor_market_data_batch_source(
        config,
        (
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch",
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
            "route_broker_dispatch_roundtrip_vendor_market_data_batch",
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
    )


def _broker_vendor_data_readiness_config(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
        (config.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness"),
        (config.get("roundtrip_broker_vendor_data_readiness"), "roundtrip_broker_vendor_data_readiness"),
        (config.get("ack_broker_vendor_data_readiness"), "ack_broker_vendor_data_readiness"),
        (config.get("dispatch_broker_vendor_data_readiness"), "dispatch_broker_vendor_data_readiness"),
        (config.get("route_broker_vendor_data_readiness"), "route_broker_vendor_data_readiness"),
        (config.get("cutover_broker_vendor_data_readiness"), "cutover_broker_vendor_data_readiness"),
        (config.get("scaleup_broker_vendor_data_readiness"), "scaleup_broker_vendor_data_readiness"),
    ]
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(
            (dispatch.get("broker_vendor_data_readiness"), "broker_vendor_data_readiness")
        )
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
    for candidate, source in candidates:
        if isinstance(candidate, dict) and _broker_vendor_data_readiness_active(candidate):
            return candidate, source
    return {}, "roundtrip_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _broker_vendor_data_readiness_failed_checks(readiness: dict[str, Any]) -> int:
    failed_checks = readiness.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_value(failed_checks, 0.0))
    return int(_number_value(readiness.get("failed_check_count", 0.0), 0.0))


def _apply_vendor_market_data_batch_config(
    frame: pd.DataFrame,
    vendor: dict[str, Any],
    *,
    field_prefix: str = "dispatch_roundtrip_vendor_market_data_batch",
    source_prefix: str = "roundtrip_vendor_market_data_batch",
) -> None:
    row = frame.iloc[0]
    comparison = vendor.get("comparison", {}) or {}
    frame.loc[0, f"{field_prefix}_provided"] = _to_bool(
        vendor.get("provided", row.get(f"{source_prefix}_provided", False))
    )
    frame.loc[0, f"{field_prefix}_ready"] = _to_bool(
        vendor.get("ready", row.get(f"{source_prefix}_ready", False))
    )
    frame.loc[0, f"{field_prefix}_adapter"] = _object_text(
        vendor.get("adapter", row.get(f"{source_prefix}_adapter", ""))
    )
    frame.loc[0, f"{field_prefix}_kind"] = _object_text(vendor.get("kind", row.get(f"{source_prefix}_kind", "")))
    frame.loc[0, f"{field_prefix}_manifest_run_type"] = _object_text(
        vendor.get("manifest_run_type", row.get(f"{source_prefix}_manifest_run_type", ""))
    )
    frame.loc[0, f"{field_prefix}_market"] = _object_text(
        vendor.get("market", row.get(f"{source_prefix}_market", ""))
    )
    frame.loc[0, f"{field_prefix}_dataset_count"] = int(
        _number_value(vendor.get("dataset_count"), _number(row, f"{source_prefix}_dataset_count", 0.0))
    )
    frame.loc[0, f"{field_prefix}_ready_datasets"] = int(
        _number_value(vendor.get("ready_datasets"), _number(row, f"{source_prefix}_ready_datasets", 0.0))
    )
    frame.loc[0, f"{field_prefix}_failed_datasets"] = int(
        _number_value(vendor.get("failed_datasets"), _number(row, f"{source_prefix}_failed_datasets", 0.0))
    )
    frame.loc[0, f"{field_prefix}_ready_rate"] = _number_value(
        vendor.get("ready_rate"),
        _number(row, f"{source_prefix}_ready_rate", 0.0),
    )
    frame.loc[0, f"{field_prefix}_unique_source_files"] = int(
        _number_value(
            vendor.get("unique_source_files"),
            _number(row, f"{source_prefix}_unique_source_files", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_source_file_fingerprint_coverage"] = _number_value(
        vendor.get("source_file_fingerprint_coverage"),
        _number(row, f"{source_prefix}_source_file_fingerprint_coverage", 0.0),
    )
    frame.loc[0, f"{field_prefix}_min_mapping_coverage"] = _number_value(
        vendor.get("min_mapping_coverage"),
        _number(row, f"{source_prefix}_min_mapping_coverage", 0.0),
    )
    frame.loc[0, f"{field_prefix}_unique_header_fingerprints"] = int(
        _number_value(
            vendor.get("unique_header_fingerprints"),
            _number(row, f"{source_prefix}_unique_header_fingerprints", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_unique_mapping_drafts"] = int(
        _number_value(
            vendor.get("unique_mapping_drafts"),
            _number(row, f"{source_prefix}_unique_mapping_drafts", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_mapping_sources"] = _object_text(
        vendor.get("mapping_sources", row.get(f"{source_prefix}_mapping_sources", ""))
    )
    frame.loc[0, f"{field_prefix}_mapping_source_mode"] = _object_text(
        vendor.get(
            "mapping_source_mode",
            row.get(f"{source_prefix}_mapping_source_mode", ""),
        )
    )
    frame.loc[0, f"{field_prefix}_mapping_application_count"] = int(
        _number_value(
            vendor.get("mapping_application_count"),
            _number(row, f"{source_prefix}_mapping_application_count", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_unique_mapping_applications"] = int(
        _number_value(
            vendor.get("unique_mapping_applications"),
            _number(row, f"{source_prefix}_unique_mapping_applications", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_target_application_coverage"] = _number_value(
        vendor.get("target_application_coverage"),
        _number(row, f"{source_prefix}_target_application_coverage", 0.0),
    )
    frame.loc[0, f"{field_prefix}_comparison_accepted"] = _to_bool(
        comparison.get("accepted", row.get(f"{source_prefix}_comparison_accepted", False))
    )
    frame.loc[0, f"{field_prefix}_comparison_failed_checks"] = int(
        _number_value(
            comparison.get("failed_checks"),
            _number(row, f"{source_prefix}_comparison_failed_checks", 0.0),
        )
    )
    datasets = vendor.get("datasets", row.get(f"{source_prefix}_datasets_json", ""))
    frame.loc[0, f"{field_prefix}_datasets_json"] = json.dumps(
        _vendor_market_data_batch_datasets(datasets),
        sort_keys=True,
    )


def _apply_shadow_broker_readiness_config(
    frame: pd.DataFrame,
    readiness: dict[str, Any],
    *,
    field_prefix: str,
) -> None:
    _ensure_object_columns(
        frame,
        [
            f"{field_prefix}_adapter",
            f"{field_prefix}_route_readiness_strategy",
            f"{field_prefix}_route_readiness_market",
            f"{field_prefix}_dispatch_roundtrip_strategy",
            f"{field_prefix}_dispatch_roundtrip_market",
            f"{field_prefix}_route_dispatch_roundtrip_strategy",
            f"{field_prefix}_route_dispatch_roundtrip_market",
        ],
    )
    route = readiness.get("route_readiness", {}) or {}
    dispatch = readiness.get("dispatch_roundtrip", {}) or {}
    route_dispatch = readiness.get("route_dispatch_roundtrip", {}) or {}
    vendor_readiness = readiness.get("broker_vendor_data_readiness", {}) or {}
    row = frame.iloc[0]
    frame.loc[0, f"{field_prefix}_readiness_provided"] = _to_bool(
        readiness.get("provided", row.get(f"{field_prefix}_readiness_provided", False))
    )
    frame.loc[0, f"{field_prefix}_readiness_sessions"] = int(
        _number_value(readiness.get("sessions"), _number(row, f"{field_prefix}_readiness_sessions", 0.0))
    )
    frame.loc[0, f"{field_prefix}_readiness_ready_sessions"] = int(
        _number_value(
            readiness.get("ready_sessions"),
            _number(row, f"{field_prefix}_readiness_ready_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_vendor_data_readiness_sessions"] = int(
        _number_value(
            vendor_readiness.get("sessions"),
            _number(row, f"{field_prefix}_vendor_data_readiness_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_vendor_data_readiness_provided_sessions"] = int(
        _number_value(
            vendor_readiness.get("provided_sessions"),
            _number(row, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_vendor_data_readiness_ready_sessions"] = int(
        _number_value(
            vendor_readiness.get("ready_sessions"),
            _number(row, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_vendor_data_readiness_failed_checks"] = int(
        _number_value(
            vendor_readiness.get("failed_checks"),
            _number(row, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_adapter"] = _object_text(readiness.get("adapter", row.get(f"{field_prefix}_adapter", "")))
    frame.loc[0, f"{field_prefix}_adapter_count"] = int(
        _number_value(readiness.get("adapter_count"), _number(row, f"{field_prefix}_adapter_count", 0.0))
    )
    frame.loc[0, f"{field_prefix}_route_readiness_sessions"] = int(
        _number_value(route.get("sessions"), _number(row, f"{field_prefix}_route_readiness_sessions", 0.0))
    )
    frame.loc[0, f"{field_prefix}_route_readiness_ready_sessions"] = int(
        _number_value(
            route.get("ready_sessions"),
            _number(row, f"{field_prefix}_route_readiness_ready_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_route_readiness_strategy"] = _object_text(
        route.get("strategy", row.get(f"{field_prefix}_route_readiness_strategy", ""))
    )
    frame.loc[0, f"{field_prefix}_route_readiness_market"] = _object_text(
        route.get("market", row.get(f"{field_prefix}_route_readiness_market", ""))
    )
    frame.loc[0, f"{field_prefix}_route_readiness_gap_pairs"] = int(
        _number_value(route.get("max_gap_pairs"), _number(row, f"{field_prefix}_route_readiness_gap_pairs", 0.0))
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_sessions"] = int(
        _number_value(dispatch.get("sessions"), _number(row, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0))
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_ready_sessions"] = int(
        _number_value(
            dispatch.get("ready_sessions"),
            _number(row, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_strategy"] = _object_text(
        dispatch.get("strategy", row.get(f"{field_prefix}_dispatch_roundtrip_strategy", ""))
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_market"] = _object_text(
        dispatch.get("market", row.get(f"{field_prefix}_dispatch_roundtrip_market", ""))
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_scenario_count"] = int(
        _number_value(
            dispatch.get("scenario_count"),
            _number(row, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_missing_request_acks"] = int(
        _number_value(
            dispatch.get("max_missing_request_acks"),
            _number(row, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_rejected_orders"] = int(
        _number_value(
            dispatch.get("max_rejected_orders"),
            _number(row, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_dispatch_roundtrip_unmatched_acks"] = int(
        _number_value(
            dispatch.get("max_unmatched_acks"),
            _number(row, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_route_dispatch_roundtrip_sessions"] = int(
        _number_value(
            route_dispatch.get("sessions"),
            _number(row, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions"] = int(
        _number_value(
            route_dispatch.get("ready_sessions"),
            _number(row, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0),
        )
    )
    frame.loc[0, f"{field_prefix}_route_dispatch_roundtrip_strategy"] = _object_text(
        route_dispatch.get("strategy", row.get(f"{field_prefix}_route_dispatch_roundtrip_strategy", ""))
    )
    frame.loc[0, f"{field_prefix}_route_dispatch_roundtrip_market"] = _object_text(
        route_dispatch.get("market", row.get(f"{field_prefix}_route_dispatch_roundtrip_market", ""))
    )
    frame.loc[0, f"{field_prefix}_route_dispatch_roundtrip_scenario_count"] = int(
        _number_value(
            route_dispatch.get("scenario_count"),
            _number(row, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0),
        )
    )


def _ensure_object_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].astype("object")


def _item(
    component: str,
    summary: pd.DataFrame,
    thresholds: BrokerReadinessThresholds,
    *,
    schema_review_checklist: pd.DataFrame | None = None,
) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    vendor_market_data_batch_only = component == "dispatch_roundtrip" and _to_bool(
        row.get("vendor_market_data_batch_only", False)
    )
    provided = bool(not summary.empty and not vendor_market_data_batch_only)
    dispatch_roundtrip_context = component == "dispatch_roundtrip" and (
        provided or vendor_market_data_batch_only
    )
    ready = _component_ready(component, row) if provided else False
    adapter = str(row.get("adapter", "")).strip()
    schema_status = str(row.get("adapter_schema_status", "")).strip()
    failed_checks = _number(row, "failed_checks", fallback=_number(row, "unmapped_required_columns", fallback=0.0))
    required = _component_required(component, thresholds)
    adapter_match = (not adapter) or adapter == thresholds.adapter or not thresholds.require_adapter_match
    return {
        "component": component,
        "required": required,
        "provided": provided,
        "ready": ready,
        "vendor_market_data_batch_only": vendor_market_data_batch_only,
        "adapter": adapter,
        "expected_adapter": thresholds.adapter,
        "expected_market": thresholds.expected_market,
        "expected_vendor_data_kind": thresholds.expected_vendor_data_kind,
        "adapter_match": adapter_match,
        "adapter_schema_status": schema_status,
        **_schema_review_checklist_item_fields(component, schema_review_checklist),
        "failed_checks": int(failed_checks) if not pd.isna(failed_checks) else 0,
        "runtime_guard_action": str(row.get("guard_action", "")).strip() if component == "runtime_session" else "",
        "runtime_guard_halted": _guard_halted(row) if component == "runtime_session" and provided else False,
        "runtime_target_mode": _runtime_text(component, row, "target_mode"),
        "runtime_strategy": _runtime_text(component, row, "strategy"),
        "runtime_market": _runtime_text(component, row, "market"),
        "resume_strategy": _resume_text(component, row, "strategy"),
        "resume_market": _resume_text(component, row, "market"),
        "resume_incident_strategy": _resume_text(component, row, "incident_strategy"),
        "resume_incident_market": _resume_text(component, row, "incident_market"),
        "resume_proof_refresh_ready": _resume_bool(component, row, "proof_refresh_ready"),
        "resume_proof_refresh_strategy": _resume_text(component, row, "proof_refresh_strategy"),
        "resume_proof_refresh_market": _resume_text(component, row, "proof_refresh_market"),
        "resume_incident_proof_refresh_strategy": _resume_text(component, row, "incident_proof_refresh_strategy"),
        "resume_incident_proof_refresh_market": _resume_text(component, row, "incident_proof_refresh_market"),
        "resume_broker_route_readiness_required": _resume_bool(
            component,
            row,
            "broker_route_readiness_required",
        ),
        "resume_broker_route_readiness_provided": _resume_bool(
            component,
            row,
            "broker_route_readiness_provided",
        ),
        "resume_broker_route_readiness_ready": _resume_bool(component, row, "broker_route_readiness_ready"),
        "resume_broker_route_readiness_strategy": _resume_text(component, row, "broker_route_readiness_strategy"),
        "resume_broker_route_readiness_market": _resume_text(component, row, "broker_route_readiness_market"),
        "resume_broker_route_readiness_route_ready_pairs": int(
            _resume_number(component, row, "broker_route_readiness_route_ready_pairs")
        ),
        "resume_broker_route_readiness_gap_pairs": int(
            _resume_number(component, row, "broker_route_readiness_gap_pairs")
        ),
        "resume_broker_route_readiness_recommendation": _resume_text(
            component,
            row,
            "broker_route_readiness_recommendation",
        ),
        "resume_broker_route_readiness_ops_launch_controls_ready": _resume_bool(
            component,
            row,
            "broker_route_readiness_ops_launch_controls_ready",
        ),
        "resume_broker_route_readiness_ops_launch_control_failures": _resume_text(
            component,
            row,
            "broker_route_readiness_ops_launch_control_failures",
        ),
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _resume_number(component, row, "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs")
        ),
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _resume_number(component, row, "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs")
        ),
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _resume_number(
                component,
                row,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            )
        ),
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _resume_number(
                component,
                row,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            )
        ),
        "resume_incident_broker_route_readiness_required": _resume_bool(
            component,
            row,
            "incident_broker_route_readiness_required",
        ),
        "resume_incident_broker_route_readiness_provided": _resume_bool(
            component,
            row,
            "incident_broker_route_readiness_provided",
        ),
        "resume_incident_broker_route_readiness_ready": _resume_bool(
            component,
            row,
            "incident_broker_route_readiness_ready",
        ),
        "resume_incident_broker_route_readiness_strategy": _resume_text(
            component,
            row,
            "incident_broker_route_readiness_strategy",
        ),
        "resume_incident_broker_route_readiness_market": _resume_text(
            component,
            row,
            "incident_broker_route_readiness_market",
        ),
        "resume_incident_broker_route_readiness_route_ready_pairs": int(
            _resume_number(component, row, "incident_broker_route_readiness_route_ready_pairs")
        ),
        "resume_incident_broker_route_readiness_gap_pairs": int(
            _resume_number(component, row, "incident_broker_route_readiness_gap_pairs")
        ),
        "resume_incident_broker_route_readiness_recommendation": _resume_text(
            component,
            row,
            "incident_broker_route_readiness_recommendation",
        ),
        "resume_incident_broker_route_readiness_ops_launch_controls_ready": _resume_bool(
            component,
            row,
            "incident_broker_route_readiness_ops_launch_controls_ready",
        ),
        "resume_incident_broker_route_readiness_ops_launch_control_failures": _resume_text(
            component,
            row,
            "incident_broker_route_readiness_ops_launch_control_failures",
        ),
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _resume_number(
                component,
                row,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            )
        ),
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _resume_number(
                component,
                row,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            )
        ),
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _resume_number(
                component,
                row,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            )
        ),
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _resume_number(
                component,
                row,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            )
        ),
        "dispatch_roundtrip_target_mode": _dispatch_text(component, row, "target_mode"),
        "dispatch_roundtrip_strategy": _dispatch_text(component, row, "strategy"),
        "dispatch_roundtrip_market": _dispatch_text(component, row, "market"),
        "dispatch_roundtrip_scenario_key": _dispatch_text(component, row, "scenario_key"),
        "dispatch_roundtrip_batch_id": _dispatch_text(component, row, "dispatch_batch_id"),
        "dispatch_roundtrip_requests": int(_number(row, "send_requests", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_acked_orders": int(_number(row, "acked_orders", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_missing_request_acks": int(_number(row, "missing_request_acks", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_rejected_orders": int(_number(row, "rejected_orders", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_unmatched_acks": int(_number(row, "unmatched_acks", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "dispatch_roundtrip_failed_checks": int(failed_checks)
        if component == "dispatch_roundtrip" and provided and not pd.isna(failed_checks)
        else 0,
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "broker_vendor_data_readiness_provided": _dispatch_bool(
            component,
            row,
            "broker_vendor_data_readiness_provided",
        ),
        "broker_vendor_data_readiness_ready": _dispatch_bool(
            component,
            row,
            "broker_vendor_data_readiness_ready",
        ),
        "broker_vendor_data_readiness_failed_checks": int(
            _number(row, "broker_vendor_data_readiness_failed_checks", 0.0)
        )
        if component == "dispatch_roundtrip"
        else 0,
        "route_readiness_required": _dispatch_bool(component, row, "route_readiness_required"),
        "route_readiness_provided": _dispatch_bool(component, row, "route_readiness_provided"),
        "route_readiness_ready": _dispatch_bool(component, row, "route_readiness_ready"),
        "route_readiness_strategy": _dispatch_text(component, row, "route_readiness_strategy"),
        "route_readiness_market": _dispatch_text(component, row, "route_readiness_market"),
        "route_readiness_route_ready_pairs": int(_number(row, "route_readiness_route_ready_pairs", 0.0))
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_gap_pairs": int(_number(row, "route_readiness_gap_pairs", 0.0))
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_recommendation": _dispatch_text(component, row, "route_readiness_recommendation"),
        "route_readiness_ops_legacy_counts_present": _dispatch_route_readiness_legacy_ops_present(component, row),
        "route_readiness_ops_launch_controls_present": _dispatch_bool(
            component,
            row,
            "route_readiness_ops_launch_controls_present",
        ),
        "route_readiness_ops_launch_controls_blocked_pairs": int(
            _number(row, "route_readiness_ops_launch_controls_blocked_pairs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
            _number(row, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
            _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_ops_launch_controls_ready": _dispatch_bool(
            component,
            row,
            "route_readiness_ops_launch_controls_ready",
        ),
        "route_readiness_ops_launch_control_failures": _dispatch_text(
            component,
            row,
            "route_readiness_ops_launch_control_failures",
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(row, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(row, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_broker_route_readiness_required": _dispatch_bool(
            component,
            row,
            "route_broker_route_readiness_required",
        ),
        "route_broker_route_readiness_provided": _dispatch_bool(
            component,
            row,
            "route_broker_route_readiness_provided",
        ),
        "route_broker_route_readiness_ready": _dispatch_bool(
            component,
            row,
            "route_broker_route_readiness_ready",
        ),
        "route_broker_route_readiness_strategy": _dispatch_text(
            component,
            row,
            "route_broker_route_readiness_strategy",
        ),
        "route_broker_route_readiness_market": _dispatch_text(
            component,
            row,
            "route_broker_route_readiness_market",
        ),
        "route_broker_route_readiness_route_ready_pairs": int(
            _number(row, "route_broker_route_readiness_route_ready_pairs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_broker_route_readiness_gap_pairs": int(
            _number(row, "route_broker_route_readiness_gap_pairs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_broker_route_readiness_recommendation": _dispatch_text(
            component,
            row,
            "route_broker_route_readiness_recommendation",
        ),
        "route_broker_route_readiness_ops_launch_controls_ready": _dispatch_bool(
            component,
            row,
            "route_broker_route_readiness_ops_launch_controls_ready",
        ),
        "route_broker_route_readiness_ops_launch_control_failures": _dispatch_text(
            component,
            row,
            "route_broker_route_readiness_ops_launch_control_failures",
        ),
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        )
        if dispatch_roundtrip_context
        else 0,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(
                row,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        )
        if dispatch_roundtrip_context
        else 0,
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(
                row,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        )
        if dispatch_roundtrip_context
        else 0,
        "route_dispatch_roundtrip_required": _dispatch_bool(component, row, "route_dispatch_roundtrip_required"),
        "route_dispatch_roundtrip_provided": _dispatch_bool(component, row, "route_dispatch_roundtrip_provided"),
        "route_dispatch_roundtrip_ready": _dispatch_bool(component, row, "route_dispatch_roundtrip_ready"),
        "route_dispatch_roundtrip_target_mode": _dispatch_text(component, row, "route_dispatch_roundtrip_target_mode"),
        "route_dispatch_roundtrip_strategy": _dispatch_text(component, row, "route_dispatch_roundtrip_strategy"),
        "route_dispatch_roundtrip_market": _dispatch_text(component, row, "route_dispatch_roundtrip_market"),
        "route_dispatch_roundtrip_scenario_key": _dispatch_text(
            component,
            row,
            "route_dispatch_roundtrip_scenario_key",
        ),
        "route_dispatch_roundtrip_batch_id": _dispatch_text(component, row, "route_dispatch_roundtrip_batch_id"),
        "route_dispatch_roundtrip_requests": int(_number(row, "route_dispatch_roundtrip_requests", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_acked_orders": int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_rejected_orders": int(
            _number(row, "route_dispatch_roundtrip_rejected_orders", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_readiness_provided": _dispatch_bool(component, row, "shadow_broker_readiness_provided")
        or (
            component == "dispatch_roundtrip"
            and provided
            and int(_number(row, "shadow_broker_readiness_sessions", 0.0)) > 0
        ),
        "shadow_broker_readiness_sessions": int(_number(row, "shadow_broker_readiness_sessions", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_readiness_ready_sessions": int(
            _number(row, "shadow_broker_readiness_ready_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_vendor_data_readiness_sessions": int(
            _number(row, "shadow_broker_vendor_data_readiness_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number(row, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number(row, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_vendor_data_readiness_failed_checks": int(
            _number(row, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_adapter": _dispatch_text(component, row, "shadow_broker_adapter"),
        "shadow_broker_adapter_count": int(_number(row, "shadow_broker_adapter_count", 0.0))
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_route_readiness_sessions": int(
            _number(row, "shadow_broker_route_readiness_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_route_readiness_ready_sessions": int(
            _number(row, "shadow_broker_route_readiness_ready_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_route_readiness_strategy": _dispatch_text(
            component,
            row,
            "shadow_broker_route_readiness_strategy",
        ),
        "shadow_broker_route_readiness_market": _dispatch_text(
            component,
            row,
            "shadow_broker_route_readiness_market",
        ),
        "shadow_broker_route_readiness_gap_pairs": int(
            _number(row, "shadow_broker_route_readiness_gap_pairs", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_dispatch_roundtrip_sessions": int(
            _number(row, "shadow_broker_dispatch_roundtrip_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number(row, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_dispatch_roundtrip_strategy": _dispatch_text(
            component,
            row,
            "shadow_broker_dispatch_roundtrip_strategy",
        ),
        "shadow_broker_dispatch_roundtrip_market": _dispatch_text(
            component,
            row,
            "shadow_broker_dispatch_roundtrip_market",
        ),
        "shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number(row, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number(row, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number(row, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number(row, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number(row, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        "shadow_broker_route_dispatch_roundtrip_strategy": _dispatch_text(
            component,
            row,
            "shadow_broker_route_dispatch_roundtrip_strategy",
        ),
        "shadow_broker_route_dispatch_roundtrip_market": _dispatch_text(
            component,
            row,
            "shadow_broker_route_dispatch_roundtrip_market",
        ),
        "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)
        )
        if component == "dispatch_roundtrip" and provided
        else 0,
        **_prefixed_shadow_broker_item_fields(
            component,
            row,
            field_prefix="broker_shadow_broker",
            provided=provided,
        ),
        **_vendor_market_data_batch_item_fields(component, row, provided=provided),
        **_vendor_market_data_batch_item_fields(
            component,
            row,
            provided=provided,
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
            source_prefix="roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
        "source_file": SUMMARY_FILES[component],
        "recommendation": _component_recommendation(component, provided, ready, required),
    }


def _schema_review_checklist_item_fields(
    component: str,
    checklist: pd.DataFrame | None,
) -> dict[str, Any]:
    if component != "schema_audit" or checklist is None or checklist.empty:
        return {
            "schema_review_checklist_present": False,
            "schema_review_check_count": 0,
            "schema_review_blocked_checks": 0,
            "schema_review_review_checks": 0,
            "schema_review_blocked_check_names": "",
            "schema_review_review_check_names": "",
        }
    frame = checklist.copy()
    status = frame.get("status", pd.Series([""] * len(frame), index=frame.index)).astype(str)
    blocked = status.str.casefold().eq("blocked")
    review = status.str.casefold().eq("review")
    return {
        "schema_review_checklist_present": True,
        "schema_review_check_count": int(len(frame)),
        "schema_review_blocked_checks": int(blocked.sum()),
        "schema_review_review_checks": int(review.sum()),
        "schema_review_blocked_check_names": ";".join(_check_names(frame, blocked)),
        "schema_review_review_check_names": ";".join(_check_names(frame, review)),
    }


def _check_names(frame: pd.DataFrame, mask: pd.Series) -> list[str]:
    if "check_name" not in frame.columns:
        return []
    return frame.loc[mask, "check_name"].dropna().astype(str).tolist()


def _prefixed_shadow_broker_item_fields(
    component: str,
    row: pd.Series,
    *,
    field_prefix: str,
    provided: bool,
) -> dict[str, Any]:
    active = component == "dispatch_roundtrip" and provided
    return {
        f"{field_prefix}_readiness_provided": _dispatch_bool(component, row, f"{field_prefix}_readiness_provided")
        or (active and int(_number(row, f"{field_prefix}_readiness_sessions", 0.0)) > 0),
        f"{field_prefix}_readiness_sessions": int(_number(row, f"{field_prefix}_readiness_sessions", 0.0))
        if active
        else 0,
        f"{field_prefix}_readiness_ready_sessions": int(
            _number(row, f"{field_prefix}_readiness_ready_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_vendor_data_readiness_sessions": int(
            _number(row, f"{field_prefix}_vendor_data_readiness_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_vendor_data_readiness_provided_sessions": int(
            _number(row, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_vendor_data_readiness_ready_sessions": int(
            _number(row, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_vendor_data_readiness_failed_checks": int(
            _number(row, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_adapter": _dispatch_text(component, row, f"{field_prefix}_adapter"),
        f"{field_prefix}_adapter_count": int(_number(row, f"{field_prefix}_adapter_count", 0.0))
        if active
        else 0,
        f"{field_prefix}_route_readiness_sessions": int(
            _number(row, f"{field_prefix}_route_readiness_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_route_readiness_ready_sessions": int(
            _number(row, f"{field_prefix}_route_readiness_ready_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_route_readiness_strategy": _dispatch_text(
            component,
            row,
            f"{field_prefix}_route_readiness_strategy",
        ),
        f"{field_prefix}_route_readiness_market": _dispatch_text(
            component,
            row,
            f"{field_prefix}_route_readiness_market",
        ),
        f"{field_prefix}_route_readiness_gap_pairs": int(
            _number(row, f"{field_prefix}_route_readiness_gap_pairs", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_dispatch_roundtrip_sessions": int(
            _number(row, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_dispatch_roundtrip_ready_sessions": int(
            _number(row, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_dispatch_roundtrip_strategy": _dispatch_text(
            component,
            row,
            f"{field_prefix}_dispatch_roundtrip_strategy",
        ),
        f"{field_prefix}_dispatch_roundtrip_market": _dispatch_text(
            component,
            row,
            f"{field_prefix}_dispatch_roundtrip_market",
        ),
        f"{field_prefix}_dispatch_roundtrip_scenario_count": int(
            _number(row, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_dispatch_roundtrip_missing_request_acks": int(
            _number(row, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_dispatch_roundtrip_rejected_orders": int(
            _number(row, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_dispatch_roundtrip_unmatched_acks": int(
            _number(row, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_route_dispatch_roundtrip_sessions": int(
            _number(row, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_route_dispatch_roundtrip_ready_sessions": int(
            _number(row, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0)
        )
        if active
        else 0,
        f"{field_prefix}_route_dispatch_roundtrip_strategy": _dispatch_text(
            component,
            row,
            f"{field_prefix}_route_dispatch_roundtrip_strategy",
        ),
        f"{field_prefix}_route_dispatch_roundtrip_market": _dispatch_text(
            component,
            row,
            f"{field_prefix}_route_dispatch_roundtrip_market",
        ),
        f"{field_prefix}_route_dispatch_roundtrip_scenario_count": int(
            _number(row, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0)
        )
        if active
        else 0,
    }


def _vendor_market_data_batch_item_fields(
    component: str,
    row: pd.Series,
    *,
    provided: bool,
    field_prefix: str = "dispatch_roundtrip_vendor_market_data_batch",
    source_prefix: str = "roundtrip_vendor_market_data_batch",
) -> dict[str, Any]:
    vendor_market_data_batch_only = _to_bool(row.get("vendor_market_data_batch_only", False))
    active = component == "dispatch_roundtrip" and (provided or vendor_market_data_batch_only)
    dataset_count = int(
        _dispatch_number_any(component, row, f"{field_prefix}_dataset_count", f"{source_prefix}_dataset_count")
    )
    return {
        f"{field_prefix}_provided": _dispatch_bool_any(
            component,
            row,
            f"{field_prefix}_provided",
            f"{source_prefix}_provided",
        )
        or (active and dataset_count > 0),
        f"{field_prefix}_ready": _dispatch_bool_any(
            component,
            row,
            f"{field_prefix}_ready",
            f"{source_prefix}_ready",
        ),
        f"{field_prefix}_adapter": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_adapter",
            f"{source_prefix}_adapter",
        ),
        f"{field_prefix}_kind": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_kind",
            f"{source_prefix}_kind",
        ),
        f"{field_prefix}_manifest_run_type": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_manifest_run_type",
            f"{source_prefix}_manifest_run_type",
        ),
        f"{field_prefix}_market": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_market",
            f"{source_prefix}_market",
        ),
        f"{field_prefix}_dataset_count": dataset_count if active else 0,
        f"{field_prefix}_ready_datasets": int(
            _dispatch_number_any(component, row, f"{field_prefix}_ready_datasets", f"{source_prefix}_ready_datasets")
        )
        if active
        else 0,
        f"{field_prefix}_failed_datasets": int(
            _dispatch_number_any(component, row, f"{field_prefix}_failed_datasets", f"{source_prefix}_failed_datasets")
        )
        if active
        else 0,
        f"{field_prefix}_ready_rate": _dispatch_number_any(
            component,
            row,
            f"{field_prefix}_ready_rate",
            f"{source_prefix}_ready_rate",
        )
        if active
        else 0.0,
        f"{field_prefix}_unique_source_files": int(
            _dispatch_number_any(
                component,
                row,
                f"{field_prefix}_unique_source_files",
                f"{source_prefix}_unique_source_files",
            )
        )
        if active
        else 0,
        f"{field_prefix}_source_file_fingerprint_coverage": _dispatch_number_any(
            component,
            row,
            f"{field_prefix}_source_file_fingerprint_coverage",
            f"{source_prefix}_source_file_fingerprint_coverage",
        )
        if active
        else 0.0,
        f"{field_prefix}_min_mapping_coverage": _dispatch_number_any(
            component,
            row,
            f"{field_prefix}_min_mapping_coverage",
            f"{source_prefix}_min_mapping_coverage",
        )
        if active
        else 0.0,
        f"{field_prefix}_unique_header_fingerprints": int(
            _dispatch_number_any(
                component,
                row,
                f"{field_prefix}_unique_header_fingerprints",
                f"{source_prefix}_unique_header_fingerprints",
            )
        )
        if active
        else 0,
        f"{field_prefix}_unique_mapping_drafts": int(
            _dispatch_number_any(
                component,
                row,
                f"{field_prefix}_unique_mapping_drafts",
                f"{source_prefix}_unique_mapping_drafts",
            )
        )
        if active
        else 0,
        f"{field_prefix}_mapping_sources": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_mapping_sources",
            f"{source_prefix}_mapping_sources",
        ),
        f"{field_prefix}_mapping_source_mode": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_mapping_source_mode",
            f"{source_prefix}_mapping_source_mode",
        ),
        f"{field_prefix}_mapping_application_count": int(
            _dispatch_number_any(
                component,
                row,
                f"{field_prefix}_mapping_application_count",
                f"{source_prefix}_mapping_application_count",
            )
        )
        if active
        else 0,
        f"{field_prefix}_unique_mapping_applications": int(
            _dispatch_number_any(
                component,
                row,
                f"{field_prefix}_unique_mapping_applications",
                f"{source_prefix}_unique_mapping_applications",
            )
        )
        if active
        else 0,
        f"{field_prefix}_target_application_coverage": _dispatch_number_any(
            component,
            row,
            f"{field_prefix}_target_application_coverage",
            f"{source_prefix}_target_application_coverage",
        )
        if active
        else 0.0,
        f"{field_prefix}_comparison_accepted": _dispatch_bool_any(
            component,
            row,
            f"{field_prefix}_comparison_accepted",
            f"{source_prefix}_comparison_accepted",
        ),
        f"{field_prefix}_comparison_failed_checks": int(
            _dispatch_number_any(
                component,
                row,
                f"{field_prefix}_comparison_failed_checks",
                f"{source_prefix}_comparison_failed_checks",
            )
        )
        if active
        else 0,
        f"{field_prefix}_datasets_json": _dispatch_text_any(
            component,
            row,
            f"{field_prefix}_datasets_json",
            f"{source_prefix}_datasets_json",
        ),
    }


def _checks(items: pd.DataFrame, thresholds: BrokerReadinessThresholds) -> pd.DataFrame:
    schema_review = _schema_review_state(items, thresholds)
    checks: list[dict[str, Any]] = [
        _check(
            "schema_reviewed",
            schema_review["mode"],
            "!=",
            "placeholder_unreviewed",
            (not thresholds.require_reviewed_schema) or bool(schema_review["reviewed"]),
            "adapter schema is still placeholder; review a real vendor sample before broker integration",
        )
    ]
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
        if bool(row.provided) and thresholds.require_adapter_match:
            checks.append(
                _check(
                    f"{row.component}_adapter_match",
                    row.adapter or thresholds.adapter,
                    "==",
                    thresholds.adapter,
                    bool(row.adapter_match),
                    f"{row.component} adapter does not match expected broker adapter",
                )
            )
        if row.component == "resume_gate" and bool(row.provided):
            if _resume_broker_route_readiness_active(row):
                checks.extend(_resume_broker_route_readiness_checks(row))
            if _resume_incident_broker_route_readiness_active(row):
                checks.extend(_resume_incident_broker_route_readiness_checks(row))
        if row.component == "dispatch_roundtrip" and bool(row.provided):
            checks.append(
                _check(
                    "route_enable_dispatch_roundtrip_failed_checks",
                    int(row.route_enable_dispatch_roundtrip_failed_checks),
                    "<=",
                    0,
                    int(row.route_enable_dispatch_roundtrip_failed_checks) <= 0,
                    "route-enable dispatch round-trip has failed component checks",
                )
            )
            route_required = _route_dispatch_roundtrip_required(row)
            if route_required:
                checks.append(
                    _check(
                        "route_dispatch_roundtrip_provided",
                        bool(row.route_dispatch_roundtrip_provided),
                        "is",
                        True,
                        bool(row.route_dispatch_roundtrip_provided),
                        "dispatch round-trip summary must carry route proof for live dry-run readiness",
                    )
                )
            if route_required or bool(row.route_dispatch_roundtrip_provided):
                checks.extend(_route_dispatch_roundtrip_checks(row))
            route_readiness_required = _route_readiness_required(row, thresholds)
            if route_readiness_required:
                checks.append(
                    _check(
                        "route_readiness_provided",
                        bool(row.route_readiness_provided),
                        "is",
                        True,
                        bool(row.route_readiness_provided),
                        "dispatch round-trip summary must carry route-readiness proof for live dry-run readiness",
                    )
                )
            if route_readiness_required or bool(row.route_readiness_provided):
                checks.extend(_route_readiness_checks(row))
            if _shadow_broker_readiness_active(row):
                checks.extend(_shadow_broker_readiness_checks(row))
            if _broker_shadow_broker_readiness_active(row):
                checks.extend(_broker_shadow_broker_readiness_checks(row))
        if row.component == "dispatch_roundtrip" and (
            bool(row.provided) or bool(getattr(row, "vendor_market_data_batch_only", False))
        ):
            if bool(getattr(row, "broker_vendor_data_readiness_provided", False)):
                checks.extend(_broker_vendor_data_readiness_checks(row))
            if _dispatch_roundtrip_vendor_market_data_batch_active(row):
                checks.extend(_dispatch_roundtrip_vendor_market_data_batch_checks(row))
            if _broker_dispatch_roundtrip_vendor_market_data_batch_active(row):
                checks.extend(_broker_dispatch_roundtrip_vendor_market_data_batch_checks(row))
    return pd.DataFrame(checks)


def _resume_broker_route_readiness_active(row: Any) -> bool:
    return bool(
        row.resume_broker_route_readiness_required
        or row.resume_broker_route_readiness_provided
        or row.resume_broker_route_readiness_ready
        or int(row.resume_broker_route_readiness_route_ready_pairs) > 0
        or int(row.resume_broker_route_readiness_gap_pairs) > 0
        or _identity_key(row.resume_broker_route_readiness_strategy)
        or _identity_key(row.resume_broker_route_readiness_market)
        or _identity_key(row.resume_broker_route_readiness_recommendation)
        or row.resume_broker_route_readiness_ops_launch_controls_ready
        or bool(str(row.resume_broker_route_readiness_ops_launch_control_failures).strip())
        or int(row.resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs) > 0
        or int(row.resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs) > 0
        or int(row.resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs) > 0
        or int(row.resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs) > 0
    )


def _resume_incident_broker_route_readiness_active(row: Any) -> bool:
    return bool(
        row.resume_incident_broker_route_readiness_required
        or row.resume_incident_broker_route_readiness_provided
        or row.resume_incident_broker_route_readiness_ready
        or int(row.resume_incident_broker_route_readiness_route_ready_pairs) > 0
        or int(row.resume_incident_broker_route_readiness_gap_pairs) > 0
        or _identity_key(row.resume_incident_broker_route_readiness_strategy)
        or _identity_key(row.resume_incident_broker_route_readiness_market)
        or _identity_key(row.resume_incident_broker_route_readiness_recommendation)
        or row.resume_incident_broker_route_readiness_ops_launch_controls_ready
        or bool(str(row.resume_incident_broker_route_readiness_ops_launch_control_failures).strip())
        or int(row.resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs) > 0
        or int(row.resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs) > 0
        or int(row.resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs) > 0
        or int(row.resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs)
        > 0
    )


def _resume_broker_route_readiness_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "resume_broker_route_readiness_provided",
            bool(row.resume_broker_route_readiness_provided),
            "is",
            True,
            bool(row.resume_broker_route_readiness_provided),
            "resume gate broker route proof is required but missing",
        ),
        _check(
            "resume_broker_route_readiness_ready",
            bool(row.resume_broker_route_readiness_ready),
            "is",
            True,
            bool(row.resume_broker_route_readiness_ready),
            "resume gate broker route proof is not ready",
        ),
        _check(
            "resume_broker_route_readiness_strategy_matches",
            _identity_key(row.resume_broker_route_readiness_strategy),
            "==",
            _identity_key(row.resume_strategy),
            bool(
                _identity_key(row.resume_broker_route_readiness_strategy)
                and _identity_key(row.resume_strategy)
                and _identity_key(row.resume_broker_route_readiness_strategy) == _identity_key(row.resume_strategy)
            ),
            "resume gate broker route proof strategy does not match resume strategy",
        ),
        _check(
            "resume_broker_route_readiness_market_matches",
            _identity_key(row.resume_broker_route_readiness_market),
            "==",
            _identity_key(row.resume_market),
            bool(
                _identity_key(row.resume_broker_route_readiness_market)
                and _identity_key(row.resume_market)
                and _identity_key(row.resume_broker_route_readiness_market) == _identity_key(row.resume_market)
            ),
            "resume gate broker route proof market does not match resume market",
        ),
        _check(
            "resume_broker_route_readiness_gap_pairs",
            int(row.resume_broker_route_readiness_gap_pairs),
            "<=",
            0,
            int(row.resume_broker_route_readiness_gap_pairs) <= 0,
            "resume gate broker route proof still reports route gaps",
        ),
        *_resume_broker_route_readiness_ops_checks(
            row,
            prefix="resume_broker_route_readiness",
            label="resume gate broker route proof",
        ),
    ]


def _resume_incident_broker_route_readiness_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "resume_incident_broker_route_readiness_provided",
            bool(row.resume_incident_broker_route_readiness_provided),
            "is",
            True,
            bool(row.resume_incident_broker_route_readiness_provided),
            "resume incident broker route proof is required but missing",
        ),
        _check(
            "resume_incident_broker_route_readiness_ready",
            bool(row.resume_incident_broker_route_readiness_ready),
            "is",
            True,
            bool(row.resume_incident_broker_route_readiness_ready),
            "resume incident broker route proof is not ready",
        ),
        _check(
            "resume_incident_broker_route_readiness_strategy_matches",
            _identity_key(row.resume_incident_broker_route_readiness_strategy),
            "==",
            _identity_key(row.resume_incident_strategy),
            bool(
                _identity_key(row.resume_incident_broker_route_readiness_strategy)
                and _identity_key(row.resume_incident_strategy)
                and _identity_key(row.resume_incident_broker_route_readiness_strategy)
                == _identity_key(row.resume_incident_strategy)
            ),
            "resume incident broker route proof strategy does not match incident strategy",
        ),
        _check(
            "resume_incident_broker_route_readiness_market_matches",
            _identity_key(row.resume_incident_broker_route_readiness_market),
            "==",
            _identity_key(row.resume_incident_market),
            bool(
                _identity_key(row.resume_incident_broker_route_readiness_market)
                and _identity_key(row.resume_incident_market)
                and _identity_key(row.resume_incident_broker_route_readiness_market)
                == _identity_key(row.resume_incident_market)
            ),
            "resume incident broker route proof market does not match incident market",
        ),
        _check(
            "resume_incident_broker_route_readiness_gap_pairs",
            int(row.resume_incident_broker_route_readiness_gap_pairs),
            "<=",
            0,
            int(row.resume_incident_broker_route_readiness_gap_pairs) <= 0,
            "resume incident broker route proof still reports route gaps",
        ),
        *_resume_broker_route_readiness_ops_checks(
            row,
            prefix="resume_incident_broker_route_readiness",
            label="resume incident broker route proof",
        ),
    ]


def _resume_broker_route_readiness_ops_checks(
    row: pd.Series,
    *,
    prefix: str,
    label: str,
) -> list[dict[str, Any]]:
    return [
        _check(
            f"{prefix}_ops_launch_controls_ready",
            bool(getattr(row, f"{prefix}_ops_launch_controls_ready")),
            "is",
            True,
            bool(getattr(row, f"{prefix}_ops_launch_controls_ready")),
            f"{label} did not preserve launch-grade broker controls",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs")),
            ">",
            0,
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs")) > 0,
            f"{label} has no allocation-safe broker round-trip run",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs")),
            "<=",
            0,
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs")) <= 0,
            f"{label} reports allocation breach broker round-trip runs",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs")),
            ">",
            0,
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs")) > 0,
            f"{label} has no concentration-OK broker round-trip run",
        ),
        _check(
            f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs")),
            "<=",
            0,
            int(getattr(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs")) <= 0,
            f"{label} reports concentration breach broker round-trip runs",
        ),
    ]


def _broker_vendor_data_readiness_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "broker_vendor_data_readiness_ready",
            bool(row.broker_vendor_data_readiness_ready),
            "is",
            True,
            bool(row.broker_vendor_data_readiness_ready),
            "broker-vendor data readiness root is not ready",
        ),
        _check(
            "broker_vendor_data_readiness_failed_checks",
            int(row.broker_vendor_data_readiness_failed_checks),
            "<=",
            0,
            int(row.broker_vendor_data_readiness_failed_checks) <= 0,
            "broker-vendor data readiness root has failed checks",
        ),
    ]


def _route_readiness_checks(row: pd.Series) -> list[dict[str, Any]]:
    checks = [
        _check(
            "route_readiness_ready",
            bool(row.route_readiness_ready),
            "is",
            True,
            bool(row.route_readiness_ready),
            "route-readiness proof is not ready",
        ),
        _check(
            "route_readiness_strategy_matches",
            _identity_key(row.route_readiness_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.route_readiness_strategy)
                and _identity_key(row.dispatch_roundtrip_strategy)
                and _identity_key(row.route_readiness_strategy) == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "route-readiness proof strategy does not match dispatch round-trip strategy",
        ),
        _check(
            "route_readiness_market_matches",
            _identity_key(row.route_readiness_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.route_readiness_market)
                and _identity_key(row.dispatch_roundtrip_market)
                and _identity_key(row.route_readiness_market) == _identity_key(row.dispatch_roundtrip_market)
            ),
            "route-readiness proof market does not match dispatch round-trip market",
        ),
        _check(
            "route_readiness_gap_pairs",
            int(row.route_readiness_gap_pairs),
            "==",
            0,
            int(row.route_readiness_gap_pairs) == 0,
            "route-readiness proof still reports market/strategy route gaps",
        ),
        _check(
            "route_readiness_ops_launch_controls_present",
            bool(row.route_readiness_ops_launch_controls_present),
            "is",
            True,
            bool(row.route_readiness_ops_launch_controls_present),
            "route-readiness proof did not preserve launch-grade ops broker controls",
        ),
        _check(
            "route_readiness_ops_launch_controls_blocked_pairs",
            int(row.route_readiness_ops_launch_controls_blocked_pairs),
            "<=",
            0,
            int(row.route_readiness_ops_launch_controls_blocked_pairs) <= 0,
            "route-readiness proof reports blocked launch-control pairs",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
            int(row.route_readiness_ops_broker_roundtrip_portfolio_breach_pairs),
            "<=",
            0,
            int(row.route_readiness_ops_broker_roundtrip_portfolio_breach_pairs) <= 0,
            "route-readiness proof reports broker round-trip allocation breach pairs",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
            int(row.route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs),
            "<=",
            0,
            int(row.route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs) <= 0,
            "route-readiness proof reports broker round-trip concentration breach pairs",
        ),
    ]
    if bool(row.route_readiness_ops_legacy_counts_present):
        checks.extend(_route_readiness_legacy_ops_checks(row))
    if _route_broker_route_readiness_active(row):
        checks.extend(_route_broker_route_readiness_checks(row))
    return checks


def _route_readiness_legacy_ops_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "route_readiness_ops_launch_controls_ready",
            bool(row.route_readiness_ops_launch_controls_ready),
            "is",
            True,
            bool(row.route_readiness_ops_launch_controls_ready),
            "route-readiness proof did not preserve launch-grade ops broker controls",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            int(row.route_readiness_ops_broker_roundtrip_portfolio_safe_runs),
            ">=",
            1,
            int(row.route_readiness_ops_broker_roundtrip_portfolio_safe_runs) >= 1,
            "route-readiness proof does not include a portfolio-safe broker round-trip",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            int(row.route_readiness_ops_broker_roundtrip_portfolio_breach_runs),
            "==",
            0,
            int(row.route_readiness_ops_broker_roundtrip_portfolio_breach_runs) == 0,
            "route-readiness proof reports broker round-trip allocation breaches",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            int(row.route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs),
            ">=",
            1,
            int(row.route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs) >= 1,
            "route-readiness proof does not include a concentration-ok broker round-trip",
        ),
        _check(
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            int(row.route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs),
            "==",
            0,
            int(row.route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs) == 0,
            "route-readiness proof reports broker round-trip concentration breaches",
        ),
    ]


def _route_broker_route_readiness_active(row: Any) -> bool:
    return bool(
        row.route_broker_route_readiness_required
        or row.route_broker_route_readiness_provided
        or row.route_broker_route_readiness_ready
        or int(row.route_broker_route_readiness_route_ready_pairs) > 0
        or int(row.route_broker_route_readiness_gap_pairs) > 0
        or _identity_key(row.route_broker_route_readiness_strategy)
        or _identity_key(row.route_broker_route_readiness_market)
        or _identity_key(row.route_broker_route_readiness_recommendation)
        or row.route_broker_route_readiness_ops_launch_controls_ready
        or bool(str(row.route_broker_route_readiness_ops_launch_control_failures).strip())
        or int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs) > 0
        or int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs) > 0
        or int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs) > 0
        or int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs) > 0
    )


def _route_broker_route_readiness_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "route_broker_route_readiness_provided",
            bool(row.route_broker_route_readiness_provided),
            "is",
            True,
            bool(row.route_broker_route_readiness_provided),
            "broker-carried route proof is required but missing",
        ),
        _check(
            "route_broker_route_readiness_ready",
            bool(row.route_broker_route_readiness_ready),
            "is",
            True,
            bool(row.route_broker_route_readiness_ready),
            "broker-carried route proof is not ready",
        ),
        _check(
            "route_broker_route_readiness_strategy_matches",
            _identity_key(row.route_broker_route_readiness_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.route_broker_route_readiness_strategy)
                and _identity_key(row.dispatch_roundtrip_strategy)
                and _identity_key(row.route_broker_route_readiness_strategy)
                == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "broker-carried route proof strategy does not match dispatch round-trip strategy",
        ),
        _check(
            "route_broker_route_readiness_market_matches",
            _identity_key(row.route_broker_route_readiness_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.route_broker_route_readiness_market)
                and _identity_key(row.dispatch_roundtrip_market)
                and _identity_key(row.route_broker_route_readiness_market)
                == _identity_key(row.dispatch_roundtrip_market)
            ),
            "broker-carried route proof market does not match dispatch round-trip market",
        ),
        _check(
            "route_broker_route_readiness_gap_pairs",
            int(row.route_broker_route_readiness_gap_pairs),
            "<=",
            0,
            int(row.route_broker_route_readiness_gap_pairs) <= 0,
            "broker-carried route proof still reports market/strategy route gaps",
        ),
        _check(
            "route_broker_route_readiness_ops_launch_controls_ready",
            bool(row.route_broker_route_readiness_ops_launch_controls_ready),
            "is",
            True,
            bool(row.route_broker_route_readiness_ops_launch_controls_ready),
            "broker-carried route proof did not preserve launch-grade ops broker controls",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs),
            ">",
            0,
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs) > 0,
            "broker-carried route proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs),
            "<=",
            0,
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs) <= 0,
            "broker-carried route proof reports allocation breach broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs),
            ">",
            0,
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs) > 0,
            "broker-carried route proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs),
            "<=",
            0,
            int(row.route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs) <= 0,
            "broker-carried route proof reports concentration breach broker round-trip runs",
        ),
    ]


def _route_dispatch_roundtrip_checks(row: pd.Series) -> list[dict[str, Any]]:
    return [
        _check(
            "route_dispatch_roundtrip_ready",
            bool(row.route_dispatch_roundtrip_ready),
            "is",
            True,
            bool(row.route_dispatch_roundtrip_ready),
            "dispatch route proof is not ready",
        ),
        _check(
            "route_dispatch_roundtrip_target_mode_matches",
            _identity_key(row.route_dispatch_roundtrip_target_mode),
            "==",
            _identity_key(row.dispatch_roundtrip_target_mode),
            bool(
                _identity_key(row.route_dispatch_roundtrip_target_mode)
                and _identity_key(row.dispatch_roundtrip_target_mode)
                and _identity_key(row.route_dispatch_roundtrip_target_mode)
                == _identity_key(row.dispatch_roundtrip_target_mode)
            ),
            "dispatch route proof target mode does not match dispatch round-trip target",
        ),
        _check(
            "route_dispatch_roundtrip_strategy_matches",
            _identity_key(row.route_dispatch_roundtrip_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.route_dispatch_roundtrip_strategy)
                and _identity_key(row.dispatch_roundtrip_strategy)
                and _identity_key(row.route_dispatch_roundtrip_strategy) == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "dispatch route proof strategy does not match dispatch round-trip strategy",
        ),
        _check(
            "route_dispatch_roundtrip_market_matches",
            _identity_key(row.route_dispatch_roundtrip_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.route_dispatch_roundtrip_market)
                and _identity_key(row.dispatch_roundtrip_market)
                and _identity_key(row.route_dispatch_roundtrip_market) == _identity_key(row.dispatch_roundtrip_market)
            ),
            "dispatch route proof market does not match dispatch round-trip market",
        ),
        _check(
            "route_dispatch_roundtrip_scenario_matches",
            str(row.route_dispatch_roundtrip_scenario_key),
            "==",
            str(row.dispatch_roundtrip_scenario_key),
            bool(
                str(row.route_dispatch_roundtrip_scenario_key)
                and str(row.dispatch_roundtrip_scenario_key)
                and str(row.route_dispatch_roundtrip_scenario_key) == str(row.dispatch_roundtrip_scenario_key)
            ),
            "dispatch route proof scenario does not match dispatch round-trip scenario",
        ),
        _check(
            "route_dispatch_roundtrip_request_count_matches",
            int(row.route_dispatch_roundtrip_requests),
            "==",
            int(row.dispatch_roundtrip_requests),
            int(row.route_dispatch_roundtrip_requests) == int(row.dispatch_roundtrip_requests)
            and int(row.route_dispatch_roundtrip_acked_orders) == int(row.dispatch_roundtrip_acked_orders),
            "dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            "route_dispatch_roundtrip_missing_request_acks",
            int(row.route_dispatch_roundtrip_missing_request_acks),
            "<=",
            0,
            int(row.route_dispatch_roundtrip_missing_request_acks) <= 0,
            "dispatch route proof has missing request acknowledgements",
        ),
        _check(
            "route_dispatch_roundtrip_rejected_orders",
            int(row.route_dispatch_roundtrip_rejected_orders),
            "<=",
            0,
            int(row.route_dispatch_roundtrip_rejected_orders) <= 0,
            "dispatch route proof has rejected orders",
        ),
        _check(
            "route_dispatch_roundtrip_unmatched_acks",
            int(row.route_dispatch_roundtrip_unmatched_acks),
            "<=",
            0,
            int(row.route_dispatch_roundtrip_unmatched_acks) <= 0,
            "dispatch route proof has unmatched acknowledgements",
        ),
    ]


def _shadow_broker_readiness_active(row: Any) -> bool:
    return bool(
        row.shadow_broker_readiness_provided
        or int(row.shadow_broker_readiness_sessions) > 0
        or int(row.shadow_broker_vendor_data_readiness_sessions) > 0
        or int(row.shadow_broker_route_readiness_sessions) > 0
        or int(row.shadow_broker_dispatch_roundtrip_sessions) > 0
        or int(row.shadow_broker_route_dispatch_roundtrip_sessions) > 0
    )


def _shadow_broker_readiness_checks(row: Any) -> list[dict[str, Any]]:
    return [
        _check(
            "shadow_broker_readiness_provided",
            bool(row.shadow_broker_readiness_provided),
            "is",
            True,
            bool(row.shadow_broker_readiness_provided),
            "dispatch round-trip shadow broker-readiness proof is active but not marked provided",
        ),
        _check(
            "shadow_broker_readiness_ready",
            int(row.shadow_broker_readiness_ready_sessions),
            "==",
            int(row.shadow_broker_readiness_sessions),
            int(row.shadow_broker_readiness_sessions) > 0
            and int(row.shadow_broker_readiness_ready_sessions) == int(row.shadow_broker_readiness_sessions),
            "dispatch round-trip shadow broker-readiness proof is not ready",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_present_for_broker_sessions",
            int(row.shadow_broker_vendor_data_readiness_sessions),
            "==",
            int(row.shadow_broker_readiness_sessions),
            int(row.shadow_broker_vendor_data_readiness_sessions) == 0
            or int(row.shadow_broker_vendor_data_readiness_sessions) == int(row.shadow_broker_readiness_sessions),
            "dispatch round-trip shadow broker vendor-data wrapper proof is present for only some broker-readiness sessions",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_provided",
            int(row.shadow_broker_vendor_data_readiness_provided_sessions),
            "==",
            int(row.shadow_broker_readiness_sessions),
            int(row.shadow_broker_vendor_data_readiness_sessions) == 0
            or int(row.shadow_broker_vendor_data_readiness_provided_sessions)
            == int(row.shadow_broker_readiness_sessions),
            "dispatch round-trip shadow broker vendor-data wrapper proof is missing for some broker-readiness sessions",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_ready",
            int(row.shadow_broker_vendor_data_readiness_ready_sessions),
            "==",
            int(row.shadow_broker_readiness_sessions),
            int(row.shadow_broker_vendor_data_readiness_sessions) == 0
            or int(row.shadow_broker_vendor_data_readiness_ready_sessions) == int(row.shadow_broker_readiness_sessions),
            "dispatch round-trip shadow broker vendor-data wrapper proof is not ready",
        ),
        _check(
            "shadow_broker_vendor_data_readiness_failed_checks",
            int(row.shadow_broker_vendor_data_readiness_failed_checks),
            "<=",
            0,
            int(row.shadow_broker_vendor_data_readiness_sessions) == 0
            or int(row.shadow_broker_vendor_data_readiness_failed_checks) <= 0,
            "dispatch round-trip shadow broker vendor-data wrapper proof has failed checks",
        ),
        _check(
            "shadow_broker_adapter_matches",
            _identity_key(row.shadow_broker_adapter),
            "==",
            _identity_key(row.dispatch_roundtrip_adapter if hasattr(row, "dispatch_roundtrip_adapter") else row.adapter),
            _shadow_broker_adapter_matches(row),
            "dispatch round-trip shadow broker adapter does not match broker readiness adapter",
        ),
        _check(
            "shadow_broker_adapter_consistent",
            int(row.shadow_broker_adapter_count),
            "==",
            1,
            int(row.shadow_broker_adapter_count) == 1,
            "dispatch round-trip shadow broker adapter identity is missing or mixed",
        ),
        _check(
            "shadow_broker_route_readiness_ready",
            int(row.shadow_broker_route_readiness_ready_sessions),
            "==",
            int(row.shadow_broker_route_readiness_sessions),
            int(row.shadow_broker_route_readiness_sessions) > 0
            and int(row.shadow_broker_route_readiness_ready_sessions)
            == int(row.shadow_broker_route_readiness_sessions),
            "dispatch round-trip shadow broker route-readiness proof is not ready",
        ),
        _check(
            "shadow_broker_route_readiness_strategy_matches",
            _identity_key(row.shadow_broker_route_readiness_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.shadow_broker_route_readiness_strategy)
                and _identity_key(row.shadow_broker_route_readiness_strategy)
                == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "dispatch round-trip shadow broker route-readiness strategy does not match",
        ),
        _check(
            "shadow_broker_route_readiness_market_matches",
            _identity_key(row.shadow_broker_route_readiness_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.shadow_broker_route_readiness_market)
                and _identity_key(row.shadow_broker_route_readiness_market)
                == _identity_key(row.dispatch_roundtrip_market)
            ),
            "dispatch round-trip shadow broker route-readiness market does not match",
        ),
        _check(
            "shadow_broker_route_readiness_gap_pairs",
            int(row.shadow_broker_route_readiness_gap_pairs),
            "<=",
            0,
            int(row.shadow_broker_route_readiness_gap_pairs) <= 0,
            "dispatch round-trip shadow broker route-readiness proof has route gaps",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_ready",
            int(row.shadow_broker_dispatch_roundtrip_ready_sessions),
            "==",
            int(row.shadow_broker_dispatch_roundtrip_sessions),
            int(row.shadow_broker_dispatch_roundtrip_sessions) > 0
            and int(row.shadow_broker_dispatch_roundtrip_ready_sessions)
            == int(row.shadow_broker_dispatch_roundtrip_sessions),
            "dispatch round-trip shadow broker dispatch proof is not ready",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_strategy_matches",
            _identity_key(row.shadow_broker_dispatch_roundtrip_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.shadow_broker_dispatch_roundtrip_strategy)
                and _identity_key(row.shadow_broker_dispatch_roundtrip_strategy)
                == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "dispatch round-trip shadow broker dispatch proof strategy does not match",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_market_matches",
            _identity_key(row.shadow_broker_dispatch_roundtrip_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.shadow_broker_dispatch_roundtrip_market)
                and _identity_key(row.shadow_broker_dispatch_roundtrip_market)
                == _identity_key(row.dispatch_roundtrip_market)
            ),
            "dispatch round-trip shadow broker dispatch proof market does not match",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_scenario_consistent",
            int(row.shadow_broker_dispatch_roundtrip_scenario_count),
            "==",
            1,
            int(row.shadow_broker_dispatch_roundtrip_scenario_count) == 1,
            "dispatch round-trip shadow broker dispatch proof scenario is missing or mixed",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_missing_request_acks",
            int(row.shadow_broker_dispatch_roundtrip_missing_request_acks),
            "<=",
            0,
            int(row.shadow_broker_dispatch_roundtrip_missing_request_acks) <= 0,
            "dispatch round-trip shadow broker dispatch proof has missing request acknowledgements",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_rejected_orders",
            int(row.shadow_broker_dispatch_roundtrip_rejected_orders),
            "<=",
            0,
            int(row.shadow_broker_dispatch_roundtrip_rejected_orders) <= 0,
            "dispatch round-trip shadow broker dispatch proof has rejected orders",
        ),
        _check(
            "shadow_broker_dispatch_roundtrip_unmatched_acks",
            int(row.shadow_broker_dispatch_roundtrip_unmatched_acks),
            "<=",
            0,
            int(row.shadow_broker_dispatch_roundtrip_unmatched_acks) <= 0,
            "dispatch round-trip shadow broker dispatch proof has unmatched acknowledgements",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_ready",
            int(row.shadow_broker_route_dispatch_roundtrip_ready_sessions),
            "==",
            int(row.shadow_broker_route_dispatch_roundtrip_sessions),
            int(row.shadow_broker_route_dispatch_roundtrip_sessions) > 0
            and int(row.shadow_broker_route_dispatch_roundtrip_ready_sessions)
            == int(row.shadow_broker_route_dispatch_roundtrip_sessions),
            "dispatch round-trip shadow broker route dispatch proof is not ready",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_strategy_matches",
            _identity_key(row.shadow_broker_route_dispatch_roundtrip_strategy),
            "==",
            _identity_key(row.dispatch_roundtrip_strategy),
            bool(
                _identity_key(row.shadow_broker_route_dispatch_roundtrip_strategy)
                and _identity_key(row.shadow_broker_route_dispatch_roundtrip_strategy)
                == _identity_key(row.dispatch_roundtrip_strategy)
            ),
            "dispatch round-trip shadow broker route dispatch proof strategy does not match",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_market_matches",
            _identity_key(row.shadow_broker_route_dispatch_roundtrip_market),
            "==",
            _identity_key(row.dispatch_roundtrip_market),
            bool(
                _identity_key(row.shadow_broker_route_dispatch_roundtrip_market)
                and _identity_key(row.shadow_broker_route_dispatch_roundtrip_market)
                == _identity_key(row.dispatch_roundtrip_market)
            ),
            "dispatch round-trip shadow broker route dispatch proof market does not match",
        ),
        _check(
            "shadow_broker_route_dispatch_roundtrip_scenario_consistent",
            int(row.shadow_broker_route_dispatch_roundtrip_scenario_count),
            "==",
            1,
            int(row.shadow_broker_route_dispatch_roundtrip_scenario_count) == 1,
            "dispatch round-trip shadow broker route dispatch proof scenario is missing or mixed",
        ),
    ]


def _broker_shadow_broker_readiness_active(row: Any) -> bool:
    return bool(
        row.broker_shadow_broker_readiness_provided
        or int(row.broker_shadow_broker_readiness_sessions) > 0
        or int(row.broker_shadow_broker_vendor_data_readiness_sessions) > 0
        or int(row.broker_shadow_broker_route_readiness_sessions) > 0
        or int(row.broker_shadow_broker_dispatch_roundtrip_sessions) > 0
        or int(row.broker_shadow_broker_route_dispatch_roundtrip_sessions) > 0
    )


def _broker_shadow_broker_readiness_checks(row: Any) -> list[dict[str, Any]]:
    projected = _shadow_broker_projection(row, source_prefix="broker_shadow_broker")
    checks: list[dict[str, Any]] = []
    for check in _shadow_broker_readiness_checks(projected):
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


def _dispatch_roundtrip_vendor_market_data_batch_active(row: Any) -> bool:
    return bool(
        row.dispatch_roundtrip_vendor_market_data_batch_provided
        or int(row.dispatch_roundtrip_vendor_market_data_batch_dataset_count) > 0
        or _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_adapter)
        or _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_market)
    )


def _dispatch_roundtrip_vendor_market_data_batch_checks(row: Any) -> list[dict[str, Any]]:
    expected_kind = _vendor_market_data_batch_expected_kind(row)
    vendor_kind = _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_kind)
    manifest_run_type = _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_manifest_run_type)
    expected_market = _vendor_market_data_batch_expected_market(row)
    vendor_market = _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_market)
    checks = [
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_provided",
            bool(row.dispatch_roundtrip_vendor_market_data_batch_provided),
            "is",
            True,
            bool(row.dispatch_roundtrip_vendor_market_data_batch_provided),
            "dispatch round-trip vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_ready",
            bool(row.dispatch_roundtrip_vendor_market_data_batch_ready),
            "is",
            True,
            bool(row.dispatch_roundtrip_vendor_market_data_batch_ready),
            "dispatch round-trip vendor market-data batch proof is not ready",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
            _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_adapter),
            "==",
            _identity_key(row.expected_adapter),
            bool(
                _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_adapter)
                and _identity_key(row.dispatch_roundtrip_vendor_market_data_batch_adapter)
                == _identity_key(row.expected_adapter)
            ),
            "dispatch round-trip vendor market-data adapter does not match broker readiness adapter",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_kind_matches",
            vendor_kind,
            "==" if expected_kind else "present",
            expected_kind if expected_kind else "nonempty kind",
            bool(vendor_kind and (not expected_kind or vendor_kind == expected_kind)),
            "dispatch round-trip vendor market-data kind does not match broker readiness expected kind",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "dispatch round-trip vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_market_matches",
            vendor_market,
            "==" if expected_market else "present",
            expected_market if expected_market else "nonempty market",
            bool(vendor_market and (not expected_market or vendor_market == expected_market)),
            "dispatch round-trip vendor market-data market does not match broker readiness market",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_dataset_count",
            int(row.dispatch_roundtrip_vendor_market_data_batch_dataset_count),
            ">",
            0,
            int(row.dispatch_roundtrip_vendor_market_data_batch_dataset_count) > 0,
            "dispatch round-trip vendor market-data batch has no datasets",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
            int(row.dispatch_roundtrip_vendor_market_data_batch_failed_datasets),
            "<=",
            0,
            int(row.dispatch_roundtrip_vendor_market_data_batch_failed_datasets) <= 0,
            "dispatch round-trip vendor market-data batch has failed datasets",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_source_files",
            int(row.dispatch_roundtrip_vendor_market_data_batch_unique_source_files),
            ">",
            0,
            int(row.dispatch_roundtrip_vendor_market_data_batch_unique_source_files) > 0,
            "dispatch round-trip vendor market-data batch is missing source-file provenance",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
            int(row.dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints),
            ">",
            0,
            int(row.dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints) > 0,
            "dispatch round-trip vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
            row.dispatch_roundtrip_vendor_market_data_batch_mapping_sources,
            "!=",
            "",
            bool(str(row.dispatch_roundtrip_vendor_market_data_batch_mapping_sources).strip()),
            "dispatch round-trip vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
            bool(row.dispatch_roundtrip_vendor_market_data_batch_comparison_accepted),
            "is",
            True,
            bool(row.dispatch_roundtrip_vendor_market_data_batch_comparison_accepted),
            "dispatch round-trip vendor market-data comparison was not accepted",
        ),
        _check(
            "dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
            int(row.dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks),
            "<=",
            0,
            int(row.dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks) <= 0,
            "dispatch round-trip vendor market-data comparison has failed checks",
        ),
    ]
    if _target_application_batch_active(row):
        dataset_count = int(
            row.dispatch_roundtrip_vendor_market_data_batch_dataset_count
        )
        mapping_application_count = int(
            row.dispatch_roundtrip_vendor_market_data_batch_mapping_application_count
        )
        unique_mapping_applications = int(
            row.dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications
        )
        target_application_coverage = float(
            row.dispatch_roundtrip_vendor_market_data_batch_target_application_coverage
        )
        lineage_datasets = _target_application_lineage_dataset_count(row)
        checks.extend(
            [
                _check(
                    "dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
                    _identity_key(
                        row.dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode
                    ),
                    "==",
                    TARGET_APPLICATION_BATCH_MODE,
                    _identity_key(
                        row.dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode
                    )
                    == TARGET_APPLICATION_BATCH_MODE,
                    "dispatch round-trip vendor market-data target applications are missing strict source mode",
                ),
                _check(
                    "dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
                    mapping_application_count,
                    "==",
                    dataset_count,
                    dataset_count > 0 and mapping_application_count == dataset_count,
                    "dispatch round-trip vendor market-data target applications are not aligned one for one",
                ),
                _check(
                    "dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
                    unique_mapping_applications,
                    "==",
                    dataset_count,
                    dataset_count > 0 and unique_mapping_applications == dataset_count,
                    "dispatch round-trip vendor market-data target applications are not distinct per dataset",
                ),
                _check(
                    "dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
                    target_application_coverage,
                    ">=",
                    1.0,
                    target_application_coverage >= 1.0,
                    "dispatch round-trip vendor market-data target-application coverage is incomplete",
                ),
                _check(
                    "dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
                    lineage_datasets,
                    "==",
                    dataset_count,
                    dataset_count > 0 and lineage_datasets == dataset_count,
                    "dispatch round-trip vendor market-data datasets are missing target-application lineage",
                ),
            ]
        )
    return checks


def _target_application_batch_active(row: Any) -> bool:
    mapping_sources = {
        value.strip().lower()
        for value in str(
            row.dispatch_roundtrip_vendor_market_data_batch_mapping_sources
        ).split(";")
        if value.strip()
    }
    return bool(
        _identity_key(
            row.dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode
        )
        == TARGET_APPLICATION_BATCH_MODE
        or "verified_target_application" in mapping_sources
        or int(
            row.dispatch_roundtrip_vendor_market_data_batch_mapping_application_count
        )
        > 0
        or float(
            row.dispatch_roundtrip_vendor_market_data_batch_target_application_coverage
        )
        > 0.0
    )


def _target_application_lineage_dataset_count(row: Any) -> int:
    datasets = _json_list(
        row.dispatch_roundtrip_vendor_market_data_batch_datasets_json
    )
    required_fields = (
        "mapping_application_path",
        "mapping_application_id",
        "mapping_application_sha256",
        "mapping_scope_review_id",
        "mapping_scope_review_sha256",
        "target_intake_receipt_id",
        "applied_mapping_sha256",
    )
    return sum(
        isinstance(dataset, dict)
        and all(_object_text(dataset.get(field)) for field in required_fields)
        for dataset in datasets
    )


def _vendor_market_data_batch_expected_kind(row: Any) -> str:
    return _identity_key(getattr(row, "expected_vendor_data_kind", ""))


def _vendor_market_data_batch_expected_market(row: Any) -> str:
    return _identity_key(getattr(row, "dispatch_roundtrip_market", "")) or _identity_key(
        getattr(row, "expected_market", "")
    )


def _broker_dispatch_roundtrip_vendor_market_data_batch_active(row: Any) -> bool:
    return _dispatch_roundtrip_vendor_market_data_batch_active(
        _vendor_market_data_batch_projection(
            row,
            source_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    )


def _broker_dispatch_roundtrip_vendor_market_data_batch_checks(row: Any) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    projected = _vendor_market_data_batch_projection(
        row,
        source_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    for check in _dispatch_roundtrip_vendor_market_data_batch_checks(projected):
        renamed = dict(check)
        renamed["check"] = str(renamed["check"]).replace(
            "dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
        )
        if "reason" in renamed:
            renamed["reason"] = str(renamed["reason"]).replace(
                "dispatch round-trip vendor market-data",
                "broker-readiness dispatch round-trip vendor market-data",
            )
        checks.append(renamed)
    return checks


def _shadow_broker_projection(row: Any, *, source_prefix: str) -> Any:
    data = row._asdict() if hasattr(row, "_asdict") else dict(vars(row))
    for suffix in (
        "readiness_provided",
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
        data[f"shadow_broker_{suffix}"] = data.get(f"{source_prefix}_{suffix}", "")
    return SimpleNamespace(**data)


def _vendor_market_data_batch_projection(row: Any, *, source_prefix: str) -> Any:
    data = row._asdict() if hasattr(row, "_asdict") else dict(vars(row))
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
        "source_file_fingerprint_coverage",
        "min_mapping_coverage",
        "unique_header_fingerprints",
        "unique_mapping_drafts",
        "mapping_sources",
        "mapping_source_mode",
        "mapping_application_count",
        "unique_mapping_applications",
        "target_application_coverage",
        "comparison_accepted",
        "comparison_failed_checks",
        "datasets_json",
    ):
        data[f"dispatch_roundtrip_vendor_market_data_batch_{suffix}"] = data.get(
            f"{source_prefix}_{suffix}",
            "",
        )
    return SimpleNamespace(**data)


def _shadow_broker_adapter_matches(row: Any) -> bool:
    shadow_adapter = _identity_key(row.shadow_broker_adapter)
    expected_adapter = _identity_key(row.adapter or row.expected_adapter)
    return bool(shadow_adapter and expected_adapter and shadow_adapter == expected_adapter)


def _summary(
    items: pd.DataFrame,
    checks: pd.DataFrame,
    thresholds: BrokerReadinessThresholds,
) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    required_items = items.loc[items["required"].astype(bool)] if not items.empty else pd.DataFrame()
    missing_required = int((~required_items["provided"].astype(bool)).sum()) if not required_items.empty else 0
    ready_items = int(items["ready"].astype(bool).sum()) if not items.empty else 0
    schema_status = adapter_schema_status(thresholds.adapter)
    schema_review = _schema_review_state(items, thresholds)
    ready = failed == 0
    schema_item = _component_item(items, "schema_audit")
    runtime_item = _component_item(items, "runtime_session")
    resume_item = _component_item(items, "resume_gate")
    dispatch_item = _component_item(items, "dispatch_roundtrip")
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": thresholds.adapter,
                "adapter_schema_status": schema_status,
                "schema_reviewed": bool(schema_review["reviewed"]),
                "schema_review_mode": schema_review["mode"],
                "schema_review_checklist_present": _item_bool(schema_item, "schema_review_checklist_present"),
                "schema_review_check_count": int(_number(schema_item, "schema_review_check_count", 0.0)),
                "schema_review_blocked_checks": int(_number(schema_item, "schema_review_blocked_checks", 0.0)),
                "schema_review_review_checks": int(_number(schema_item, "schema_review_review_checks", 0.0)),
                "schema_review_blocked_check_names": _item_text(schema_item, "schema_review_blocked_check_names"),
                "schema_review_review_check_names": _item_text(schema_item, "schema_review_review_check_names"),
                "required_components": int(len(required_items)),
                "provided_components": int(items["provided"].astype(bool).sum()) if not items.empty else 0,
                "ready_components": ready_items,
                "missing_required_components": missing_required,
                "failed_checks": failed,
                "runtime_session_provided": _item_bool(runtime_item, "provided"),
                "runtime_session_ready": _item_bool(runtime_item, "ready"),
                "runtime_guard_action": _item_text(runtime_item, "runtime_guard_action"),
                "runtime_guard_halted": _item_bool(runtime_item, "runtime_guard_halted"),
                "runtime_target_mode": _item_text(runtime_item, "runtime_target_mode"),
                "runtime_strategy": _item_text(runtime_item, "runtime_strategy"),
                "runtime_market": _item_text(runtime_item, "runtime_market"),
                "resume_gate_provided": _item_bool(resume_item, "provided"),
                "resume_gate_ready": _item_bool(resume_item, "ready"),
                "resume_strategy": _item_text(resume_item, "resume_strategy"),
                "resume_market": _item_text(resume_item, "resume_market"),
                "resume_incident_strategy": _item_text(resume_item, "resume_incident_strategy"),
                "resume_incident_market": _item_text(resume_item, "resume_incident_market"),
                "resume_proof_refresh_ready": _item_bool(resume_item, "resume_proof_refresh_ready"),
                "resume_proof_refresh_strategy": _item_text(resume_item, "resume_proof_refresh_strategy"),
                "resume_proof_refresh_market": _item_text(resume_item, "resume_proof_refresh_market"),
                "resume_incident_proof_refresh_strategy": _item_text(
                    resume_item,
                    "resume_incident_proof_refresh_strategy",
                ),
                "resume_incident_proof_refresh_market": _item_text(
                    resume_item,
                    "resume_incident_proof_refresh_market",
                ),
                "resume_broker_route_readiness_required": _item_bool(
                    resume_item,
                    "resume_broker_route_readiness_required",
                ),
                "resume_broker_route_readiness_provided": _item_bool(
                    resume_item,
                    "resume_broker_route_readiness_provided",
                ),
                "resume_broker_route_readiness_ready": _item_bool(
                    resume_item,
                    "resume_broker_route_readiness_ready",
                ),
                "resume_broker_route_readiness_strategy": _item_text(
                    resume_item,
                    "resume_broker_route_readiness_strategy",
                ),
                "resume_broker_route_readiness_market": _item_text(
                    resume_item,
                    "resume_broker_route_readiness_market",
                ),
                "resume_broker_route_readiness_route_ready_pairs": int(
                    _number(resume_item, "resume_broker_route_readiness_route_ready_pairs", 0.0)
                ),
                "resume_broker_route_readiness_gap_pairs": int(
                    _number(resume_item, "resume_broker_route_readiness_gap_pairs", 0.0)
                ),
                "resume_broker_route_readiness_recommendation": _item_text(
                    resume_item,
                    "resume_broker_route_readiness_recommendation",
                ),
                "resume_broker_route_readiness_ops_launch_controls_ready": _item_bool(
                    resume_item,
                    "resume_broker_route_readiness_ops_launch_controls_ready",
                ),
                "resume_broker_route_readiness_ops_launch_control_failures": _item_text(
                    resume_item,
                    "resume_broker_route_readiness_ops_launch_control_failures",
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    _number(
                        resume_item,
                        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                        0.0,
                    )
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    _number(
                        resume_item,
                        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                        0.0,
                    )
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    _number(
                        resume_item,
                        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                        0.0,
                    )
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    _number(
                        resume_item,
                        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        0.0,
                    )
                ),
                "resume_incident_broker_route_readiness_required": _item_bool(
                    resume_item,
                    "resume_incident_broker_route_readiness_required",
                ),
                "resume_incident_broker_route_readiness_provided": _item_bool(
                    resume_item,
                    "resume_incident_broker_route_readiness_provided",
                ),
                "resume_incident_broker_route_readiness_ready": _item_bool(
                    resume_item,
                    "resume_incident_broker_route_readiness_ready",
                ),
                "resume_incident_broker_route_readiness_strategy": _item_text(
                    resume_item,
                    "resume_incident_broker_route_readiness_strategy",
                ),
                "resume_incident_broker_route_readiness_market": _item_text(
                    resume_item,
                    "resume_incident_broker_route_readiness_market",
                ),
                "resume_incident_broker_route_readiness_route_ready_pairs": int(
                    _number(resume_item, "resume_incident_broker_route_readiness_route_ready_pairs", 0.0)
                ),
                "resume_incident_broker_route_readiness_gap_pairs": int(
                    _number(resume_item, "resume_incident_broker_route_readiness_gap_pairs", 0.0)
                ),
                "resume_incident_broker_route_readiness_recommendation": _item_text(
                    resume_item,
                    "resume_incident_broker_route_readiness_recommendation",
                ),
                "resume_incident_broker_route_readiness_ops_launch_controls_ready": _item_bool(
                    resume_item,
                    "resume_incident_broker_route_readiness_ops_launch_controls_ready",
                ),
                "resume_incident_broker_route_readiness_ops_launch_control_failures": _item_text(
                    resume_item,
                    "resume_incident_broker_route_readiness_ops_launch_control_failures",
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    _number(
                        resume_item,
                        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                        0.0,
                    )
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    _number(
                        resume_item,
                        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                        0.0,
                    )
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    _number(
                        resume_item,
                        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                        0.0,
                    )
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    _number(
                        resume_item,
                        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        0.0,
                    )
                ),
                "dispatch_roundtrip_provided": _item_bool(dispatch_item, "provided"),
                "dispatch_roundtrip_ready": _item_bool(dispatch_item, "ready"),
                "dispatch_roundtrip_target_mode": _item_text(dispatch_item, "dispatch_roundtrip_target_mode"),
                "dispatch_roundtrip_strategy": _item_text(dispatch_item, "dispatch_roundtrip_strategy"),
                "dispatch_roundtrip_market": _item_text(dispatch_item, "dispatch_roundtrip_market"),
                "dispatch_roundtrip_scenario_key": _item_text(dispatch_item, "dispatch_roundtrip_scenario_key"),
                "dispatch_roundtrip_batch_id": _item_text(dispatch_item, "dispatch_roundtrip_batch_id"),
                "dispatch_roundtrip_requests": int(_number(dispatch_item, "dispatch_roundtrip_requests", 0.0)),
                "dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_item, "dispatch_roundtrip_acked_orders", 0.0)
                ),
                "dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_item, "dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_item, "dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_item, "dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "dispatch_roundtrip_failed_checks": int(
                    _number(dispatch_item, "dispatch_roundtrip_failed_checks", 0.0)
                ),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    _number(dispatch_item, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
                ),
                "broker_vendor_data_readiness_provided": _item_bool(
                    dispatch_item,
                    "broker_vendor_data_readiness_provided",
                ),
                "broker_vendor_data_readiness_ready": _item_bool(
                    dispatch_item,
                    "broker_vendor_data_readiness_ready",
                ),
                "broker_vendor_data_readiness_failed_checks": int(
                    _number(dispatch_item, "broker_vendor_data_readiness_failed_checks", 0.0)
                ),
                "route_readiness_required": _item_bool(dispatch_item, "route_readiness_required"),
                "route_readiness_provided": _item_bool(dispatch_item, "route_readiness_provided"),
                "route_readiness_ready": _item_bool(dispatch_item, "route_readiness_ready"),
                "route_readiness_strategy": _item_text(dispatch_item, "route_readiness_strategy"),
                "route_readiness_market": _item_text(dispatch_item, "route_readiness_market"),
                "route_readiness_route_ready_pairs": int(
                    _number(dispatch_item, "route_readiness_route_ready_pairs", 0.0)
                ),
                "route_readiness_gap_pairs": int(_number(dispatch_item, "route_readiness_gap_pairs", 0.0)),
                "route_readiness_recommendation": _item_text(dispatch_item, "route_readiness_recommendation"),
                "route_readiness_ops_legacy_counts_present": _item_bool(
                    dispatch_item,
                    "route_readiness_ops_legacy_counts_present",
                ),
                "route_readiness_ops_launch_controls_present": _item_bool(
                    dispatch_item,
                    "route_readiness_ops_launch_controls_present",
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": int(
                    _number(dispatch_item, "route_readiness_ops_launch_controls_blocked_pairs", 0.0)
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    _number(dispatch_item, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0)
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    _number(
                        dispatch_item,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                        0.0,
                    )
                ),
                "route_readiness_ops_launch_controls_ready": _item_bool(
                    dispatch_item,
                    "route_readiness_ops_launch_controls_ready",
                ),
                "route_readiness_ops_launch_control_failures": _item_text(
                    dispatch_item,
                    "route_readiness_ops_launch_control_failures",
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    _number(dispatch_item, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    _number(dispatch_item, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    _number(
                        dispatch_item,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                        0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    _number(
                        dispatch_item,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        0.0,
                    )
                ),
                "route_broker_route_readiness_required": _item_bool(
                    dispatch_item,
                    "route_broker_route_readiness_required",
                ),
                "route_broker_route_readiness_provided": _item_bool(
                    dispatch_item,
                    "route_broker_route_readiness_provided",
                ),
                "route_broker_route_readiness_ready": _item_bool(
                    dispatch_item,
                    "route_broker_route_readiness_ready",
                ),
                "route_broker_route_readiness_strategy": _item_text(
                    dispatch_item,
                    "route_broker_route_readiness_strategy",
                ),
                "route_broker_route_readiness_market": _item_text(
                    dispatch_item,
                    "route_broker_route_readiness_market",
                ),
                "route_broker_route_readiness_route_ready_pairs": int(
                    _number(dispatch_item, "route_broker_route_readiness_route_ready_pairs", 0.0)
                ),
                "route_broker_route_readiness_gap_pairs": int(
                    _number(dispatch_item, "route_broker_route_readiness_gap_pairs", 0.0)
                ),
                "route_broker_route_readiness_recommendation": _item_text(
                    dispatch_item,
                    "route_broker_route_readiness_recommendation",
                ),
                "route_broker_route_readiness_ops_launch_controls_ready": _item_bool(
                    dispatch_item,
                    "route_broker_route_readiness_ops_launch_controls_ready",
                ),
                "route_broker_route_readiness_ops_launch_control_failures": _item_text(
                    dispatch_item,
                    "route_broker_route_readiness_ops_launch_control_failures",
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    _number(dispatch_item, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    _number(
                        dispatch_item,
                        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                        0.0,
                    )
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    _number(
                        dispatch_item,
                        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                        0.0,
                    )
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    _number(
                        dispatch_item,
                        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        0.0,
                    )
                ),
                "route_dispatch_roundtrip_required": _item_bool(dispatch_item, "route_dispatch_roundtrip_required"),
                "route_dispatch_roundtrip_provided": _item_bool(dispatch_item, "route_dispatch_roundtrip_provided"),
                "route_dispatch_roundtrip_ready": _item_bool(dispatch_item, "route_dispatch_roundtrip_ready"),
                "route_dispatch_roundtrip_target_mode": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_target_mode",
                ),
                "route_dispatch_roundtrip_strategy": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_strategy",
                ),
                "route_dispatch_roundtrip_market": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_market",
                ),
                "route_dispatch_roundtrip_scenario_key": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_scenario_key",
                ),
                "route_dispatch_roundtrip_batch_id": _item_text(
                    dispatch_item,
                    "route_dispatch_roundtrip_batch_id",
                ),
                "route_dispatch_roundtrip_requests": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_requests", 0.0)
                ),
                "route_dispatch_roundtrip_acked_orders": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_acked_orders", 0.0)
                ),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "route_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "route_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_item, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "shadow_broker_readiness_provided": _item_bool(dispatch_item, "shadow_broker_readiness_provided"),
                "shadow_broker_readiness_sessions": int(
                    _number(dispatch_item, "shadow_broker_readiness_sessions", 0.0)
                ),
                "shadow_broker_readiness_ready_sessions": int(
                    _number(dispatch_item, "shadow_broker_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_sessions": int(
                    _number(dispatch_item, "shadow_broker_vendor_data_readiness_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    _number(dispatch_item, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    _number(dispatch_item, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    _number(dispatch_item, "shadow_broker_vendor_data_readiness_failed_checks", 0.0)
                ),
                "shadow_broker_adapter": _item_text(dispatch_item, "shadow_broker_adapter"),
                "shadow_broker_adapter_count": int(_number(dispatch_item, "shadow_broker_adapter_count", 0.0)),
                "shadow_broker_route_readiness_sessions": int(
                    _number(dispatch_item, "shadow_broker_route_readiness_sessions", 0.0)
                ),
                "shadow_broker_route_readiness_ready_sessions": int(
                    _number(dispatch_item, "shadow_broker_route_readiness_ready_sessions", 0.0)
                ),
                "shadow_broker_route_readiness_strategy": _item_text(
                    dispatch_item,
                    "shadow_broker_route_readiness_strategy",
                ),
                "shadow_broker_route_readiness_market": _item_text(
                    dispatch_item,
                    "shadow_broker_route_readiness_market",
                ),
                "shadow_broker_route_readiness_gap_pairs": int(
                    _number(dispatch_item, "shadow_broker_route_readiness_gap_pairs", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    _number(dispatch_item, "shadow_broker_dispatch_roundtrip_sessions", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    _number(dispatch_item, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_strategy": _item_text(
                    dispatch_item,
                    "shadow_broker_dispatch_roundtrip_strategy",
                ),
                "shadow_broker_dispatch_roundtrip_market": _item_text(
                    dispatch_item,
                    "shadow_broker_dispatch_roundtrip_market",
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    _number(dispatch_item, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    _number(dispatch_item, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    _number(dispatch_item, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0)
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    _number(dispatch_item, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    _number(dispatch_item, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    _number(dispatch_item, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": _item_text(
                    dispatch_item,
                    "shadow_broker_route_dispatch_roundtrip_strategy",
                ),
                "shadow_broker_route_dispatch_roundtrip_market": _item_text(
                    dispatch_item,
                    "shadow_broker_route_dispatch_roundtrip_market",
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    _number(dispatch_item, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0)
                ),
                **_prefixed_shadow_broker_summary_fields(
                    dispatch_item,
                    field_prefix="broker_shadow_broker",
                ),
                **_vendor_market_data_batch_summary_fields(dispatch_item),
                **_vendor_market_data_batch_summary_fields(
                    dispatch_item,
                    field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
                ),
                "recommendation": _summary_recommendation(ready, schema_status, schema_review, thresholds),
            }
        ]
    )


def _vendor_market_data_batch_summary_fields(
    item: pd.Series,
    *,
    field_prefix: str = "dispatch_roundtrip_vendor_market_data_batch",
) -> dict[str, Any]:
    return {
        f"{field_prefix}_provided": _item_bool(item, f"{field_prefix}_provided"),
        f"{field_prefix}_ready": _item_bool(item, f"{field_prefix}_ready"),
        f"{field_prefix}_adapter": _item_text(item, f"{field_prefix}_adapter"),
        f"{field_prefix}_kind": _item_text(item, f"{field_prefix}_kind"),
        f"{field_prefix}_manifest_run_type": _item_text(item, f"{field_prefix}_manifest_run_type"),
        f"{field_prefix}_market": _item_text(item, f"{field_prefix}_market"),
        f"{field_prefix}_dataset_count": int(_number(item, f"{field_prefix}_dataset_count", 0.0)),
        f"{field_prefix}_ready_datasets": int(_number(item, f"{field_prefix}_ready_datasets", 0.0)),
        f"{field_prefix}_failed_datasets": int(_number(item, f"{field_prefix}_failed_datasets", 0.0)),
        f"{field_prefix}_ready_rate": _number(item, f"{field_prefix}_ready_rate", 0.0),
        f"{field_prefix}_unique_source_files": int(_number(item, f"{field_prefix}_unique_source_files", 0.0)),
        f"{field_prefix}_source_file_fingerprint_coverage": _number(
            item,
            f"{field_prefix}_source_file_fingerprint_coverage",
            0.0,
        ),
        f"{field_prefix}_min_mapping_coverage": _number(item, f"{field_prefix}_min_mapping_coverage", 0.0),
        f"{field_prefix}_unique_header_fingerprints": int(
            _number(item, f"{field_prefix}_unique_header_fingerprints", 0.0)
        ),
        f"{field_prefix}_unique_mapping_drafts": int(_number(item, f"{field_prefix}_unique_mapping_drafts", 0.0)),
        f"{field_prefix}_mapping_sources": _item_text(item, f"{field_prefix}_mapping_sources"),
        f"{field_prefix}_mapping_source_mode": _item_text(
            item,
            f"{field_prefix}_mapping_source_mode",
        ),
        f"{field_prefix}_mapping_application_count": int(
            _number(item, f"{field_prefix}_mapping_application_count", 0.0)
        ),
        f"{field_prefix}_unique_mapping_applications": int(
            _number(item, f"{field_prefix}_unique_mapping_applications", 0.0)
        ),
        f"{field_prefix}_target_application_coverage": _number(
            item,
            f"{field_prefix}_target_application_coverage",
            0.0,
        ),
        f"{field_prefix}_comparison_accepted": _item_bool(item, f"{field_prefix}_comparison_accepted"),
        f"{field_prefix}_comparison_failed_checks": int(
            _number(item, f"{field_prefix}_comparison_failed_checks", 0.0)
        ),
        f"{field_prefix}_datasets_json": _item_text(item, f"{field_prefix}_datasets_json"),
    }


def _prefixed_shadow_broker_summary_fields(item: pd.Series, *, field_prefix: str) -> dict[str, Any]:
    return {
        f"{field_prefix}_readiness_provided": _item_bool(item, f"{field_prefix}_readiness_provided"),
        f"{field_prefix}_readiness_sessions": int(_number(item, f"{field_prefix}_readiness_sessions", 0.0)),
        f"{field_prefix}_readiness_ready_sessions": int(
            _number(item, f"{field_prefix}_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_sessions": int(
            _number(item, f"{field_prefix}_vendor_data_readiness_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_provided_sessions": int(
            _number(item, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_ready_sessions": int(
            _number(item, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_vendor_data_readiness_failed_checks": int(
            _number(item, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0)
        ),
        f"{field_prefix}_adapter": _item_text(item, f"{field_prefix}_adapter"),
        f"{field_prefix}_adapter_count": int(_number(item, f"{field_prefix}_adapter_count", 0.0)),
        f"{field_prefix}_route_readiness_sessions": int(
            _number(item, f"{field_prefix}_route_readiness_sessions", 0.0)
        ),
        f"{field_prefix}_route_readiness_ready_sessions": int(
            _number(item, f"{field_prefix}_route_readiness_ready_sessions", 0.0)
        ),
        f"{field_prefix}_route_readiness_strategy": _item_text(
            item,
            f"{field_prefix}_route_readiness_strategy",
        ),
        f"{field_prefix}_route_readiness_market": _item_text(
            item,
            f"{field_prefix}_route_readiness_market",
        ),
        f"{field_prefix}_route_readiness_gap_pairs": int(
            _number(item, f"{field_prefix}_route_readiness_gap_pairs", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_sessions": int(
            _number(item, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_ready_sessions": int(
            _number(item, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_strategy": _item_text(
            item,
            f"{field_prefix}_dispatch_roundtrip_strategy",
        ),
        f"{field_prefix}_dispatch_roundtrip_market": _item_text(
            item,
            f"{field_prefix}_dispatch_roundtrip_market",
        ),
        f"{field_prefix}_dispatch_roundtrip_scenario_count": int(
            _number(item, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_missing_request_acks": int(
            _number(item, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_rejected_orders": int(
            _number(item, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0)
        ),
        f"{field_prefix}_dispatch_roundtrip_unmatched_acks": int(
            _number(item, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_sessions": int(
            _number(item, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_ready_sessions": int(
            _number(item, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0)
        ),
        f"{field_prefix}_route_dispatch_roundtrip_strategy": _item_text(
            item,
            f"{field_prefix}_route_dispatch_roundtrip_strategy",
        ),
        f"{field_prefix}_route_dispatch_roundtrip_market": _item_text(
            item,
            f"{field_prefix}_route_dispatch_roundtrip_market",
        ),
        f"{field_prefix}_route_dispatch_roundtrip_scenario_count": int(
            _number(item, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0)
        ),
    }


def _config(
    items: pd.DataFrame,
    checks: pd.DataFrame,
    summary: pd.DataFrame,
    action_queue: pd.DataFrame,
    thresholds: BrokerReadinessThresholds,
) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    failed_checks = (
        [str(check) for check in checks.loc[~checks["passed"].astype(bool), "check"].tolist()]
        if not checks.empty and "passed" in checks.columns
        else []
    )
    ready_actions = _actions_with_status(action_queue, "ready")
    blocked_actions = _actions_with_status(action_queue, "blocked")
    primary_action = _first_action_record(action_queue)
    return {
        "ready": _item_bool(row, "ready"),
        "adapter": _item_text(row, "adapter"),
        "adapter_schema_status": _item_text(row, "adapter_schema_status"),
        "schema_reviewed": _item_bool(row, "schema_reviewed"),
        "schema_review_mode": _item_text(row, "schema_review_mode"),
        "schema_review_checklist": {
            "provided": _item_bool(row, "schema_review_checklist_present"),
            "check_count": int(_number(row, "schema_review_check_count", 0.0)),
            "blocked_checks": int(_number(row, "schema_review_blocked_checks", 0.0)),
            "review_checks": int(_number(row, "schema_review_review_checks", 0.0)),
            "blocked_check_names": _split_names(_item_text(row, "schema_review_blocked_check_names")),
            "review_check_names": _split_names(_item_text(row, "schema_review_review_check_names")),
        },
        "recommendation": _item_text(row, "recommendation"),
        "thresholds": asdict(thresholds),
        "component_counts": {
            "required": int(_number(row, "required_components", 0.0)),
            "provided": int(_number(row, "provided_components", 0.0)),
            "ready": int(_number(row, "ready_components", 0.0)),
            "missing_required": int(_number(row, "missing_required_components", 0.0)),
            "failed_checks": int(_number(row, "failed_checks", 0.0)),
        },
        "failed_checks": failed_checks,
        "ready_action_count": int(len(ready_actions)),
        "blocked_action_count": int(len(blocked_actions)),
        "next_gate": _first_action_value(action_queue, "next_gate"),
        "next_gate_help_command": _first_action_value(action_queue, "next_gate_help_command"),
        "primary_action_status": _action_value(primary_action.get("queue_status")),
        "primary_action": primary_action,
        "next_actions": _action_records(action_queue),
        "ready_actions": _action_records(ready_actions),
        "blocked_actions": _action_records(blocked_actions),
        "components": {
            component: _component_config(items, component)
            for component in SUMMARY_FILES
        },
        "runtime_session": _runtime_session_config(row),
        "resume_gate": _resume_gate_config(row),
        "dispatch_roundtrip": _dispatch_roundtrip_config(row),
        "shadow_broker_readiness": _prefixed_shadow_broker_config(row, field_prefix="shadow_broker"),
        "broker_shadow_broker_readiness": _prefixed_shadow_broker_config(
            row,
            field_prefix="broker_shadow_broker",
        ),
    }


def _action_queue(checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not checks.empty and "passed" in checks.columns:
        failed = checks.loc[~checks["passed"].astype(bool)].reset_index(drop=True)
        for priority, row in enumerate(failed.to_dict(orient="records"), start=1):
            check_name = str(row.get("check", ""))
            component = _action_component(check_name)
            next_gate = BROKER_READINESS_NEXT_GATES.get(component, "review-broker-readiness")
            rows.append(
                {
                    "priority": priority,
                    "queue_status": "blocked",
                    "check": check_name,
                    "component": component,
                    "next_gate": next_gate,
                    "next_gate_help_command": _help_command(next_gate),
                    "actual": _action_value(row.get("value")),
                    "operator": _action_value(row.get("operator")),
                    "expected": _action_value(row.get("threshold")),
                    "reason": str(row.get("reason", "")),
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "priority",
            "queue_status",
            "check",
            "component",
            "next_gate",
            "next_gate_help_command",
            "actual",
            "operator",
            "expected",
            "reason",
        ],
    )


def _first_action_record(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    return _jsonable_record(frame.iloc[0].to_dict())


def _action_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_jsonable_record(row) for row in frame.to_dict(orient="records")]


def _actions_with_status(action_queue: pd.DataFrame, status: str) -> pd.DataFrame:
    if action_queue.empty or "queue_status" not in action_queue.columns:
        return action_queue.iloc[0:0].copy()
    return action_queue.loc[action_queue["queue_status"].astype(str) == status].copy()


def _jsonable_record(row: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Path):
            record[str(key)] = str(value)
            continue
        try:
            if pd.isna(value):
                record[str(key)] = None
                continue
        except (TypeError, ValueError):
            pass
        record[str(key)] = value
    return record


def _first_action_value(action_queue: pd.DataFrame, column: str) -> str:
    if action_queue.empty or column not in action_queue.columns:
        return ""
    return _action_value(action_queue.iloc[0].get(column))


def _action_component(check_name: str) -> str:
    prefixes = [
        ("route_enable_dispatch_roundtrip_", "route_enable"),
        ("route_dispatch_roundtrip_", "dispatch_roundtrip"),
        ("route_broker_route_readiness_", "route_readiness"),
        ("route_readiness_", "route_readiness"),
        ("resume_incident_broker_route_readiness_", "route_readiness"),
        ("resume_broker_route_readiness_", "route_readiness"),
        ("broker_vendor_data_readiness_", "vendor_market_data"),
        ("dispatch_roundtrip_vendor_market_data_batch_", "vendor_market_data"),
        ("broker_dispatch_roundtrip_vendor_market_data_batch_", "vendor_market_data"),
        ("shadow_broker_", "broker_readiness"),
        ("broker_shadow_broker_", "broker_readiness"),
        ("schema_reviewed", "schema_audit"),
        ("schema_audit_", "schema_audit"),
        ("order_export_", "order_export"),
        ("mapping_draft_", "mapping_draft"),
        ("mapped_orders_", "mapped_orders"),
        ("upload_pack_", "upload_pack"),
        ("halt_export_", "halt_export"),
        ("reconciliation_", "reconciliation"),
        ("runtime_session_", "runtime_session"),
        ("resume_gate_", "resume_gate"),
        ("dispatch_roundtrip_", "dispatch_roundtrip"),
    ]
    for prefix, component in prefixes:
        if check_name == prefix or check_name.startswith(prefix):
            return component
    return "broker_readiness"


def _help_command(next_gate: str) -> str:
    return f"python -m hft_cli {next_gate} --help" if next_gate else ""


def _action_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _runbook_markdown(summary: pd.DataFrame, items: pd.DataFrame, action_queue: pd.DataFrame) -> str:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    lines = [
        "# Broker Readiness Runbook",
        "",
        f"- Ready: {_yes_no(_item_bool(row, 'ready'))}",
        f"- Adapter: {_item_text(row, 'adapter')}",
        f"- Recommendation: {_item_text(row, 'recommendation')}",
        f"- Schema review mode: {_item_text(row, 'schema_review_mode')}",
        f"- Failed checks: {int(_number(row, 'failed_checks', 0.0))}",
        f"- Missing required components: {int(_number(row, 'missing_required_components', 0.0))}",
        f"- Schema blocked checks: {_item_text(row, 'schema_review_blocked_check_names')}",
        f"- Schema review checks: {_item_text(row, 'schema_review_review_check_names')}",
        "",
        "## Components",
        "",
        _components_table(items),
        "",
        "## Blocked Actions",
        "",
        _action_queue_table(action_queue),
        "",
    ]
    return "\n".join(lines)


def _components_table(items: pd.DataFrame) -> str:
    if items.empty:
        return "_None_"
    rows = [
        [
            _item_text(row, "component"),
            _yes_no(_item_bool(row, "required")),
            _yes_no(_item_bool(row, "provided")),
            _yes_no(_item_bool(row, "ready")),
            _item_text(row, "recommendation"),
        ]
        for _, row in items.iterrows()
    ]
    return _markdown_table(["Component", "Required", "Provided", "Ready", "Recommendation"], rows)


def _action_queue_table(action_queue: pd.DataFrame) -> str:
    if action_queue.empty:
        return "_None_"
    rows = [
        [
            str(int(_number(row, "priority", 0.0))),
            _item_text(row, "check"),
            _item_text(row, "component"),
            _item_text(row, "next_gate"),
            _item_text(row, "next_gate_help_command"),
            _item_text(row, "reason"),
        ]
        for _, row in action_queue.iterrows()
    ]
    return _markdown_table(["Priority", "Check", "Component", "Next gate", "Help", "Reason"], rows)


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_"
    header = "| " + " | ".join(_escape_cell(value) for value in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_cell(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _component_config(items: pd.DataFrame, component: str) -> dict[str, Any]:
    item = _component_item(items, component)
    return {
        "required": _item_bool(item, "required"),
        "provided": _item_bool(item, "provided"),
        "ready": _item_bool(item, "ready"),
        "recommendation": _item_text(item, "recommendation"),
        "source_file": _item_text(item, "source_file"),
    }


def _runtime_session_config(row: pd.Series) -> dict[str, Any]:
    return {
        "provided": _item_bool(row, "runtime_session_provided"),
        "ready": _item_bool(row, "runtime_session_ready"),
        "guard_action": _item_text(row, "runtime_guard_action"),
        "guard_halted": _item_bool(row, "runtime_guard_halted"),
        "target_mode": _item_text(row, "runtime_target_mode"),
        "strategy": _item_text(row, "runtime_strategy"),
        "market": _item_text(row, "runtime_market"),
    }


def _resume_gate_config(row: pd.Series) -> dict[str, Any]:
    return {
        "provided": _item_bool(row, "resume_gate_provided"),
        "ready": _item_bool(row, "resume_gate_ready"),
        "strategy": _item_text(row, "resume_strategy"),
        "market": _item_text(row, "resume_market"),
        "incident_strategy": _item_text(row, "resume_incident_strategy"),
        "incident_market": _item_text(row, "resume_incident_market"),
        "proof_refresh": {
            "ready": _item_bool(row, "resume_proof_refresh_ready"),
            "strategy": _item_text(row, "resume_proof_refresh_strategy"),
            "market": _item_text(row, "resume_proof_refresh_market"),
            "incident_strategy": _item_text(row, "resume_incident_proof_refresh_strategy"),
            "incident_market": _item_text(row, "resume_incident_proof_refresh_market"),
        },
        "broker_route_readiness": _resume_broker_route_readiness_config(
            row,
            prefix="resume_broker_route_readiness",
        ),
        "incident_broker_route_readiness": _resume_broker_route_readiness_config(
            row,
            prefix="resume_incident_broker_route_readiness",
        ),
    }


def _resume_broker_route_readiness_config(row: pd.Series, *, prefix: str) -> dict[str, Any]:
    return {
        "required": _item_bool(row, f"{prefix}_required"),
        "provided": _item_bool(row, f"{prefix}_provided"),
        "ready": _item_bool(row, f"{prefix}_ready"),
        "strategy": _item_text(row, f"{prefix}_strategy"),
        "market": _item_text(row, f"{prefix}_market"),
        "route_ready_pairs": int(_number(row, f"{prefix}_route_ready_pairs", 0.0)),
        "gap_pairs": int(_number(row, f"{prefix}_gap_pairs", 0.0)),
        "recommendation": _item_text(row, f"{prefix}_recommendation"),
        "ops_launch_controls_ready": _item_bool(row, f"{prefix}_ops_launch_controls_ready"),
        "ops_launch_control_failures": _item_text(row, f"{prefix}_ops_launch_control_failures"),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(row, f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(row, f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(row, f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0)
        ),
    }


def _dispatch_roundtrip_config(row: pd.Series) -> dict[str, Any]:
    return {
        "provided": _item_bool(row, "dispatch_roundtrip_provided"),
        "ready": _item_bool(row, "dispatch_roundtrip_ready"),
        "target_mode": _item_text(row, "dispatch_roundtrip_target_mode"),
        "strategy": _item_text(row, "dispatch_roundtrip_strategy"),
        "market": _item_text(row, "dispatch_roundtrip_market"),
        "scenario_key": _item_text(row, "dispatch_roundtrip_scenario_key"),
        "batch_id": _item_text(row, "dispatch_roundtrip_batch_id"),
        "requests": int(_number(row, "dispatch_roundtrip_requests", 0.0)),
        "acked_orders": int(_number(row, "dispatch_roundtrip_acked_orders", 0.0)),
        "missing_request_acks": int(_number(row, "dispatch_roundtrip_missing_request_acks", 0.0)),
        "rejected_orders": int(_number(row, "dispatch_roundtrip_rejected_orders", 0.0)),
        "unmatched_acks": int(_number(row, "dispatch_roundtrip_unmatched_acks", 0.0)),
        "failed_checks": int(_number(row, "dispatch_roundtrip_failed_checks", 0.0)),
        "route_enable_dispatch_roundtrip": {
            "failed_checks": int(_number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)),
        },
        "broker_vendor_data_readiness": {
            "provided": _item_bool(row, "broker_vendor_data_readiness_provided"),
            "ready": _item_bool(row, "broker_vendor_data_readiness_ready"),
            "failed_checks": int(_number(row, "broker_vendor_data_readiness_failed_checks", 0.0)),
        },
        "route_readiness": {
            "required": _item_bool(row, "route_readiness_required"),
            "provided": _item_bool(row, "route_readiness_provided"),
            "ready": _item_bool(row, "route_readiness_ready"),
            "strategy": _item_text(row, "route_readiness_strategy"),
            "market": _item_text(row, "route_readiness_market"),
            "route_ready_pairs": int(_number(row, "route_readiness_route_ready_pairs", 0.0)),
            "gap_pairs": int(_number(row, "route_readiness_gap_pairs", 0.0)),
            "recommendation": _item_text(row, "route_readiness_recommendation"),
            "ops_launch_controls_present": _item_bool(row, "route_readiness_ops_launch_controls_present"),
            "ops_launch_controls_blocked_pairs": int(
                _number(row, "route_readiness_ops_launch_controls_blocked_pairs", 0.0)
            ),
            "ops_broker_roundtrip_portfolio_breach_pairs": int(
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0)
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs", 0.0)
            ),
            "ops_legacy_counts_present": _item_bool(row, "route_readiness_ops_legacy_counts_present"),
            "ops_launch_controls_ready": _item_bool(row, "route_readiness_ops_launch_controls_ready"),
            "ops_launch_control_failures": _item_text(row, "route_readiness_ops_launch_control_failures"),
            "ops_broker_roundtrip_portfolio_safe_runs": int(
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": int(
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0)
            ),
        },
        "route_broker_route_readiness": _route_broker_route_readiness_config(row),
        "route_dispatch_roundtrip": {
            "required": _item_bool(row, "route_dispatch_roundtrip_required"),
            "provided": _item_bool(row, "route_dispatch_roundtrip_provided"),
            "ready": _item_bool(row, "route_dispatch_roundtrip_ready"),
            "target_mode": _item_text(row, "route_dispatch_roundtrip_target_mode"),
            "strategy": _item_text(row, "route_dispatch_roundtrip_strategy"),
            "market": _item_text(row, "route_dispatch_roundtrip_market"),
            "scenario_key": _item_text(row, "route_dispatch_roundtrip_scenario_key"),
            "batch_id": _item_text(row, "route_dispatch_roundtrip_batch_id"),
            "requests": int(_number(row, "route_dispatch_roundtrip_requests", 0.0)),
            "acked_orders": int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0)),
            "missing_request_acks": int(
                _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0)
            ),
            "rejected_orders": int(_number(row, "route_dispatch_roundtrip_rejected_orders", 0.0)),
            "unmatched_acks": int(_number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0)),
        },
        "vendor_market_data_batch": _vendor_market_data_batch_config(row),
        "broker_dispatch_roundtrip_vendor_market_data_batch": _vendor_market_data_batch_config(
            row,
            field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
        ),
    }


def _route_broker_route_readiness_config(row: pd.Series) -> dict[str, Any]:
    return {
        "required": _item_bool(row, "route_broker_route_readiness_required"),
        "provided": _item_bool(row, "route_broker_route_readiness_provided"),
        "ready": _item_bool(row, "route_broker_route_readiness_ready"),
        "strategy": _item_text(row, "route_broker_route_readiness_strategy"),
        "market": _item_text(row, "route_broker_route_readiness_market"),
        "route_ready_pairs": int(_number(row, "route_broker_route_readiness_route_ready_pairs", 0.0)),
        "gap_pairs": int(_number(row, "route_broker_route_readiness_gap_pairs", 0.0)),
        "recommendation": _item_text(row, "route_broker_route_readiness_recommendation"),
        "ops_launch_controls_ready": _item_bool(
            row,
            "route_broker_route_readiness_ops_launch_controls_ready",
        ),
        "ops_launch_control_failures": _item_text(
            row,
            "route_broker_route_readiness_ops_launch_control_failures",
        ),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(row, "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(
                row,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(
                row,
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        ),
    }


def _vendor_market_data_batch_config(
    row: pd.Series,
    *,
    field_prefix: str = "dispatch_roundtrip_vendor_market_data_batch",
) -> dict[str, Any]:
    return {
        "provided": _item_bool(row, f"{field_prefix}_provided"),
        "ready": _item_bool(row, f"{field_prefix}_ready"),
        "adapter": _item_text(row, f"{field_prefix}_adapter"),
        "kind": _item_text(row, f"{field_prefix}_kind"),
        "manifest_run_type": _item_text(row, f"{field_prefix}_manifest_run_type"),
        "market": _item_text(row, f"{field_prefix}_market"),
        "dataset_count": int(_number(row, f"{field_prefix}_dataset_count", 0.0)),
        "ready_datasets": int(_number(row, f"{field_prefix}_ready_datasets", 0.0)),
        "failed_datasets": int(_number(row, f"{field_prefix}_failed_datasets", 0.0)),
        "ready_rate": _jsonable(_number(row, f"{field_prefix}_ready_rate", 0.0)),
        "unique_source_files": int(_number(row, f"{field_prefix}_unique_source_files", 0.0)),
        "source_file_fingerprint_coverage": _jsonable(
            _number(row, f"{field_prefix}_source_file_fingerprint_coverage", 0.0)
        ),
        "min_mapping_coverage": _jsonable(_number(row, f"{field_prefix}_min_mapping_coverage", 0.0)),
        "unique_header_fingerprints": int(_number(row, f"{field_prefix}_unique_header_fingerprints", 0.0)),
        "unique_mapping_drafts": int(_number(row, f"{field_prefix}_unique_mapping_drafts", 0.0)),
        "mapping_sources": _item_text(row, f"{field_prefix}_mapping_sources"),
        "mapping_source_mode": _item_text(row, f"{field_prefix}_mapping_source_mode"),
        "mapping_application_count": int(
            _number(row, f"{field_prefix}_mapping_application_count", 0.0)
        ),
        "unique_mapping_applications": int(
            _number(row, f"{field_prefix}_unique_mapping_applications", 0.0)
        ),
        "target_application_coverage": _jsonable(
            _number(row, f"{field_prefix}_target_application_coverage", 0.0)
        ),
        "comparison": {
            "accepted": _item_bool(row, f"{field_prefix}_comparison_accepted"),
            "failed_checks": int(_number(row, f"{field_prefix}_comparison_failed_checks", 0.0)),
        },
        "datasets": _json_list(_item_text(row, f"{field_prefix}_datasets_json")),
    }


def _prefixed_shadow_broker_config(row: pd.Series, *, field_prefix: str) -> dict[str, Any]:
    return {
        "provided": _item_bool(row, f"{field_prefix}_readiness_provided"),
        "sessions": int(_number(row, f"{field_prefix}_readiness_sessions", 0.0)),
        "ready_sessions": int(_number(row, f"{field_prefix}_readiness_ready_sessions", 0.0)),
        "adapter": _item_text(row, f"{field_prefix}_adapter"),
        "adapter_count": int(_number(row, f"{field_prefix}_adapter_count", 0.0)),
        "broker_vendor_data_readiness": {
            "sessions": int(_number(row, f"{field_prefix}_vendor_data_readiness_sessions", 0.0)),
            "provided_sessions": int(
                _number(row, f"{field_prefix}_vendor_data_readiness_provided_sessions", 0.0)
            ),
            "ready_sessions": int(_number(row, f"{field_prefix}_vendor_data_readiness_ready_sessions", 0.0)),
            "failed_checks": int(_number(row, f"{field_prefix}_vendor_data_readiness_failed_checks", 0.0)),
        },
        "route_readiness": {
            "sessions": int(_number(row, f"{field_prefix}_route_readiness_sessions", 0.0)),
            "ready_sessions": int(_number(row, f"{field_prefix}_route_readiness_ready_sessions", 0.0)),
            "strategy": _item_text(row, f"{field_prefix}_route_readiness_strategy"),
            "market": _item_text(row, f"{field_prefix}_route_readiness_market"),
            "max_gap_pairs": int(_number(row, f"{field_prefix}_route_readiness_gap_pairs", 0.0)),
        },
        "dispatch_roundtrip": {
            "sessions": int(_number(row, f"{field_prefix}_dispatch_roundtrip_sessions", 0.0)),
            "ready_sessions": int(
                _number(row, f"{field_prefix}_dispatch_roundtrip_ready_sessions", 0.0)
            ),
            "strategy": _item_text(row, f"{field_prefix}_dispatch_roundtrip_strategy"),
            "market": _item_text(row, f"{field_prefix}_dispatch_roundtrip_market"),
            "scenario_count": int(_number(row, f"{field_prefix}_dispatch_roundtrip_scenario_count", 0.0)),
            "max_missing_request_acks": int(
                _number(row, f"{field_prefix}_dispatch_roundtrip_missing_request_acks", 0.0)
            ),
            "max_rejected_orders": int(
                _number(row, f"{field_prefix}_dispatch_roundtrip_rejected_orders", 0.0)
            ),
            "max_unmatched_acks": int(
                _number(row, f"{field_prefix}_dispatch_roundtrip_unmatched_acks", 0.0)
            ),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(_number(row, f"{field_prefix}_route_dispatch_roundtrip_sessions", 0.0)),
            "ready_sessions": int(
                _number(row, f"{field_prefix}_route_dispatch_roundtrip_ready_sessions", 0.0)
            ),
            "strategy": _item_text(row, f"{field_prefix}_route_dispatch_roundtrip_strategy"),
            "market": _item_text(row, f"{field_prefix}_route_dispatch_roundtrip_market"),
            "scenario_count": int(
                _number(row, f"{field_prefix}_route_dispatch_roundtrip_scenario_count", 0.0)
            ),
        },
    }


def _schema_review_state(items: pd.DataFrame, thresholds: BrokerReadinessThresholds) -> dict[str, Any]:
    schema_status = adapter_schema_status(thresholds.adapter)
    if schema_status != "placeholder_normalized_pending_vendor_schema":
        return {"reviewed": True, "mode": "native_schema"}
    schema_item = _component_item(items, "schema_audit")
    mapping_item = _component_item(items, "mapping_draft")
    mapped_item = _component_item(items, "mapped_orders")
    mapping_reviewed = all(
        [
            _item_bool(schema_item, "provided"),
            _item_bool(schema_item, "ready"),
            _item_bool(schema_item, "adapter_match"),
            _item_bool(mapping_item, "provided"),
            _item_bool(mapping_item, "ready"),
            _item_bool(mapping_item, "adapter_match"),
            _item_bool(mapped_item, "provided"),
            _item_bool(mapped_item, "ready"),
            _item_bool(mapped_item, "adapter_match"),
        ]
    )
    if mapping_reviewed:
        return {"reviewed": True, "mode": "reviewed_vendor_mapping"}
    return {"reviewed": False, "mode": "placeholder_unreviewed"}


def _component_required(component: str, thresholds: BrokerReadinessThresholds) -> bool:
    return bool(
        {
            "schema_audit": thresholds.require_schema_audit,
            "order_export": thresholds.require_order_export,
            "mapping_draft": thresholds.require_mapping_draft,
            "mapped_orders": thresholds.require_mapped_orders,
            "upload_pack": thresholds.require_upload_pack,
            "halt_export": thresholds.require_halt_export,
            "reconciliation": thresholds.require_reconciliation,
            "runtime_session": thresholds.require_runtime_session,
            "resume_gate": thresholds.require_resume_gate,
            "dispatch_roundtrip": thresholds.require_dispatch_roundtrip or thresholds.require_route_readiness,
        }[component]
    )


def _component_ready(component: str, row: pd.Series) -> bool:
    if component == "schema_audit":
        return _to_bool(row.get("all_required_present", False))
    if component == "reconciliation":
        return _to_bool(row.get("passed", False))
    if component == "runtime_session":
        return _to_bool(row.get("ready", False)) and not _guard_halted(row)
    if component == "resume_gate":
        return _to_bool(row.get("ready", False))
    if component == "dispatch_roundtrip":
        return _to_bool(row.get("passed", False)) and int(_number(row, "failed_checks", 0.0)) <= 0
    return _to_bool(row.get("ready", False))


def _component_recommendation(component: str, provided: bool, ready: bool, required: bool) -> str:
    if not provided and required:
        return f"run_{component}"
    if not provided:
        return "optional_not_supplied"
    if not ready:
        return f"fix_{component}"
    return "accepted"


def _summary_recommendation(
    ready: bool,
    schema_status: str,
    schema_review: dict[str, Any],
    thresholds: BrokerReadinessThresholds,
) -> str:
    if (
        ready
        and schema_status == "placeholder_normalized_pending_vendor_schema"
        and schema_review.get("mode") != "reviewed_vendor_mapping"
    ):
        return "dry_run_only_until_vendor_schema_review"
    if ready:
        return "broker_integration_ready"
    if (
        thresholds.require_reviewed_schema
        and schema_status == "placeholder_normalized_pending_vendor_schema"
        and not bool(schema_review.get("reviewed"))
    ):
        return "obtain_vendor_schema_samples"
    return "fix_broker_readiness_gaps"


def _component_item(items: pd.DataFrame, component: str) -> pd.Series:
    if items.empty or "component" not in items.columns:
        return pd.Series(dtype=object)
    matches = items.loc[items["component"] == component]
    return matches.iloc[0] if not matches.empty else pd.Series(dtype=object)


def _item_bool(item: pd.Series, column: str) -> bool:
    if item.empty or column not in item.index:
        return False
    return _to_bool(item[column])


def _item_text(item: pd.Series, column: str) -> str:
    if item.empty or column not in item.index or pd.isna(item[column]):
        return ""
    return str(item[column])


def _split_names(value: str) -> list[str]:
    return [part for part in str(value).split(";") if part]


def _runtime_text(component: str, row: pd.Series, column: str) -> str:
    if component != "runtime_session" or row.empty:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _resume_text(component: str, row: pd.Series, column: str) -> str:
    if component != "resume_gate" or row.empty:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _resume_bool(component: str, row: pd.Series, column: str) -> bool:
    if component != "resume_gate" or row.empty:
        return False
    return _to_bool(row.get(column, False))


def _resume_number(component: str, row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if component != "resume_gate" or row.empty:
        return float(fallback)
    return _number(row, column, fallback)


def _dispatch_text(component: str, row: pd.Series, column: str) -> str:
    if component != "dispatch_roundtrip" or row.empty:
        return ""
    value = row.get(column, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _dispatch_bool(component: str, row: pd.Series, column: str) -> bool:
    if component != "dispatch_roundtrip" or row.empty:
        return False
    return _to_bool(row.get(column, False))


def _dispatch_bool_any(component: str, row: pd.Series, *columns: str) -> bool:
    if component != "dispatch_roundtrip" or row.empty:
        return False
    return any(_to_bool(row.get(column, False)) for column in columns if column in row.index)


def _dispatch_route_readiness_legacy_ops_present(component: str, row: pd.Series) -> bool:
    if component != "dispatch_roundtrip" or row.empty:
        return False
    legacy_flag = row.get("route_readiness_ops_legacy_counts_present")
    if _route_readiness_legacy_value_present(legacy_flag):
        return _to_bool(legacy_flag)
    return any(
        _route_readiness_legacy_value_present(row.get(column))
        for column in (
            "route_readiness_ops_launch_controls_ready",
            "route_readiness_ops_launch_control_failures",
            "route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            "route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
        )
        if column in row.index
    )


def _route_readiness_legacy_value_present(value: Any) -> bool:
    if value is None:
        return False
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _dispatch_text_any(component: str, row: pd.Series, *columns: str) -> str:
    if component != "dispatch_roundtrip" or row.empty:
        return ""
    for column in columns:
        if column not in row.index:
            continue
        text = _object_text(row.get(column, ""))
        if text:
            return text
    return ""


def _dispatch_number_any(component: str, row: pd.Series, *columns: str, fallback: float = 0.0) -> float:
    if component != "dispatch_roundtrip" or row.empty:
        return float(fallback)
    for column in columns:
        if column not in row.index:
            continue
        parsed = pd.to_numeric(row.get(column), errors="coerce")
        if not pd.isna(parsed):
            return float(parsed)
    return float(fallback)


def _route_dispatch_roundtrip_required(row: Any) -> bool:
    return bool(
        row.route_dispatch_roundtrip_required
        or _identity_key(row.dispatch_roundtrip_target_mode) == "live_dryrun"
    )


def _route_readiness_required(row: Any, thresholds: BrokerReadinessThresholds) -> bool:
    return bool(
        thresholds.require_route_readiness
        or row.route_readiness_required
        or _identity_key(row.dispatch_roundtrip_target_mode) == "live_dryrun"
    )


def _read_optional_summary(path: str | Path | None, component: str) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = _summary_path(path, component)
    if not candidate.exists():
        raise FileNotFoundError(f"{component} summary not found: {candidate}")
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"{component} summary is empty: {candidate}")
    return frame


def _read_optional_schema_review_checklist(path: str | Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    candidate = _config_path(path, SCHEMA_REVIEW_CHECKLIST_FILE)
    if not candidate.exists():
        return None
    frame = pd.read_csv(candidate)
    if frame.empty:
        raise ValueError(f"schema review checklist is empty: {candidate}")
    return frame


def _summary_path(path: str | Path, component: str) -> Path:
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / SUMMARY_FILES[component]
    if direct.exists():
        return direct
    return next(
        (
            nested
            for folder in SUMMARY_FALLBACK_DIRS.get(component, ())
            if (nested := candidate / folder / SUMMARY_FILES[component]).exists()
        ),
        direct,
    )


def _manifest_summary_input(path: str | Path | None, component: str) -> Path | None:
    if path is None:
        return None
    summary_path = _summary_path(path, component)
    return summary_path if summary_path.exists() else Path(path)


def _manifest_config_input(path: str | Path | None, file_name: str) -> Path | None:
    if path is None:
        return None
    candidate = _config_path(path, file_name)
    return candidate if candidate.exists() else None


def _read_optional_config(path: str | Path | None, file_name: str) -> dict[str, Any]:
    if path is None:
        return {}
    candidate = _config_path(path, file_name)
    if not candidate.exists():
        return {}
    return json.loads(candidate.read_text(encoding="utf-8"))


def _read_required_optional_config(
    path: str | Path | None,
    file_name: str,
    *,
    component: str,
) -> dict[str, Any]:
    if path is None:
        return {}
    candidate = _config_path(path, file_name)
    if not candidate.exists():
        raise FileNotFoundError(f"{component} config not found: {candidate}")
    return json.loads(candidate.read_text(encoding="utf-8"))


def _read_vendor_market_data_batch_config(
    path: str | Path | None,
    file_name: str,
) -> dict[str, Any]:
    config = _read_required_optional_config(
        path,
        file_name,
        component="vendor market-data batch",
    )
    if not config:
        return {}
    manifest = _read_required_optional_config(
        path,
        "manifest.json",
        component="vendor market-data batch",
    )
    enriched = dict(config)
    enriched["manifest_run_type"] = str(manifest.get("run_type", ""))
    return enriched


def _dispatch_roundtrip_config_with_vendor_market_data_batch(
    dispatch_roundtrip_config: dict[str, Any],
    vendor_market_data_batch_config: dict[str, Any],
    broker_vendor_data_readiness_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(dispatch_roundtrip_config)
    if broker_vendor_data_readiness_config:
        merged["broker_vendor_data_readiness"] = dict(broker_vendor_data_readiness_config)
        for key, value in _broker_vendor_data_dispatch_roundtrip_config(
            broker_vendor_data_readiness_config
        ).items():
            merged.setdefault(key, value)
    if not vendor_market_data_batch_config:
        return merged
    vendor = dict(vendor_market_data_batch_config)
    merged["roundtrip_vendor_market_data_batch"] = vendor
    merged["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    return merged


def _broker_vendor_data_dispatch_roundtrip_config(config: dict[str, Any]) -> dict[str, Any]:
    broker_readiness = config.get("broker_readiness", {}) or {}
    candidates = [
        config.get("dispatch_roundtrip", {}),
        broker_readiness.get("dispatch_roundtrip", {}) if isinstance(broker_readiness, dict) else {},
    ]
    promoted: dict[str, Any] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in (
            "route_readiness",
            "route_broker_route_readiness",
            "route_enable_dispatch_roundtrip",
        ):
            value = candidate.get(key, {})
            if isinstance(value, dict) and value and key not in promoted:
                promoted[key] = dict(value)
    return promoted


def _resolve_vendor_market_data_batch_dir(path: str | Path | None) -> str | Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir() and not (candidate / "vendor_market_data_batch_config.json").exists():
        nested = candidate / "01_vendor_market_data_batch"
        if (nested / "vendor_market_data_batch_config.json").exists():
            return nested
    return path


def _config_path(path: str | Path, file_name: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        return candidate / file_name
    if candidate.name == file_name:
        return candidate
    return candidate.with_name(file_name)


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _validate_thresholds(thresholds: BrokerReadinessThresholds) -> None:
    get_adapter(thresholds.adapter)


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    value = row.get(column, fallback)
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_value(value: object, fallback: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _object_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _identity_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


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


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            pass
    return value


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        return _json_list(parsed)
    return []


def _vendor_market_data_batch_datasets(value: object) -> list[dict[str, object]]:
    datasets = _json_list(value)
    clean: list[dict[str, object]] = []
    for dataset in datasets:
        if isinstance(dataset, dict):
            clean.append({str(key): _jsonable(nested) for key, nested in dataset.items()})
    return clean


def _guard_halted(row: pd.Series) -> bool:
    return _to_bool(row.get("halted", False)) or str(row.get("guard_action", "")).strip().lower() == "halt"


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
