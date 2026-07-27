from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.leadlag_lineage import (
    LEADLAG_LINEAGE_FIELDS,
    leadlag_lineage_field_matches,
    leadlag_lineage_fields,
    leadlag_lineage_ready,
)
from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    cutover_lineage_fields,
    cutover_lineage_manifest_inputs,
    empty_cutover_lineage,
    load_cutover_lineage,
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
CUTOVER_LINEAGE_OUTPUT_COLUMNS = tuple(
    cutover_lineage_fields(empty_cutover_lineage()).keys()
)
STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    "leadlag_edge_lineage_required",
    *LEADLAG_LINEAGE_FIELDS,
    "leadlag_edge_lineage_matches_scaleup",
)
STRATEGY_PORTFOLIO_LEADLAG_OUTPUT_FIELDS = (
    *STRATEGY_PORTFOLIO_LEADLAG_FIELDS,
    "leadlag_cutover_contract_consistent",
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
CUTOVER_FINAL_LINEAGE_COMPARISON_KEY = (
    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_FINAL_LINEAGE_FIELD_PREFIX = (
    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
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
)
CUTOVER_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
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
)
ROUTE_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    *CUTOVER_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "cutover_final_review_carried_application_lineage_sha256",
    "route_final_review_carried_application_lineage_sha256",
    "dispatch_final_review_carried_application_lineage_sha256",
    "send_final_review_carried_application_lineage_sha256",
    "ack_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_complete_final_review_carried_application_lineage_sha256",
)
ROUTE_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_COMPARISON_KEY = (
    "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX = (
    "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_SUMMARY_FIELD_PREFIX = (
    "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS: tuple[str, ...] = (
    *CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "scaleup_complete_final_review_carried_application_lineage_sha256",
    "cutover_complete_final_review_carried_application_lineage_sha256",
    "route_complete_final_review_carried_application_lineage_sha256",
    "dispatch_complete_final_review_carried_application_lineage_sha256",
    "send_complete_final_review_carried_application_lineage_sha256",
    "ack_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
)
ROUTE_EXTENDED_COMPLETE_FINAL_LINEAGE_37_COMPARISON_KEY = (
    "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_COMPARISON_KEY = (
    "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX = (
    "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_SUMMARY_FIELD_PREFIX = (
    "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_DIGEST_FIELDS: tuple[str, ...] = (
    *CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS,
    "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
ROUTE_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_45_COMPARISON_KEY = (
    "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_COMPARISON_KEY = (
    "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX = (
    "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_SUMMARY_FIELD_PREFIX = (
    "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS: tuple[
    str, ...
] = (
    *CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS,
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS: tuple[
    str, ...
] = (
    "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "route_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
ROUTE_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_53_COMPARISON_KEY = (
    "route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_COMPARISON_KEY = (
    "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX = (
    "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SUMMARY_FIELD_PREFIX = (
    "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS: tuple[
    str, ...
] = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS: tuple[
    str, ...
] = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS: tuple[
    str, ...
] = (
    "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD = (
    "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD = (
    "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
ROUTE_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_61_COMPARISON_KEY = (
    "route_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_COMPARISON_KEY = (
    "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX = (
    "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SUMMARY_FIELD_PREFIX = (
    "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS: tuple[
    str, ...
] = CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS: tuple[
    str, ...
] = CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS: tuple[
    str, ...
] = CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS: tuple[
    str, ...
] = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD = (
    "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD = (
    "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD = (
    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD = (
    "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD = (
    "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
ROUTE_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_69_COMPARISON_KEY = (
    "route_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_COMPARISON_KEY = (
    "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_FIELD_PREFIX = (
    "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_SUMMARY_FIELD_PREFIX = (
    "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CONFIRMED_REVIEW_FIELDS: tuple[
    str, ...
] = (
    "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD = (
    "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
ROUTE_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_77_COMPARISON_KEY = (
    "route_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)


@dataclass(frozen=True)
class RouteEnableThresholds:
    target_mode: str = "live_dryrun"
    require_cutover_ready: bool = True
    require_upload_ready: bool = True
    require_order_export_ready: bool = False
    require_adapter_match: bool = True
    require_route_readiness: bool = False
    require_dispatch_roundtrip: bool = False
    min_orders: int = 1


@dataclass(frozen=True)
class RouteEnableReport:
    packet: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_route_enable_packet(
    *,
    cutover_summary: pd.DataFrame,
    cutover_config: dict[str, Any] | None = None,
    upload_summary: pd.DataFrame,
    order_export_summary: pd.DataFrame | None = None,
    cutover_lineage: dict[str, Any] | None = None,
    thresholds: RouteEnableThresholds | None = None,
) -> RouteEnableReport:
    thresholds = thresholds or RouteEnableThresholds()
    _validate_thresholds(thresholds)
    cutover_summary = _require_nonempty(cutover_summary, "cutover_summary")
    upload_summary = _require_nonempty(upload_summary, "upload_summary")
    order_export_summary = _optional_frame(order_export_summary)
    cutover_config = cutover_config or {}

    state = {
        "cutover": _cutover_state(
            cutover_summary.iloc[0],
            cutover_config,
            cutover_lineage or empty_cutover_lineage(),
        ),
        "upload": _upload_state(upload_summary.iloc[0]),
        "order_export": _order_export_state(order_export_summary),
    }
    checks = _checks(state, thresholds)
    packet = _packet(state, thresholds, checks)
    action_queue = _action_queue(packet.iloc[0], checks)
    summary = _summary_with_actions(_summary(packet.iloc[0], checks), checks, action_queue)
    config = _config(packet.iloc[0], thresholds, checks, action_queue)
    return RouteEnableReport(
        packet=packet,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_route_enable_packet(
    *,
    cutover_dir: str | Path,
    upload_pack_dir: str | Path,
    output_dir: str | Path,
    order_export_dir: str | Path | None = None,
    thresholds: RouteEnableThresholds | None = None,
) -> RouteEnableReport:
    thresholds = thresholds or RouteEnableThresholds()
    _validate_thresholds(thresholds)
    cutover = Path(cutover_dir)
    upload = Path(upload_pack_dir)
    cutover_config_path = cutover / "cutover_config.json" if cutover.is_dir() else Path(cutover_dir)
    upload_summary_path = _summary_path(
        upload,
        "broker_upload_summary.csv",
        fallback_dirs=("05_upload_pack", "04_upload_pack"),
    )
    order_export_summary_path = (
        _summary_path(
            order_export_dir,
            "broker_order_summary.csv",
            fallback_dirs=("04_export", "03_export"),
        )
        if order_export_dir is not None
        else None
    )
    if not cutover_config_path.exists():
        raise FileNotFoundError(f"cutover config not found: {cutover_config_path}")
    cutover_summary_path = (
        cutover / "cutover_summary.csv" if cutover.is_dir() else cutover_config_path.with_name("cutover_summary.csv")
    )
    cutover_manifest_path = _sidecar_path(cutover_dir, "manifest.json")
    cutover_lineage = load_cutover_lineage(cutover_config_path)
    cutover_config = json.loads(cutover_config_path.read_text(encoding="utf-8"))
    broker_readiness_config_path = _manifest_input_path(cutover_manifest_path, "broker_readiness_config")
    if broker_readiness_config_path is not None:
        cutover_config = _with_broker_readiness_config_vendor_market_data_batch(
            cutover_config,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    report = evaluate_route_enable_packet(
        cutover_summary=_read_required(cutover_summary_path, "cutover_summary"),
        cutover_config=cutover_config,
        upload_summary=_read_required(upload_summary_path, "broker_upload_summary"),
        order_export_summary=(
            _read_optional(order_export_summary_path) if order_export_summary_path is not None else None
        ),
        cutover_lineage=cutover_lineage,
        thresholds=thresholds,
    )
    out = Path(output_dir).resolve()
    _reject_input_output_collision(
        out,
        {
            "cutover": cutover_config_path,
            "upload pack": upload_summary_path,
            "order export": order_export_summary_path,
        },
    )
    out.mkdir(parents=True, exist_ok=True)
    report.packet.to_csv(out / "route_enable_packet.csv", index=False)
    report.checks.to_csv(out / "route_enable_checks.csv", index=False)
    report.summary.to_csv(out / "route_enable_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(
        report.packet.iloc[0], report.checks
    )
    action_queue.to_csv(out / "route_enable_action_queue.csv", index=False)
    (out / "route_enable_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out / "route_enable_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "cutover_summary": cutover_summary_path,
        "cutover_config": cutover_config_path,
        "upload_pack": upload_summary_path,
    }
    if cutover_manifest_path is not None:
        inputs["cutover_manifest"] = cutover_manifest_path
    if order_export_summary_path is not None:
        inputs["order_export"] = (
            order_export_summary_path if order_export_summary_path.exists() else Path(order_export_dir)
        )
    inputs.update(cutover_lineage_manifest_inputs(cutover_lineage))
    write_experiment_manifest(
        out,
        run_type="route_enable_packet",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
        extra={
            "ready": bool(report.ready),
            **_strategy_portfolio_leadlag_summary_fields(
                report.summary.iloc[0]
            ),
            **cutover_lineage_fields(cutover_lineage),
            "authorizes_submission": False,
        },
    )
    return RouteEnableReport(
        packet=report.packet,
        checks=report.checks,
        summary=report.summary,
        config=report.config,
        output_dir=out,
        action_queue=action_queue,
    )


def _checks(state: dict[str, dict[str, Any]], thresholds: RouteEnableThresholds) -> pd.DataFrame:
    cutover = state["cutover"]
    upload = state["upload"]
    order_export = state["order_export"]
    target_mode = _identity_key(thresholds.target_mode)
    upload_orders = int(upload["orders"])
    max_orders = int(cutover["max_orders_per_session"])
    max_notional = float(cutover["max_notional_per_session"])
    export_notional = float(order_export["total_notional"])
    route_readiness_required = _route_readiness_required(thresholds, cutover)
    route_readiness_active = bool(route_readiness_required or cutover["route_readiness_provided"])
    checks = [
        _check(
            "cutover_ready",
            cutover["ready"],
            "is",
            True,
            bool(cutover["ready"]) or not thresholds.require_cutover_ready,
            "cutover gate is not ready",
        ),
        _check(
            "target_mode_matches",
            cutover["target_mode"],
            "==",
            target_mode,
            bool(cutover["target_mode"] and cutover["target_mode"] == target_mode),
            "cutover target mode does not match route-enable target mode",
        ),
        _check(
            "cutover_dispatch_roundtrip_provided",
            cutover["dispatch_roundtrip_provided"],
            "is",
            True,
            bool(cutover["dispatch_roundtrip_provided"]) or not _dispatch_roundtrip_required(thresholds),
            "route enable requires cutover with dry-run dispatch round-trip proof",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_provided",
            cutover["route_dispatch_roundtrip_provided"],
            "is",
            True,
            bool(cutover["route_dispatch_roundtrip_provided"]) or not _route_dispatch_roundtrip_required(
                thresholds,
                cutover,
            ),
            "route enable requires cutover with dispatch route proof",
        ),
    ]
    if cutover["cutover_lineage_required"]:
        checks.extend(
            [
                _check(
                    "cutover_lineage_provided",
                    cutover["cutover_lineage_provided"],
                    "is",
                    True,
                    bool(cutover["cutover_lineage_provided"]),
                    "cutover lineage evidence is required but missing",
                ),
                _check(
                    "cutover_manifest_current",
                    cutover["cutover_manifest_current"],
                    "is",
                    True,
                    bool(cutover["cutover_manifest_current"]),
                    "cutover manifest is missing, stale, or incomplete",
                ),
                _check(
                    "cutover_scaleup_manifest_required",
                    cutover["cutover_scaleup_manifest_required"],
                    "is",
                    True,
                    bool(cutover["cutover_scaleup_manifest_required"]),
                    "cutover does not require sealed scale-up provenance",
                ),
                _check(
                    "cutover_scaleup_provenance_gate_passed",
                    cutover["cutover_scaleup_provenance_gate_passed"],
                    "is",
                    True,
                    bool(cutover["cutover_scaleup_provenance_gate_passed"]),
                    "cutover did not retain a valid scale-up provenance gate",
                ),
                _check(
                    "cutover_scaleup_source_bound",
                    cutover["cutover_scaleup_source_bound"],
                    "is",
                    True,
                    bool(cutover["cutover_scaleup_source_bound"]),
                    "cutover does not bind the scale-up source needed for recursive verification",
                ),
                _check(
                    "cutover_current_scaleup_provenance_gate_passed",
                    cutover[
                        "cutover_current_scaleup_provenance_gate_passed"
                    ],
                    "is",
                    True,
                    bool(
                        cutover[
                            "cutover_current_scaleup_provenance_gate_passed"
                        ]
                    ),
                    "the current scale-up source provenance gate did not pass",
                ),
                _check(
                    "cutover_scaleup_provenance_matches_current",
                    cutover["cutover_scaleup_provenance_matches_current"],
                    "is",
                    True,
                    bool(
                        cutover["cutover_scaleup_provenance_matches_current"]
                    ),
                    "cutover scale-up provenance no longer matches its current source",
                ),
                _check(
                    "cutover_lineage_contract_consistent",
                    cutover["cutover_lineage_contract_consistent"],
                    "is",
                    True,
                    bool(cutover["cutover_lineage_contract_consistent"]),
                    "cutover summary, config, and manifest lineage disagree",
                ),
                _check(
                    "cutover_non_authorizing",
                    cutover["cutover_non_authorizing"],
                    "is",
                    True,
                    bool(cutover["cutover_non_authorizing"]),
                    "cutover lineage contains an authorizing claim",
                ),
                _check(
                    "cutover_runtime_lineage_gate_passed",
                    cutover["cutover_runtime_lineage_gate_passed"],
                    "is",
                    True,
                    bool(cutover["cutover_runtime_lineage_gate_passed"]),
                    "cutover did not retain a valid runtime-session lineage gate",
                ),
            ]
        )
        if cutover[
            "cutover_current_scaleup_proof_refresh_active"
        ]:
            checks.extend(
                [
                    _check(
                        "cutover_current_scaleup_proof_refresh_source_semantically_verified",
                        cutover[
                            "cutover_current_scaleup_proof_refresh_"
                            "source_semantically_verified"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "cutover_current_scaleup_proof_refresh_"
                                "source_semantically_verified"
                            ]
                        ),
                        "current scale-up proof-refresh source failed semantic verification",
                    ),
                    _check(
                        "cutover_current_scaleup_proof_refresh_source_provenance_gate_passed",
                        cutover[
                            "cutover_current_scaleup_proof_refresh_"
                            "source_provenance_gate_passed"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "cutover_current_scaleup_proof_refresh_"
                                "source_provenance_gate_passed"
                            ]
                        ),
                        "current scale-up proof-refresh source provenance gate did not pass",
                    ),
                    _check(
                        "cutover_current_scaleup_proof_refresh_matches_current",
                        cutover[
                            "cutover_current_scaleup_proof_refresh_matches_current"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "cutover_current_scaleup_proof_refresh_matches_current"
                            ]
                        ),
                        "current scale-up proof-refresh lineage does not match its source",
                    ),
                ]
            )
        if cutover["cutover_broker_readiness_required"]:
            checks.extend(
                [
                    _check(
                        "cutover_runtime_lineage_source_bound",
                        cutover["cutover_runtime_lineage_source_bound"],
                        "is",
                        True,
                        bool(cutover["cutover_runtime_lineage_source_bound"]),
                        (
                            "cutover does not bind the runtime, scale-up, and "
                            "broker-readiness sources needed for recursive verification"
                        ),
                    ),
                    _check(
                        "cutover_runtime_lineage_matches_current",
                        cutover["cutover_runtime_lineage_matches_current"],
                        "is",
                        True,
                        bool(cutover["cutover_runtime_lineage_matches_current"]),
                        (
                            "cutover runtime lineage no longer matches the current "
                            "recursively verified source"
                        ),
                    ),
                    _check(
                        "cutover_broker_readiness_source_matches_scaleup",
                        cutover[
                            "cutover_broker_readiness_source_matches_scaleup"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "cutover_broker_readiness_source_matches_scaleup"
                            ]
                        ),
                        "cutover broker readiness is not the source bound by scale-up",
                    ),
                    _check(
                        "cutover_broker_readiness_matches_current",
                        cutover["cutover_broker_readiness_matches_current"],
                        "is",
                        True,
                        bool(cutover["cutover_broker_readiness_matches_current"]),
                        (
                            "cutover broker-readiness lineage no longer matches the "
                            "current recursive source"
                        ),
                    ),
                ]
            )
            if cutover["cutover_runtime_contract_identity_active"]:
                runtime_identity_sha256 = str(
                    cutover[
                        (
                            "cutover_runtime_telemetry_broker_readiness_"
                            "roundtrip_contract_identity_sha256"
                        )
                    ]
                ).strip()
                current_identity_sha256 = str(
                    cutover[
                        "cutover_current_runtime_contract_identity_sha256"
                    ]
                ).strip()
                checks.extend(
                    [
                        _check(
                            (
                                "cutover_runtime_telemetry_broker_readiness_"
                                "roundtrip_contract_identity_sha256_present"
                            ),
                            runtime_identity_sha256,
                            "present",
                            True,
                            bool(runtime_identity_sha256),
                            (
                                "cutover runtime contract identity digest "
                                "is missing"
                            ),
                        ),
                        _check(
                            (
                                "cutover_runtime_telemetry_broker_readiness_"
                                "roundtrip_contract_identity_sha256_"
                                "matches_current"
                            ),
                            runtime_identity_sha256,
                            "==",
                            current_identity_sha256,
                            bool(
                                runtime_identity_sha256
                                and current_identity_sha256
                                and runtime_identity_sha256
                                == current_identity_sha256
                            ),
                            (
                                "cutover runtime contract identity digest "
                                "differs from current broker readiness"
                            ),
                        ),
                        _check(
                            (
                                "cutover_runtime_"
                                "contract_identity_matches_current"
                            ),
                            cutover[
                                "cutover_runtime_contract_identity_matches_current"
                            ],
                            "is",
                            True,
                            bool(
                                cutover[
                                    "cutover_runtime_contract_identity_matches_current"
                                ]
                            ),
                            (
                                "cutover contract identity no longer matches "
                                "the current recursive broker-readiness source"
                            ),
                        ),
                    ]
                )
            if cutover["cutover_runtime_route_contract_identity_active"]:
                runtime_route_identity_sha256 = str(
                    cutover[
                        (
                            "cutover_runtime_telemetry_broker_readiness_"
                            "route_contract_identity_sha256"
                        )
                    ]
                ).strip()
                current_route_identity_sha256 = str(
                    cutover[
                        "cutover_current_runtime_route_contract_identity_sha256"
                    ]
                ).strip()
                checks.extend(
                    [
                        _check(
                            (
                                "cutover_runtime_telemetry_broker_readiness_"
                                "route_contract_identity_sha256_present"
                            ),
                            runtime_route_identity_sha256,
                            "present",
                            True,
                            bool(runtime_route_identity_sha256),
                            (
                                "cutover runtime route contract identity "
                                "digest is missing"
                            ),
                        ),
                        _check(
                            (
                                "cutover_runtime_telemetry_broker_readiness_"
                                "route_contract_identity_sha256_"
                                "matches_current"
                            ),
                            runtime_route_identity_sha256,
                            "==",
                            current_route_identity_sha256,
                            bool(
                                runtime_route_identity_sha256
                                and current_route_identity_sha256
                                and runtime_route_identity_sha256
                                == current_route_identity_sha256
                            ),
                            (
                                "cutover runtime route contract identity "
                                "differs from current broker readiness"
                            ),
                        ),
                        _check(
                            (
                                "cutover_runtime_route_contract_identity_"
                                "matches_current"
                            ),
                            cutover[
                                (
                                    "cutover_runtime_route_contract_identity_"
                                    "matches_current"
                                )
                            ],
                            "is",
                            True,
                            bool(
                                cutover[
                                    (
                                        "cutover_runtime_route_contract_identity_"
                                        "matches_current"
                                    )
                                ]
                            ),
                            (
                                "cutover route contract identity no longer "
                                "matches the current recursive "
                                "broker-readiness source"
                            ),
                        ),
                    ]
                )
            if cutover[
                (
                    "cutover_runtime_route_enable_"
                    "route_contract_identity_active"
                )
            ]:
                runtime_route_enable_identity_sha256 = str(
                    cutover[
                        (
                            "cutover_runtime_telemetry_broker_readiness_"
                            "route_enable_route_contract_identity_sha256"
                        )
                    ]
                ).strip()
                current_route_enable_identity_sha256 = str(
                    cutover[
                        (
                            "cutover_current_runtime_route_enable_"
                            "route_contract_identity_sha256"
                        )
                    ]
                ).strip()
                checks.extend(
                    [
                        _check(
                            (
                                "cutover_runtime_telemetry_broker_readiness_"
                                "route_enable_route_contract_identity_"
                                "sha256_present"
                            ),
                            runtime_route_enable_identity_sha256,
                            "present",
                            True,
                            bool(runtime_route_enable_identity_sha256),
                            (
                                "cutover runtime route-enable route contract "
                                "identity digest is missing"
                            ),
                        ),
                        _check(
                            (
                                "cutover_runtime_telemetry_broker_readiness_"
                                "route_enable_route_contract_identity_"
                                "sha256_matches_current"
                            ),
                            runtime_route_enable_identity_sha256,
                            "==",
                            current_route_enable_identity_sha256,
                            bool(
                                runtime_route_enable_identity_sha256
                                and current_route_enable_identity_sha256
                                and runtime_route_enable_identity_sha256
                                == current_route_enable_identity_sha256
                            ),
                            (
                                "cutover runtime route-enable route contract "
                                "identity differs from current broker "
                                "readiness"
                            ),
                        ),
                        _check(
                            (
                                "cutover_runtime_route_enable_"
                                "route_contract_identity_matches_current"
                            ),
                            cutover[
                                (
                                    "cutover_runtime_route_enable_"
                                    "route_contract_identity_matches_current"
                                )
                            ],
                            "is",
                            True,
                            bool(
                                cutover[
                                    (
                                        "cutover_runtime_route_enable_"
                                        "route_contract_identity_matches_current"
                                    )
                                ]
                            ),
                            (
                                "cutover route-enable route contract identity "
                                "no longer matches the current recursive "
                                "broker-readiness source"
                            ),
                        ),
                    ]
                )
        checks.append(
            _check(
                "cutover_lineage_gate_passed",
                cutover["cutover_lineage_gate_passed"],
                "is",
                True,
                bool(cutover["cutover_lineage_gate_passed"]),
                "cutover operational lineage gate did not pass",
            )
        )
    if route_readiness_required:
        checks.append(
            _check(
                "cutover_route_readiness_provided",
                cutover["route_readiness_provided"],
                "is",
                True,
                bool(cutover["route_readiness_provided"]),
                "route enable requires cutover with route-readiness proof",
            )
        )
    if route_readiness_active:
        checks.extend(_route_readiness_checks(cutover))
    if _resume_route_readiness_active(cutover, "broker_resume_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                cutover,
                source_prefix="broker_resume_broker_route_readiness",
                check_prefix="cutover_broker_resume_broker_route_readiness",
                label="cutover broker resume-gate broker route-readiness",
            )
        )
    if _resume_route_readiness_active(cutover, "broker_resume_incident_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                cutover,
                source_prefix="broker_resume_incident_broker_route_readiness",
                check_prefix="cutover_broker_resume_incident_broker_route_readiness",
                label="cutover broker resume-gate incident broker route-readiness",
            )
        )
    checks.extend(
        [
            _check(
                "upload_ready",
                upload["ready"],
                "is",
                True,
                bool(upload["ready"]) or not thresholds.require_upload_ready,
                "broker upload pack is not ready",
            ),
            _check(
                "upload_orders_min",
                upload_orders,
                ">=",
                thresholds.min_orders,
                upload_orders >= thresholds.min_orders,
                "broker upload pack does not contain enough orders",
            ),
            _check(
                "upload_orders_within_cutover_limit",
                upload_orders,
                "<=",
                max_orders,
                upload_orders <= max_orders,
                "broker upload order count exceeds cutover limit",
            ),
            _check(
                "upload_adapter_matches",
                upload["adapter"],
                "==",
                cutover["adapter"],
                (not thresholds.require_adapter_match) or upload["adapter"] == cutover["adapter"],
                "broker upload adapter does not match cutover adapter",
            ),
        ]
    )
    if _strategy_portfolio_active(cutover):
        checks.extend(
            [
                _check(
                    "strategy_portfolio_provided",
                    cutover["strategy_portfolio_provided"],
                    "is",
                    True,
                    bool(cutover["strategy_portfolio_provided"]),
                    "cutover strategy portfolio allocation was not provided",
                ),
                _check(
                    "strategy_portfolio_ready",
                    cutover["strategy_portfolio_ready"],
                    "is",
                    True,
                    bool(cutover["strategy_portfolio_ready"]),
                    "cutover strategy portfolio allocation is not ready",
                ),
                _check(
                    "strategy_portfolio_allocation_eligible",
                    cutover["strategy_portfolio_selected_eligible"],
                    "is",
                    True,
                    bool(cutover["strategy_portfolio_selected_eligible"]),
                    "cutover strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "strategy_portfolio_strategy_matches",
                    cutover["strategy_portfolio_selected_strategy"],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover["strategy_portfolio_selected_strategy"]
                        and cutover["strategy"]
                        and cutover["strategy_portfolio_selected_strategy"] == cutover["strategy"]
                    ),
                    "cutover strategy portfolio strategy does not match route strategy",
                ),
                _check(
                    "strategy_portfolio_market_matches",
                    cutover["strategy_portfolio_selected_market"],
                    "==",
                    cutover["market"],
                    bool(
                        cutover["strategy_portfolio_selected_market"]
                        and cutover["market"]
                        and cutover["strategy_portfolio_selected_market"] == cutover["market"]
                    ),
                    "cutover strategy portfolio market does not match route market",
                ),
                _check(
                    "strategy_portfolio_allocation_notional",
                    cutover["strategy_portfolio_selected_allocation_notional"],
                    ">",
                    0.0,
                    float(cutover["strategy_portfolio_selected_allocation_notional"]) > 0.0,
                    "cutover strategy portfolio allocation notional must be positive",
                ),
            ]
        )
        if _strategy_portfolio_leadlag_active(cutover):
            lineage_ready = leadlag_lineage_ready(
                cutover,
                prefix="strategy_portfolio_",
            )
            checks.extend(
                [
                    _check(
                        "strategy_portfolio_leadlag_cutover_contract_consistent",
                        cutover[
                            "strategy_portfolio_leadlag_cutover_contract_consistent"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "strategy_portfolio_leadlag_cutover_contract_consistent"
                            ]
                        ),
                        "cutover summary and config disagree on lead-lag measured-edge lineage",
                    ),
                    _check(
                        "strategy_portfolio_leadlag_edge_lineage_required",
                        cutover[
                            "strategy_portfolio_leadlag_edge_lineage_required"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "strategy_portfolio_leadlag_edge_lineage_required"
                            ]
                        ),
                        "cutover did not carry the required lead-lag lineage marker",
                    ),
                    _check(
                        "strategy_portfolio_leadlag_profile",
                        cutover["strategy_portfolio_selected_profile"],
                        "==",
                        "leadlag",
                        _identity_key(cutover["strategy_portfolio_selected_profile"])
                        == "leadlag",
                        "cutover lead-lag lineage is attached to a different portfolio profile",
                    ),
                    _check(
                        "strategy_portfolio_leadlag_edge_lineage_ready",
                        lineage_ready,
                        "is",
                        True,
                        lineage_ready,
                        "cutover lost or malformed the lead-lag measured-edge lineage",
                    ),
                    _check(
                        "strategy_portfolio_leadlag_edge_lineage_matches_scaleup",
                        cutover[
                            "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
                        ],
                        "is",
                        True,
                        bool(
                            cutover[
                                "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
                            ]
                        ),
                        "cutover did not retain the guard-validated lead-lag scale-up match",
                    ),
                ]
            )
    if _dispatch_roundtrip_required(thresholds) or cutover["dispatch_roundtrip_provided"]:
        checks.extend(_dispatch_roundtrip_checks(cutover, target_mode))
    if _route_dispatch_roundtrip_required(thresholds, cutover):
        checks.extend(_route_dispatch_roundtrip_checks(cutover, target_mode))
    if _shadow_broker_readiness_active(cutover):
        checks.extend(_shadow_broker_readiness_checks(cutover))
    if _broker_shadow_broker_readiness_active(cutover):
        checks.extend(_broker_shadow_broker_readiness_checks(cutover))
    if _broker_vendor_data_readiness_active(cutover):
        checks.extend(_broker_vendor_data_readiness_checks(cutover))
    if _broker_vendor_market_data_batch_active(cutover):
        checks.extend(_broker_vendor_market_data_batch_checks(cutover))
    if thresholds.require_order_export_ready:
        checks.append(
            _check(
                "order_export_provided",
                order_export["provided"],
                "is",
                True,
                bool(order_export["provided"]),
                "order export summary is required but missing",
            )
        )
    if order_export["provided"]:
        checks.extend(
            [
                _check(
                    "order_export_ready",
                    order_export["ready"],
                    "is",
                    True,
                    bool(order_export["ready"]) or not thresholds.require_order_export_ready,
                    "order export is not ready",
                ),
                _check(
                    "order_export_adapter_matches",
                    order_export["adapter"],
                    "==",
                    cutover["adapter"],
                    (not thresholds.require_adapter_match) or order_export["adapter"] == cutover["adapter"],
                    "order export adapter does not match cutover adapter",
                ),
                _check(
                    "order_export_orders_match_upload",
                    order_export["orders"],
                    "==",
                    upload_orders,
                    int(order_export["orders"]) == upload_orders,
                    "order export and upload pack order counts differ",
                ),
                _check(
                    "order_export_notional_within_cutover_limit",
                    export_notional,
                    "<=",
                    max_notional,
                    export_notional <= max_notional,
                    "order export notional exceeds cutover limit",
                ),
            ]
        )
        if _strategy_portfolio_active(cutover):
            checks.append(
                _check(
                    "order_export_notional_within_strategy_portfolio_allocation",
                    export_notional,
                    "<=",
                    cutover["strategy_portfolio_selected_allocation_notional"],
                    export_notional <= float(cutover["strategy_portfolio_selected_allocation_notional"]),
                    "order export notional exceeds selected strategy portfolio allocation",
                )
            )
    return pd.DataFrame(checks)


def _route_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    checks = [
        _check(
            "cutover_route_readiness_ready",
            cutover["route_readiness_ready"],
            "is",
            True,
            bool(cutover["route_readiness_ready"]),
            "cutover route-readiness proof is not ready",
        ),
        _check(
            "cutover_route_readiness_strategy_matches",
            cutover["route_readiness_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["route_readiness_strategy"]
                and cutover["strategy"]
                and cutover["route_readiness_strategy"] == cutover["strategy"]
            ),
            "cutover route-readiness strategy does not match route strategy",
        ),
        _check(
            "cutover_route_readiness_market_matches",
            cutover["route_readiness_market"],
            "==",
            cutover["market"],
            bool(
                cutover["route_readiness_market"]
                and cutover["market"]
                and cutover["route_readiness_market"] == cutover["market"]
            ),
            "cutover route-readiness market does not match route market",
        ),
        _check(
            "cutover_route_readiness_ops_launch_controls_present",
            cutover["route_readiness_ops_launch_controls_present"],
            "is",
            True,
            bool(cutover["route_readiness_ops_launch_controls_present"]),
            "cutover route-readiness proof is missing launch-grade ops broker controls",
        ),
        _check(
            "cutover_route_readiness_ops_launch_controls_blocked_pairs",
            cutover["route_readiness_ops_launch_controls_blocked_pairs"],
            "<=",
            0,
            int(cutover["route_readiness_ops_launch_controls_blocked_pairs"]) <= 0,
            "cutover route-readiness proof has blocked launch-control pairs",
        ),
        _check(
            "cutover_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
            cutover["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"],
            "<=",
            0,
            int(cutover["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) <= 0,
            "cutover route-readiness proof has broker round-trip allocation breach pairs",
        ),
        _check(
            "cutover_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
            cutover["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"],
            "<=",
            0,
            int(cutover["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]) <= 0,
            "cutover route-readiness proof has broker round-trip concentration breach pairs",
        ),
    ]
    if _broker_route_readiness_active(cutover):
        checks.extend(_broker_route_readiness_checks(cutover))
    return checks


def _broker_route_readiness_active(cutover: dict[str, Any]) -> bool:
    return bool(
        _to_bool(cutover["broker_route_readiness_required"])
        or _to_bool(cutover["broker_route_readiness_provided"])
        or _to_bool(cutover["broker_route_readiness_ready"])
        or int(cutover["broker_route_readiness_route_ready_pairs"]) > 0
        or int(cutover["broker_route_readiness_gap_pairs"]) > 0
        or bool(_object_text(cutover["broker_route_readiness_strategy"]))
        or bool(_object_text(cutover["broker_route_readiness_market"]))
        or bool(_object_text(cutover["broker_route_readiness_recommendation"]))
        or _to_bool(cutover["broker_route_readiness_ops_launch_controls_ready"])
        or bool(_object_text(cutover["broker_route_readiness_ops_launch_control_failures"]))
        or int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0
        or int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) > 0
        or int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0
        or int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) > 0
    )


def _broker_route_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_broker_route_readiness_provided",
            cutover["broker_route_readiness_provided"],
            "is",
            True,
            bool(cutover["broker_route_readiness_provided"] or not cutover["broker_route_readiness_required"]),
            "cutover broker-readiness route proof is required but not provided",
        ),
        _check(
            "cutover_broker_route_readiness_ready",
            cutover["broker_route_readiness_ready"],
            "is",
            True,
            bool(cutover["broker_route_readiness_ready"]),
            "cutover broker-readiness route proof is not ready",
        ),
        _check(
            "cutover_broker_route_readiness_strategy_matches",
            cutover["broker_route_readiness_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["broker_route_readiness_strategy"]
                and cutover["broker_route_readiness_strategy"] == cutover["strategy"]
            ),
            "cutover broker-readiness route strategy does not match route strategy",
        ),
        _check(
            "cutover_broker_route_readiness_market_matches",
            cutover["broker_route_readiness_market"],
            "==",
            cutover["market"],
            bool(
                cutover["broker_route_readiness_market"]
                and cutover["broker_route_readiness_market"] == cutover["market"]
            ),
            "cutover broker-readiness route market does not match route market",
        ),
        _check(
            "cutover_broker_route_readiness_gap_pairs",
            cutover["broker_route_readiness_gap_pairs"],
            "<=",
            0,
            int(cutover["broker_route_readiness_gap_pairs"]) <= 0,
            "cutover broker-readiness route proof has route gaps",
        ),
        _check(
            "cutover_broker_route_readiness_ops_launch_controls_ready",
            cutover["broker_route_readiness_ops_launch_controls_ready"],
            "is",
            True,
            bool(cutover["broker_route_readiness_ops_launch_controls_ready"]),
            "cutover broker-readiness route proof is missing launch-grade ops broker controls",
        ),
        _check(
            "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"],
            ">",
            0,
            int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0,
            "cutover broker-readiness route proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"],
            "<=",
            0,
            int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) <= 0,
            "cutover broker-readiness route proof has allocation breach broker round-trip runs",
        ),
        _check(
            "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
            ">",
            0,
            int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0,
            "cutover broker-readiness route proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
            "<=",
            0,
            int(cutover["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) <= 0,
            "cutover broker-readiness route proof has concentration breach broker round-trip runs",
        ),
    ]


def _resume_route_readiness_active(cutover: dict[str, Any], prefix: str) -> bool:
    return bool(
        _to_bool(cutover[f"{prefix}_required"])
        or _to_bool(cutover[f"{prefix}_provided"])
        or _to_bool(cutover[f"{prefix}_ready"])
        or int(cutover[f"{prefix}_route_ready_pairs"]) > 0
        or int(cutover[f"{prefix}_gap_pairs"]) > 0
        or bool(_object_text(cutover[f"{prefix}_strategy"]))
        or bool(_object_text(cutover[f"{prefix}_market"]))
        or bool(_object_text(cutover[f"{prefix}_recommendation"]))
        or _to_bool(cutover[f"{prefix}_ops_launch_controls_ready"])
        or bool(_object_text(cutover[f"{prefix}_ops_launch_control_failures"]))
        or int(cutover[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]) > 0
        or int(cutover[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]) > 0
        or int(cutover[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0
        or int(cutover[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) > 0
    )


def _resume_route_readiness_checks(
    cutover: dict[str, Any],
    *,
    source_prefix: str,
    check_prefix: str,
    label: str,
) -> list[dict[str, object]]:
    return [
        _check(
            f"{check_prefix}_provided",
            cutover[f"{source_prefix}_provided"],
            "is",
            True,
            bool(cutover[f"{source_prefix}_provided"] or not cutover[f"{source_prefix}_required"]),
            f"{label} proof is required but not provided",
        ),
        _check(
            f"{check_prefix}_ready",
            cutover[f"{source_prefix}_ready"],
            "is",
            True,
            bool(cutover[f"{source_prefix}_ready"]),
            f"{label} proof is not ready",
        ),
        _check(
            f"{check_prefix}_strategy_matches",
            cutover[f"{source_prefix}_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover[f"{source_prefix}_strategy"]
                and cutover["strategy"]
                and cutover[f"{source_prefix}_strategy"] == cutover["strategy"]
            ),
            f"{label} strategy does not match route strategy",
        ),
        _check(
            f"{check_prefix}_market_matches",
            cutover[f"{source_prefix}_market"],
            "==",
            cutover["market"],
            bool(
                cutover[f"{source_prefix}_market"]
                and cutover["market"]
                and cutover[f"{source_prefix}_market"] == cutover["market"]
            ),
            f"{label} market does not match route market",
        ),
        _check(
            f"{check_prefix}_route_ready_pairs",
            cutover[f"{source_prefix}_route_ready_pairs"],
            ">",
            0,
            int(cutover[f"{source_prefix}_route_ready_pairs"]) > 0,
            f"{label} has no route-ready pairs",
        ),
        _check(
            f"{check_prefix}_gap_pairs",
            cutover[f"{source_prefix}_gap_pairs"],
            "<=",
            0,
            int(cutover[f"{source_prefix}_gap_pairs"]) <= 0,
            f"{label} has route gaps",
        ),
        _check(
            f"{check_prefix}_ops_launch_controls_ready",
            cutover[f"{source_prefix}_ops_launch_controls_ready"],
            "is",
            True,
            bool(cutover[f"{source_prefix}_ops_launch_controls_ready"]),
            f"{label} is missing launch-grade ops broker controls",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"],
            ">",
            0,
            int(cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"]) > 0,
            f"{label} has no allocation-safe broker round-trip runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"],
            "<=",
            0,
            int(cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"]) <= 0,
            f"{label} has allocation breach broker round-trip runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
            ">",
            0,
            int(cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0,
            f"{label} has no concentration-OK broker round-trip runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
            "<=",
            0,
            int(cutover[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) <= 0,
            f"{label} has concentration breach broker round-trip runs",
        ),
    ]


def _dispatch_roundtrip_checks(cutover: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_dispatch_roundtrip_ready",
            cutover["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(cutover["dispatch_roundtrip_ready"]),
            "cutover dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            "cutover_dispatch_roundtrip_target_mode_matches",
            cutover["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(cutover["dispatch_roundtrip_target_mode"] and cutover["dispatch_roundtrip_target_mode"] == target_mode),
            "cutover dispatch round-trip target mode does not match route target",
        ),
        _check(
            "cutover_dispatch_roundtrip_strategy_matches",
            cutover["dispatch_roundtrip_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["dispatch_roundtrip_strategy"]
                and cutover["strategy"]
                and cutover["dispatch_roundtrip_strategy"] == cutover["strategy"]
            ),
            "cutover dispatch round-trip strategy does not match route strategy",
        ),
        _check(
            "cutover_dispatch_roundtrip_market_matches",
            cutover["dispatch_roundtrip_market"],
            "==",
            cutover["market"],
            bool(
                cutover["dispatch_roundtrip_market"]
                and cutover["market"]
                and cutover["dispatch_roundtrip_market"] == cutover["market"]
            ),
            "cutover dispatch round-trip market does not match route market",
        ),
        _check(
            "cutover_dispatch_roundtrip_scenario_matches",
            cutover["dispatch_roundtrip_scenario_key"],
            "==",
            cutover["scenario_key"],
            bool(
                cutover["dispatch_roundtrip_scenario_key"]
                and cutover["scenario_key"]
                and cutover["dispatch_roundtrip_scenario_key"] == cutover["scenario_key"]
            ),
            "cutover dispatch round-trip scenario does not match route scenario",
        ),
        _check(
            "cutover_dispatch_roundtrip_missing_request_acks",
            cutover["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_missing_request_acks"]) <= 0,
            "cutover dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            "cutover_dispatch_roundtrip_rejected_orders",
            cutover["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_rejected_orders"]) <= 0,
            "cutover dispatch round-trip has rejected orders",
        ),
        _check(
            "cutover_dispatch_roundtrip_unmatched_acks",
            cutover["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_unmatched_acks"]) <= 0,
            "cutover dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            "cutover_dispatch_roundtrip_failed_checks",
            cutover["dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(cutover["dispatch_roundtrip_failed_checks"]) <= 0,
            "cutover dispatch round-trip has failed component checks",
        ),
        _check(
            "cutover_route_enable_dispatch_roundtrip_failed_checks",
            cutover["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(cutover["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            "cutover carries failed route-enable dispatch round-trip checks",
        ),
    ]


def _route_dispatch_roundtrip_checks(cutover: dict[str, Any], target_mode: str) -> list[dict[str, object]]:
    return [
        _check(
            "cutover_route_dispatch_roundtrip_ready",
            cutover["route_dispatch_roundtrip_ready"],
            "is",
            True,
            bool(cutover["route_dispatch_roundtrip_ready"]),
            "cutover dispatch route proof is not ready",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_target_mode_matches",
            cutover["route_dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(
                cutover["route_dispatch_roundtrip_target_mode"]
                and cutover["route_dispatch_roundtrip_target_mode"] == target_mode
            ),
            "cutover dispatch route proof target mode does not match route target",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_strategy_matches",
            cutover["route_dispatch_roundtrip_strategy"],
            "==",
            cutover["strategy"],
            bool(
                cutover["route_dispatch_roundtrip_strategy"]
                and cutover["strategy"]
                and cutover["route_dispatch_roundtrip_strategy"] == cutover["strategy"]
            ),
            "cutover dispatch route proof strategy does not match route strategy",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_market_matches",
            cutover["route_dispatch_roundtrip_market"],
            "==",
            cutover["market"],
            bool(
                cutover["route_dispatch_roundtrip_market"]
                and cutover["market"]
                and cutover["route_dispatch_roundtrip_market"] == cutover["market"]
            ),
            "cutover dispatch route proof market does not match route market",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_scenario_matches",
            cutover["route_dispatch_roundtrip_scenario_key"],
            "==",
            cutover["scenario_key"],
            bool(
                cutover["route_dispatch_roundtrip_scenario_key"]
                and cutover["scenario_key"]
                and cutover["route_dispatch_roundtrip_scenario_key"] == cutover["scenario_key"]
            ),
            "cutover dispatch route proof scenario does not match route scenario",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_batch_id_provided",
            cutover["route_dispatch_roundtrip_batch_id"],
            "is not",
            "",
            bool(cutover["route_dispatch_roundtrip_batch_id"]),
            "cutover dispatch route proof batch id is missing",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_request_count_matches",
            f"{cutover['route_dispatch_roundtrip_requests']}/{cutover['route_dispatch_roundtrip_acked_orders']}",
            "==",
            f"{cutover['dispatch_roundtrip_requests']}/{cutover['dispatch_roundtrip_acked_orders']}",
            (
                int(cutover["route_dispatch_roundtrip_requests"]) == int(cutover["dispatch_roundtrip_requests"])
                and int(cutover["route_dispatch_roundtrip_acked_orders"])
                == int(cutover["dispatch_roundtrip_acked_orders"])
            ),
            "cutover dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_missing_request_acks",
            cutover["route_dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_missing_request_acks"]) <= 0,
            "cutover dispatch route proof has missing request acknowledgements",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_rejected_orders",
            cutover["route_dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_rejected_orders"]) <= 0,
            "cutover dispatch route proof has rejected orders",
        ),
        _check(
            "cutover_route_dispatch_roundtrip_unmatched_acks",
            cutover["route_dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(cutover["route_dispatch_roundtrip_unmatched_acks"]) <= 0,
            "cutover dispatch route proof has unmatched acknowledgements",
        ),
    ]


def _broker_vendor_market_data_batch_active(cutover: dict[str, Any]) -> bool:
    vendor = cutover["broker_dispatch_roundtrip_vendor_market_data_batch"]
    return bool(_to_bool(vendor["provided"]) or int(vendor["dataset_count"]) > 0)


def _broker_vendor_data_readiness_active(cutover: dict[str, Any]) -> bool:
    readiness = cutover["broker_vendor_data_readiness"]
    return bool(
        _to_bool(readiness["provided"])
        or _to_bool(readiness["ready"])
        or int(readiness["failed_checks"]) > 0
    )


def _broker_vendor_data_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    readiness = cutover["broker_vendor_data_readiness"]
    prefix = "cutover_broker_vendor_data_readiness"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(readiness["provided"]),
            "is",
            True,
            _to_bool(readiness["provided"]),
            "cutover broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(readiness["ready"]),
            "is",
            True,
            _to_bool(readiness["ready"]),
            "cutover broker-vendor readiness wrapper proof is not ready",
        ),
        _check(
            f"{prefix}_failed_checks",
            int(readiness["failed_checks"]),
            "<=",
            0,
            int(readiness["failed_checks"]) <= 0,
            "cutover broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _broker_vendor_market_data_batch_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    vendor = cutover["broker_dispatch_roundtrip_vendor_market_data_batch"]
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    checks = [
        _check(
            f"{prefix}_provided",
            _to_bool(vendor["provided"]),
            "is",
            True,
            _to_bool(vendor["provided"]),
            "cutover broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(vendor["ready"]),
            "is",
            True,
            _to_bool(vendor["ready"]),
            "cutover broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            f"{prefix}_adapter_matches",
            vendor["adapter"],
            "==",
            cutover["adapter"],
            bool(vendor["adapter"] and cutover["adapter"] and vendor["adapter"] == cutover["adapter"]),
            "cutover broker-readiness vendor market-data adapter does not match route adapter",
        ),
        _check(
            f"{prefix}_market_matches",
            vendor["market"],
            "==",
            cutover["market"],
            bool(vendor["market"] and cutover["market"] and vendor["market"] == cutover["market"]),
            "cutover broker-readiness vendor market-data market does not match route market",
        ),
        _check(
            f"{prefix}_manifest_run_type",
            vendor["manifest_run_type"],
            "==",
            "vendor_market_data_batch_pipeline",
            vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline",
            "cutover broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            f"{prefix}_dataset_count",
            int(vendor["dataset_count"]),
            ">",
            0,
            int(vendor["dataset_count"]) > 0,
            "cutover broker-readiness vendor market-data batch has no datasets",
        ),
        _check(
            f"{prefix}_failed_datasets",
            int(vendor["failed_datasets"]),
            "<=",
            0,
            int(vendor["failed_datasets"]) <= 0,
            "cutover broker-readiness vendor market-data batch has failed datasets",
        ),
        _check(
            f"{prefix}_source_files",
            int(vendor["unique_source_files"]),
            ">",
            0,
            int(vendor["unique_source_files"]) > 0,
            "cutover broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            f"{prefix}_header_fingerprints",
            int(vendor["unique_header_fingerprints"]),
            ">",
            0,
            int(vendor["unique_header_fingerprints"]) > 0,
            "cutover broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            f"{prefix}_source_file_fingerprint_coverage",
            float(vendor["source_file_fingerprint_coverage"]),
            ">=",
            1.0,
            float(vendor["source_file_fingerprint_coverage"]) >= 1.0,
            "cutover broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            f"{prefix}_min_mapping_coverage",
            float(vendor["min_mapping_coverage"]),
            ">=",
            1.0,
            float(vendor["min_mapping_coverage"]) >= 1.0,
            "cutover broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            f"{prefix}_mapping_drafts",
            int(vendor["unique_mapping_drafts"]),
            ">",
            0,
            int(vendor["unique_mapping_drafts"]) > 0,
            "cutover broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            f"{prefix}_mapping_sources",
            str(vendor["mapping_sources"]).strip(),
            "!=",
            "",
            bool(str(vendor["mapping_sources"]).strip()),
            "cutover broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            f"{prefix}_comparison_accepted",
            _to_bool(vendor["comparison_accepted"]),
            "is",
            True,
            _to_bool(vendor["comparison_accepted"]),
            "cutover broker-readiness vendor market-data comparison was not accepted",
        ),
        _check(
            f"{prefix}_comparison_failed_checks",
            int(vendor["comparison_failed_checks"]),
            "<=",
            0,
            int(vendor["comparison_failed_checks"]) <= 0,
            "cutover broker-readiness vendor market-data comparison has failed checks",
        ),
    ]
    if _target_application_batch_active(vendor):
        dataset_count = int(vendor["dataset_count"])
        mapping_application_count = int(vendor["mapping_application_count"])
        unique_mapping_applications = int(vendor["unique_mapping_applications"])
        target_application_coverage = float(vendor["target_application_coverage"])
        lineage_datasets = _target_application_lineage_dataset_count(vendor)
        lineage_consistency_required = _to_bool(
            vendor["application_lineage_consistency_required"]
        )
        lineage_consistent = _to_bool(vendor["application_lineage_consistent"])
        lineage_match_required = _to_bool(
            cutover["broker_vendor_market_data_batch_lineage_match_required"]
        )
        lineage_matches = _to_bool(
            cutover["broker_vendor_market_data_batch_lineage_matches"]
        )
        current_lineage_sha256 = _sha256_text(
            cutover["vendor_market_data_batch_application_lineage_sha256"]
        )
        broker_lineage_sha256 = _sha256_text(
            cutover["broker_vendor_market_data_batch_application_lineage_sha256"]
        )
        scaleup_carried_lineage_sha256 = _sha256_text(
            cutover[
                "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        )
        cutover_carried_lineage_sha256 = _sha256_text(
            cutover[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        )
        route_carried_lineage_sha256 = _target_application_lineage_sha256(vendor)
        mapping_source_mode = _identity_key(vendor["mapping_source_mode"])
        checks.extend(
            [
                _check(
                    f"{prefix}_mapping_source_mode",
                    mapping_source_mode,
                    "==",
                    TARGET_APPLICATION_BATCH_MODE,
                    mapping_source_mode == TARGET_APPLICATION_BATCH_MODE,
                    "cutover broker-readiness vendor target applications are missing strict source mode",
                ),
                _check(
                    f"{prefix}_mapping_application_count",
                    mapping_application_count,
                    "==",
                    dataset_count,
                    dataset_count > 0 and mapping_application_count == dataset_count,
                    "cutover broker-readiness vendor target applications are not aligned one for one",
                ),
                _check(
                    f"{prefix}_unique_mapping_applications",
                    unique_mapping_applications,
                    "==",
                    dataset_count,
                    dataset_count > 0 and unique_mapping_applications == dataset_count,
                    "cutover broker-readiness vendor target applications are not distinct per dataset",
                ),
                _check(
                    f"{prefix}_target_application_coverage",
                    target_application_coverage,
                    ">=",
                    1.0,
                    target_application_coverage >= 1.0,
                    "cutover broker-readiness vendor target-application coverage is incomplete",
                ),
                _check(
                    f"{prefix}_application_lineage_datasets",
                    lineage_datasets,
                    "==",
                    dataset_count,
                    dataset_count > 0 and lineage_datasets == dataset_count,
                    "cutover broker-readiness vendor datasets are missing target-application lineage",
                ),
                _check(
                    f"{prefix}_lineage_match_required",
                    lineage_match_required,
                    "is",
                    True,
                    lineage_match_required,
                    "target-application route enable requires the cutover current/final lineage comparison",
                ),
                _check(
                    f"{prefix}_lineage_matches",
                    lineage_matches,
                    "is",
                    True,
                    lineage_match_required and lineage_matches,
                    "cutover current and final target-application lineages do not match",
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
                    "cutover current/final target-lineage digests are missing or disagree",
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
                    "cutover scale-up-carried target lineage does not match broker-readiness proof",
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
                    "cutover-carried target lineage does not match broker-readiness proof",
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
                    "route-enable carried target lineage does not match cutover proof",
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
                        "cutover final dispatch/send/ack target lineage was not consistent",
                    ),
                    *_broker_vendor_final_lineage_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_complete_final_lineage_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_extended_complete_final_lineage_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_extended_complete_final_lineage_36_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_latest_extended_complete_final_lineage_44_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                    *_broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_checks(
                        cutover,
                        route_lineage_sha256=route_carried_lineage_sha256,
                    ),
                ]
            )
    return checks


def _broker_vendor_final_lineage_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = CUTOVER_FINAL_LINEAGE_FIELD_PREFIX
    prefix = source_prefix
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    final_broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    final_current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    cutover_broker_lineage_sha256 = _sha256_text(
        cutover["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    cutover_lineage_sha256 = _sha256_text(
        cutover[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    checks = [
        _check(
            f"{prefix}_final_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's final lineage comparison",
        ),
        _check(
            f"{prefix}_final_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not reconcile every final target-lineage view",
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
            "cutover's final source lineage does not match final broker proof",
        ),
        _check(
            f"{prefix}_final_broker_lineage_sha256_matches",
            cutover_broker_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and cutover_broker_lineage_sha256
                and final_broker_lineage_sha256
                and cutover_broker_lineage_sha256 == final_broker_lineage_sha256
            ),
            "cutover's current/final broker digest does not match its final comparison",
        ),
        _check(
            f"{prefix}_final_application_lineage_sha256_matches",
            cutover_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and cutover_lineage_sha256
                and final_broker_lineage_sha256
                and cutover_lineage_sha256 == final_broker_lineage_sha256
            ),
            "cutover's independently recomputed batch digest does not match final comparison",
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
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage does not "
                    "match final broker proof"
                ),
            )
        )
    cutover_review_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    checks.extend(
        [
            _check(
                f"{prefix}_final_cutover_review_carried_lineage_sha256_matches",
                cutover_review_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_review_lineage_sha256
                    and final_broker_lineage_sha256
                    and cutover_review_lineage_sha256 == final_broker_lineage_sha256
                ),
                "cutover's carried review lineage does not match final broker proof",
            ),
            _check(
                f"{prefix}_route_enable_review_carried_lineage_sha256_matches",
                route_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_lineage_sha256
                    and final_broker_lineage_sha256
                    and route_lineage_sha256 == final_broker_lineage_sha256
                ),
                "route enable's independently recomputed target lineage does not match final broker proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_complete_final_lineage_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_cutover_final"
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[
            f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_broker_application_lineage_sha256"
        ]
    )
    compatibility_cutover_lineage_sha256 = _sha256_text(
        cutover[
            f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_carried_application_lineage_sha256"
        ]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's complete final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every complete final target-lineage view",
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
            "cutover final source lineage does not match final broker proof",
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
            "route compatibility broker digest does not match cutover's final proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_carried_lineage_sha256_matches",
            compatibility_cutover_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_lineage_sha256 == broker_lineage_sha256
            ),
            "route compatibility cutover digest does not match cutover's final proof",
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
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match final broker proof"
                ),
            )
        )
    cutover_final_review_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_final_review_lineage_sha256 = _sha256_text(route_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_cutover_final_review_carried_lineage_sha256_matches",
                cutover_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's carried final-review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_final_review_carried_lineage_sha256_matches",
                route_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and route_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "route enable's independently recomputed target lineage does not match cutover's final proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_extended_complete_final_lineage_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    compatibility_prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_cutover_complete_final"
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_final_review_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every extended complete-final target-lineage view",
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
            "cutover complete-final source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility cutover final review does not match cutover's extended proof",
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match extended complete-final broker proof"
                ),
            )
        )
    scaleup_complete_final_review_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_scaleup_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    cutover_complete_final_review_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_complete_final_review_lineage_sha256 = _sha256_text(
        route_lineage_sha256
    )
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
                "cutover's carried scale-up complete-final review lineage does not match final broker proof",
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
                "cutover's carried complete-final review lineage does not match final broker proof",
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
                "route enable's independently recomputed target lineage does not match cutover's extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_extended_complete_final_lineage_36_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX
    compatibility_prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = (
        f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_cutover_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_complete_final_review_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every latest extended complete-final target-lineage view",
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
            "cutover extended complete-final source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_complete_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility cutover complete-final review does not match cutover's latest extended proof",
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    broker_readiness_extended_complete_final_review_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    scaleup_extended_complete_final_review_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    cutover_extended_complete_final_review_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_extended_complete_final_review_lineage_sha256 = _sha256_text(
        route_lineage_sha256
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
                "cutover's broker-readiness extended review lineage does not match final broker proof",
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
                "cutover's scale-up extended review lineage does not match final broker proof",
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
                "cutover's carried extended complete-final review lineage does not match final broker proof",
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
                "route enable's independently recomputed target lineage does not match cutover's latest extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_latest_extended_complete_final_lineage_44_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX
    compatibility_prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX
    check_prefix = (
        f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "cutover_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_extended_complete_final_review_lineage_sha256 = (
        _sha256_text(
            cutover[f"{compatibility_prefix}_carried_application_lineage_sha256"]
        )
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every latest extended complete-final target-lineage view",
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
            "cutover latest extended complete-final source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility cutover extended review does not match cutover's latest extended proof",
        ),
    ]
    for field in CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
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
    ):
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    route_latest_extended_complete_final_review_lineage_sha256 = _sha256_text(
        route_lineage_sha256
    )
    checks.append(
        _check(
            f"{check_prefix}_route_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            route_latest_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and route_latest_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and route_latest_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "route enable's independently recomputed target lineage does not match cutover's latest extended proof",
        )
    )
    return checks


def _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX
    compatibility_prefix = CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX
    check_prefix = (
        f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "cutover_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_route_latest_lineage_sha256 = _sha256_text(
        route_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's current latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every current latest extended complete-final target-lineage view",
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
            "cutover current latest extended complete-final source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's current latest proof",
        ),
        _check(
            f"{check_prefix}_compatibility_route_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_route_latest_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_route_latest_lineage_sha256
                and broker_lineage_sha256
                and compatibility_route_latest_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility latest review does not match cutover's current proof",
        ),
    ]
    for field in CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match current latest extended complete-final broker proof"
                ),
            )
        )
    for field in CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match current latest extended complete-final broker proof"
                ),
            )
        )
    scaleup_current_latest_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    cutover_current_latest_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    cutover_current_latest_generic_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_current_latest_lineage_sha256 = _sha256_text(route_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                scaleup_current_latest_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_current_latest_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_current_latest_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's source scale-up current latest review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                cutover_current_latest_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_current_latest_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_current_latest_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's current latest review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                cutover_current_latest_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_current_latest_generic_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_current_latest_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's generic current latest review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                route_current_latest_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_current_latest_lineage_sha256
                    and broker_lineage_sha256
                    and route_current_latest_lineage_sha256
                    == broker_lineage_sha256
                ),
                "route enable's independently recomputed target lineage does not match cutover's current latest proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX
    )
    compatibility_prefix = (
        CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX
    )
    check_prefix = (
        f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "cutover_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_route_current_lineage_sha256 = _sha256_text(
        route_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target route enable requires cutover's reconciled current latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every reconciled current latest extended complete-final target-lineage view",
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
            "cutover reconciled current latest extended complete-final source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's reconciled current proof",
        ),
        _check(
            f"{check_prefix}_compatibility_route_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_route_current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_route_current_lineage_sha256
                and broker_lineage_sha256
                and compatibility_route_current_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility current review does not match cutover's reconciled current proof",
        ),
    ]
    for field in CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match reconciled current latest extended complete-final broker proof"
                ),
            )
        )
    for field in (
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match reconciled current latest extended complete-final broker proof"
                ),
            )
        )
    broker_readiness_reconciled_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD}"
        ]
    )
    scaleup_reconciled_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD}"
        ]
    )
    cutover_reconciled_lineage_sha256 = _sha256_text(
        cutover[
            f"{source_prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD}"
        ]
    )
    cutover_reconciled_generic_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_reconciled_lineage_sha256 = _sha256_text(route_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                broker_readiness_reconciled_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and broker_readiness_reconciled_lineage_sha256
                    and broker_lineage_sha256
                    and broker_readiness_reconciled_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's reconciled current review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                scaleup_reconciled_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_reconciled_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_reconciled_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's reconciled current review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                cutover_reconciled_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_reconciled_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_reconciled_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's reconciled current review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                cutover_reconciled_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_reconciled_generic_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_reconciled_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's generic reconciled current review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                route_reconciled_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_reconciled_lineage_sha256
                    and broker_lineage_sha256
                    and route_reconciled_lineage_sha256
                    == broker_lineage_sha256
                ),
                "route enable's independently recomputed target lineage does not match cutover's reconciled current proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX
    )
    compatibility_prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX
    )
    check_prefix = (
        f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "cutover_verified_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_route_reconciled_lineage_sha256 = _sha256_text(
        route_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "verified reconciled target route enable requires cutover's verified reconciled lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every verified reconciled target-lineage view",
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
            "cutover verified reconciled source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's verified reconciled proof",
        ),
        _check(
            f"{check_prefix}_compatibility_route_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_route_reconciled_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_route_reconciled_lineage_sha256
                and broker_lineage_sha256
                and compatibility_route_reconciled_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility reconciled review does not match cutover's verified reconciled proof",
        ),
    ]
    for field in CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match verified reconciled broker proof"
                ),
            )
        )
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match verified reconciled broker proof"
                ),
            )
        )
    cutover_verified_generic_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_verified_lineage_sha256 = _sha256_text(route_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                cutover_verified_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_verified_generic_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_verified_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's generic verified reconciled review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                route_verified_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_verified_lineage_sha256
                    and broker_lineage_sha256
                    and route_verified_lineage_sha256 == broker_lineage_sha256
                ),
                "route enable's independently recomputed target lineage does not match cutover's verified reconciled proof",
            ),
        ]
    )
    return checks


def _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_checks(
    cutover: dict[str, Any],
    *,
    route_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_FIELD_PREFIX
    )
    compatibility_prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX
    )
    check_prefix = (
        f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        cutover[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(cutover[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        cutover[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_route_verified_lineage_sha256 = _sha256_text(
        route_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "confirmed verified-reconciled target route enable requires cutover's confirmed lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "cutover did not match every confirmed verified-reconciled target-lineage view",
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
            "cutover confirmed verified-reconciled source lineage does not match final broker proof",
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
                and compatibility_broker_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility broker digest does not match cutover's confirmed verified-reconciled proof",
        ),
        _check(
            f"{check_prefix}_compatibility_route_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_route_verified_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_route_verified_lineage_sha256
                and broker_lineage_sha256
                and compatibility_route_verified_lineage_sha256
                == broker_lineage_sha256
            ),
            "route compatibility verified review does not match cutover's confirmed verified-reconciled proof",
        ),
    ]
    for field in CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match confirmed verified-reconciled broker proof"
                ),
            )
        )
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
        *CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CONFIRMED_REVIEW_FIELDS,
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(cutover[f"{source_prefix}_{field}"])
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
                    f"cutover's {stage.replace('_', '-')} target lineage "
                    "does not match confirmed verified-reconciled broker proof"
                ),
            )
        )
    cutover_confirmed_generic_lineage_sha256 = _sha256_text(
        cutover[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    route_confirmed_lineage_sha256 = _sha256_text(route_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                cutover_confirmed_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_confirmed_generic_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_confirmed_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's generic confirmed verified-reconciled review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_route_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                route_confirmed_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and route_confirmed_lineage_sha256
                    and broker_lineage_sha256
                    and route_confirmed_lineage_sha256
                    == broker_lineage_sha256
                ),
                "route enable's independently recomputed target lineage does not match cutover's confirmed verified-reconciled proof",
            ),
        ]
    )
    return checks


def _target_application_batch_active(vendor: dict[str, Any]) -> bool:
    mapping_sources = {
        value.strip().lower()
        for value in str(vendor["mapping_sources"]).split(";")
        if value.strip()
    }
    return bool(
        _identity_key(vendor["mapping_source_mode"]) == TARGET_APPLICATION_BATCH_MODE
        or "verified_target_application" in mapping_sources
        or int(vendor["mapping_application_count"]) > 0
        or float(vendor["target_application_coverage"]) > 0.0
    )


def _target_application_lineage_dataset_count(vendor: dict[str, Any]) -> int:
    return sum(
        isinstance(dataset, dict)
        and all(
            _first_text(dataset.get(field, ""))
            for field in TARGET_APPLICATION_DATASET_LINEAGE_FIELDS
        )
        for dataset in vendor["datasets"]
    )


def _target_application_lineage_sha256(vendor: dict[str, Any]) -> str:
    identities: list[dict[str, str]] = []
    for dataset in vendor["datasets"]:
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


def _shadow_broker_readiness_active(cutover: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(cutover, key_prefix="")


def _shadow_broker_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        cutover,
        key_prefix="",
        check_prefix="cutover_shadow_broker",
        label="cutover shadow broker",
    )


def _broker_shadow_broker_readiness_active(cutover: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(cutover, key_prefix="broker_")


def _broker_shadow_broker_readiness_checks(cutover: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        cutover,
        key_prefix="broker_",
        check_prefix="cutover_broker_shadow_broker",
        label="cutover broker-readiness shadow broker",
        check_provided=True,
    )


def _shadow_broker_readiness_active_for(cutover: dict[str, Any], *, key_prefix: str) -> bool:
    session_fields = (
        "readiness_sessions",
        "vendor_data_readiness_sessions",
        "route_readiness_sessions",
        "dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(cutover.get(_shadow_broker_key(key_prefix, "readiness_provided"), False))
        or any(int(cutover[_shadow_broker_key(key_prefix, field)]) > 0 for field in session_fields)
    )


def _shadow_broker_readiness_checks_for(
    cutover: dict[str, Any],
    *,
    key_prefix: str,
    check_prefix: str,
    label: str,
    check_provided: bool = False,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    if check_provided:
        checks.append(
            _check(
                f"{check_prefix}_readiness_provided",
                _to_bool(cutover[_shadow_broker_key(key_prefix, "readiness_provided")]),
                "is",
                True,
                _to_bool(cutover[_shadow_broker_key(key_prefix, "readiness_provided")]),
                f"{label} proof is active but not marked provided",
            )
        )
    sessions = int(cutover[_shadow_broker_key(key_prefix, "readiness_sessions")])
    if sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_readiness_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]) == sessions,
                    f"{label} readiness evidence is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_adapter_matches",
                    cutover[_shadow_broker_key(key_prefix, "adapter")],
                    "==",
                    cutover["adapter"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "adapter")]
                        and cutover[_shadow_broker_key(key_prefix, "adapter")] == cutover["adapter"]
                    ),
                    f"{label} adapter does not match route adapter",
                ),
                _check(
                    f"{check_prefix}_adapter_consistent",
                    int(cutover[_shadow_broker_key(key_prefix, "adapter_count")]),
                    "==",
                    1,
                    int(cutover[_shadow_broker_key(key_prefix, "adapter_count")]) == 1,
                    f"{label} adapter identity is missing or mixed",
                ),
            ]
        )
    vendor_sessions = int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_sessions")])
    if vendor_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_vendor_data_readiness_present_for_broker_sessions",
                    vendor_sessions,
                    "==",
                    sessions,
                    vendor_sessions == sessions,
                    f"{label} vendor-data wrapper proof is present for only some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_provided",
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")]),
                    "==",
                    sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_failed_checks",
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]) <= 0,
                    f"{label} vendor-data wrapper proof has failed checks",
                ),
            ]
        )
    route_sessions = int(cutover[_shadow_broker_key(key_prefix, "route_readiness_sessions")])
    if route_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_readiness_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]),
                    "==",
                    route_sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")])
                    == route_sessions,
                    f"{label} route-readiness proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_readiness_strategy_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_readiness_strategy")],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_readiness_strategy")]
                        and cutover[_shadow_broker_key(key_prefix, "route_readiness_strategy")] == cutover["strategy"]
                    ),
                    f"{label} route-readiness strategy does not match route strategy",
                ),
                _check(
                    f"{check_prefix}_route_readiness_market_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_readiness_market")],
                    "==",
                    cutover["market"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_readiness_market")]
                        and cutover[_shadow_broker_key(key_prefix, "route_readiness_market")] == cutover["market"]
                    ),
                    f"{label} route-readiness market does not match route market",
                ),
                _check(
                    f"{check_prefix}_route_readiness_gap_pairs",
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]) <= 0,
                    f"{label} route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_sessions")])
    if dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_dispatch_roundtrip_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")]),
                    "==",
                    dispatch_sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")])
                    == dispatch_sessions,
                    f"{label} dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_strategy_matches",
                    cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        and cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        == cutover["strategy"]
                    ),
                    f"{label} dispatch round-trip strategy does not match route strategy",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_market_matches",
                    cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")],
                    "==",
                    cutover["market"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")]
                        and cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")] == cutover["market"]
                    ),
                    f"{label} dispatch round-trip market does not match route market",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_scenario_consistent",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_missing_request_acks",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")])
                    <= 0,
                    f"{label} dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_rejected_orders",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]) <= 0,
                    f"{label} dispatch round-trip has rejected orders",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_unmatched_acks",
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]),
                    "<=",
                    0,
                    int(cutover[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]) <= 0,
                    f"{label} dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_sessions")])
    if route_dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_ready",
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")]),
                    "==",
                    route_dispatch_sessions,
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")])
                    == route_dispatch_sessions,
                    f"{label} route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_strategy_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")],
                    "==",
                    cutover["strategy"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        and cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        == cutover["strategy"]
                    ),
                    f"{label} route dispatch round-trip strategy does not match route strategy",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_market_matches",
                    cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")],
                    "==",
                    cutover["market"],
                    bool(
                        cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        and cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        == cutover["market"]
                    ),
                    f"{label} route dispatch round-trip market does not match route market",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_scenario_consistent",
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(cutover[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _shadow_broker_key(key_prefix: str, suffix: str) -> str:
    return f"{key_prefix}shadow_broker_{suffix}"


def _packet(
    state: dict[str, dict[str, Any]],
    thresholds: RouteEnableThresholds,
    checks: pd.DataFrame,
) -> pd.DataFrame:
    cutover = state["cutover"]
    upload = state["upload"]
    order_export = state["order_export"]
    ready = bool(checks["passed"].astype(bool).all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "route_enabled": ready,
                "route_state": "enabled" if ready else "disabled",
                "target_mode": cutover["target_mode"],
                "strategy": cutover["strategy"],
                "market": cutover["market"],
                "scenario_key": cutover["scenario_key"],
                "adapter": cutover["adapter"],
                "max_orders_per_session": int(cutover["max_orders_per_session"]),
                "max_notional_per_session": float(cutover["max_notional_per_session"]),
                "stop_loss": cutover["stop_loss"],
                "strategy_portfolio_required": cutover["strategy_portfolio_required"],
                "strategy_portfolio_provided": cutover["strategy_portfolio_provided"],
                "strategy_portfolio_ready": cutover["strategy_portfolio_ready"],
                "strategy_portfolio_deployment_mode": cutover["strategy_portfolio_deployment_mode"],
                "strategy_portfolio_allocation_mode": cutover["strategy_portfolio_allocation_mode"],
                "strategy_portfolio_capital_currency": cutover["strategy_portfolio_capital_currency"],
                "strategy_portfolio_selected_profile": cutover["strategy_portfolio_selected_profile"],
                "strategy_portfolio_selected_strategy": cutover["strategy_portfolio_selected_strategy"],
                "strategy_portfolio_selected_market": cutover["strategy_portfolio_selected_market"],
                "strategy_portfolio_selected_eligible": cutover["strategy_portfolio_selected_eligible"],
                "strategy_portfolio_selected_allocation_weight": cutover[
                    "strategy_portfolio_selected_allocation_weight"
                ],
                "strategy_portfolio_selected_allocation_notional": cutover[
                    "strategy_portfolio_selected_allocation_notional"
                ],
                "strategy_portfolio_notional_cap_applied": cutover["strategy_portfolio_notional_cap_applied"],
                "strategy_portfolio_min_strategy_count": cutover["strategy_portfolio_min_strategy_count"],
                "strategy_portfolio_min_market_count": cutover["strategy_portfolio_min_market_count"],
                "strategy_portfolio_max_strategy_weight": cutover["strategy_portfolio_max_strategy_weight"],
                "strategy_portfolio_max_market_weight": cutover["strategy_portfolio_max_market_weight"],
                "strategy_portfolio_allocated_strategy_count": cutover[
                    "strategy_portfolio_allocated_strategy_count"
                ],
                "strategy_portfolio_allocated_market_count": cutover[
                    "strategy_portfolio_allocated_market_count"
                ],
                "strategy_portfolio_top_strategy_by_weight": cutover["strategy_portfolio_top_strategy_by_weight"],
                "strategy_portfolio_top_market_by_weight": cutover["strategy_portfolio_top_market_by_weight"],
                "strategy_portfolio_max_strategy_allocation_weight": cutover[
                    "strategy_portfolio_max_strategy_allocation_weight"
                ],
                "strategy_portfolio_max_market_allocation_weight": cutover[
                    "strategy_portfolio_max_market_allocation_weight"
                ],
                **_strategy_portfolio_leadlag_output_fields(cutover),
                "pre_portfolio_max_notional_per_session": cutover["pre_portfolio_max_notional_per_session"],
                **_cutover_lineage_output_fields(cutover),
                "authorizes_submission": False,
                "upload_ready": upload["ready"],
                "upload_orders": int(upload["orders"]),
                "upload_output_file": upload["output_file"],
                "upload_recommendation": upload["recommendation"],
                "adapter_schema_status": upload["schema_status"],
                "broker_schema_status": cutover["broker_schema_status"],
                "broker_schema_reviewed": cutover["broker_schema_reviewed"],
                "broker_schema_review_mode": cutover["broker_schema_review_mode"],
                "order_export_provided": order_export["provided"],
                "order_export_ready": order_export["ready"],
                "order_export_orders": int(order_export["orders"]),
                "order_export_total_notional": float(order_export["total_notional"]),
                "order_export_max_order_notional": float(order_export["max_order_notional"]),
                "proof_refresh_ready": cutover["proof_refresh_ready"],
                "proof_refresh_strategy": cutover["proof_refresh_strategy"],
                "proof_refresh_market": cutover["proof_refresh_market"],
                "route_readiness_required": _route_readiness_required(thresholds, cutover),
                "route_readiness_provided": cutover["route_readiness_provided"],
                "route_readiness_ready": cutover["route_readiness_ready"],
                "route_readiness_strategy": cutover["route_readiness_strategy"],
                "route_readiness_market": cutover["route_readiness_market"],
                "route_readiness_route_ready_pairs": cutover["route_readiness_route_ready_pairs"],
                "route_readiness_gap_pairs": cutover["route_readiness_gap_pairs"],
                "route_readiness_recommendation": cutover["route_readiness_recommendation"],
                "route_readiness_ops_launch_controls_present": cutover[
                    "route_readiness_ops_launch_controls_present"
                ],
                "route_readiness_ops_launch_controls_blocked_pairs": cutover[
                    "route_readiness_ops_launch_controls_blocked_pairs"
                ],
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": cutover[
                    "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"
                ],
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": cutover[
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"
                ],
                **_broker_route_readiness_packet_fields(cutover),
                **_resume_route_readiness_packet_fields(
                    cutover,
                    source_prefix="broker_resume_broker_route_readiness",
                    output_prefix="cutover_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_packet_fields(
                    cutover,
                    source_prefix="broker_resume_incident_broker_route_readiness",
                    output_prefix="cutover_broker_resume_incident_broker_route_readiness",
                ),
                "shadow_broker_readiness_sessions": cutover["shadow_broker_readiness_sessions"],
                "shadow_broker_readiness_ready_sessions": cutover["shadow_broker_readiness_ready_sessions"],
                "shadow_broker_vendor_data_readiness_sessions": cutover[
                    "shadow_broker_vendor_data_readiness_sessions"
                ],
                "shadow_broker_vendor_data_readiness_provided_sessions": cutover[
                    "shadow_broker_vendor_data_readiness_provided_sessions"
                ],
                "shadow_broker_vendor_data_readiness_ready_sessions": cutover[
                    "shadow_broker_vendor_data_readiness_ready_sessions"
                ],
                "shadow_broker_vendor_data_readiness_failed_checks": cutover[
                    "shadow_broker_vendor_data_readiness_failed_checks"
                ],
                "shadow_broker_adapter": cutover["shadow_broker_adapter"],
                "shadow_broker_adapter_count": cutover["shadow_broker_adapter_count"],
                "shadow_broker_route_readiness_sessions": cutover["shadow_broker_route_readiness_sessions"],
                "shadow_broker_route_readiness_ready_sessions": cutover[
                    "shadow_broker_route_readiness_ready_sessions"
                ],
                "shadow_broker_route_readiness_strategy": cutover["shadow_broker_route_readiness_strategy"],
                "shadow_broker_route_readiness_market": cutover["shadow_broker_route_readiness_market"],
                "shadow_broker_route_readiness_gap_pairs": cutover["shadow_broker_route_readiness_gap_pairs"],
                "shadow_broker_dispatch_roundtrip_sessions": cutover["shadow_broker_dispatch_roundtrip_sessions"],
                "shadow_broker_dispatch_roundtrip_ready_sessions": cutover[
                    "shadow_broker_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_dispatch_roundtrip_strategy": cutover["shadow_broker_dispatch_roundtrip_strategy"],
                "shadow_broker_dispatch_roundtrip_market": cutover["shadow_broker_dispatch_roundtrip_market"],
                "shadow_broker_dispatch_roundtrip_scenario_count": cutover[
                    "shadow_broker_dispatch_roundtrip_scenario_count"
                ],
                "shadow_broker_dispatch_roundtrip_missing_request_acks": cutover[
                    "shadow_broker_dispatch_roundtrip_missing_request_acks"
                ],
                "shadow_broker_dispatch_roundtrip_rejected_orders": cutover[
                    "shadow_broker_dispatch_roundtrip_rejected_orders"
                ],
                "shadow_broker_dispatch_roundtrip_unmatched_acks": cutover[
                    "shadow_broker_dispatch_roundtrip_unmatched_acks"
                ],
                "shadow_broker_route_dispatch_roundtrip_sessions": cutover[
                    "shadow_broker_route_dispatch_roundtrip_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": cutover[
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions"
                ],
                "shadow_broker_route_dispatch_roundtrip_strategy": cutover[
                    "shadow_broker_route_dispatch_roundtrip_strategy"
                ],
                "shadow_broker_route_dispatch_roundtrip_market": cutover[
                    "shadow_broker_route_dispatch_roundtrip_market"
                ],
                "shadow_broker_route_dispatch_roundtrip_scenario_count": cutover[
                    "shadow_broker_route_dispatch_roundtrip_scenario_count"
                ],
                **_broker_shadow_broker_packet_fields(cutover),
                **_broker_vendor_data_readiness_packet_fields(cutover),
                **_broker_vendor_market_data_batch_packet_fields(cutover),
                **_vendor_market_data_batch_packet_fields(cutover),
                "broker_resume_gate_ready": cutover["broker_resume_gate_ready"],
                "broker_resume_proof_refresh_ready": cutover["broker_resume_proof_refresh_ready"],
                "dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "dispatch_roundtrip_provided": cutover["dispatch_roundtrip_provided"],
                "dispatch_roundtrip_ready": cutover["dispatch_roundtrip_ready"],
                "dispatch_roundtrip_target_mode": cutover["dispatch_roundtrip_target_mode"],
                "dispatch_roundtrip_strategy": cutover["dispatch_roundtrip_strategy"],
                "dispatch_roundtrip_market": cutover["dispatch_roundtrip_market"],
                "dispatch_roundtrip_scenario_key": cutover["dispatch_roundtrip_scenario_key"],
                "dispatch_roundtrip_batch_id": cutover["dispatch_roundtrip_batch_id"],
                "dispatch_roundtrip_requests": cutover["dispatch_roundtrip_requests"],
                "dispatch_roundtrip_acked_orders": cutover["dispatch_roundtrip_acked_orders"],
                "dispatch_roundtrip_missing_request_acks": cutover["dispatch_roundtrip_missing_request_acks"],
                "dispatch_roundtrip_rejected_orders": cutover["dispatch_roundtrip_rejected_orders"],
                "dispatch_roundtrip_unmatched_acks": cutover["dispatch_roundtrip_unmatched_acks"],
                "dispatch_roundtrip_failed_checks": cutover["dispatch_roundtrip_failed_checks"],
                "route_enable_dispatch_roundtrip_failed_checks": cutover[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "route_dispatch_roundtrip_required": _route_dispatch_roundtrip_required(thresholds, cutover),
                "route_dispatch_roundtrip_provided": cutover["route_dispatch_roundtrip_provided"],
                "route_dispatch_roundtrip_ready": cutover["route_dispatch_roundtrip_ready"],
                "route_dispatch_roundtrip_target_mode": cutover["route_dispatch_roundtrip_target_mode"],
                "route_dispatch_roundtrip_strategy": cutover["route_dispatch_roundtrip_strategy"],
                "route_dispatch_roundtrip_market": cutover["route_dispatch_roundtrip_market"],
                "route_dispatch_roundtrip_scenario_key": cutover["route_dispatch_roundtrip_scenario_key"],
                "route_dispatch_roundtrip_batch_id": cutover["route_dispatch_roundtrip_batch_id"],
                "route_dispatch_roundtrip_requests": cutover["route_dispatch_roundtrip_requests"],
                "route_dispatch_roundtrip_acked_orders": cutover["route_dispatch_roundtrip_acked_orders"],
                "route_dispatch_roundtrip_missing_request_acks": cutover["route_dispatch_roundtrip_missing_request_acks"],
                "route_dispatch_roundtrip_rejected_orders": cutover["route_dispatch_roundtrip_rejected_orders"],
                "route_dispatch_roundtrip_unmatched_acks": cutover["route_dispatch_roundtrip_unmatched_acks"],
                "failed_checks": int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1,
                "threshold_target_mode": thresholds.target_mode,
            }
        ]
    )


def _broker_route_readiness_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    return {
        "cutover_broker_route_readiness_required": cutover["broker_route_readiness_required"],
        "cutover_broker_route_readiness_provided": cutover["broker_route_readiness_provided"],
        "cutover_broker_route_readiness_ready": cutover["broker_route_readiness_ready"],
        "cutover_broker_route_readiness_strategy": cutover["broker_route_readiness_strategy"],
        "cutover_broker_route_readiness_market": cutover["broker_route_readiness_market"],
        "cutover_broker_route_readiness_route_ready_pairs": cutover[
            "broker_route_readiness_route_ready_pairs"
        ],
        "cutover_broker_route_readiness_gap_pairs": cutover["broker_route_readiness_gap_pairs"],
        "cutover_broker_route_readiness_recommendation": cutover["broker_route_readiness_recommendation"],
        "cutover_broker_route_readiness_ops_launch_controls_ready": cutover[
            "broker_route_readiness_ops_launch_controls_ready"
        ],
        "cutover_broker_route_readiness_ops_launch_control_failures": cutover[
            "broker_route_readiness_ops_launch_control_failures"
        ],
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": cutover[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"
        ],
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": cutover[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"
        ],
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": cutover[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
        ],
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": cutover[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
        ],
    }


def _resume_route_readiness_packet_fields(
    cutover: dict[str, Any],
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, Any]:
    return {
        f"{output_prefix}_required": cutover[f"{source_prefix}_required"],
        f"{output_prefix}_provided": cutover[f"{source_prefix}_provided"],
        f"{output_prefix}_ready": cutover[f"{source_prefix}_ready"],
        f"{output_prefix}_strategy": cutover[f"{source_prefix}_strategy"],
        f"{output_prefix}_market": cutover[f"{source_prefix}_market"],
        f"{output_prefix}_route_ready_pairs": cutover[f"{source_prefix}_route_ready_pairs"],
        f"{output_prefix}_gap_pairs": cutover[f"{source_prefix}_gap_pairs"],
        f"{output_prefix}_recommendation": cutover[f"{source_prefix}_recommendation"],
        f"{output_prefix}_ops_launch_controls_ready": cutover[
            f"{source_prefix}_ops_launch_controls_ready"
        ],
        f"{output_prefix}_ops_launch_control_failures": cutover[
            f"{source_prefix}_ops_launch_control_failures"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_safe_runs": cutover[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_breach_runs": cutover[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": cutover[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": cutover[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"
        ],
    }


def _broker_shadow_broker_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    return {
        "cutover_broker_shadow_broker_readiness_provided": cutover[
            "broker_shadow_broker_readiness_provided"
        ],
        "cutover_broker_shadow_broker_readiness_sessions": cutover[
            "broker_shadow_broker_readiness_sessions"
        ],
        "cutover_broker_shadow_broker_readiness_ready_sessions": cutover[
            "broker_shadow_broker_readiness_ready_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_sessions": cutover[
            "broker_shadow_broker_vendor_data_readiness_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions": cutover[
            "broker_shadow_broker_vendor_data_readiness_provided_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions": cutover[
            "broker_shadow_broker_vendor_data_readiness_ready_sessions"
        ],
        "cutover_broker_shadow_broker_vendor_data_readiness_failed_checks": cutover[
            "broker_shadow_broker_vendor_data_readiness_failed_checks"
        ],
        "cutover_broker_shadow_broker_adapter": cutover["broker_shadow_broker_adapter"],
        "cutover_broker_shadow_broker_adapter_count": cutover["broker_shadow_broker_adapter_count"],
        "cutover_broker_shadow_broker_route_readiness_sessions": cutover[
            "broker_shadow_broker_route_readiness_sessions"
        ],
        "cutover_broker_shadow_broker_route_readiness_ready_sessions": cutover[
            "broker_shadow_broker_route_readiness_ready_sessions"
        ],
        "cutover_broker_shadow_broker_route_readiness_strategy": cutover[
            "broker_shadow_broker_route_readiness_strategy"
        ],
        "cutover_broker_shadow_broker_route_readiness_market": cutover[
            "broker_shadow_broker_route_readiness_market"
        ],
        "cutover_broker_shadow_broker_route_readiness_gap_pairs": cutover[
            "broker_shadow_broker_route_readiness_gap_pairs"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_sessions": cutover[
            "broker_shadow_broker_dispatch_roundtrip_sessions"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions": cutover[
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_strategy": cutover[
            "broker_shadow_broker_dispatch_roundtrip_strategy"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_market": cutover[
            "broker_shadow_broker_dispatch_roundtrip_market"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count": cutover[
            "broker_shadow_broker_dispatch_roundtrip_scenario_count"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": cutover[
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders": cutover[
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders"
        ],
        "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": cutover[
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_sessions"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_strategy"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_market": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_market"
        ],
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": cutover[
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count"
        ],
    }


def _vendor_market_data_batch_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    vendor = cutover["vendor_market_data_batch"]
    return {
        "cutover_vendor_market_data_batch_provided": vendor["provided"],
        "cutover_vendor_market_data_batch_ready": vendor["ready"],
        "cutover_vendor_market_data_batch_adapter": vendor["adapter"],
        "cutover_vendor_market_data_batch_kind": vendor["kind"],
        "cutover_vendor_market_data_batch_manifest_run_type": vendor["manifest_run_type"],
        "cutover_vendor_market_data_batch_market": vendor["market"],
        "cutover_vendor_market_data_batch_dataset_count": vendor["dataset_count"],
        "cutover_vendor_market_data_batch_ready_datasets": vendor["ready_datasets"],
        "cutover_vendor_market_data_batch_failed_datasets": vendor["failed_datasets"],
        "cutover_vendor_market_data_batch_ready_rate": vendor["ready_rate"],
        "cutover_vendor_market_data_batch_unique_source_files": vendor["unique_source_files"],
        "cutover_vendor_market_data_batch_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        "cutover_vendor_market_data_batch_source_file_fingerprint_coverage": vendor[
            "source_file_fingerprint_coverage"
        ],
        "cutover_vendor_market_data_batch_min_mapping_coverage": vendor["min_mapping_coverage"],
        "cutover_vendor_market_data_batch_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        "cutover_vendor_market_data_batch_mapping_sources": vendor["mapping_sources"],
        "cutover_vendor_market_data_batch_comparison_accepted": vendor["comparison_accepted"],
        "cutover_vendor_market_data_batch_comparison_failed_checks": vendor["comparison_failed_checks"],
        "cutover_vendor_market_data_batch_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_market_data_batch_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    vendor = cutover["broker_dispatch_roundtrip_vendor_market_data_batch"]
    field_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    route_lineage_sha256 = _target_application_lineage_sha256(vendor)
    return {
        f"{field_prefix}_provided": vendor["provided"],
        f"{field_prefix}_ready": vendor["ready"],
        f"{field_prefix}_adapter": vendor["adapter"],
        f"{field_prefix}_kind": vendor["kind"],
        f"{field_prefix}_manifest_run_type": vendor["manifest_run_type"],
        f"{field_prefix}_market": vendor["market"],
        f"{field_prefix}_dataset_count": vendor["dataset_count"],
        f"{field_prefix}_ready_datasets": vendor["ready_datasets"],
        f"{field_prefix}_failed_datasets": vendor["failed_datasets"],
        f"{field_prefix}_ready_rate": vendor["ready_rate"],
        f"{field_prefix}_unique_source_files": vendor["unique_source_files"],
        f"{field_prefix}_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        f"{field_prefix}_source_file_fingerprint_coverage": vendor["source_file_fingerprint_coverage"],
        f"{field_prefix}_min_mapping_coverage": vendor["min_mapping_coverage"],
        f"{field_prefix}_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        f"{field_prefix}_mapping_sources": vendor["mapping_sources"],
        f"{field_prefix}_mapping_source_mode": vendor["mapping_source_mode"],
        f"{field_prefix}_mapping_application_count": vendor["mapping_application_count"],
        f"{field_prefix}_unique_mapping_applications": vendor["unique_mapping_applications"],
        f"{field_prefix}_target_application_coverage": vendor["target_application_coverage"],
        f"{field_prefix}_application_lineage_consistency_required": vendor[
            "application_lineage_consistency_required"
        ],
        f"{field_prefix}_application_lineage_consistent": vendor[
            "application_lineage_consistent"
        ],
        **_broker_vendor_final_lineage_packet_fields(cutover),
        **_broker_vendor_cutover_complete_final_lineage_packet_fields(cutover),
        **_broker_vendor_cutover_extended_complete_final_lineage_packet_fields(
            cutover
        ),
        **_broker_vendor_cutover_extended_complete_final_lineage_36_packet_fields(
            cutover
        ),
        **_broker_vendor_cutover_latest_extended_complete_final_lineage_44_packet_fields(
            cutover
        ),
        **_broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_packet_fields(
            cutover
        ),
        **_broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_packet_fields(
            cutover
        ),
        **_broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_packet_fields(
            cutover
        ),
        **_broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_packet_fields(
            cutover
        ),
        "cutover_broker_vendor_market_data_batch_lineage_match_required": cutover[
            "broker_vendor_market_data_batch_lineage_match_required"
        ],
        "cutover_broker_vendor_market_data_batch_lineage_matches": cutover[
            "broker_vendor_market_data_batch_lineage_matches"
        ],
        "cutover_vendor_market_data_batch_application_lineage_sha256": cutover[
            "vendor_market_data_batch_application_lineage_sha256"
        ],
        "cutover_broker_vendor_market_data_batch_application_lineage_sha256": cutover[
            "broker_vendor_market_data_batch_application_lineage_sha256"
        ],
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": cutover[
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ],
        f"{field_prefix}_application_lineage_sha256": cutover[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ],
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            route_lineage_sha256
        ),
        f"{field_prefix}_comparison_accepted": vendor["comparison_accepted"],
        f"{field_prefix}_comparison_failed_checks": vendor["comparison_failed_checks"],
        f"{field_prefix}_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_final_lineage_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    source_prefix = CUTOVER_FINAL_LINEAGE_FIELD_PREFIX
    field_prefix = CUTOVER_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{field_prefix}_lineage_match_required": cutover[
            f"{source_prefix}_lineage_match_required"
        ],
        f"{field_prefix}_lineage_matches": cutover[
            f"{source_prefix}_lineage_matches"
        ],
        f"{field_prefix}_cutover_review_carried_application_lineage_sha256": cutover[
            f"{source_prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in CUTOVER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{field_prefix}_{field}"] = cutover[f"{source_prefix}_{field}"]
    return fields


def _broker_vendor_cutover_complete_final_lineage_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_cutover_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in CUTOVER_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_extended_complete_final_lineage_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_extended_complete_final_lineage_36_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_latest_extended_complete_final_lineage_44_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover[
            f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS,
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS,
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD,
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_packet_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    prefix = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": cutover[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": cutover[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": cutover[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
        *CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CONFIRMED_REVIEW_FIELDS,
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = cutover[f"{prefix}_{field}"]
    return fields


def _broker_vendor_data_readiness_packet_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    readiness = cutover["broker_vendor_data_readiness"]
    return {
        "cutover_broker_vendor_data_readiness_provided": readiness["provided"],
        "cutover_broker_vendor_data_readiness_ready": readiness["ready"],
        "cutover_broker_vendor_data_readiness_failed_checks": readiness["failed_checks"],
    }


def _summary(packet: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(packet["target_mode"]),
                "strategy": str(packet["strategy"]),
                "market": str(packet["market"]),
                "scenario_key": str(packet["scenario_key"]),
                "adapter": str(packet["adapter"]),
                "route_state": "enabled" if ready else "disabled",
                "upload_orders": int(packet["upload_orders"]),
                "max_orders_per_session": int(packet["max_orders_per_session"]),
                "max_notional_per_session": float(packet["max_notional_per_session"]),
                "order_export_total_notional": float(packet["order_export_total_notional"]),
                "strategy_portfolio_required": _to_bool(packet["strategy_portfolio_required"]),
                "strategy_portfolio_provided": _to_bool(packet["strategy_portfolio_provided"]),
                "strategy_portfolio_ready": _to_bool(packet["strategy_portfolio_ready"]),
                "strategy_portfolio_deployment_mode": str(packet["strategy_portfolio_deployment_mode"]),
                "strategy_portfolio_allocation_mode": str(packet["strategy_portfolio_allocation_mode"]),
                "strategy_portfolio_capital_currency": str(packet["strategy_portfolio_capital_currency"]),
                "strategy_portfolio_selected_profile": str(packet["strategy_portfolio_selected_profile"]),
                "strategy_portfolio_selected_strategy": str(packet["strategy_portfolio_selected_strategy"]),
                "strategy_portfolio_selected_market": str(packet["strategy_portfolio_selected_market"]),
                "strategy_portfolio_selected_eligible": _to_bool(packet["strategy_portfolio_selected_eligible"]),
                "strategy_portfolio_selected_allocation_weight": float(
                    packet["strategy_portfolio_selected_allocation_weight"]
                ),
                "strategy_portfolio_selected_allocation_notional": float(
                    packet["strategy_portfolio_selected_allocation_notional"]
                ),
                "strategy_portfolio_notional_cap_applied": _to_bool(
                    packet["strategy_portfolio_notional_cap_applied"]
                ),
                "strategy_portfolio_min_strategy_count": int(packet["strategy_portfolio_min_strategy_count"]),
                "strategy_portfolio_min_market_count": int(packet["strategy_portfolio_min_market_count"]),
                "strategy_portfolio_max_strategy_weight": float(packet["strategy_portfolio_max_strategy_weight"]),
                "strategy_portfolio_max_market_weight": float(packet["strategy_portfolio_max_market_weight"]),
                "strategy_portfolio_allocated_strategy_count": int(
                    packet["strategy_portfolio_allocated_strategy_count"]
                ),
                "strategy_portfolio_allocated_market_count": int(
                    packet["strategy_portfolio_allocated_market_count"]
                ),
                "strategy_portfolio_top_strategy_by_weight": str(
                    packet["strategy_portfolio_top_strategy_by_weight"]
                ),
                "strategy_portfolio_top_market_by_weight": str(packet["strategy_portfolio_top_market_by_weight"]),
                "strategy_portfolio_max_strategy_allocation_weight": float(
                    packet["strategy_portfolio_max_strategy_allocation_weight"]
                ),
                "strategy_portfolio_max_market_allocation_weight": float(
                    packet["strategy_portfolio_max_market_allocation_weight"]
                ),
                **_strategy_portfolio_leadlag_summary_fields(packet),
                "pre_portfolio_max_notional_per_session": float(packet["pre_portfolio_max_notional_per_session"]),
                **_cutover_lineage_summary_fields(packet),
                "authorizes_submission": False,
                "adapter_schema_status": str(packet["adapter_schema_status"]),
                "broker_schema_status": str(packet["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(packet["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(packet["broker_schema_review_mode"]),
                "proof_refresh_ready": _to_bool(packet["proof_refresh_ready"]),
                "route_readiness_required": _to_bool(packet["route_readiness_required"]),
                "route_readiness_provided": _to_bool(packet["route_readiness_provided"]),
                "route_readiness_ready": _to_bool(packet["route_readiness_ready"]),
                "route_readiness_strategy": str(packet["route_readiness_strategy"]),
                "route_readiness_market": str(packet["route_readiness_market"]),
                "route_readiness_route_ready_pairs": int(packet["route_readiness_route_ready_pairs"]),
                "route_readiness_gap_pairs": int(packet["route_readiness_gap_pairs"]),
                "route_readiness_ops_launch_controls_present": _to_bool(
                    packet["route_readiness_ops_launch_controls_present"]
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": int(
                    packet["route_readiness_ops_launch_controls_blocked_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    packet["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    packet["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]
                ),
                **_broker_route_readiness_summary_fields(packet),
                **_resume_route_readiness_summary_fields(
                    packet,
                    "cutover_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_summary_fields(
                    packet,
                    "cutover_broker_resume_incident_broker_route_readiness",
                ),
                "shadow_broker_readiness_sessions": int(packet["shadow_broker_readiness_sessions"]),
                "shadow_broker_readiness_ready_sessions": int(packet["shadow_broker_readiness_ready_sessions"]),
                "shadow_broker_vendor_data_readiness_sessions": int(
                    packet["shadow_broker_vendor_data_readiness_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    packet["shadow_broker_vendor_data_readiness_provided_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    packet["shadow_broker_vendor_data_readiness_ready_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    packet["shadow_broker_vendor_data_readiness_failed_checks"]
                ),
                "shadow_broker_adapter": str(packet["shadow_broker_adapter"]),
                "shadow_broker_adapter_count": int(packet["shadow_broker_adapter_count"]),
                "shadow_broker_route_readiness_sessions": int(packet["shadow_broker_route_readiness_sessions"]),
                "shadow_broker_route_readiness_ready_sessions": int(
                    packet["shadow_broker_route_readiness_ready_sessions"]
                ),
                "shadow_broker_route_readiness_strategy": str(packet["shadow_broker_route_readiness_strategy"]),
                "shadow_broker_route_readiness_market": str(packet["shadow_broker_route_readiness_market"]),
                "shadow_broker_route_readiness_gap_pairs": int(packet["shadow_broker_route_readiness_gap_pairs"]),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    packet["shadow_broker_dispatch_roundtrip_sessions"]
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    packet["shadow_broker_dispatch_roundtrip_ready_sessions"]
                ),
                "shadow_broker_dispatch_roundtrip_strategy": str(
                    packet["shadow_broker_dispatch_roundtrip_strategy"]
                ),
                "shadow_broker_dispatch_roundtrip_market": str(packet["shadow_broker_dispatch_roundtrip_market"]),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    packet["shadow_broker_dispatch_roundtrip_scenario_count"]
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    packet["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    packet["shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    packet["shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    packet["shadow_broker_route_dispatch_roundtrip_sessions"]
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    packet["shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": str(
                    packet["shadow_broker_route_dispatch_roundtrip_strategy"]
                ),
                "shadow_broker_route_dispatch_roundtrip_market": str(
                    packet["shadow_broker_route_dispatch_roundtrip_market"]
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    packet["shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
                **_broker_shadow_broker_summary_fields(packet),
                **_broker_vendor_data_readiness_summary_fields(packet),
                **_broker_vendor_market_data_batch_summary_fields(packet),
                **_vendor_market_data_batch_summary_fields(packet),
                "broker_resume_gate_ready": _to_bool(packet["broker_resume_gate_ready"]),
                "broker_resume_proof_refresh_ready": _to_bool(packet["broker_resume_proof_refresh_ready"]),
                "dispatch_roundtrip_required": _to_bool(packet["dispatch_roundtrip_required"]),
                "dispatch_roundtrip_provided": _to_bool(packet["dispatch_roundtrip_provided"]),
                "dispatch_roundtrip_ready": _to_bool(packet["dispatch_roundtrip_ready"]),
                "dispatch_roundtrip_batch_id": str(packet["dispatch_roundtrip_batch_id"]),
                "dispatch_roundtrip_requests": int(packet["dispatch_roundtrip_requests"]),
                "dispatch_roundtrip_acked_orders": int(packet["dispatch_roundtrip_acked_orders"]),
                "dispatch_roundtrip_missing_request_acks": int(packet["dispatch_roundtrip_missing_request_acks"]),
                "dispatch_roundtrip_rejected_orders": int(packet["dispatch_roundtrip_rejected_orders"]),
                "dispatch_roundtrip_unmatched_acks": int(packet["dispatch_roundtrip_unmatched_acks"]),
                "dispatch_roundtrip_failed_checks": int(packet["dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip_failed_checks": int(
                    packet["route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "route_dispatch_roundtrip_required": _to_bool(packet["route_dispatch_roundtrip_required"]),
                "route_dispatch_roundtrip_provided": _to_bool(packet["route_dispatch_roundtrip_provided"]),
                "route_dispatch_roundtrip_ready": _to_bool(packet["route_dispatch_roundtrip_ready"]),
                "route_dispatch_roundtrip_batch_id": str(packet["route_dispatch_roundtrip_batch_id"]),
                "route_dispatch_roundtrip_requests": int(packet["route_dispatch_roundtrip_requests"]),
                "route_dispatch_roundtrip_acked_orders": int(packet["route_dispatch_roundtrip_acked_orders"]),
                "route_dispatch_roundtrip_missing_request_acks": int(
                    packet["route_dispatch_roundtrip_missing_request_acks"]
                ),
                "route_dispatch_roundtrip_rejected_orders": int(packet["route_dispatch_roundtrip_rejected_orders"]),
                "route_dispatch_roundtrip_unmatched_acks": int(packet["route_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": failed,
                "recommendation": "enable_broker_route" if ready else "keep_broker_route_disabled",
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


def _action_queue(packet: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _object_text(row.get("check")).strip()
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "route_enable_checks",
                "component": _component(check),
                "check": check,
                "actual": row.get("value"),
                "operator": _object_text(row.get("operator")).strip(),
                "expected": row.get("threshold"),
                "target_mode": _object_text(packet.get("target_mode")).strip(),
                "strategy": _object_text(packet.get("strategy")).strip(),
                "market": _object_text(packet.get("market")).strip(),
                "scenario_key": _object_text(packet.get("scenario_key")).strip(),
                "adapter": _object_text(packet.get("adapter")).strip(),
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
    if check.startswith("upload_"):
        return "upload_pack"
    if check.startswith("order_export_"):
        return "order_export"
    if check.startswith(
        (
            "cutover_scaleup_proof_refresh_",
            "cutover_current_scaleup_proof_refresh_",
        )
    ):
        return "proof_refresh"
    if check.startswith("cutover_broker_resume_") or check.startswith("broker_resume_"):
        return "resume_gate"
    if (
        "broker_readiness_roundtrip_contract_identity" in check
        or "broker_readiness_contract_identity" in check
        or "broker_readiness_route_contract_identity" in check
        or (
            "broker_readiness_route_enable_route_contract_identity"
            in check
        )
        or "runtime_contract_identity" in check
        or "runtime_route_contract_identity" in check
        or "runtime_route_enable_route_contract_identity" in check
    ):
        return "broker_readiness"
    if check.startswith("cutover_broker_readiness_") or check in {
        "cutover_runtime_lineage_source_bound",
        "cutover_runtime_lineage_matches_current",
    }:
        return "broker_readiness"
    if "route_readiness" in check:
        return "route_readiness"
    if "dispatch_roundtrip" in check:
        return "broker_dispatch_roundtrip"
    if "vendor_market_data_batch" in check:
        return "vendor_market_data"
    if "broker_vendor_data_readiness" in check or "vendor_data_readiness" in check:
        return "broker_vendor_data_readiness"
    if check.startswith("cutover_broker_shadow_broker") or check.startswith("cutover_"):
        return "cutover_gate"
    if check in {"target_mode_matches", "adapter_matches", "strategy_matches", "market_matches"}:
        return "route_identity"
    if check.startswith("strategy_portfolio_"):
        return "strategy_portfolio"
    return "route_enable"


def _next_gate(check: str) -> str:
    component = _component(check)
    if component == "upload_pack":
        return "pack-broker-upload"
    if component == "order_export":
        return "export-launch-orders"
    if component == "proof_refresh":
        return "review-proof-refresh"
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
    if component == "resume_gate":
        return "review-resume-gate"
    if component in {"cutover_gate", "strategy_portfolio"}:
        return "review-cutover-gate"
    return "review-route-enable"


def _action_recommendation(check: str) -> str:
    component = _component(check)
    if component == "upload_pack":
        return "repair_or_rebuild_broker_upload_pack"
    if component == "order_export":
        return "repair_or_rebuild_broker_order_export"
    if component == "proof_refresh":
        return "repair_proof_refresh_before_route_enable"
    if component == "route_readiness":
        return "rerun_route_readiness_before_route_enable"
    if component == "broker_dispatch_roundtrip":
        return "rerun_broker_dispatch_roundtrip_before_route_enable"
    if component == "vendor_market_data":
        return "refresh_vendor_market_data_batch_proof"
    if component == "broker_vendor_data_readiness":
        return "refresh_broker_vendor_data_readiness_wrapper"
    if component == "broker_readiness":
        return "rebuild_broker_readiness_lineage_before_route_enable"
    if component == "resume_gate":
        return "repair_resume_gate_proof_before_route_enable"
    if component == "cutover_gate":
        return "repair_cutover_gate_before_route_enable"
    if component == "strategy_portfolio":
        return "repair_strategy_portfolio_cutover_allocation"
    if component == "route_identity":
        return "align_route_enable_identity_inputs"
    return "repair_route_enable_inputs"


def _broker_route_readiness_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_broker_route_readiness_required": _to_bool(
            packet["cutover_broker_route_readiness_required"]
        ),
        "cutover_broker_route_readiness_provided": _to_bool(
            packet["cutover_broker_route_readiness_provided"]
        ),
        "cutover_broker_route_readiness_ready": _to_bool(packet["cutover_broker_route_readiness_ready"]),
        "cutover_broker_route_readiness_strategy": str(packet["cutover_broker_route_readiness_strategy"]),
        "cutover_broker_route_readiness_market": str(packet["cutover_broker_route_readiness_market"]),
        "cutover_broker_route_readiness_route_ready_pairs": int(
            packet["cutover_broker_route_readiness_route_ready_pairs"]
        ),
        "cutover_broker_route_readiness_gap_pairs": int(packet["cutover_broker_route_readiness_gap_pairs"]),
        "cutover_broker_route_readiness_recommendation": str(
            packet["cutover_broker_route_readiness_recommendation"]
        ),
        "cutover_broker_route_readiness_ops_launch_controls_ready": _to_bool(
            packet["cutover_broker_route_readiness_ops_launch_controls_ready"]
        ),
        "cutover_broker_route_readiness_ops_launch_control_failures": str(
            packet["cutover_broker_route_readiness_ops_launch_control_failures"]
        ),
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _broker_shadow_broker_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_broker_shadow_broker_readiness_provided": _to_bool(
            packet["cutover_broker_shadow_broker_readiness_provided"]
        ),
        "cutover_broker_shadow_broker_readiness_sessions": int(
            packet["cutover_broker_shadow_broker_readiness_sessions"]
        ),
        "cutover_broker_shadow_broker_readiness_ready_sessions": int(
            packet["cutover_broker_shadow_broker_readiness_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_sessions": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            packet["cutover_broker_shadow_broker_vendor_data_readiness_failed_checks"]
        ),
        "cutover_broker_shadow_broker_adapter": str(packet["cutover_broker_shadow_broker_adapter"]),
        "cutover_broker_shadow_broker_adapter_count": int(
            packet["cutover_broker_shadow_broker_adapter_count"]
        ),
        "cutover_broker_shadow_broker_route_readiness_sessions": int(
            packet["cutover_broker_shadow_broker_route_readiness_sessions"]
        ),
        "cutover_broker_shadow_broker_route_readiness_ready_sessions": int(
            packet["cutover_broker_shadow_broker_route_readiness_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_route_readiness_strategy": str(
            packet["cutover_broker_shadow_broker_route_readiness_strategy"]
        ),
        "cutover_broker_shadow_broker_route_readiness_market": str(
            packet["cutover_broker_shadow_broker_route_readiness_market"]
        ),
        "cutover_broker_shadow_broker_route_readiness_gap_pairs": int(
            packet["cutover_broker_shadow_broker_route_readiness_gap_pairs"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_sessions": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_sessions"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_strategy": str(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_strategy"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_market": str(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_market"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
        ),
        "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            packet["cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy": str(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_market": str(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_market"]
        ),
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
        ),
    }


def _vendor_market_data_batch_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_vendor_market_data_batch_provided": _to_bool(
            packet["cutover_vendor_market_data_batch_provided"]
        ),
        "cutover_vendor_market_data_batch_ready": _to_bool(packet["cutover_vendor_market_data_batch_ready"]),
        "cutover_vendor_market_data_batch_adapter": str(packet["cutover_vendor_market_data_batch_adapter"]),
        "cutover_vendor_market_data_batch_kind": str(packet["cutover_vendor_market_data_batch_kind"]),
        "cutover_vendor_market_data_batch_manifest_run_type": str(
            packet["cutover_vendor_market_data_batch_manifest_run_type"]
        ),
        "cutover_vendor_market_data_batch_market": str(packet["cutover_vendor_market_data_batch_market"]),
        "cutover_vendor_market_data_batch_dataset_count": int(
            packet["cutover_vendor_market_data_batch_dataset_count"]
        ),
        "cutover_vendor_market_data_batch_ready_datasets": int(
            packet["cutover_vendor_market_data_batch_ready_datasets"]
        ),
        "cutover_vendor_market_data_batch_failed_datasets": int(
            packet["cutover_vendor_market_data_batch_failed_datasets"]
        ),
        "cutover_vendor_market_data_batch_ready_rate": _jsonable(
            packet["cutover_vendor_market_data_batch_ready_rate"]
        ),
        "cutover_vendor_market_data_batch_unique_source_files": int(
            packet["cutover_vendor_market_data_batch_unique_source_files"]
        ),
        "cutover_vendor_market_data_batch_unique_header_fingerprints": int(
            packet["cutover_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "cutover_vendor_market_data_batch_source_file_fingerprint_coverage": _jsonable(
            packet["cutover_vendor_market_data_batch_source_file_fingerprint_coverage"]
        ),
        "cutover_vendor_market_data_batch_min_mapping_coverage": _jsonable(
            packet["cutover_vendor_market_data_batch_min_mapping_coverage"]
        ),
        "cutover_vendor_market_data_batch_unique_mapping_drafts": int(
            packet["cutover_vendor_market_data_batch_unique_mapping_drafts"]
        ),
        "cutover_vendor_market_data_batch_mapping_sources": str(
            packet["cutover_vendor_market_data_batch_mapping_sources"]
        ),
        "cutover_vendor_market_data_batch_comparison_accepted": _to_bool(
            packet["cutover_vendor_market_data_batch_comparison_accepted"]
        ),
        "cutover_vendor_market_data_batch_comparison_failed_checks": int(
            packet["cutover_vendor_market_data_batch_comparison_failed_checks"]
        ),
    }


def _broker_vendor_market_data_batch_summary_fields(packet: pd.Series) -> dict[str, Any]:
    field_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": _to_bool(packet[f"{field_prefix}_provided"]),
        f"{field_prefix}_ready": _to_bool(packet[f"{field_prefix}_ready"]),
        f"{field_prefix}_adapter": str(packet[f"{field_prefix}_adapter"]),
        f"{field_prefix}_kind": str(packet[f"{field_prefix}_kind"]),
        f"{field_prefix}_manifest_run_type": str(packet[f"{field_prefix}_manifest_run_type"]),
        f"{field_prefix}_market": str(packet[f"{field_prefix}_market"]),
        f"{field_prefix}_dataset_count": int(packet[f"{field_prefix}_dataset_count"]),
        f"{field_prefix}_ready_datasets": int(packet[f"{field_prefix}_ready_datasets"]),
        f"{field_prefix}_failed_datasets": int(packet[f"{field_prefix}_failed_datasets"]),
        f"{field_prefix}_ready_rate": _jsonable(packet[f"{field_prefix}_ready_rate"]),
        f"{field_prefix}_unique_source_files": int(packet[f"{field_prefix}_unique_source_files"]),
        f"{field_prefix}_unique_header_fingerprints": int(
            packet[f"{field_prefix}_unique_header_fingerprints"]
        ),
        f"{field_prefix}_source_file_fingerprint_coverage": _jsonable(
            packet[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        f"{field_prefix}_min_mapping_coverage": _jsonable(packet[f"{field_prefix}_min_mapping_coverage"]),
        f"{field_prefix}_unique_mapping_drafts": int(packet[f"{field_prefix}_unique_mapping_drafts"]),
        f"{field_prefix}_mapping_sources": str(packet[f"{field_prefix}_mapping_sources"]),
        f"{field_prefix}_mapping_source_mode": str(packet[f"{field_prefix}_mapping_source_mode"]),
        f"{field_prefix}_mapping_application_count": int(
            packet[f"{field_prefix}_mapping_application_count"]
        ),
        f"{field_prefix}_unique_mapping_applications": int(
            packet[f"{field_prefix}_unique_mapping_applications"]
        ),
        f"{field_prefix}_target_application_coverage": _jsonable(
            packet[f"{field_prefix}_target_application_coverage"]
        ),
        f"{field_prefix}_application_lineage_consistency_required": _to_bool(
            packet[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        f"{field_prefix}_application_lineage_consistent": _to_bool(
            packet[f"{field_prefix}_application_lineage_consistent"]
        ),
        **_broker_vendor_final_lineage_summary_fields(packet),
        **_broker_vendor_cutover_complete_final_lineage_summary_fields(packet),
        **_broker_vendor_cutover_extended_complete_final_lineage_summary_fields(
            packet
        ),
        **_broker_vendor_cutover_extended_complete_final_lineage_36_summary_fields(
            packet
        ),
        **_broker_vendor_cutover_latest_extended_complete_final_lineage_44_summary_fields(
            packet
        ),
        **_broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_summary_fields(
            packet
        ),
        **_broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_summary_fields(
            packet
        ),
        **_broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_summary_fields(
            packet
        ),
        **_broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_summary_fields(
            packet
        ),
        "cutover_broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            packet["cutover_broker_vendor_market_data_batch_lineage_match_required"]
        ),
        "cutover_broker_vendor_market_data_batch_lineage_matches": _to_bool(
            packet["cutover_broker_vendor_market_data_batch_lineage_matches"]
        ),
        "cutover_vendor_market_data_batch_application_lineage_sha256": str(
            packet["cutover_vendor_market_data_batch_application_lineage_sha256"]
        ),
        "cutover_broker_vendor_market_data_batch_application_lineage_sha256": str(
            packet[
                "cutover_broker_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": str(
            packet[
                "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
        f"{field_prefix}_application_lineage_sha256": str(
            packet[f"{field_prefix}_application_lineage_sha256"]
        ),
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
        f"{field_prefix}_comparison_accepted": _to_bool(packet[f"{field_prefix}_comparison_accepted"]),
        f"{field_prefix}_comparison_failed_checks": int(packet[f"{field_prefix}_comparison_failed_checks"]),
        f"{field_prefix}_datasets_json": str(packet[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_final_lineage_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    field_prefix = CUTOVER_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{field_prefix}_lineage_match_required": _to_bool(
            packet[f"{field_prefix}_lineage_match_required"]
        ),
        f"{field_prefix}_lineage_matches": _to_bool(
            packet[f"{field_prefix}_lineage_matches"]
        ),
        f"{field_prefix}_cutover_review_carried_application_lineage_sha256": str(
            packet[
                f"{field_prefix}_cutover_review_carried_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{field_prefix}_{field}"] = str(
            packet[f"{field_prefix}_{field}"]
        )
    return fields


def _broker_vendor_cutover_complete_final_lineage_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_cutover_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_final_review_carried_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_extended_complete_final_lineage_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_route_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_extended_complete_final_lineage_36_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_route_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_latest_extended_complete_final_lineage_44_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_route_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS,
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD}": str(
            packet[
                f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD}"
            ]
        ),
        f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD}": str(
            packet[
                f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD}"
            ]
        ),
        f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD}": str(
            packet[
                f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD}"
            ]
        ),
        f"{prefix}_route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            packet[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            packet[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_route_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
        *CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CONFIRMED_REVIEW_FIELDS,
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(packet[f"{prefix}_{field}"])
    return fields


def _broker_vendor_data_readiness_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {
        "cutover_broker_vendor_data_readiness_provided": _to_bool(
            packet["cutover_broker_vendor_data_readiness_provided"]
        ),
        "cutover_broker_vendor_data_readiness_ready": _to_bool(
            packet["cutover_broker_vendor_data_readiness_ready"]
        ),
        "cutover_broker_vendor_data_readiness_failed_checks": int(
            packet["cutover_broker_vendor_data_readiness_failed_checks"]
        ),
    }


def _config(
    packet: pd.Series,
    thresholds: RouteEnableThresholds,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "route_enabled": _to_bool(packet["route_enabled"]),
        "route_state": str(packet["route_state"]),
        "failed_check_count": len(failed_check_records),
        "target_mode": str(packet["target_mode"]),
        "strategy": str(packet["strategy"]),
        "market": str(packet["market"]),
        "scenario_key": str(packet["scenario_key"]),
        "adapter": str(packet["adapter"]),
        "limits": {
            "max_orders_per_session": int(packet["max_orders_per_session"]),
            "max_notional_per_session": float(packet["max_notional_per_session"]),
            "stop_loss": _jsonable(packet["stop_loss"]),
        },
        "strategy_portfolio": {
            "required": _to_bool(packet["strategy_portfolio_required"]),
            "provided": _to_bool(packet["strategy_portfolio_provided"]),
            "ready": _to_bool(packet["strategy_portfolio_ready"]),
            "deployment_mode": str(packet["strategy_portfolio_deployment_mode"]),
            "allocation_mode": str(packet["strategy_portfolio_allocation_mode"]),
            "capital_currency": str(packet["strategy_portfolio_capital_currency"]),
            "selected_profile": str(packet["strategy_portfolio_selected_profile"]),
            "selected_strategy": str(packet["strategy_portfolio_selected_strategy"]),
            "selected_market": str(packet["strategy_portfolio_selected_market"]),
            "selected_eligible": _to_bool(packet["strategy_portfolio_selected_eligible"]),
            "selected_allocation_weight": float(packet["strategy_portfolio_selected_allocation_weight"]),
            "selected_allocation_notional": float(packet["strategy_portfolio_selected_allocation_notional"]),
            "notional_cap_applied": _to_bool(packet["strategy_portfolio_notional_cap_applied"]),
            "min_strategy_count": int(packet["strategy_portfolio_min_strategy_count"]),
            "min_market_count": int(packet["strategy_portfolio_min_market_count"]),
            "max_strategy_weight": float(packet["strategy_portfolio_max_strategy_weight"]),
            "max_market_weight": float(packet["strategy_portfolio_max_market_weight"]),
            "allocated_strategy_count": int(packet["strategy_portfolio_allocated_strategy_count"]),
            "allocated_market_count": int(packet["strategy_portfolio_allocated_market_count"]),
            "top_strategy_by_weight": str(packet["strategy_portfolio_top_strategy_by_weight"]),
            "top_market_by_weight": str(packet["strategy_portfolio_top_market_by_weight"]),
            "max_strategy_allocation_weight": float(packet["strategy_portfolio_max_strategy_allocation_weight"]),
            "max_market_allocation_weight": float(packet["strategy_portfolio_max_market_allocation_weight"]),
            **_strategy_portfolio_leadlag_config(packet),
            "pre_portfolio_max_notional_per_session": float(packet["pre_portfolio_max_notional_per_session"]),
        },
        "cutover_lineage": _cutover_lineage_config(packet),
        "upload": {
            "ready": _to_bool(packet["upload_ready"]),
            "orders": int(packet["upload_orders"]),
            "output_file": str(packet["upload_output_file"]),
            "adapter_schema_status": str(packet["adapter_schema_status"]),
            "recommendation": str(packet["upload_recommendation"]),
        },
        "broker_readiness": {
            "adapter_schema_status": str(packet["broker_schema_status"]),
            "schema_reviewed": _to_bool(packet["broker_schema_reviewed"]),
            "schema_review_mode": str(packet["broker_schema_review_mode"]),
        },
        "order_export": {
            "provided": _to_bool(packet["order_export_provided"]),
            "ready": _to_bool(packet["order_export_ready"]),
            "orders": int(packet["order_export_orders"]),
            "total_notional": float(packet["order_export_total_notional"]),
            "max_order_notional": float(packet["order_export_max_order_notional"]),
        },
        "proof_freshness": {
            "ready": _to_bool(packet["proof_refresh_ready"]),
            "strategy": str(packet["proof_refresh_strategy"]),
            "market": str(packet["proof_refresh_market"]),
        },
        "route_readiness": {
            "required": _to_bool(packet["route_readiness_required"]),
            "provided": _to_bool(packet["route_readiness_provided"]),
            "ready": _to_bool(packet["route_readiness_ready"]),
            "strategy": str(packet["route_readiness_strategy"]),
            "market": str(packet["route_readiness_market"]),
            "route_ready_pairs": int(packet["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(packet["route_readiness_gap_pairs"]),
            "ops_launch_controls_present": _to_bool(packet["route_readiness_ops_launch_controls_present"]),
            "ops_launch_controls_blocked_pairs": int(
                packet["route_readiness_ops_launch_controls_blocked_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_breach_pairs": int(
                packet["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                packet["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]
            ),
            "recommendation": str(packet["route_readiness_recommendation"]),
        },
        "shadow_broker_readiness": {
            "provided": int(packet["shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(packet["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(packet["shadow_broker_readiness_ready_sessions"]),
            "adapter": str(packet["shadow_broker_adapter"]),
            "adapter_count": int(packet["shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(packet["shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(packet["shadow_broker_vendor_data_readiness_provided_sessions"]),
                "ready_sessions": int(packet["shadow_broker_vendor_data_readiness_ready_sessions"]),
                "failed_checks": int(packet["shadow_broker_vendor_data_readiness_failed_checks"]),
            },
            "route_readiness": {
                "sessions": int(packet["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(packet["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(packet["shadow_broker_route_readiness_strategy"]),
                "market": str(packet["shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(packet["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(packet["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(packet["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(packet["shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(packet["shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(packet["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    packet["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(packet["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(packet["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(packet["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(packet["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(packet["shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(packet["shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(packet["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "cutover_broker_route_readiness": _broker_route_readiness_config(packet),
        "cutover_broker_resume_gate": {
            "broker_route_readiness": _resume_route_readiness_config(
                packet,
                "cutover_broker_resume_broker_route_readiness",
            ),
            "incident_broker_route_readiness": _resume_route_readiness_config(
                packet,
                "cutover_broker_resume_incident_broker_route_readiness",
            ),
        },
        "cutover_broker_shadow_broker_readiness": _broker_shadow_broker_config(packet),
        "cutover_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(packet),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _broker_vendor_market_data_batch_config(packet)
        ),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": {
            "required": _to_bool(
                packet[
                    "cutover_broker_vendor_market_data_batch_lineage_match_required"
                ]
            ),
            "matches": _to_bool(
                packet["cutover_broker_vendor_market_data_batch_lineage_matches"]
            ),
            "current_application_lineage_sha256": str(
                packet["cutover_vendor_market_data_batch_application_lineage_sha256"]
            ),
            "broker_application_lineage_sha256": str(
                packet[
                    "cutover_broker_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "scaleup_carried_application_lineage_sha256": str(
                packet[
                    "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "cutover_carried_application_lineage_sha256": str(
                packet[
                    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "route_carried_application_lineage_sha256": str(
                packet[
                    "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
        },
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
            _broker_vendor_route_final_lineage_config(packet)
        ),
        ROUTE_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_route_complete_final_lineage_config(packet)
        ),
        ROUTE_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_route_extended_complete_final_lineage_config(
                packet
            )
        ),
        ROUTE_EXTENDED_COMPLETE_FINAL_LINEAGE_37_COMPARISON_KEY: (
            _broker_vendor_route_extended_complete_final_lineage_37_config(
                packet
            )
        ),
        ROUTE_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_45_COMPARISON_KEY: (
            _broker_vendor_route_latest_extended_complete_final_lineage_45_config(
                packet
            )
        ),
        ROUTE_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_53_COMPARISON_KEY: (
            _broker_vendor_route_current_latest_extended_complete_final_lineage_53_config(
                packet
            )
        ),
        ROUTE_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_61_COMPARISON_KEY: (
            _broker_vendor_route_reconciled_current_latest_extended_complete_final_lineage_61_config(
                packet
            )
        ),
        ROUTE_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_69_COMPARISON_KEY: (
            _broker_vendor_route_verified_reconciled_current_latest_extended_complete_final_lineage_69_config(
                packet
            )
        ),
        ROUTE_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_77_COMPARISON_KEY: (
            _broker_vendor_route_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_77_config(
                packet
            )
        ),
        "cutover_vendor_market_data_batch": _vendor_market_data_batch_config(packet),
        "broker_resume_gate": {
            "ready": _to_bool(packet["broker_resume_gate_ready"]),
            "proof_refresh_ready": _to_bool(packet["broker_resume_proof_refresh_ready"]),
        },
        "dispatch_roundtrip": {
            "required": _to_bool(packet["dispatch_roundtrip_required"]),
            "provided": _to_bool(packet["dispatch_roundtrip_provided"]),
            "ready": _to_bool(packet["dispatch_roundtrip_ready"]),
            "target_mode": str(packet["dispatch_roundtrip_target_mode"]),
            "strategy": str(packet["dispatch_roundtrip_strategy"]),
            "market": str(packet["dispatch_roundtrip_market"]),
            "scenario_key": str(packet["dispatch_roundtrip_scenario_key"]),
            "dispatch_batch_id": str(packet["dispatch_roundtrip_batch_id"]),
            "requests": int(packet["dispatch_roundtrip_requests"]),
            "acked_orders": int(packet["dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(packet["dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(packet["dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(packet["dispatch_roundtrip_unmatched_acks"]),
            "failed_checks": int(packet["dispatch_roundtrip_failed_checks"]),
            "route_enable_dispatch_roundtrip": {
                "failed_checks": int(packet["route_enable_dispatch_roundtrip_failed_checks"]),
            },
            "route_proof": {
                "required": _to_bool(packet["route_dispatch_roundtrip_required"]),
                "provided": _to_bool(packet["route_dispatch_roundtrip_provided"]),
                "ready": _to_bool(packet["route_dispatch_roundtrip_ready"]),
                "target_mode": str(packet["route_dispatch_roundtrip_target_mode"]),
                "strategy": str(packet["route_dispatch_roundtrip_strategy"]),
                "market": str(packet["route_dispatch_roundtrip_market"]),
                "scenario_key": str(packet["route_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(packet["route_dispatch_roundtrip_batch_id"]),
                "requests": int(packet["route_dispatch_roundtrip_requests"]),
                "acked_orders": int(packet["route_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(packet["route_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(packet["route_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(packet["route_dispatch_roundtrip_unmatched_acks"]),
            },
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
    return [
        {str(key): _jsonable_check_value(value) for key, value in row.items()}
        for row in failed.to_dict(orient="records")
    ]


def _jsonable_check_value(value: object) -> object:
    value = _jsonable(value)
    if hasattr(value, "item"):
        try:
            return value.item()  # type: ignore[attr-defined]
        except (AttributeError, TypeError, ValueError):
            pass
    return value


def _runbook_markdown(summary_row: pd.Series, action_queue: pd.DataFrame) -> str:
    ready_label = "yes" if _to_bool(summary_row.get("ready", False)) else "no"
    lines = [
        "# Route Enable Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Route state: {_object_text(summary_row.get('route_state')).strip()}",
        f"- Target mode: {_object_text(summary_row.get('target_mode')).strip()}",
        f"- Strategy: {_object_text(summary_row.get('strategy')).strip()}",
        f"- Market: {_object_text(summary_row.get('market')).strip()}",
        f"- Scenario: {_object_text(summary_row.get('scenario_key')).strip()}",
        f"- Adapter: {_object_text(summary_row.get('adapter')).strip()}",
        f"- Upload orders: {_int_value(summary_row.get('upload_orders'))}",
        f"- Dispatch round-trip ready: {_object_text(summary_row.get('dispatch_roundtrip_ready')).strip()}",
        f"- Route readiness ready: {_object_text(summary_row.get('route_readiness_ready')).strip()}",
        f"- Cutover lineage current: {'yes' if _to_bool(summary_row.get('cutover_lineage_gate_passed')) else 'no'}",
        f"- Broker route contract identity active: {'yes' if _to_bool(summary_row.get('cutover_runtime_route_contract_identity_active')) else 'no'}",
        f"- Broker route contract identity digest: {_code(summary_row.get('cutover_runtime_telemetry_broker_readiness_route_contract_identity_sha256'))}",
        f"- Current broker route contract identity digest: {_code(summary_row.get('cutover_current_runtime_route_contract_identity_sha256'))}",
        f"- Broker route contract identity matches current: {'yes' if _to_bool(summary_row.get('cutover_runtime_route_contract_identity_matches_current')) else 'no'}",
        f"- Broker route-enable route contract identity active: {'yes' if _to_bool(summary_row.get('cutover_runtime_route_enable_route_contract_identity_active')) else 'no'}",
        f"- Broker route-enable route contract identity digest: {_code(summary_row.get('cutover_runtime_telemetry_broker_readiness_route_enable_route_contract_identity_sha256'))}",
        f"- Current broker route-enable route contract identity digest: {_code(summary_row.get('cutover_current_runtime_route_enable_route_contract_identity_sha256'))}",
        f"- Broker route-enable route contract identity matches current: {'yes' if _to_bool(summary_row.get('cutover_runtime_route_enable_route_contract_identity_matches_current')) else 'no'}",
        f"- Research family: {_object_text(summary_row.get('cutover_runtime_scaleup_research_family_id')).strip()}",
        f"- Lead-lag cutover contract consistent: {'yes' if _to_bool(summary_row.get('strategy_portfolio_leadlag_cutover_contract_consistent')) else 'no'}",
        f"- Lead-lag lineage matches scale-up: {'yes' if _to_bool(summary_row.get('strategy_portfolio_leadlag_edge_lineage_matches_scaleup')) else 'no'}",
        f"- Lead-lag lineage contract: {_code(summary_row.get('strategy_portfolio_leadlag_edge_lineage_contract_version'))} / {_code(summary_row.get('strategy_portfolio_leadlag_edge_lineage_contract_sha256'))}",
        "- Submission authorization: no",
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
        return "No route-enable actions."
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


def _broker_route_readiness_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "required": _to_bool(packet["cutover_broker_route_readiness_required"]),
        "provided": _to_bool(packet["cutover_broker_route_readiness_provided"]),
        "ready": _to_bool(packet["cutover_broker_route_readiness_ready"]),
        "strategy": str(packet["cutover_broker_route_readiness_strategy"]),
        "market": str(packet["cutover_broker_route_readiness_market"]),
        "route_ready_pairs": int(packet["cutover_broker_route_readiness_route_ready_pairs"]),
        "gap_pairs": int(packet["cutover_broker_route_readiness_gap_pairs"]),
        "recommendation": str(packet["cutover_broker_route_readiness_recommendation"]),
        "ops_launch_controls_ready": _to_bool(
            packet["cutover_broker_route_readiness_ops_launch_controls_ready"]
        ),
        "ops_launch_control_failures": str(
            packet["cutover_broker_route_readiness_ops_launch_control_failures"]
        ),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            packet["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _resume_route_readiness_summary_fields(packet: pd.Series, prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_required": _to_bool(packet[f"{prefix}_required"]),
        f"{prefix}_provided": _to_bool(packet[f"{prefix}_provided"]),
        f"{prefix}_ready": _to_bool(packet[f"{prefix}_ready"]),
        f"{prefix}_strategy": str(packet[f"{prefix}_strategy"]),
        f"{prefix}_market": str(packet[f"{prefix}_market"]),
        f"{prefix}_route_ready_pairs": int(packet[f"{prefix}_route_ready_pairs"]),
        f"{prefix}_gap_pairs": int(packet[f"{prefix}_gap_pairs"]),
        f"{prefix}_recommendation": str(packet[f"{prefix}_recommendation"]),
        f"{prefix}_ops_launch_controls_ready": _to_bool(packet[f"{prefix}_ops_launch_controls_ready"]),
        f"{prefix}_ops_launch_control_failures": str(packet[f"{prefix}_ops_launch_control_failures"]),
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _resume_route_readiness_config(packet: pd.Series, prefix: str) -> dict[str, Any]:
    return {
        "required": _to_bool(packet[f"{prefix}_required"]),
        "provided": _to_bool(packet[f"{prefix}_provided"]),
        "ready": _to_bool(packet[f"{prefix}_ready"]),
        "strategy": str(packet[f"{prefix}_strategy"]),
        "market": str(packet[f"{prefix}_market"]),
        "route_ready_pairs": int(packet[f"{prefix}_route_ready_pairs"]),
        "gap_pairs": int(packet[f"{prefix}_gap_pairs"]),
        "recommendation": str(packet[f"{prefix}_recommendation"]),
        "ops_launch_controls_ready": _to_bool(packet[f"{prefix}_ops_launch_controls_ready"]),
        "ops_launch_control_failures": str(packet[f"{prefix}_ops_launch_control_failures"]),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            packet[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _broker_shadow_broker_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(packet["cutover_broker_shadow_broker_readiness_provided"]),
        "sessions": int(packet["cutover_broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(packet["cutover_broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(packet["cutover_broker_shadow_broker_adapter"]),
        "adapter_count": int(packet["cutover_broker_shadow_broker_adapter_count"]),
        "broker_vendor_data_readiness": {
            "sessions": int(packet["cutover_broker_shadow_broker_vendor_data_readiness_sessions"]),
            "provided_sessions": int(
                packet["cutover_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
            ),
            "ready_sessions": int(packet["cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions"]),
            "failed_checks": int(packet["cutover_broker_shadow_broker_vendor_data_readiness_failed_checks"]),
        },
        "route_readiness": {
            "sessions": int(packet["cutover_broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(packet["cutover_broker_shadow_broker_route_readiness_ready_sessions"]),
            "strategy": str(packet["cutover_broker_shadow_broker_route_readiness_strategy"]),
            "market": str(packet["cutover_broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(packet["cutover_broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(packet["cutover_broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(packet["cutover_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(packet["cutover_broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(packet["cutover_broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(packet["cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(
                packet["cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(
                packet["cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
            ),
            "max_unmatched_acks": int(
                packet["cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
            ),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(
                packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
            ),
            "strategy": str(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy"]),
            "market": str(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(packet["cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _vendor_market_data_batch_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(packet["cutover_vendor_market_data_batch_provided"]),
        "ready": _to_bool(packet["cutover_vendor_market_data_batch_ready"]),
        "adapter": str(packet["cutover_vendor_market_data_batch_adapter"]),
        "kind": str(packet["cutover_vendor_market_data_batch_kind"]),
        "manifest_run_type": str(packet["cutover_vendor_market_data_batch_manifest_run_type"]),
        "market": str(packet["cutover_vendor_market_data_batch_market"]),
        "dataset_count": int(packet["cutover_vendor_market_data_batch_dataset_count"]),
        "ready_datasets": int(packet["cutover_vendor_market_data_batch_ready_datasets"]),
        "failed_datasets": int(packet["cutover_vendor_market_data_batch_failed_datasets"]),
        "ready_rate": _jsonable(packet["cutover_vendor_market_data_batch_ready_rate"]),
        "unique_source_files": int(packet["cutover_vendor_market_data_batch_unique_source_files"]),
        "unique_header_fingerprints": int(
            packet["cutover_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "source_file_fingerprint_coverage": _jsonable(
            packet["cutover_vendor_market_data_batch_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(packet["cutover_vendor_market_data_batch_min_mapping_coverage"]),
        "unique_mapping_drafts": int(packet["cutover_vendor_market_data_batch_unique_mapping_drafts"]),
        "mapping_sources": str(packet["cutover_vendor_market_data_batch_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(packet["cutover_vendor_market_data_batch_comparison_accepted"]),
            "failed_checks": int(packet["cutover_vendor_market_data_batch_comparison_failed_checks"]),
        },
        "datasets": _json_list(packet["cutover_vendor_market_data_batch_datasets_json"]),
    }


def _broker_vendor_market_data_batch_config(packet: pd.Series) -> dict[str, Any]:
    field_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(packet[f"{field_prefix}_provided"]),
        "ready": _to_bool(packet[f"{field_prefix}_ready"]),
        "adapter": str(packet[f"{field_prefix}_adapter"]),
        "kind": str(packet[f"{field_prefix}_kind"]),
        "manifest_run_type": str(packet[f"{field_prefix}_manifest_run_type"]),
        "market": str(packet[f"{field_prefix}_market"]),
        "dataset_count": int(packet[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(packet[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(packet[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(packet[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(packet[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(packet[f"{field_prefix}_unique_header_fingerprints"]),
        "source_file_fingerprint_coverage": _jsonable(
            packet[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(packet[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(packet[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": str(packet[f"{field_prefix}_mapping_sources"]),
        "mapping_source_mode": str(packet[f"{field_prefix}_mapping_source_mode"]),
        "mapping_application_count": int(packet[f"{field_prefix}_mapping_application_count"]),
        "unique_mapping_applications": int(
            packet[f"{field_prefix}_unique_mapping_applications"]
        ),
        "target_application_coverage": _jsonable(
            packet[f"{field_prefix}_target_application_coverage"]
        ),
        "application_lineage_consistency_required": _to_bool(
            packet[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        "application_lineage_consistent": _to_bool(
            packet[f"{field_prefix}_application_lineage_consistent"]
        ),
        "application_lineage_sha256": str(
            packet[f"{field_prefix}_application_lineage_sha256"]
        ),
        "comparison": {
            "accepted": _to_bool(packet[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(packet[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(packet[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_route_final_lineage_config(
    packet: pd.Series,
) -> dict[str, Any]:
    field_prefix = CUTOVER_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{field_prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{field_prefix}_lineage_matches"]),
        "cutover_review_carried_application_lineage_sha256": str(
            packet[
                f"{field_prefix}_cutover_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(packet[f"{field_prefix}_{field}"])
    return config


def _broker_vendor_route_complete_final_lineage_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "cutover_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_extended_complete_final_lineage_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "scaleup_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "cutover_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_extended_complete_final_lineage_37_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "cutover_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS:
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_latest_extended_complete_final_lineage_45_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            packet[
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_DIGEST_FIELDS:
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_current_latest_extended_complete_final_lineage_53_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX
    route_lineage_sha256 = str(
        packet[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            packet[
                f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256": route_lineage_sha256,
        "carried_application_lineage_sha256": route_lineage_sha256,
    }
    for field in (
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS,
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS,
    ):
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_reconciled_current_latest_extended_complete_final_lineage_61_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX
    )
    route_lineage_sha256 = str(
        packet[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD: str(
            packet[
                f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD}"
            ]
        ),
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD: str(
            packet[
                f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD}"
            ]
        ),
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD: str(
            packet[
                f"{prefix}_{CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD}"
            ]
        ),
        "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": route_lineage_sha256,
        "carried_application_lineage_sha256": route_lineage_sha256,
    }
    for field in (
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS,
    ):
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_verified_reconciled_current_latest_extended_complete_final_lineage_69_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX
    )
    route_lineage_sha256 = str(
        packet[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": route_lineage_sha256,
        "carried_application_lineage_sha256": route_lineage_sha256,
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
    ):
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_route_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_77_config(
    packet: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_FIELD_PREFIX
    )
    route_lineage_sha256 = str(
        packet[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(packet[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(packet[f"{prefix}_lineage_matches"]),
        "route_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": route_lineage_sha256,
        "carried_application_lineage_sha256": route_lineage_sha256,
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
        *CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CONFIRMED_REVIEW_FIELDS,
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD,
    ):
        config[field] = str(packet[f"{prefix}_{field}"])
    return config


def _broker_vendor_data_readiness_config(packet: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(packet["cutover_broker_vendor_data_readiness_provided"]),
        "ready": _to_bool(packet["cutover_broker_vendor_data_readiness_ready"]),
        "failed_checks": int(packet["cutover_broker_vendor_data_readiness_failed_checks"]),
    }


def _vendor_market_data_batch_state(
    vendor: dict[str, Any],
    *,
    row: pd.Series | None = None,
    field_prefix: str = "",
) -> dict[str, Any]:
    row = pd.Series(dtype=object) if row is None else row
    comparison = vendor.get("comparison", {}) or {}
    datasets = vendor.get("datasets")
    if datasets is None and field_prefix:
        datasets = _json_list(row.get(f"{field_prefix}_datasets_json", "[]"))
    datasets = datasets or []
    row_value = (lambda suffix, default: row.get(f"{field_prefix}_{suffix}", default)) if field_prefix else (
        lambda _suffix, default: default
    )
    return {
        "provided": _to_bool(vendor.get("provided", row_value("provided", False))),
        "ready": _to_bool(vendor.get("ready", row_value("ready", False))),
        "adapter": _identity_key(_first_text(vendor.get("adapter", ""), row_value("adapter", ""))),
        "kind": _first_text(vendor.get("kind", ""), row_value("kind", "")),
        "manifest_run_type": _identity_key(
            _first_text(vendor.get("manifest_run_type", ""), row_value("manifest_run_type", ""))
        ),
        "market": _identity_key(_first_text(vendor.get("market", ""), row_value("market", ""))),
        "dataset_count": int(_number_from(vendor, "dataset_count", _number(row, f"{field_prefix}_dataset_count", 0.0))),
        "ready_datasets": int(
            _number_from(vendor, "ready_datasets", _number(row, f"{field_prefix}_ready_datasets", 0.0))
        ),
        "failed_datasets": int(
            _number_from(vendor, "failed_datasets", _number(row, f"{field_prefix}_failed_datasets", 0.0))
        ),
        "ready_rate": _number_from(vendor, "ready_rate", _number(row, f"{field_prefix}_ready_rate", 0.0)),
        "unique_source_files": int(
            _number_from(
                vendor,
                "unique_source_files",
                _number(row, f"{field_prefix}_unique_source_files", 0.0),
            )
        ),
        "unique_header_fingerprints": int(
            _number_from(
                vendor,
                "unique_header_fingerprints",
                _number(row, f"{field_prefix}_unique_header_fingerprints", 0.0),
            )
        ),
        "source_file_fingerprint_coverage": _number_from(
            vendor,
            "source_file_fingerprint_coverage",
            _number(row, f"{field_prefix}_source_file_fingerprint_coverage", 0.0),
        ),
        "min_mapping_coverage": _number_from(
            vendor,
            "min_mapping_coverage",
            _number(row, f"{field_prefix}_min_mapping_coverage", 0.0),
        ),
        "unique_mapping_drafts": int(
            _number_from(
                vendor,
                "unique_mapping_drafts",
                _number(row, f"{field_prefix}_unique_mapping_drafts", 0.0),
            )
        ),
        "mapping_sources": _first_text(vendor.get("mapping_sources", ""), row_value("mapping_sources", "")),
        "mapping_source_mode": _identity_key(
            _first_text(
                vendor.get("mapping_source_mode", ""),
                row_value("mapping_source_mode", ""),
            )
        ),
        "mapping_application_count": int(
            _number_from(
                vendor,
                "mapping_application_count",
                _number(row, f"{field_prefix}_mapping_application_count", 0.0),
            )
        ),
        "unique_mapping_applications": int(
            _number_from(
                vendor,
                "unique_mapping_applications",
                _number(row, f"{field_prefix}_unique_mapping_applications", 0.0),
            )
        ),
        "target_application_coverage": _number_from(
            vendor,
            "target_application_coverage",
            _number(row, f"{field_prefix}_target_application_coverage", 0.0),
        ),
        "application_lineage_consistency_required": _to_bool(
            vendor.get(
                "application_lineage_consistency_required",
                row_value("application_lineage_consistency_required", False),
            )
        ),
        "application_lineage_consistent": _to_bool(
            vendor.get(
                "application_lineage_consistent",
                row_value("application_lineage_consistent", False),
            )
        ),
        "application_lineage_sha256": _sha256_text(
            _first_text(
                vendor.get("application_lineage_sha256", ""),
                row_value("application_lineage_sha256", ""),
            )
        ),
        "comparison_accepted": _to_bool(comparison.get("accepted", row_value("comparison_accepted", False))),
        "comparison_failed_checks": int(
            _number_from(
                comparison,
                "failed_checks",
                _number(row, f"{field_prefix}_comparison_failed_checks", 0.0),
            )
        ),
        "datasets": [
            {
                "dataset": _first_text(item.get("dataset", "")),
                "ready": _to_bool(item.get("ready", False)),
                "source_file_sha256": _first_text(item.get("source_file_sha256", "")),
                "source_header_sha256": _first_text(item.get("source_header_sha256", "")),
                "mapping_draft_sha256": _first_text(item.get("mapping_draft_sha256", "")),
                "mapping_source": _first_text(item.get("mapping_source", "")),
                "mapping_application_path": _first_text(item.get("mapping_application_path", "")),
                "mapping_application_id": _first_text(item.get("mapping_application_id", "")),
                "mapping_application_sha256": _first_text(
                    item.get("mapping_application_sha256", "")
                ),
                "mapping_scope_review_id": _first_text(item.get("mapping_scope_review_id", "")),
                "mapping_scope_review_sha256": _first_text(
                    item.get("mapping_scope_review_sha256", "")
                ),
                "target_intake_receipt_id": _first_text(item.get("target_intake_receipt_id", "")),
                "applied_mapping_sha256": _first_text(item.get("applied_mapping_sha256", "")),
            }
            for item in datasets
            if isinstance(item, dict)
        ],
    }


def _broker_vendor_data_readiness_state(
    readiness: dict[str, Any],
    *,
    row: pd.Series | None = None,
    field_prefix: str = "",
) -> dict[str, Any]:
    row = pd.Series(dtype=object) if row is None else row
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    row_value = (lambda suffix, default: row.get(f"{field_prefix}_{suffix}", default)) if field_prefix else (
        lambda _suffix, default: default
    )
    return {
        "provided": _to_bool(readiness.get("provided", row_value("provided", active_config))),
        "ready": _to_bool(readiness.get("ready", row_value("ready", False))),
        "failed_checks": _broker_vendor_data_readiness_failed_checks(
            readiness,
            fallback=_number(row, f"{field_prefix}_failed_checks", 0.0) if field_prefix else 0.0,
        ),
    }


def _broker_vendor_data_readiness_failed_checks(
    readiness: dict[str, Any],
    *,
    fallback: float = 0.0,
) -> int:
    failed_checks = readiness.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_from(readiness, "failed_checks", fallback))
    return int(_number_from(readiness, "failed_check_count", fallback))


def _resume_route_readiness_state_fields(
    row: pd.Series,
    route_readiness: object,
    *,
    source_prefix: str,
    row_prefix: str,
) -> dict[str, Any]:
    readiness = route_readiness if isinstance(route_readiness, dict) else {}
    return {
        f"{source_prefix}_required": _to_bool(
            readiness.get("required", row.get(f"{row_prefix}_required", False))
        ),
        f"{source_prefix}_provided": _to_bool(
            readiness.get("provided", row.get(f"{row_prefix}_provided", False))
        ),
        f"{source_prefix}_ready": _to_bool(readiness.get("ready", row.get(f"{row_prefix}_ready", False))),
        f"{source_prefix}_strategy": _strategy_key(
            _first_text(readiness.get("strategy", ""), row.get(f"{row_prefix}_strategy", ""))
        ),
        f"{source_prefix}_market": _identity_key(
            _first_text(readiness.get("market", ""), row.get(f"{row_prefix}_market", ""))
        ),
        f"{source_prefix}_route_ready_pairs": int(
            _number_from(readiness, "route_ready_pairs", _number(row, f"{row_prefix}_route_ready_pairs", 0.0))
        ),
        f"{source_prefix}_gap_pairs": int(
            _number_from(readiness, "gap_pairs", _number(row, f"{row_prefix}_gap_pairs", 0.0))
        ),
        f"{source_prefix}_recommendation": _first_text(
            readiness.get("recommendation", ""),
            row.get(f"{row_prefix}_recommendation", ""),
        ),
        f"{source_prefix}_ops_launch_controls_ready": _to_bool(
            readiness.get("ops_launch_controls_ready", row.get(f"{row_prefix}_ops_launch_controls_ready", False))
        ),
        f"{source_prefix}_ops_launch_control_failures": _first_text(
            readiness.get("ops_launch_control_failures", ""),
            row.get(f"{row_prefix}_ops_launch_control_failures", ""),
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_safe_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_breach_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number_from(
                readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                _number(row, f"{row_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0),
            )
        ),
    }


def _cutover_state(
    row: pd.Series,
    config: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    proof = config.get("proof_freshness", {}) or {}
    runtime_session = config.get("runtime_session", {}) or {}
    strategy_portfolio = runtime_session.get("strategy_portfolio", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    resume = broker_readiness.get("resume_gate", {}) or {}
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    broker_route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route_readiness = config.get("scaleup_route_readiness", {}) or {}
    broker_route_readiness = config.get("scaleup_broker_route_readiness", {}) or {}
    scaleup_broker_resume_gate = (
        config.get("scaleup_broker_resume_gate", {})
        or config.get("cutover_broker_resume_gate", {})
        or {}
    )
    if not isinstance(scaleup_broker_resume_gate, dict):
        scaleup_broker_resume_gate = {}
    resume_broker_route_readiness = scaleup_broker_resume_gate.get("broker_route_readiness", {}) or {}
    resume_incident_broker_route_readiness = (
        scaleup_broker_resume_gate.get("incident_broker_route_readiness", {}) or {}
    )
    shadow_broker = config.get("scaleup_shadow_broker_readiness", {}) or {}
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_shadow_broker = config.get("scaleup_broker_shadow_broker_readiness", {}) or {}
    (
        broker_vendor_market_data_batch,
        broker_vendor_market_data_batch_prefix,
    ) = _broker_vendor_market_data_batch_source(config)
    if not vendor_market_data_batch_source_active(broker_vendor_market_data_batch):
        broker_vendor_market_data_batch_prefix = _broker_vendor_market_data_batch_row_prefix(row)
    lineage_comparison = _broker_vendor_market_data_batch_lineage_comparison_source(
        config
    )
    final_lineage_comparison = _broker_vendor_final_lineage_comparison_source(config)
    cutover_complete_final_lineage_comparison = (
        _broker_vendor_cutover_complete_final_lineage_comparison_source(config)
    )
    cutover_extended_complete_final_lineage_comparison = (
        _broker_vendor_cutover_extended_complete_final_lineage_comparison_source(
            config
        )
    )
    cutover_extended_complete_final_lineage_36_comparison = (
        _broker_vendor_cutover_extended_complete_final_lineage_36_comparison_source(
            config
        )
    )
    cutover_latest_extended_complete_final_lineage_44_comparison = (
        _broker_vendor_cutover_latest_extended_complete_final_lineage_44_comparison_source(
            config
        )
    )
    cutover_current_latest_extended_complete_final_lineage_52_comparison = (
        _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_comparison_source(
            config
        )
    )
    cutover_reconciled_current_latest_extended_complete_final_lineage_60_comparison = (
        _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_comparison_source(
            config
        )
    )
    cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_comparison = (
        _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_comparison_source(
            config
        )
    )
    cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_comparison = (
        _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_comparison_source(
            config
        )
    )
    broker_vendor_market_data_batch_state = _vendor_market_data_batch_state(
        broker_vendor_market_data_batch,
        row=row,
        field_prefix=broker_vendor_market_data_batch_prefix,
    )
    (
        broker_vendor_data_readiness,
        broker_vendor_data_readiness_prefix,
    ) = _broker_vendor_data_readiness_source(config)
    vendor_market_data_batch = config.get("scaleup_vendor_market_data_batch", {}) or {}
    scaleup_dispatch = config.get("scaleup_dispatch_roundtrip", {}) or {}
    scaleup_route_enable = scaleup_dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route = dispatch.get("route_proof", {}) or {}
    strategy_portfolio_leadlag = _strategy_portfolio_leadlag_state(
        row,
        strategy_portfolio,
    )
    return {
        "ready": _to_bool(row.get("ready", config.get("ready", False))),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""))),
        "market": _identity_key(_first_text(row.get("market", ""), config.get("market", ""))),
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "strategy_portfolio_required": _to_bool(
            strategy_portfolio.get(
                "required",
                row.get("runtime_strategy_portfolio_required", row.get("strategy_portfolio_required", False)),
            )
        ),
        "strategy_portfolio_provided": _to_bool(
            strategy_portfolio.get(
                "provided",
                row.get("runtime_strategy_portfolio_provided", row.get("strategy_portfolio_provided", False)),
            )
        ),
        "strategy_portfolio_ready": _to_bool(
            strategy_portfolio.get(
                "ready",
                row.get("runtime_strategy_portfolio_ready", row.get("strategy_portfolio_ready", False)),
            )
        ),
        "strategy_portfolio_deployment_mode": _first_text(
            strategy_portfolio.get("deployment_mode", ""),
            row.get("runtime_strategy_portfolio_deployment_mode", ""),
            row.get("strategy_portfolio_deployment_mode", ""),
        ),
        "strategy_portfolio_allocation_mode": _first_text(
            strategy_portfolio.get("allocation_mode", ""),
            row.get("runtime_strategy_portfolio_allocation_mode", ""),
            row.get("strategy_portfolio_allocation_mode", ""),
        ),
        "strategy_portfolio_capital_currency": _first_text(
            strategy_portfolio.get("capital_currency", ""),
            row.get("runtime_strategy_portfolio_capital_currency", ""),
            row.get("strategy_portfolio_capital_currency", ""),
        ),
        "strategy_portfolio_selected_profile": _first_text(
            strategy_portfolio.get("selected_profile", ""),
            row.get("runtime_strategy_portfolio_selected_profile", ""),
            row.get("strategy_portfolio_selected_profile", ""),
        ),
        "strategy_portfolio_selected_strategy": _strategy_key(
            _first_text(
                strategy_portfolio.get("selected_strategy", ""),
                row.get("runtime_strategy_portfolio_selected_strategy", ""),
                row.get("strategy_portfolio_selected_strategy", ""),
            )
        ),
        "strategy_portfolio_selected_market": _identity_key(
            _first_text(
                strategy_portfolio.get("selected_market", ""),
                row.get("runtime_strategy_portfolio_selected_market", ""),
                row.get("strategy_portfolio_selected_market", ""),
            )
        ),
        "strategy_portfolio_selected_eligible": _to_bool(
            strategy_portfolio.get(
                "selected_eligible",
                row.get(
                    "runtime_strategy_portfolio_selected_eligible",
                    row.get("strategy_portfolio_selected_eligible", False),
                ),
            )
        ),
        "strategy_portfolio_selected_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "selected_allocation_weight",
                _number(
                    row,
                    "runtime_strategy_portfolio_selected_allocation_weight",
                    _number(row, "strategy_portfolio_selected_allocation_weight", 0.0),
                ),
            )
        ),
        "strategy_portfolio_selected_allocation_notional": float(
            _number_from(
                strategy_portfolio,
                "selected_allocation_notional",
                _number(
                    row,
                    "runtime_strategy_portfolio_selected_allocation_notional",
                    _number(row, "strategy_portfolio_selected_allocation_notional", 0.0),
                ),
            )
        ),
        "strategy_portfolio_notional_cap_applied": _to_bool(
            strategy_portfolio.get(
                "notional_cap_applied",
                row.get(
                    "runtime_strategy_portfolio_notional_cap_applied",
                    row.get("strategy_portfolio_notional_cap_applied", False),
                ),
            )
        ),
        "strategy_portfolio_min_strategy_count": int(
            _number_from(
                strategy_portfolio,
                "min_strategy_count",
                _number(
                    row,
                    "runtime_strategy_portfolio_min_strategy_count",
                    _number(row, "strategy_portfolio_min_strategy_count", 0.0),
                ),
            )
        ),
        "strategy_portfolio_min_market_count": int(
            _number_from(
                strategy_portfolio,
                "min_market_count",
                _number(
                    row,
                    "runtime_strategy_portfolio_min_market_count",
                    _number(row, "strategy_portfolio_min_market_count", 0.0),
                ),
            )
        ),
        "strategy_portfolio_max_strategy_weight": float(
            _number_from(
                strategy_portfolio,
                "max_strategy_weight",
                _number(
                    row,
                    "runtime_strategy_portfolio_max_strategy_weight",
                    _number(row, "strategy_portfolio_max_strategy_weight", 0.0),
                ),
            )
        ),
        "strategy_portfolio_max_market_weight": float(
            _number_from(
                strategy_portfolio,
                "max_market_weight",
                _number(
                    row,
                    "runtime_strategy_portfolio_max_market_weight",
                    _number(row, "strategy_portfolio_max_market_weight", 0.0),
                ),
            )
        ),
        "strategy_portfolio_allocated_strategy_count": int(
            _number_from(
                strategy_portfolio,
                "allocated_strategy_count",
                _number(
                    row,
                    "runtime_strategy_portfolio_allocated_strategy_count",
                    _number(row, "strategy_portfolio_allocated_strategy_count", 0.0),
                ),
            )
        ),
        "strategy_portfolio_allocated_market_count": int(
            _number_from(
                strategy_portfolio,
                "allocated_market_count",
                _number(
                    row,
                    "runtime_strategy_portfolio_allocated_market_count",
                    _number(row, "strategy_portfolio_allocated_market_count", 0.0),
                ),
            )
        ),
        "strategy_portfolio_top_strategy_by_weight": _strategy_key(
            _first_text(
                strategy_portfolio.get("top_strategy_by_weight", ""),
                row.get("runtime_strategy_portfolio_top_strategy_by_weight", ""),
                row.get("strategy_portfolio_top_strategy_by_weight", ""),
            )
        ),
        "strategy_portfolio_top_market_by_weight": _identity_key(
            _first_text(
                strategy_portfolio.get("top_market_by_weight", ""),
                row.get("runtime_strategy_portfolio_top_market_by_weight", ""),
                row.get("strategy_portfolio_top_market_by_weight", ""),
            )
        ),
        "strategy_portfolio_max_strategy_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "max_strategy_allocation_weight",
                _number(
                    row,
                    "runtime_strategy_portfolio_max_strategy_allocation_weight",
                    _number(row, "strategy_portfolio_max_strategy_allocation_weight", 0.0),
                ),
            )
        ),
        "strategy_portfolio_max_market_allocation_weight": float(
            _number_from(
                strategy_portfolio,
                "max_market_allocation_weight",
                _number(
                    row,
                    "runtime_strategy_portfolio_max_market_allocation_weight",
                    _number(row, "strategy_portfolio_max_market_allocation_weight", 0.0),
                ),
            )
        ),
        "pre_portfolio_max_notional_per_session": float(
            _number_from(
                strategy_portfolio,
                "pre_portfolio_max_notional_per_session",
                _number(
                    row,
                    "runtime_pre_portfolio_max_notional_per_session",
                    _number(row, "pre_portfolio_max_notional_per_session", 0.0),
                ),
            )
        ),
        **strategy_portfolio_leadlag,
        **cutover_lineage_fields(lineage),
        "proof_refresh_ready": _to_bool(proof.get("ready", row.get("proof_refresh_ready", False))),
        "proof_refresh_strategy": _strategy_key(
            _first_text(proof.get("strategy", ""), row.get("proof_refresh_strategy", ""))
        ),
        "proof_refresh_market": _identity_key(_first_text(proof.get("market", ""), row.get("proof_refresh_market", ""))),
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("scaleup_route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("scaleup_route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(
            route_readiness.get("ready", row.get("scaleup_route_readiness_ready", False))
        ),
        "route_readiness_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get("scaleup_route_readiness_strategy", ""))
        ),
        "route_readiness_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get("scaleup_route_readiness_market", ""))
        ),
        "route_readiness_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, "scaleup_route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "route_readiness_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, "scaleup_route_readiness_gap_pairs", 0.0))
        ),
        "route_readiness_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get("scaleup_route_readiness_recommendation", ""),
        ),
        "route_readiness_ops_launch_controls_present": _to_bool(
            route_readiness.get(
                "ops_launch_controls_present",
                row.get("scaleup_route_readiness_ops_launch_controls_present", False),
            )
        ),
        "route_readiness_ops_launch_controls_blocked_pairs": int(
            _number_from(
                route_readiness,
                "ops_launch_controls_blocked_pairs",
                _number(row, "scaleup_route_readiness_ops_launch_controls_blocked_pairs", 0.0),
            )
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_breach_pairs",
                _number(row, "scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0),
            )
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                _number(
                    row,
                    "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    0.0,
                ),
            )
        ),
        "broker_route_readiness_required": _to_bool(
            broker_route_readiness.get("required", row.get("scaleup_broker_route_readiness_required", False))
        ),
        "broker_route_readiness_provided": _to_bool(
            broker_route_readiness.get("provided", row.get("scaleup_broker_route_readiness_provided", False))
        ),
        "broker_route_readiness_ready": _to_bool(
            broker_route_readiness.get("ready", row.get("scaleup_broker_route_readiness_ready", False))
        ),
        "broker_route_readiness_strategy": _strategy_key(
            _first_text(
                broker_route_readiness.get("strategy", ""),
                row.get("scaleup_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_route_readiness_market": _identity_key(
            _first_text(
                broker_route_readiness.get("market", ""),
                row.get("scaleup_broker_route_readiness_market", ""),
            )
        ),
        "broker_route_readiness_route_ready_pairs": int(
            _number_from(
                broker_route_readiness,
                "route_ready_pairs",
                _number(row, "scaleup_broker_route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "broker_route_readiness_gap_pairs": int(
            _number_from(
                broker_route_readiness,
                "gap_pairs",
                _number(row, "scaleup_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_route_readiness_recommendation": _first_text(
            broker_route_readiness.get("recommendation", ""),
            row.get("scaleup_broker_route_readiness_recommendation", ""),
        ),
        "broker_route_readiness_ops_launch_controls_ready": _to_bool(
            broker_route_readiness.get(
                "ops_launch_controls_ready",
                row.get("scaleup_broker_route_readiness_ops_launch_controls_ready", False),
            )
        ),
        "broker_route_readiness_ops_launch_control_failures": _first_text(
            broker_route_readiness.get("ops_launch_control_failures", ""),
            row.get("scaleup_broker_route_readiness_ops_launch_control_failures", ""),
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_safe_runs",
                _number(row, "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_breach_runs",
                _number(row, "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                _number(
                    row,
                    "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    0.0,
                ),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                _number(
                    row,
                    "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                ),
            )
        ),
        **_resume_route_readiness_state_fields(
            row,
            resume_broker_route_readiness,
            source_prefix="broker_resume_broker_route_readiness",
            row_prefix="scaleup_broker_resume_broker_route_readiness",
        ),
        **_resume_route_readiness_state_fields(
            row,
            resume_incident_broker_route_readiness,
            source_prefix="broker_resume_incident_broker_route_readiness",
            row_prefix="scaleup_broker_resume_incident_broker_route_readiness",
        ),
        "shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "scaleup_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "scaleup_shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("scaleup_shadow_broker_adapter", ""))
        ),
        "shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "scaleup_shadow_broker_adapter_count", 0.0),
            )
        ),
        "shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "scaleup_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("scaleup_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("scaleup_shadow_broker_route_readiness_market", ""),
            )
        ),
        "shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "scaleup_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("scaleup_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("scaleup_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "scaleup_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("scaleup_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("scaleup_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        **_broker_shadow_broker_state_fields(row, broker_shadow_broker),
        "broker_dispatch_roundtrip_vendor_market_data_batch": broker_vendor_market_data_batch_state,
        "broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            lineage_comparison.get(
                "required",
                row.get(
                    "scaleup_broker_vendor_market_data_batch_lineage_match_required",
                    row.get(
                        "cutover_broker_vendor_market_data_batch_lineage_match_required",
                        False,
                    ),
                ),
            )
        ),
        "broker_vendor_market_data_batch_lineage_matches": _to_bool(
            lineage_comparison.get(
                "matches",
                row.get(
                    "scaleup_broker_vendor_market_data_batch_lineage_matches",
                    row.get(
                        "cutover_broker_vendor_market_data_batch_lineage_matches",
                        False,
                    ),
                ),
            )
        ),
        "vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                lineage_comparison.get("current_application_lineage_sha256", ""),
                row.get("scaleup_vendor_market_data_batch_application_lineage_sha256", ""),
                row.get("cutover_vendor_market_data_batch_application_lineage_sha256", ""),
            )
        ),
        "broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                lineage_comparison.get("broker_application_lineage_sha256", ""),
                row.get(
                    "scaleup_broker_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
                row.get(
                    "cutover_broker_vendor_market_data_batch_application_lineage_sha256",
                    "",
                ),
            )
        ),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    lineage_comparison.get(
                        "scaleup_carried_application_lineage_sha256",
                        "",
                    ),
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
                    lineage_comparison.get(
                        "cutover_carried_application_lineage_sha256",
                        "",
                    ),
                    row.get(
                        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        **_broker_vendor_final_lineage_state_fields(
            final_lineage_comparison,
            row,
        ),
        **_broker_vendor_cutover_complete_final_lineage_state_fields(
            cutover_complete_final_lineage_comparison,
            row,
        ),
        **_broker_vendor_cutover_extended_complete_final_lineage_state_fields(
            cutover_extended_complete_final_lineage_comparison,
            row,
        ),
        **_broker_vendor_cutover_extended_complete_final_lineage_36_state_fields(
            cutover_extended_complete_final_lineage_36_comparison,
            row,
        ),
        **_broker_vendor_cutover_latest_extended_complete_final_lineage_44_state_fields(
            cutover_latest_extended_complete_final_lineage_44_comparison,
            row,
        ),
        **_broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_state_fields(
            cutover_current_latest_extended_complete_final_lineage_52_comparison,
            row,
        ),
        **_broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_state_fields(
            cutover_reconciled_current_latest_extended_complete_final_lineage_60_comparison,
            row,
        ),
        **_broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_state_fields(
            cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_comparison,
            row,
        ),
        **_broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_state_fields(
            cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_comparison,
            row,
        ),
        "broker_vendor_data_readiness": _broker_vendor_data_readiness_state(
            broker_vendor_data_readiness,
            row=row,
            field_prefix=broker_vendor_data_readiness_prefix,
        ),
        "vendor_market_data_batch": _vendor_market_data_batch_state(vendor_market_data_batch),
        "broker_schema_status": _first_text(
            broker_readiness.get("adapter_schema_status", ""),
            row.get("broker_schema_status", ""),
        ),
        "broker_schema_reviewed": _to_bool(
            broker_readiness.get("schema_reviewed", row.get("broker_schema_reviewed", False))
        ),
        "broker_schema_review_mode": _first_text(
            broker_readiness.get("schema_review_mode", ""),
            row.get("broker_schema_review_mode", ""),
        ),
        "broker_resume_gate_ready": _to_bool(resume.get("ready", row.get("broker_resume_gate_ready", False))),
        "broker_resume_proof_refresh_ready": _to_bool(
            resume.get("proof_refresh_ready", row.get("broker_resume_proof_refresh_ready", False))
        ),
        "dispatch_roundtrip_required": _to_bool(
            dispatch.get("required", row.get("broker_dispatch_roundtrip_required", False))
        ),
        "dispatch_roundtrip_provided": _to_bool(
            dispatch.get("provided", row.get("broker_dispatch_roundtrip_provided", False))
        ),
        "dispatch_roundtrip_ready": _to_bool(
            dispatch.get("ready", row.get("broker_dispatch_roundtrip_ready", False))
        ),
        "dispatch_roundtrip_target_mode": _identity_key(
            _first_text(dispatch.get("target_mode", ""), row.get("broker_dispatch_roundtrip_target_mode", ""))
        ),
        "dispatch_roundtrip_strategy": _strategy_key(
            _first_text(dispatch.get("strategy", ""), row.get("broker_dispatch_roundtrip_strategy", ""))
        ),
        "dispatch_roundtrip_market": _identity_key(
            _first_text(dispatch.get("market", ""), row.get("broker_dispatch_roundtrip_market", ""))
        ),
        "dispatch_roundtrip_scenario_key": _first_text(
            dispatch.get("scenario_key", ""),
            row.get("broker_dispatch_roundtrip_scenario_key", ""),
        ),
        "dispatch_roundtrip_batch_id": _first_text(
            dispatch.get("dispatch_batch_id", ""),
            row.get("broker_dispatch_roundtrip_batch_id", ""),
        ),
        "dispatch_roundtrip_requests": int(
            _number_from(
                dispatch,
                "requests",
                _number(row, "broker_dispatch_roundtrip_requests", 0.0),
            )
        ),
        "dispatch_roundtrip_acked_orders": int(
            _number_from(
                dispatch,
                "acked_orders",
                _number(row, "broker_dispatch_roundtrip_acked_orders", 0.0),
            )
        ),
        "dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                dispatch,
                "missing_request_acks",
                _number(row, "broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_rejected_orders": int(
            _number_from(
                dispatch,
                "rejected_orders",
                _number(row, "broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                dispatch,
                "unmatched_acks",
                _number(row, "broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "dispatch_roundtrip_failed_checks": int(
            _number_from(
                dispatch,
                "failed_checks",
                _number(row, "broker_dispatch_roundtrip_failed_checks", 0.0),
            )
        ),
        "route_enable_dispatch_roundtrip_failed_checks": max(
            int(
                _number_from(
                    broker_route_enable,
                    "failed_checks",
                    _number(row, "broker_route_enable_dispatch_roundtrip_failed_checks", 0.0),
                )
            ),
            int(
                _number_from(
                    scaleup_route_enable,
                    "failed_checks",
                    _number(row, "scaleup_route_enable_dispatch_roundtrip_failed_checks", 0.0),
                )
            ),
        ),
        "route_dispatch_roundtrip_required": _to_bool(
            route.get("required", row.get("broker_route_dispatch_roundtrip_required", False))
        ),
        "route_dispatch_roundtrip_provided": _to_bool(
            route.get("provided", row.get("broker_route_dispatch_roundtrip_provided", False))
        ),
        "route_dispatch_roundtrip_ready": _to_bool(
            route.get("ready", row.get("broker_route_dispatch_roundtrip_ready", False))
        ),
        "route_dispatch_roundtrip_target_mode": _identity_key(
            _first_text(route.get("target_mode", ""), row.get("broker_route_dispatch_roundtrip_target_mode", ""))
        ),
        "route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(route.get("strategy", ""), row.get("broker_route_dispatch_roundtrip_strategy", ""))
        ),
        "route_dispatch_roundtrip_market": _identity_key(
            _first_text(route.get("market", ""), row.get("broker_route_dispatch_roundtrip_market", ""))
        ),
        "route_dispatch_roundtrip_scenario_key": _first_text(
            route.get("scenario_key", ""),
            row.get("broker_route_dispatch_roundtrip_scenario_key", ""),
        ),
        "route_dispatch_roundtrip_batch_id": _first_text(
            route.get("dispatch_batch_id", ""),
            row.get("broker_route_dispatch_roundtrip_batch_id", ""),
        ),
        "route_dispatch_roundtrip_requests": int(
            _number_from(
                route,
                "requests",
                _number(row, "broker_route_dispatch_roundtrip_requests", 0.0),
            )
        ),
        "route_dispatch_roundtrip_acked_orders": int(
            _number_from(
                route,
                "acked_orders",
                _number(row, "broker_route_dispatch_roundtrip_acked_orders", 0.0),
            )
        ),
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                route,
                "missing_request_acks",
                _number(row, "broker_route_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "route_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                route,
                "rejected_orders",
                _number(row, "broker_route_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                route,
                "unmatched_acks",
                _number(row, "broker_route_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
    }


def _broker_vendor_market_data_batch_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return select_vendor_market_data_batch_source(
        config,
        (
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_vendor_market_data_batch",
        ),
        default_source="scaleup_broker_dispatch_roundtrip_vendor_market_data_batch",
    )


def _broker_vendor_market_data_batch_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    for key in (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison",
    ):
        comparison = config.get(key)
        if isinstance(comparison, dict) and comparison:
            return comparison
    return {}


def _broker_vendor_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(CUTOVER_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_complete_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(CUTOVER_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY)
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_extended_complete_final_lineage_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_extended_complete_final_lineage_36_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_latest_extended_complete_final_lineage_44_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_comparison_source(
    config: dict[str, Any],
) -> dict[str, Any]:
    comparison = config.get(
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_COMPARISON_KEY
    )
    return comparison if isinstance(comparison, dict) else {}


def _broker_vendor_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = CUTOVER_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, Any] = {
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
                row.get(f"{prefix}_application_lineage_sha256", ""),
            )
        ),
    }
    for field in CUTOVER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_complete_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = CUTOVER_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, Any] = {
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
                    f"{CUTOVER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in CUTOVER_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_extended_complete_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    fields: dict[str, Any] = {
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
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_cutover_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_extended_complete_final_lineage_36_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_FIELD_PREFIX
    summary_prefix = CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_SUMMARY_FIELD_PREFIX
    fields: dict[str, Any] = {
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
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_36_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_latest_extended_complete_final_lineage_44_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_FIELD_PREFIX
    summary_prefix = (
        CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_SUMMARY_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
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
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_FIELD_PREFIX
    summary_prefix = (
        CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_SUMMARY_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
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
        f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get(
                    "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
                row.get(
                    f"{summary_prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in (
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_DIGEST_FIELDS,
        *CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_FIELD_PREFIX
    )
    summary_prefix = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SUMMARY_FIELD_PREFIX
    )
    cutover_review_field = (
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD
    )
    fields: dict[str, Any] = {
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
                row.get(f"{summary_prefix}_{cutover_review_field}", ""),
            )
        ),
    }
    for field in (
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_DIGEST_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_STAGE_FIELDS,
        *CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CURRENT_STAGE_FIELDS,
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_SCALEUP_REVIEW_FIELD,
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_FIELD_PREFIX
    )
    summary_prefix = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SUMMARY_FIELD_PREFIX
    )
    cutover_review_field = (
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD
    )
    fields: dict[str, Any] = {
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
                row.get(f"{summary_prefix}_{cutover_review_field}", ""),
            )
        ),
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_FIELD_PREFIX
    )
    summary_prefix = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_SUMMARY_FIELD_PREFIX
    )
    cutover_review_field = (
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD
    )
    fields: dict[str, Any] = {
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
                row.get(f"{summary_prefix}_{cutover_review_field}", ""),
            )
        ),
    }
    for field in (
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_DIGEST_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CURRENT_STAGE_FIELDS,
        *CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_REVIEW_FIELDS,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ACK_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_ROUNDTRIP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_BROKER_READINESS_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_SCALEUP_REVIEW_FIELD,
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_CUTOVER_REVIEW_FIELD,
        *CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CONFIRMED_REVIEW_FIELDS,
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_CUTOVER_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_market_data_batch_row_prefix(row: pd.Series) -> str:
    prefixes = (
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_vendor_market_data_batch",
    )
    for prefix in prefixes:
        if (
            _to_bool(row.get(f"{prefix}_provided", False))
            or int(_number(row, f"{prefix}_dataset_count", 0.0)) > 0
            or _identity_key(row.get(f"{prefix}_adapter", ""))
            or _identity_key(row.get(f"{prefix}_market", ""))
            or _identity_key(row.get(f"{prefix}_manifest_run_type", ""))
        ):
            return prefix
    return "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates: list[tuple[object, str]] = [
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
    return {}, "scaleup_broker_vendor_data_readiness"


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    cutover_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    vendor, _source = _broker_vendor_market_data_batch_source(cutover_config)
    sidecar_broker = broker_readiness_config.get(
        "broker_readiness",
        broker_readiness_config,
    ) or {}
    if not isinstance(sidecar_broker, dict):
        return cutover_config
    dispatch = sidecar_broker.get("dispatch_roundtrip", {}) or {}
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
    existing_readiness, _readiness_source = _broker_vendor_data_readiness_source(cutover_config)
    sidecar_readiness, _sidecar_readiness_source = _broker_vendor_data_readiness_source(
        sidecar_broker
    )
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(existing_readiness)
        and _broker_vendor_data_readiness_source_active(sidecar_readiness)
    )
    existing_lineage = _broker_vendor_market_data_batch_lineage_comparison_source(
        cutover_config
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
        return cutover_config

    out = dict(cutover_config)
    if should_hydrate_vendor:
        out["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(sidecar_vendor)
    if should_hydrate_readiness:
        out["scaleup_broker_vendor_data_readiness"] = dict(sidecar_readiness)
    if should_hydrate_lineage:
        out[
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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


def _broker_shadow_broker_state_fields(row: pd.Series, shadow_broker: dict[str, Any]) -> dict[str, Any]:
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    return {
        "broker_shadow_broker_readiness_provided": _to_bool(
            shadow_broker.get("provided", row.get("scaleup_broker_shadow_broker_readiness_provided", False))
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("scaleup_broker_shadow_broker_adapter", ""))
        ),
        "broker_shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "scaleup_broker_shadow_broker_adapter_count", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("scaleup_broker_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("scaleup_broker_shadow_broker_route_readiness_market", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "scaleup_broker_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("scaleup_broker_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("scaleup_broker_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("scaleup_broker_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
    }


def _upload_state(row: pd.Series) -> dict[str, Any]:
    return {
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "schema_status": _first_text(row.get("adapter_schema_status", "")),
        "orders": int(_number(row, "orders", 0.0)),
        "output_file": _first_text(row.get("output_file", "")),
        "recommendation": _first_text(row.get("recommendation", "")),
    }


def _order_export_state(summary: pd.DataFrame) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "provided": not summary.empty,
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "orders": int(_number(row, "orders", 0.0)),
        "total_notional": float(_number(row, "total_notional", 0.0)),
        "max_order_notional": float(_number(row, "max_order_notional", 0.0)),
    }


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required route-enable input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required route-enable input is empty: {name}")
    return frame


def _read_optional(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_csv(file_path)


def _summary_path(path: str | Path | None, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path:
    if path is None:
        return Path(filename)
    candidate = Path(path)
    if not candidate.is_dir():
        return candidate
    direct = candidate / filename
    if direct.exists():
        return direct
    return next(
        (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
        direct,
    )


def _sidecar_path(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        file_path = candidate / filename
    else:
        file_path = candidate if candidate.name == filename else candidate.with_name(filename)
    return file_path if file_path.exists() else None


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _dispatch_roundtrip_required(thresholds: RouteEnableThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: RouteEnableThresholds, cutover: dict[str, Any] | None = None) -> bool:
    return bool(
        thresholds.require_route_readiness
        or thresholds.target_mode == "live_dryrun"
        or (cutover is not None and cutover["route_readiness_required"])
    )


def _strategy_portfolio_active(cutover: dict[str, Any]) -> bool:
    return bool(
        cutover["strategy_portfolio_required"]
        or cutover["strategy_portfolio_provided"]
        or _strategy_portfolio_leadlag_active(cutover)
    )


def _strategy_portfolio_leadlag_active(cutover: dict[str, Any]) -> bool:
    return bool(
        cutover["strategy_portfolio_leadlag_edge_lineage_required"]
        or _identity_key(cutover["strategy_portfolio_selected_profile"])
        == "leadlag"
    )


def _strategy_portfolio_leadlag_state(
    row: pd.Series,
    strategy_portfolio: dict[str, Any],
) -> dict[str, Any]:
    prefixes = ("runtime_strategy_portfolio_", "strategy_portfolio_")
    summary_prefix = next(
        (
            prefix
            for prefix in prefixes
            if any(
                f"{prefix}{field}" in row.index
                for field in STRATEGY_PORTFOLIO_LEADLAG_FIELDS
            )
        ),
        prefixes[0],
    )
    config_lineage = leadlag_lineage_fields(strategy_portfolio)
    summary_lineage = leadlag_lineage_fields(
        row,
        source_prefix=summary_prefix,
    )
    config_required = _to_bool(
        strategy_portfolio.get("leadlag_edge_lineage_required", False)
    )
    summary_required = _to_bool(
        row.get(f"{summary_prefix}leadlag_edge_lineage_required", False)
    )
    config_matches = _to_bool(
        strategy_portfolio.get(
            "leadlag_edge_lineage_matches_scaleup",
            False,
        )
    )
    summary_matches = _to_bool(
        row.get(
            f"{summary_prefix}leadlag_edge_lineage_matches_scaleup",
            False,
        )
    )
    config_profile = _first_text(strategy_portfolio.get("selected_profile", ""))
    summary_profile = _first_text(
        row.get("runtime_strategy_portfolio_selected_profile", ""),
        row.get("strategy_portfolio_selected_profile", ""),
    )
    config_has_lineage = any(
        field in strategy_portfolio
        for field in STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    )
    summary_has_lineage = any(
        f"{summary_prefix}{field}" in row.index
        for field in STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    )
    active = bool(
        config_required
        or summary_required
        or _identity_key(config_profile) == "leadlag"
        or _identity_key(summary_profile) == "leadlag"
    )
    consistent = bool(
        not active
        or (
            config_has_lineage
            and summary_has_lineage
            and _identity_key(config_profile) == _identity_key(summary_profile)
            and config_required == summary_required
            and config_matches == summary_matches
            and all(
                leadlag_lineage_field_matches(
                    field,
                    config_lineage[field],
                    summary_lineage[field],
                )
                for field in LEADLAG_LINEAGE_FIELDS
            )
        )
    )
    selected_lineage = config_lineage if config_has_lineage else summary_lineage
    return {
        "strategy_portfolio_leadlag_edge_lineage_required": (
            config_required if config_has_lineage else summary_required
        ),
        **{
            f"strategy_portfolio_{field}": value
            for field, value in selected_lineage.items()
        },
        "strategy_portfolio_leadlag_edge_lineage_matches_scaleup": (
            config_matches if config_has_lineage else summary_matches
        ),
        "strategy_portfolio_leadlag_cutover_contract_consistent": consistent,
    }


def _strategy_portfolio_leadlag_output_fields(
    cutover: dict[str, Any],
) -> dict[str, Any]:
    return {
        f"strategy_portfolio_{field}": cutover[f"strategy_portfolio_{field}"]
        for field in STRATEGY_PORTFOLIO_LEADLAG_OUTPUT_FIELDS
    }


def _strategy_portfolio_leadlag_summary_fields(
    packet: pd.Series,
) -> dict[str, Any]:
    return {
        f"strategy_portfolio_{field}": packet[f"strategy_portfolio_{field}"]
        for field in STRATEGY_PORTFOLIO_LEADLAG_OUTPUT_FIELDS
    }


def _strategy_portfolio_leadlag_config(packet: pd.Series) -> dict[str, Any]:
    return {
        field: _jsonable_check_value(packet[f"strategy_portfolio_{field}"])
        for field in STRATEGY_PORTFOLIO_LEADLAG_OUTPUT_FIELDS
    }


def _cutover_lineage_output_fields(cutover: dict[str, Any]) -> dict[str, Any]:
    return {column: cutover[column] for column in CUTOVER_LINEAGE_OUTPUT_COLUMNS}


def _cutover_lineage_summary_fields(packet: pd.Series) -> dict[str, Any]:
    return {column: packet[column] for column in CUTOVER_LINEAGE_OUTPUT_COLUMNS}


def _cutover_lineage_config(packet: pd.Series) -> dict[str, Any]:
    return {
        column: _jsonable_check_value(packet[column])
        for column in CUTOVER_LINEAGE_OUTPUT_COLUMNS
    }


def _reject_input_output_collision(
    output_dir: Path,
    inputs: dict[str, Path | None],
) -> None:
    for label, value in inputs.items():
        if value is None:
            continue
        path = Path(value).resolve()
        root = path if path.is_dir() else path.parent
        if output_dir == root or root in output_dir.parents or output_dir in root.parents:
            raise ValueError(f"route-enable output_dir must not overwrite the {label} source directory")


def _route_dispatch_roundtrip_required(thresholds: RouteEnableThresholds, cutover: dict[str, Any]) -> bool:
    return bool(
        _dispatch_roundtrip_required(thresholds)
        or cutover["route_dispatch_roundtrip_required"]
        or cutover["route_dispatch_roundtrip_provided"]
    )


def _validate_thresholds(thresholds: RouteEnableThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")


def _number(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    if row.empty or column not in row.index:
        return float(fallback)
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return float(fallback)
    return float(value)


def _number_from(mapping: dict[str, Any], key: str, fallback: float) -> float:
    value = mapping.get(key, fallback)
    if value is None or _is_missing(value):
        return float(fallback)
    return float(value)


def _nullable_number(value: object) -> float | None:
    if value is None or _is_missing(value):
        return None
    return float(value)


def _first_text(*values: object) -> str:
    for value in values:
        text = _object_text(value)
        if text:
            return text
    return ""


def _strategy_key(value: object) -> str:
    key = _identity_key(value)
    aliases = {
        "leadlag": "lead_lag_taker",
        "lead_lag": "lead_lag_taker",
        "leadlag_taker": "lead_lag_taker",
        "microprice_imbalance": "imbalance",
        "surface_market_making": "surface_mm",
        "parity_box": "parity",
    }
    return aliases.get(key, key)


def _identity_key(value: object) -> str:
    return _object_text(value).lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _object_text(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed", "enabled"}
    return bool(value)


def _is_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value: object) -> object:
    if _is_missing(value):
        return None
    return value


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
