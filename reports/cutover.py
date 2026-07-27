from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from reports.leadlag_lineage import (
    LEADLAG_LINEAGE_BOOLEAN_FIELDS,
    LEADLAG_LINEAGE_FIELDS,
    LEADLAG_LINEAGE_INTEGER_FIELDS,
    LEADLAG_LINEAGE_NUMERIC_FIELDS,
    LEADLAG_LINEAGE_TEXT_FIELDS,
    leadlag_lineage_ready,
)
from reports.manifest import write_experiment_manifest
from reports.operational_lineage import (
    empty_runtime_session_lineage,
    load_runtime_session_lineage,
    runtime_session_lineage_fields,
    runtime_session_lineage_manifest_inputs,
)
from reports.scaleup_runtime_provenance import (
    BROKER_READINESS_CONTRACT_IDENTITY_GATE_CHECKS,
    empty_scaleup_runtime_provenance,
    load_scaleup_runtime_provenance,
    scaleup_runtime_fields,
    scaleup_runtime_manifest_inputs,
)
from reports.vendor_market_data import vendor_market_data_batch_source_active


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
RUNTIME_LINEAGE_OUTPUT_COLUMNS = tuple(
    runtime_session_lineage_fields(empty_runtime_session_lineage()).keys()
)
SCALEUP_PROVENANCE_OUTPUT_COLUMNS = tuple(
    scaleup_runtime_fields(empty_scaleup_runtime_provenance()).keys()
)
STRATEGY_PORTFOLIO_LEADLAG_FIELDS = (
    "leadlag_edge_lineage_required",
    *LEADLAG_LINEAGE_FIELDS,
    "leadlag_edge_lineage_matches_scaleup",
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
BROKER_FINAL_LINEAGE_COMPARISON_KEY = (
    "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_FINAL_LINEAGE_FIELD_PREFIX = "broker_dispatch_roundtrip_vendor_market_data_batch"
BROKER_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
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
)
SCALEUP_FINAL_LINEAGE_COMPARISON_KEY = (
    "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_FINAL_LINEAGE_FIELD_PREFIX = (
    "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
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
)
CUTOVER_FINAL_LINEAGE_COMPARISON_KEY = (
    "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    *SCALEUP_FINAL_LINEAGE_DIGEST_FIELDS,
    "scaleup_final_review_carried_application_lineage_sha256",
    "cutover_final_review_carried_application_lineage_sha256",
    "route_final_review_carried_application_lineage_sha256",
    "dispatch_final_review_carried_application_lineage_sha256",
    "send_final_review_carried_application_lineage_sha256",
    "ack_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_complete_final_review_carried_application_lineage_sha256",
)
CUTOVER_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    *SCALEUP_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "scaleup_complete_final_review_carried_application_lineage_sha256",
    "cutover_complete_final_review_carried_application_lineage_sha256",
    "route_complete_final_review_carried_application_lineage_sha256",
    "dispatch_complete_final_review_carried_application_lineage_sha256",
    "send_complete_final_review_carried_application_lineage_sha256",
    "ack_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_COMPARISON_KEY = (
    "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX = (
    "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_DIGEST_FIELDS: tuple[str, ...] = (
    *SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_COMPARISON_KEY = (
    "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX = (
    "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS: tuple[
    str, ...
] = (
    *SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS: tuple[
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
CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_COMPARISON_KEY = (
    "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_COMPARISON_KEY = (
    "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_COMPARISON_KEY = (
    "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX = (
    "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS: tuple[
    str, ...
] = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS: tuple[
    str, ...
] = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS: tuple[
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
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD = (
    "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_COMPARISON_KEY = (
    "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_COMPARISON_KEY = (
    "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX = (
    "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS: tuple[
    str, ...
] = SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS: tuple[
    str, ...
] = SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS: tuple[
    str, ...
] = SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS: tuple[
    str, ...
] = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD = (
    "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD = (
    "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD = (
    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD = (
    "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_COMPARISON_KEY = (
    "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_COMPARISON_KEY = (
    "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_FIELD_PREFIX = (
    "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SUMMARY_FIELD_PREFIX = (
    "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_CONFIRMED_REVIEW_FIELDS: tuple[
    str, ...
] = (
    "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD = (
    "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_COMPARISON_KEY = (
    "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)


@dataclass(frozen=True)
class CutoverGateThresholds:
    target_mode: str = "live_dryrun"
    require_scaleup_ready: bool = True
    require_route_readiness: bool = False
    require_broker_readiness: bool = True
    require_runtime_session: bool = True
    require_runtime_guard_continue: bool = True
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
    require_operator_approval: bool = True
    require_operator_identity_ack: bool = True
    require_operator_limits_ack: bool = True
    max_failed_scaleup_checks: int = 0


@dataclass(frozen=True)
class CutoverGateReport:
    authorization: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None
    action_queue: pd.DataFrame | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_cutover_gate(
    *,
    scaleup_summary: pd.DataFrame,
    scaleup_config: dict[str, Any] | None = None,
    scaleup_checks: pd.DataFrame | None = None,
    broker_readiness_summary: pd.DataFrame | None = None,
    runtime_session_summary: pd.DataFrame | None = None,
    runtime_session_lineage: dict[str, Any] | None = None,
    scaleup_provenance: dict[str, Any] | None = None,
    operator_review: pd.DataFrame | None = None,
    thresholds: CutoverGateThresholds | None = None,
) -> CutoverGateReport:
    thresholds = thresholds or CutoverGateThresholds()
    _validate_thresholds(thresholds)
    scaleup_summary = _require_nonempty(scaleup_summary, "scaleup_summary")
    scaleup_config = scaleup_config or {}
    scaleup_checks = pd.DataFrame() if scaleup_checks is None else scaleup_checks.copy().reset_index(drop=True)
    broker_readiness_summary = _optional_frame(broker_readiness_summary)
    runtime_session_summary = _optional_frame(runtime_session_summary)
    operator_review = _optional_frame(operator_review)
    scaleup_provenance = (
        scaleup_provenance
        or empty_scaleup_runtime_provenance()
    )

    scaleup = _scaleup_state(scaleup_summary.iloc[0], scaleup_config, scaleup_checks)
    broker = _broker_state(broker_readiness_summary)
    runtime = _runtime_state(
        runtime_session_summary,
        broker,
        runtime_session_lineage or empty_runtime_session_lineage(),
    )
    operator = _operator_state(operator_review, scaleup)
    checks = _checks(
        scaleup,
        broker,
        runtime,
        operator,
        thresholds,
        scaleup_provenance,
    )
    authorization = _authorization(
        scaleup,
        broker,
        runtime,
        operator,
        thresholds,
        checks,
        scaleup_provenance,
    )
    action_queue = _action_queue(authorization.iloc[0], checks)
    summary = _summary_with_actions(_summary(authorization.iloc[0], checks), checks, action_queue)
    config = _config(authorization.iloc[0], thresholds, checks, action_queue)
    return CutoverGateReport(
        authorization=authorization,
        checks=checks,
        summary=summary,
        config=config,
        action_queue=action_queue,
    )


def write_cutover_gate_report(
    *,
    scaleup_dir: str | Path,
    broker_readiness_dir: str | Path,
    output_dir: str | Path,
    runtime_session_dir: str | Path | None = None,
    operator_review_path: str | Path | None = None,
    thresholds: CutoverGateThresholds | None = None,
) -> CutoverGateReport:
    scaleup = Path(scaleup_dir)
    broker = Path(broker_readiness_dir)
    thresholds = thresholds or CutoverGateThresholds()
    _validate_thresholds(thresholds)
    scaleup_config_path = scaleup / "scaleup_config.json" if scaleup.is_dir() else Path(scaleup_dir)
    broker_readiness_summary_path = _summary_path(
        broker,
        "broker_readiness_summary.csv",
        fallback_dirs=("06_broker_readiness", "05_broker_readiness"),
    )
    broker_readiness_config_path = _sidecar_path(
        broker,
        "broker_readiness_config.json",
        fallback_dirs=("06_broker_readiness", "05_broker_readiness"),
    )
    if not scaleup_config_path.exists():
        raise FileNotFoundError(f"scale-up config not found: {scaleup_config_path}")
    scaleup_summary_path = (
        scaleup / "scaleup_summary.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_summary.csv")
    )
    scaleup_checks_path = (
        scaleup / "scaleup_checks.csv" if scaleup.is_dir() else scaleup_config_path.with_name("scaleup_checks.csv")
    )
    scaleup_provenance = load_scaleup_runtime_provenance(
        scaleup_config_path
    )
    runtime_session_summary_path = (
        _summary_path(runtime_session_dir, "runtime_session_summary.csv")
        if runtime_session_dir is not None
        else None
    )
    runtime_lineage = empty_runtime_session_lineage(
        required=bool(thresholds.require_runtime_session or runtime_session_dir is not None)
    )
    if runtime_session_summary_path is not None and runtime_session_summary_path.is_file():
        runtime_lineage = load_runtime_session_lineage(
            runtime_session_summary_path,
            scaleup_config_path,
            expected_broker_readiness_config_path=(
                broker_readiness_config_path
                or broker_readiness_summary_path.with_name(
                    "broker_readiness_config.json"
                )
            ),
        )
    scaleup_config = json.loads(scaleup_config_path.read_text(encoding="utf-8"))
    if broker_readiness_config_path is not None:
        scaleup_config = _with_broker_readiness_config_vendor_market_data_batch(
            scaleup_config,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    report = evaluate_cutover_gate(
        scaleup_summary=_read_required(scaleup_summary_path, "scaleup_summary"),
        scaleup_config=scaleup_config,
        scaleup_checks=_read_optional(scaleup_checks_path),
        broker_readiness_summary=_read_required(broker_readiness_summary_path, "broker_readiness"),
        runtime_session_summary=_read_optional(runtime_session_summary_path),
        runtime_session_lineage=runtime_lineage,
        scaleup_provenance=scaleup_provenance,
        operator_review=_read_optional(operator_review_path),
        thresholds=thresholds,
    )
    out = Path(output_dir).resolve()
    _reject_input_output_collision(
        out,
        {
            "scale-up": scaleup_config_path,
            "broker readiness": broker_readiness_summary_path,
            "runtime session": runtime_session_summary_path,
        },
    )
    out.mkdir(parents=True, exist_ok=True)
    report.authorization.to_csv(out / "cutover_authorization.csv", index=False)
    report.checks.to_csv(out / "cutover_checks.csv", index=False)
    report.summary.to_csv(out / "cutover_summary.csv", index=False)
    action_queue = report.action_queue if report.action_queue is not None else _action_queue(
        report.authorization.iloc[0], report.checks
    )
    action_queue.to_csv(out / "cutover_action_queue.csv", index=False)
    (out / "cutover_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "cutover_runbook.md").write_text(
        _runbook_markdown(report.summary.iloc[0], action_queue),
        encoding="utf-8",
    )
    inputs: dict[str, Any] = {
        "scaleup_summary": scaleup_summary_path,
        "scaleup_config": scaleup_config_path,
        "broker_readiness_summary": broker_readiness_summary_path,
    }
    if broker_readiness_config_path is not None:
        inputs["broker_readiness_config"] = broker_readiness_config_path
    if scaleup_checks_path.exists():
        inputs["scaleup_checks"] = scaleup_checks_path
    if runtime_session_summary_path is not None:
        inputs["runtime_session_summary"] = runtime_session_summary_path
    if operator_review_path is not None:
        inputs["operator_review"] = Path(operator_review_path)
    inputs.update(
        scaleup_runtime_manifest_inputs(scaleup_provenance)
    )
    inputs.update(runtime_session_lineage_manifest_inputs(runtime_lineage))
    write_experiment_manifest(
        out,
        run_type="cutover_gate",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
        extra={
            "ready": bool(report.ready),
            **_runtime_strategy_portfolio_leadlag_summary_fields(
                report.summary.iloc[0]
            ),
            **scaleup_runtime_fields(scaleup_provenance),
            **runtime_session_lineage_fields(runtime_lineage),
            "authorizes_submission": False,
        },
    )
    return CutoverGateReport(
        authorization=report.authorization,
        checks=report.checks,
        summary=report.summary,
        config=report.config,
        output_dir=out,
        action_queue=action_queue,
    )


def _checks(
    scaleup: dict[str, Any],
    broker: dict[str, Any],
    runtime: dict[str, Any],
    operator: dict[str, Any],
    thresholds: CutoverGateThresholds,
    scaleup_provenance: dict[str, Any],
) -> pd.DataFrame:
    target_mode = _identity_key(thresholds.target_mode)
    checks = [
        _check(
            "scaleup_ready",
            scaleup["ready"],
            "is",
            True,
            bool(scaleup["ready"]) or not thresholds.require_scaleup_ready,
            "scale-up plan is not ready",
        ),
        _check(
            "scaleup_target_mode",
            scaleup["target_mode"],
            "==",
            target_mode,
            bool(scaleup["target_mode"] and scaleup["target_mode"] == target_mode),
            "scale-up target mode does not match cutover target mode",
        ),
        _check(
            "scaleup_failed_checks",
            scaleup["failed_checks"],
            "<=",
            thresholds.max_failed_scaleup_checks,
            int(scaleup["failed_checks"]) <= thresholds.max_failed_scaleup_checks,
            "scale-up checks still have failures",
        ),
        _check(
            "broker_readiness_provided",
            broker["provided"],
            "is",
            True,
            bool(broker["provided"]) or not thresholds.require_broker_readiness,
            "broker readiness evidence is required but missing",
        ),
        _check(
            "broker_readiness_ready",
            broker["ready"],
            "is",
            True,
            bool(broker["ready"]) or not thresholds.require_broker_readiness,
            "broker readiness is not ready",
        ),
        _check(
            "broker_adapter_matches",
            broker["adapter"] or scaleup["adapter"],
            "==",
            scaleup["adapter"],
            bool((not broker["adapter"]) or broker["adapter"] == scaleup["adapter"]),
            "broker readiness adapter does not match scale-up adapter",
        ),
        _check(
            "runtime_session_provided",
            runtime["provided"],
            "is",
            True,
            bool(runtime["provided"]) or not thresholds.require_runtime_session,
            "runtime-session evidence is required but missing",
        ),
        _check(
            "runtime_session_ready",
            runtime["ready"],
            "is",
            True,
            bool(runtime["ready"]) or not thresholds.require_runtime_session,
            "runtime session is not ready",
        ),
        _check(
            "runtime_guard_continue",
            runtime["guard_action"] or ("halt" if runtime["halted"] else ""),
            "==",
            "continue",
            (runtime["guard_action"] == "continue" and not runtime["halted"])
            or not thresholds.require_runtime_guard_continue,
            "runtime guard is not continuing",
        ),
        _check(
            "runtime_target_mode_matches",
            runtime["target_mode"],
            "==",
            target_mode,
            bool(runtime["target_mode"] and runtime["target_mode"] == target_mode),
            "runtime-session target mode does not match cutover target mode",
        ),
        _check(
            "runtime_strategy_matches",
            runtime["strategy"],
            "==",
            scaleup["strategy"],
            bool(runtime["strategy"] and scaleup["strategy"] and runtime["strategy"] == scaleup["strategy"]),
            "runtime-session strategy does not match scale-up strategy",
        ),
        _check(
            "runtime_market_matches",
            runtime["market"],
            "==",
            scaleup["market"],
            bool(runtime["market"] and scaleup["market"] and runtime["market"] == scaleup["market"]),
            "runtime-session market does not match scale-up market",
        ),
        _check(
            "proof_refresh_ready",
            scaleup["proof_refresh_ready"] if scaleup["proof_refresh_active"] else "inactive",
            "is",
            True,
            (not scaleup["proof_refresh_active"])
            or bool(scaleup["proof_refresh_provided"] and scaleup["proof_refresh_ready"]),
            "scale-up proof freshness is missing or not ready",
        ),
        _check(
            "proof_refresh_identity_consistent",
            scaleup["proof_refresh_mixed_identity"] if scaleup["proof_refresh_active"] else "inactive",
            "is",
            False,
            (not scaleup["proof_refresh_active"]) or not bool(scaleup["proof_refresh_mixed_identity"]),
            "scale-up proof freshness has mixed strategy or market identity",
        ),
        _check(
            "proof_refresh_strategy_matches",
            scaleup["proof_refresh_strategy"] if scaleup["proof_refresh_active"] else "inactive",
            "==",
            scaleup["strategy"] if scaleup["proof_refresh_active"] else "inactive",
            (not scaleup["proof_refresh_active"])
            or bool(scaleup["proof_refresh_strategy"] and scaleup["proof_refresh_strategy"] == scaleup["strategy"]),
            "scale-up proof freshness strategy does not match cutover strategy",
        ),
        _check(
            "proof_refresh_market_matches",
            scaleup["proof_refresh_market"] if scaleup["proof_refresh_active"] else "inactive",
            "==",
            scaleup["market"] if scaleup["proof_refresh_active"] else "inactive",
            (not scaleup["proof_refresh_active"])
            or bool(scaleup["proof_refresh_market"] and scaleup["proof_refresh_market"] == scaleup["market"]),
            "scale-up proof freshness market does not match cutover market",
        ),
    ]
    checks.extend(
        _scaleup_provenance_checks(scaleup_provenance)
    )
    checks.extend(
        _broker_readiness_contract_identity_checks(
            scaleup_provenance,
            runtime,
        )
    )
    checks.extend(
        _broker_readiness_route_contract_identity_checks(
            scaleup_provenance,
            runtime,
        )
    )
    checks.extend(
        _broker_readiness_route_enable_route_contract_identity_checks(
            scaleup_provenance,
            runtime,
        )
    )
    checks.extend(
        _broker_readiness_route_enable_route_enable_route_contract_identity_checks(
            scaleup_provenance,
            runtime,
        )
    )
    if _runtime_strategy_portfolio_active(runtime):
        checks.extend(
            [
                _check(
                    "runtime_strategy_portfolio_provided",
                    runtime["strategy_portfolio_provided"],
                    "is",
                    True,
                    bool(runtime["strategy_portfolio_provided"]),
                    "runtime-session strategy portfolio allocation was not provided",
                ),
                _check(
                    "runtime_strategy_portfolio_ready",
                    runtime["strategy_portfolio_ready"],
                    "is",
                    True,
                    bool(runtime["strategy_portfolio_ready"]),
                    "runtime-session strategy portfolio allocation is not ready",
                ),
                _check(
                    "runtime_strategy_portfolio_allocation_eligible",
                    runtime["strategy_portfolio_selected_eligible"],
                    "is",
                    True,
                    bool(runtime["strategy_portfolio_selected_eligible"]),
                    "runtime-session strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "runtime_strategy_portfolio_strategy_matches",
                    runtime["strategy_portfolio_selected_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(
                        runtime["strategy_portfolio_selected_strategy"]
                        and scaleup["strategy"]
                        and runtime["strategy_portfolio_selected_strategy"] == scaleup["strategy"]
                    ),
                    "runtime-session strategy portfolio strategy does not match scale-up strategy",
                ),
                _check(
                    "runtime_strategy_portfolio_market_matches",
                    runtime["strategy_portfolio_selected_market"],
                    "==",
                    scaleup["market"],
                    bool(
                        runtime["strategy_portfolio_selected_market"]
                        and scaleup["market"]
                        and runtime["strategy_portfolio_selected_market"] == scaleup["market"]
                    ),
                    "runtime-session strategy portfolio market does not match scale-up market",
                ),
                _check(
                    "runtime_strategy_portfolio_allocation_notional",
                    runtime["strategy_portfolio_selected_allocation_notional"],
                    ">",
                    0.0,
                    float(runtime["strategy_portfolio_selected_allocation_notional"]) > 0.0,
                    "runtime-session strategy portfolio allocation notional must be positive",
                ),
            ]
        )
        if _runtime_strategy_portfolio_leadlag_active(runtime):
            lineage_ready = leadlag_lineage_ready(
                runtime,
                prefix="strategy_portfolio_",
            )
            checks.extend(
                [
                    _check(
                        "runtime_strategy_portfolio_leadlag_edge_lineage_required",
                        runtime["strategy_portfolio_leadlag_edge_lineage_required"],
                        "is",
                        True,
                        bool(runtime["strategy_portfolio_leadlag_edge_lineage_required"]),
                        "runtime session did not carry the required lead-lag lineage marker",
                    ),
                    _check(
                        "runtime_strategy_portfolio_leadlag_profile",
                        runtime["strategy_portfolio_selected_profile"],
                        "==",
                        "leadlag",
                        _identity_key(runtime["strategy_portfolio_selected_profile"])
                        == "leadlag",
                        "runtime session lead-lag lineage is attached to a different portfolio profile",
                    ),
                    _check(
                        "runtime_strategy_portfolio_leadlag_edge_lineage_ready",
                        lineage_ready,
                        "is",
                        True,
                        lineage_ready,
                        "runtime session lost or malformed the lead-lag measured-edge lineage",
                    ),
                    _check(
                        "runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup",
                        runtime[
                            "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
                        ],
                        "is",
                        True,
                        bool(
                            runtime[
                                "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
                            ]
                        ),
                        "runtime guard did not validate the lead-lag lineage against current scale-up",
                    ),
                ]
            )
    if runtime["runtime_lineage_required"]:
        checks.extend(
            [
                _check(
                    "runtime_lineage_provided",
                    runtime["runtime_lineage_provided"],
                    "is",
                    True,
                    bool(runtime["runtime_lineage_provided"]),
                    "runtime-session lineage evidence is required but missing",
                ),
                _check(
                    "runtime_session_manifest_current",
                    runtime["runtime_session_manifest_current"],
                    "is",
                    True,
                    bool(runtime["runtime_session_manifest_current"]),
                    "runtime-session manifest is missing, stale, or incomplete",
                ),
                _check(
                    "runtime_lineage_contract_consistent",
                    runtime["runtime_lineage_contract_consistent"],
                    "is",
                    True,
                    bool(runtime["runtime_lineage_contract_consistent"]),
                    "runtime-session summary, config, and manifest lineage disagree",
                ),
                _check(
                    "runtime_lineage_non_authorizing",
                    runtime["runtime_lineage_non_authorizing"],
                    "is",
                    True,
                    bool(runtime["runtime_lineage_non_authorizing"]),
                    "runtime-session lineage contains an authorizing claim",
                ),
                _check(
                    "runtime_lineage_scaleup_matches_current",
                    runtime["runtime_lineage_scaleup_matches_current"],
                    "is",
                    True,
                    bool(runtime["runtime_lineage_scaleup_matches_current"]),
                    "runtime-session scale-up manifest does not match the current cutover source",
                ),
                _check(
                    "runtime_telemetry_lineage_matches_current",
                    runtime["runtime_telemetry_lineage_matches_current"],
                    "is",
                    True,
                    bool(runtime["runtime_telemetry_lineage_matches_current"]),
                    "runtime telemetry lineage no longer matches current research proof",
                ),
                _check(
                    "runtime_lineage_gate_passed",
                    runtime["runtime_lineage_gate_passed"],
                    "is",
                    True,
                    bool(runtime["runtime_lineage_gate_passed"]),
                    "runtime-session operational lineage gate did not pass",
                ),
            ]
        )
        if runtime["runtime_lineage_broker_readiness_required"]:
            checks.extend(
                [
                    _check(
                        "runtime_lineage_broker_readiness_source_matches_scaleup",
                        runtime[
                            "runtime_lineage_broker_readiness_source_matches_scaleup"
                        ],
                        "is",
                        True,
                        bool(
                            runtime[
                                "runtime_lineage_broker_readiness_source_matches_scaleup"
                            ]
                        ),
                        "cutover broker readiness is not the source bound by scale-up",
                    ),
                    _check(
                        "runtime_lineage_broker_readiness_matches_current",
                        runtime[
                            "runtime_lineage_broker_readiness_matches_current"
                        ],
                        "is",
                        True,
                        bool(
                            runtime[
                                "runtime_lineage_broker_readiness_matches_current"
                            ]
                        ),
                        "runtime broker-readiness lineage no longer matches the current recursive source",
                    ),
                ]
            )
    route_readiness_required = _route_readiness_required(thresholds)
    route_readiness_active = bool(route_readiness_required or scaleup["route_readiness_provided"])
    if route_readiness_required:
        checks.append(
            _check(
                "scaleup_route_readiness_provided",
                scaleup["route_readiness_provided"],
                "is",
                True,
                bool(scaleup["route_readiness_provided"]),
                "cutover requires scale-up proof carrying route-readiness evidence",
            )
        )
    if route_readiness_active:
        checks.extend(
            [
                _check(
                    "scaleup_route_readiness_ready",
                    scaleup["route_readiness_ready"],
                    "is",
                    True,
                    bool(scaleup["route_readiness_ready"]),
                    "scale-up route-readiness evidence is not ready",
                ),
                _check(
                    "scaleup_route_readiness_strategy_matches",
                    scaleup["route_readiness_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup["route_readiness_strategy"]
                        and scaleup["route_readiness_strategy"] == scaleup["strategy"]
                    ),
                    "scale-up route-readiness strategy does not match cutover strategy",
                ),
                _check(
                    "scaleup_route_readiness_market_matches",
                    scaleup["route_readiness_market"],
                    "==",
                    scaleup["market"],
                    bool(scaleup["route_readiness_market"] and scaleup["route_readiness_market"] == scaleup["market"]),
                    "scale-up route-readiness market does not match cutover market",
                ),
                _check(
                    "scaleup_route_readiness_ops_launch_controls_present",
                    scaleup["route_readiness_ops_launch_controls_present"],
                    "is",
                    True,
                    bool(scaleup["route_readiness_ops_launch_controls_present"]),
                    "scale-up route-readiness proof is missing launch-grade ops broker controls",
                ),
                _check(
                    "scaleup_route_readiness_ops_launch_controls_blocked_pairs",
                    scaleup["route_readiness_ops_launch_controls_blocked_pairs"],
                    "<=",
                    0,
                    int(scaleup["route_readiness_ops_launch_controls_blocked_pairs"]) <= 0,
                    "scale-up route-readiness ops launch controls have blocked route pairs",
                ),
                _check(
                    "scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
                    scaleup["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"],
                    "<=",
                    0,
                    int(scaleup["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) <= 0,
                    "scale-up route-readiness broker round-trip allocation proof has breach pairs",
                ),
                _check(
                    "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    scaleup["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"],
                    "<=",
                    0,
                    int(scaleup["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]) <= 0,
                    "scale-up route-readiness broker round-trip concentration proof has breach pairs",
                ),
            ]
        )
    if _broker_route_readiness_active(scaleup):
        checks.extend(_broker_route_readiness_checks(scaleup))
    if _resume_route_readiness_active(scaleup, "broker_resume_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                scaleup,
                source_prefix="broker_resume_broker_route_readiness",
                check_prefix="scaleup_broker_resume_broker_route_readiness",
                label="scale-up broker resume-gate route proof",
            )
        )
    if _resume_route_readiness_active(scaleup, "broker_resume_incident_broker_route_readiness"):
        checks.extend(
            _resume_route_readiness_checks(
                scaleup,
                source_prefix="broker_resume_incident_broker_route_readiness",
                check_prefix="scaleup_broker_resume_incident_broker_route_readiness",
                label="scale-up broker resume-gate incident route proof",
            )
        )
    dispatch_roundtrip_required = _dispatch_roundtrip_required(thresholds)
    scaleup_dispatch_active = bool(
        dispatch_roundtrip_required
        or scaleup["dispatch_roundtrip_required"]
        or scaleup["dispatch_roundtrip_provided"]
    )
    broker_dispatch_active = bool(dispatch_roundtrip_required or broker["dispatch_roundtrip_provided"])
    scaleup_route_active = _route_dispatch_roundtrip_active(dispatch_roundtrip_required, scaleup)
    broker_route_active = _route_dispatch_roundtrip_active(dispatch_roundtrip_required, broker)
    if dispatch_roundtrip_required:
        checks.extend(
            [
                _check(
                    "scaleup_dispatch_roundtrip_provided",
                    scaleup["dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(scaleup["dispatch_roundtrip_provided"]),
                    "cutover requires scale-up proof carrying dry-run dispatch round-trip evidence",
                ),
                _check(
                    "broker_dispatch_roundtrip_provided",
                    broker["dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(broker["dispatch_roundtrip_provided"]),
                    "cutover requires broker readiness with dry-run dispatch round-trip proof",
                ),
                _check(
                    "scaleup_route_dispatch_roundtrip_provided",
                    scaleup["route_dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(scaleup["route_dispatch_roundtrip_provided"]),
                    "cutover requires scale-up proof carrying dispatch route proof",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_provided",
                    broker["route_dispatch_roundtrip_provided"],
                    "is",
                    True,
                    bool(broker["route_dispatch_roundtrip_provided"]),
                    "cutover requires broker readiness with dispatch route proof",
                ),
            ]
        )
    if scaleup_dispatch_active:
        checks.extend(_dispatch_roundtrip_checks("scaleup", scaleup, scaleup, target_mode))
    if broker_dispatch_active:
        checks.extend(_dispatch_roundtrip_checks("broker", broker, scaleup, target_mode))
    if scaleup_route_active:
        checks.extend(_route_dispatch_roundtrip_checks("scaleup", scaleup, scaleup, target_mode))
    if broker_route_active:
        checks.extend(_route_dispatch_roundtrip_checks("broker", broker, scaleup, target_mode))
    if scaleup_dispatch_active and broker_dispatch_active:
        checks.append(
            _check(
                "dispatch_roundtrip_batch_matches",
                broker["dispatch_roundtrip_batch_id"],
                "==",
                scaleup["dispatch_roundtrip_batch_id"],
                bool(
                    broker["dispatch_roundtrip_batch_id"]
                    and scaleup["dispatch_roundtrip_batch_id"]
                    and broker["dispatch_roundtrip_batch_id"] == scaleup["dispatch_roundtrip_batch_id"]
                ),
                "scale-up and broker readiness dispatch round-trip batches differ",
            )
        )
    if scaleup_route_active and broker_route_active:
        checks.append(
            _check(
                "route_dispatch_roundtrip_batch_matches",
                broker["route_dispatch_roundtrip_batch_id"],
                "==",
                scaleup["route_dispatch_roundtrip_batch_id"],
                bool(
                    broker["route_dispatch_roundtrip_batch_id"]
                    and scaleup["route_dispatch_roundtrip_batch_id"]
                    and broker["route_dispatch_roundtrip_batch_id"] == scaleup["route_dispatch_roundtrip_batch_id"]
                ),
                "scale-up and broker readiness route proof batches differ",
            )
        )
    if _shadow_broker_readiness_active(scaleup):
        checks.extend(_shadow_broker_readiness_checks(scaleup))
    if _broker_shadow_broker_readiness_active(scaleup):
        checks.extend(_broker_shadow_broker_readiness_checks(scaleup))
    if _broker_vendor_data_readiness_active(scaleup):
        checks.extend(_broker_vendor_data_readiness_checks(scaleup))
    if _broker_vendor_market_data_batch_active(scaleup):
        checks.extend(_broker_vendor_market_data_batch_checks(scaleup))
    resume_active = bool(thresholds.require_resume_gate or broker["resume_gate_provided"])
    if thresholds.require_resume_gate:
        checks.append(
            _check(
                "broker_resume_gate_provided",
                broker["resume_gate_provided"],
                "is",
                True,
                bool(broker["resume_gate_provided"]),
                "broker resume-gate authorization is required but missing",
            )
        )
    if resume_active:
        checks.extend(
            [
                _check(
                    "broker_resume_gate_ready",
                    broker["resume_gate_ready"],
                    "is",
                    True,
                    bool(broker["resume_gate_ready"]),
                    "broker resume-gate authorization is not ready",
                ),
                _check(
                    "broker_resume_strategy_matches",
                    broker["resume_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(broker["resume_strategy"] and broker["resume_strategy"] == scaleup["strategy"]),
                    "broker resume-gate strategy does not match cutover strategy",
                ),
                _check(
                    "broker_resume_market_matches",
                    broker["resume_market"],
                    "==",
                    scaleup["market"],
                    bool(broker["resume_market"] and broker["resume_market"] == scaleup["market"]),
                    "broker resume-gate market does not match cutover market",
                ),
                _check(
                    "broker_resume_proof_refresh_ready",
                    broker["resume_proof_refresh_ready"],
                    "is",
                    True,
                    bool(broker["resume_proof_refresh_ready"]),
                    "broker resume-gate proof freshness is not ready",
                ),
                _check(
                    "broker_resume_proof_refresh_strategy_matches",
                    broker["resume_proof_refresh_strategy"],
                    "==",
                    scaleup["strategy"],
                    bool(
                        broker["resume_proof_refresh_strategy"]
                        and broker["resume_proof_refresh_strategy"] == scaleup["strategy"]
                    ),
                    "broker resume-gate proof strategy does not match cutover strategy",
                ),
                _check(
                    "broker_resume_proof_refresh_market_matches",
                    broker["resume_proof_refresh_market"],
                    "==",
                    scaleup["market"],
                    bool(
                        broker["resume_proof_refresh_market"]
                        and broker["resume_proof_refresh_market"] == scaleup["market"]
                    ),
                    "broker resume-gate proof market does not match cutover market",
                ),
            ]
        )
    operator_approval_required = _operator_approval_required(thresholds)
    operator_identity_required = _operator_identity_ack_required(thresholds)
    operator_limits_required = _operator_limits_ack_required(thresholds)
    checks.extend(
        [
            _check(
                "operator_approved",
                operator["approved"] if operator["provided"] else "missing",
                "is",
                True,
                bool(operator["approved"]) or not operator_approval_required,
                "operator cutover approval is missing or false",
            ),
            _check(
                "operator_identity_ack",
                operator["identity_ack"] if operator["provided"] else "missing",
                "is",
                True,
                bool(operator["identity_ack"]) or not operator_identity_required,
                "operator review did not acknowledge cutover strategy and market",
            ),
            _check(
                "operator_limits_ack",
                operator["limits_ack"] if operator["provided"] else "missing",
                "is",
                True,
                bool(operator["limits_ack"]) or not operator_limits_required,
                "operator review did not acknowledge scale-up order and notional limits",
            ),
        ]
    )
    return pd.DataFrame(checks)


def _dispatch_roundtrip_checks(
    prefix: str,
    source: dict[str, Any],
    scaleup: dict[str, Any],
    target_mode: str,
) -> list[dict[str, object]]:
    label = prefix.replace("_", " ")
    return [
        _check(
            f"{prefix}_dispatch_roundtrip_ready",
            source["dispatch_roundtrip_ready"],
            "is",
            True,
            bool(source["dispatch_roundtrip_ready"]),
            f"{label} dry-run dispatch round-trip proof is not ready",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_target_mode_matches",
            source["dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(source["dispatch_roundtrip_target_mode"] and source["dispatch_roundtrip_target_mode"] == target_mode),
            f"{label} dispatch round-trip target mode does not match cutover target",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_strategy_matches",
            source["dispatch_roundtrip_strategy"],
            "==",
            scaleup["strategy"],
            bool(
                source["dispatch_roundtrip_strategy"]
                and scaleup["strategy"]
                and source["dispatch_roundtrip_strategy"] == scaleup["strategy"]
            ),
            f"{label} dispatch round-trip strategy does not match cutover strategy",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_market_matches",
            source["dispatch_roundtrip_market"],
            "==",
            scaleup["market"],
            bool(
                source["dispatch_roundtrip_market"]
                and scaleup["market"]
                and source["dispatch_roundtrip_market"] == scaleup["market"]
            ),
            f"{label} dispatch round-trip market does not match cutover market",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_scenario_matches",
            source["dispatch_roundtrip_scenario_key"],
            "==",
            scaleup["scenario_key"],
            bool(
                source["dispatch_roundtrip_scenario_key"]
                and scaleup["scenario_key"]
                and source["dispatch_roundtrip_scenario_key"] == scaleup["scenario_key"]
            ),
            f"{label} dispatch round-trip scenario does not match cutover scenario",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_missing_request_acks",
            source["dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(source["dispatch_roundtrip_missing_request_acks"]) <= 0,
            f"{label} dispatch round-trip has missing request acknowledgements",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_rejected_orders",
            source["dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(source["dispatch_roundtrip_rejected_orders"]) <= 0,
            f"{label} dispatch round-trip has rejected orders",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_unmatched_acks",
            source["dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(source["dispatch_roundtrip_unmatched_acks"]) <= 0,
            f"{label} dispatch round-trip has unmatched acknowledgements",
        ),
        _check(
            f"{prefix}_dispatch_roundtrip_failed_checks",
            source["dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(source["dispatch_roundtrip_failed_checks"]) <= 0,
            f"{label} dispatch round-trip has failed component checks",
        ),
        _check(
            f"{prefix}_route_enable_dispatch_roundtrip_failed_checks",
            source["route_enable_dispatch_roundtrip_failed_checks"],
            "<=",
            0,
            int(source["route_enable_dispatch_roundtrip_failed_checks"]) <= 0,
            f"{label} route-enable dispatch round-trip has failed component checks",
        ),
    ]


def _route_dispatch_roundtrip_checks(
    prefix: str,
    source: dict[str, Any],
    scaleup: dict[str, Any],
    target_mode: str,
) -> list[dict[str, object]]:
    label = prefix.replace("_", " ")
    return [
        _check(
            f"{prefix}_route_dispatch_roundtrip_ready",
            source["route_dispatch_roundtrip_ready"],
            "is",
            True,
            bool(source["route_dispatch_roundtrip_ready"]),
            f"{label} dispatch route proof is not ready",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_target_mode_matches",
            source["route_dispatch_roundtrip_target_mode"],
            "==",
            target_mode,
            bool(
                source["route_dispatch_roundtrip_target_mode"]
                and source["route_dispatch_roundtrip_target_mode"] == target_mode
            ),
            f"{label} dispatch route proof target mode does not match cutover target",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_strategy_matches",
            source["route_dispatch_roundtrip_strategy"],
            "==",
            scaleup["strategy"],
            bool(
                source["route_dispatch_roundtrip_strategy"]
                and scaleup["strategy"]
                and source["route_dispatch_roundtrip_strategy"] == scaleup["strategy"]
            ),
            f"{label} dispatch route proof strategy does not match cutover strategy",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_market_matches",
            source["route_dispatch_roundtrip_market"],
            "==",
            scaleup["market"],
            bool(
                source["route_dispatch_roundtrip_market"]
                and scaleup["market"]
                and source["route_dispatch_roundtrip_market"] == scaleup["market"]
            ),
            f"{label} dispatch route proof market does not match cutover market",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_scenario_matches",
            source["route_dispatch_roundtrip_scenario_key"],
            "==",
            scaleup["scenario_key"],
            bool(
                source["route_dispatch_roundtrip_scenario_key"]
                and scaleup["scenario_key"]
                and source["route_dispatch_roundtrip_scenario_key"] == scaleup["scenario_key"]
            ),
            f"{label} dispatch route proof scenario does not match cutover scenario",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_batch_id_provided",
            source["route_dispatch_roundtrip_batch_id"],
            "is not",
            "",
            bool(source["route_dispatch_roundtrip_batch_id"]),
            f"{label} dispatch route proof batch id is missing",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_request_count_matches",
            f"{source['route_dispatch_roundtrip_requests']}/{source['route_dispatch_roundtrip_acked_orders']}",
            "==",
            f"{source['dispatch_roundtrip_requests']}/{source['dispatch_roundtrip_acked_orders']}",
            (
                int(source["route_dispatch_roundtrip_requests"]) == int(source["dispatch_roundtrip_requests"])
                and int(source["route_dispatch_roundtrip_acked_orders"])
                == int(source["dispatch_roundtrip_acked_orders"])
            ),
            f"{label} dispatch route proof request/ack counts do not match dispatch round-trip counts",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_missing_request_acks",
            source["route_dispatch_roundtrip_missing_request_acks"],
            "<=",
            0,
            int(source["route_dispatch_roundtrip_missing_request_acks"]) <= 0,
            f"{label} dispatch route proof has missing request acknowledgements",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_rejected_orders",
            source["route_dispatch_roundtrip_rejected_orders"],
            "<=",
            0,
            int(source["route_dispatch_roundtrip_rejected_orders"]) <= 0,
            f"{label} dispatch route proof has rejected orders",
        ),
        _check(
            f"{prefix}_route_dispatch_roundtrip_unmatched_acks",
            source["route_dispatch_roundtrip_unmatched_acks"],
            "<=",
            0,
            int(source["route_dispatch_roundtrip_unmatched_acks"]) <= 0,
            f"{label} dispatch route proof has unmatched acknowledgements",
        ),
    ]


def _shadow_broker_readiness_active(scaleup: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(scaleup, key_prefix="")


def _shadow_broker_readiness_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        scaleup,
        key_prefix="",
        check_prefix="scaleup_shadow_broker",
        label="scale-up shadow broker",
    )


def _broker_shadow_broker_readiness_active(scaleup: dict[str, Any]) -> bool:
    return _shadow_broker_readiness_active_for(scaleup, key_prefix="broker_")


def _broker_shadow_broker_readiness_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    return _shadow_broker_readiness_checks_for(
        scaleup,
        key_prefix="broker_",
        check_prefix="scaleup_broker_shadow_broker",
        label="scale-up broker-readiness shadow broker",
        check_provided=True,
    )


def _shadow_broker_readiness_active_for(scaleup: dict[str, Any], *, key_prefix: str) -> bool:
    session_fields = (
        "readiness_sessions",
        "vendor_data_readiness_sessions",
        "route_readiness_sessions",
        "dispatch_roundtrip_sessions",
        "route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(scaleup.get(_shadow_broker_key(key_prefix, "readiness_provided"), False))
        or any(int(scaleup[_shadow_broker_key(key_prefix, field)]) > 0 for field in session_fields)
    )


def _shadow_broker_readiness_checks_for(
    scaleup: dict[str, Any],
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
                _to_bool(scaleup[_shadow_broker_key(key_prefix, "readiness_provided")]),
                "is",
                True,
                _to_bool(scaleup[_shadow_broker_key(key_prefix, "readiness_provided")]),
                f"{label} proof is active but not marked provided",
            )
        )
    sessions = int(scaleup[_shadow_broker_key(key_prefix, "readiness_sessions")])
    if sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_readiness_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "readiness_ready_sessions")]) == sessions,
                    f"{label} readiness evidence is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_adapter_matches",
                    scaleup[_shadow_broker_key(key_prefix, "adapter")],
                    "==",
                    scaleup["adapter"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "adapter")]
                        and scaleup[_shadow_broker_key(key_prefix, "adapter")] == scaleup["adapter"]
                    ),
                    f"{label} adapter does not match cutover adapter",
                ),
                _check(
                    f"{check_prefix}_adapter_consistent",
                    int(scaleup[_shadow_broker_key(key_prefix, "adapter_count")]),
                    "==",
                    1,
                    int(scaleup[_shadow_broker_key(key_prefix, "adapter_count")]) == 1,
                    f"{label} adapter identity is missing or mixed",
                ),
            ]
        )
    vendor_sessions = int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_sessions")])
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
                    int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")]),
                    "==",
                    sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_provided_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")]),
                    "==",
                    sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_ready_sessions")])
                    == sessions,
                    f"{label} vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _check(
                    f"{check_prefix}_vendor_data_readiness_failed_checks",
                    int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "vendor_data_readiness_failed_checks")]) <= 0,
                    f"{label} vendor-data wrapper proof has failed checks",
                ),
            ]
        )
    route_sessions = int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_sessions")])
    if route_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_readiness_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")]),
                    "==",
                    route_sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_ready_sessions")])
                    == route_sessions,
                    f"{label} route-readiness proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_readiness_strategy_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_readiness_strategy")],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_readiness_strategy")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_readiness_strategy")] == scaleup["strategy"]
                    ),
                    f"{label} route-readiness strategy does not match cutover strategy",
                ),
                _check(
                    f"{check_prefix}_route_readiness_market_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_readiness_market")],
                    "==",
                    scaleup["market"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_readiness_market")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_readiness_market")] == scaleup["market"]
                    ),
                    f"{label} route-readiness market does not match cutover market",
                ),
                _check(
                    f"{check_prefix}_route_readiness_gap_pairs",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_readiness_gap_pairs")]) <= 0,
                    f"{label} route-readiness proof has route gaps",
                ),
            ]
        )
    dispatch_sessions = int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_sessions")])
    if dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_dispatch_roundtrip_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")]),
                    "==",
                    dispatch_sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_ready_sessions")])
                    == dispatch_sessions,
                    f"{label} dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_strategy_matches",
                    scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        and scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_strategy")]
                        == scaleup["strategy"]
                    ),
                    f"{label} dispatch round-trip strategy does not match cutover strategy",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_market_matches",
                    scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")],
                    "==",
                    scaleup["market"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")]
                        and scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_market")] == scaleup["market"]
                    ),
                    f"{label} dispatch round-trip market does not match cutover market",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_scenario_consistent",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} dispatch round-trip scenario is missing or mixed",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_missing_request_acks",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_missing_request_acks")])
                    <= 0,
                    f"{label} dispatch round-trip has missing request acknowledgements",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_rejected_orders",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_rejected_orders")]) <= 0,
                    f"{label} dispatch round-trip has rejected orders",
                ),
                _check(
                    f"{check_prefix}_dispatch_roundtrip_unmatched_acks",
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]),
                    "<=",
                    0,
                    int(scaleup[_shadow_broker_key(key_prefix, "dispatch_roundtrip_unmatched_acks")]) <= 0,
                    f"{label} dispatch round-trip has unmatched acknowledgements",
                ),
            ]
        )
    route_dispatch_sessions = int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_sessions")])
    if route_dispatch_sessions > 0:
        checks.extend(
            [
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_ready",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")]),
                    "==",
                    route_dispatch_sessions,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_ready_sessions")])
                    == route_dispatch_sessions,
                    f"{label} route dispatch round-trip proof is not ready for every carried session",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_strategy_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")],
                    "==",
                    scaleup["strategy"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_strategy")]
                        == scaleup["strategy"]
                    ),
                    f"{label} route dispatch round-trip strategy does not match cutover strategy",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_market_matches",
                    scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")],
                    "==",
                    scaleup["market"],
                    bool(
                        scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        and scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_market")]
                        == scaleup["market"]
                    ),
                    f"{label} route dispatch round-trip market does not match cutover market",
                ),
                _check(
                    f"{check_prefix}_route_dispatch_roundtrip_scenario_consistent",
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]),
                    "==",
                    1,
                    int(scaleup[_shadow_broker_key(key_prefix, "route_dispatch_roundtrip_scenario_count")]) == 1,
                    f"{label} route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    return checks


def _broker_route_readiness_active(scaleup: dict[str, Any]) -> bool:
    return bool(
        _to_bool(scaleup["broker_route_readiness_required"])
        or _to_bool(scaleup["broker_route_readiness_provided"])
        or _to_bool(scaleup["broker_route_readiness_ready"])
        or int(scaleup["broker_route_readiness_route_ready_pairs"]) > 0
        or int(scaleup["broker_route_readiness_gap_pairs"]) > 0
        or bool(_object_text(scaleup["broker_route_readiness_strategy"]))
        or bool(_object_text(scaleup["broker_route_readiness_market"]))
        or bool(_object_text(scaleup["broker_route_readiness_recommendation"]))
        or _to_bool(scaleup["broker_route_readiness_ops_launch_controls_ready"])
        or bool(_object_text(scaleup["broker_route_readiness_ops_launch_control_failures"]))
        or int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0
        or int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) > 0
        or int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0
        or int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) > 0
    )


def _broker_route_readiness_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    return [
        _check(
            "scaleup_broker_route_readiness_provided",
            scaleup["broker_route_readiness_provided"],
            "is",
            True,
            bool(scaleup["broker_route_readiness_provided"] or not scaleup["broker_route_readiness_required"]),
            "scale-up broker-readiness route proof is required but not provided",
        ),
        _check(
            "scaleup_broker_route_readiness_ready",
            scaleup["broker_route_readiness_ready"],
            "is",
            True,
            bool(scaleup["broker_route_readiness_ready"]),
            "scale-up broker-readiness route proof is not ready",
        ),
        _check(
            "scaleup_broker_route_readiness_strategy_matches",
            scaleup["broker_route_readiness_strategy"],
            "==",
            scaleup["strategy"],
            bool(
                scaleup["broker_route_readiness_strategy"]
                and scaleup["broker_route_readiness_strategy"] == scaleup["strategy"]
            ),
            "scale-up broker-readiness route strategy does not match cutover strategy",
        ),
        _check(
            "scaleup_broker_route_readiness_market_matches",
            scaleup["broker_route_readiness_market"],
            "==",
            scaleup["market"],
            bool(
                scaleup["broker_route_readiness_market"]
                and scaleup["broker_route_readiness_market"] == scaleup["market"]
            ),
            "scale-up broker-readiness route market does not match cutover market",
        ),
        _check(
            "scaleup_broker_route_readiness_gap_pairs",
            scaleup["broker_route_readiness_gap_pairs"],
            "<=",
            0,
            int(scaleup["broker_route_readiness_gap_pairs"]) <= 0,
            "scale-up broker-readiness route proof has route gaps",
        ),
        _check(
            "scaleup_broker_route_readiness_ops_launch_controls_ready",
            scaleup["broker_route_readiness_ops_launch_controls_ready"],
            "is",
            True,
            bool(scaleup["broker_route_readiness_ops_launch_controls_ready"]),
            "scale-up broker-readiness route proof is missing launch-grade ops broker controls",
        ),
        _check(
            "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
            scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"],
            ">",
            0,
            int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) > 0,
            "scale-up broker-readiness route proof has no allocation-safe broker round-trip runs",
        ),
        _check(
            "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
            scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"],
            "<=",
            0,
            int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) <= 0,
            "scale-up broker-readiness route proof has allocation breach broker round-trip runs",
        ),
        _check(
            "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
            ">",
            0,
            int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0,
            "scale-up broker-readiness route proof has no concentration-OK broker round-trip runs",
        ),
        _check(
            "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
            "<=",
            0,
            int(scaleup["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) <= 0,
            "scale-up broker-readiness route proof has concentration breach broker round-trip runs",
        ),
    ]


def _resume_route_readiness_state_fields(
    row: pd.Series,
    route_readiness: dict[str, Any],
    *,
    source_prefix: str,
) -> dict[str, Any]:
    return {
        f"{source_prefix}_required": _to_bool(
            route_readiness.get("required", row.get(f"{source_prefix}_required", False))
        ),
        f"{source_prefix}_provided": _to_bool(
            route_readiness.get("provided", row.get(f"{source_prefix}_provided", False))
        ),
        f"{source_prefix}_ready": _to_bool(
            route_readiness.get("ready", row.get(f"{source_prefix}_ready", False))
        ),
        f"{source_prefix}_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get(f"{source_prefix}_strategy", ""))
        ),
        f"{source_prefix}_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get(f"{source_prefix}_market", ""))
        ),
        f"{source_prefix}_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, f"{source_prefix}_route_ready_pairs", 0.0),
            )
        ),
        f"{source_prefix}_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, f"{source_prefix}_gap_pairs", 0.0))
        ),
        f"{source_prefix}_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get(f"{source_prefix}_recommendation", ""),
        ),
        f"{source_prefix}_ops_launch_controls_ready": _to_bool(
            route_readiness.get(
                "ops_launch_controls_ready",
                row.get(f"{source_prefix}_ops_launch_controls_ready", False),
            )
        ),
        f"{source_prefix}_ops_launch_control_failures": _first_text(
            route_readiness.get("ops_launch_control_failures", ""),
            row.get(f"{source_prefix}_ops_launch_control_failures", ""),
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_safe_runs",
                _number(row, f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_breach_runs",
                _number(row, f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                _number(row, f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0),
            )
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_runs",
                _number(row, f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0),
            )
        ),
    }


def _resume_route_readiness_active(scaleup: dict[str, Any], source_prefix: str) -> bool:
    return bool(
        _to_bool(scaleup[f"{source_prefix}_required"])
        or _to_bool(scaleup[f"{source_prefix}_provided"])
        or _to_bool(scaleup[f"{source_prefix}_ready"])
        or int(scaleup[f"{source_prefix}_route_ready_pairs"]) > 0
        or int(scaleup[f"{source_prefix}_gap_pairs"]) > 0
        or _to_bool(scaleup[f"{source_prefix}_ops_launch_controls_ready"])
        or bool(_object_text(scaleup[f"{source_prefix}_ops_launch_control_failures"]))
        or int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"]) > 0
        or int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"]) > 0
        or int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0
        or int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) > 0
    )


def _resume_route_readiness_checks(
    scaleup: dict[str, Any],
    *,
    source_prefix: str,
    check_prefix: str,
    label: str,
) -> list[dict[str, object]]:
    return [
        _check(
            f"{check_prefix}_provided",
            scaleup[f"{source_prefix}_provided"],
            "is",
            True,
            bool(scaleup[f"{source_prefix}_provided"] or not scaleup[f"{source_prefix}_required"]),
            f"{label} is active but not marked provided",
        ),
        _check(
            f"{check_prefix}_ready",
            scaleup[f"{source_prefix}_ready"],
            "is",
            True,
            bool(scaleup[f"{source_prefix}_ready"]),
            f"{label} is not ready",
        ),
        _check(
            f"{check_prefix}_strategy_matches",
            scaleup[f"{source_prefix}_strategy"],
            "==",
            scaleup["strategy"],
            bool(scaleup[f"{source_prefix}_strategy"] and scaleup[f"{source_prefix}_strategy"] == scaleup["strategy"]),
            f"{label} strategy does not match cutover strategy",
        ),
        _check(
            f"{check_prefix}_market_matches",
            scaleup[f"{source_prefix}_market"],
            "==",
            scaleup["market"],
            bool(scaleup[f"{source_prefix}_market"] and scaleup[f"{source_prefix}_market"] == scaleup["market"]),
            f"{label} market does not match cutover market",
        ),
        _check(
            f"{check_prefix}_route_ready_pairs",
            scaleup[f"{source_prefix}_route_ready_pairs"],
            ">",
            0,
            int(scaleup[f"{source_prefix}_route_ready_pairs"]) > 0,
            f"{label} has no ready route pairs",
        ),
        _check(
            f"{check_prefix}_gap_pairs",
            scaleup[f"{source_prefix}_gap_pairs"],
            "<=",
            0,
            int(scaleup[f"{source_prefix}_gap_pairs"]) <= 0,
            f"{label} has route gaps",
        ),
        _check(
            f"{check_prefix}_ops_launch_controls_ready",
            scaleup[f"{source_prefix}_ops_launch_controls_ready"],
            "is",
            True,
            bool(scaleup[f"{source_prefix}_ops_launch_controls_ready"]),
            f"{label} did not preserve launch-grade ops controls",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"],
            ">",
            0,
            int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"]) > 0,
            f"{label} has no safe broker round-trip portfolio run",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"],
            "<=",
            0,
            int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"]) <= 0,
            f"{label} has broker round-trip portfolio breach runs",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"],
            ">",
            0,
            int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) > 0,
            f"{label} has no concentration-safe broker round-trip portfolio run",
        ),
        _check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"],
            "<=",
            0,
            int(scaleup[f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) <= 0,
            f"{label} has concentration breach runs",
        ),
    ]


def _shadow_broker_key(key_prefix: str, suffix: str) -> str:
    return f"{key_prefix}shadow_broker_{suffix}"


def _broker_vendor_market_data_batch_active(scaleup: dict[str, Any]) -> bool:
    vendor = scaleup["broker_dispatch_roundtrip_vendor_market_data_batch"]
    return bool(_to_bool(vendor["provided"]) or int(vendor["dataset_count"]) > 0)


def _broker_vendor_data_readiness_active(scaleup: dict[str, Any]) -> bool:
    readiness = scaleup["broker_vendor_data_readiness"]
    return bool(
        _to_bool(readiness["provided"])
        or _to_bool(readiness["ready"])
        or int(readiness["failed_checks"]) > 0
    )


def _broker_vendor_data_readiness_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    readiness = scaleup["broker_vendor_data_readiness"]
    prefix = "scaleup_broker_vendor_data_readiness"
    return [
        _check(
            f"{prefix}_provided",
            _to_bool(readiness["provided"]),
            "is",
            True,
            _to_bool(readiness["provided"]),
            "scale-up broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(readiness["ready"]),
            "is",
            True,
            _to_bool(readiness["ready"]),
            "scale-up broker-vendor readiness wrapper proof is not ready",
        ),
        _check(
            f"{prefix}_failed_checks",
            int(readiness["failed_checks"]),
            "<=",
            0,
            int(readiness["failed_checks"]) <= 0,
            "scale-up broker-vendor readiness wrapper proof has failed checks",
        ),
    ]


def _broker_vendor_market_data_batch_checks(scaleup: dict[str, Any]) -> list[dict[str, object]]:
    vendor = scaleup["broker_dispatch_roundtrip_vendor_market_data_batch"]
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    checks = [
        _check(
            f"{prefix}_provided",
            _to_bool(vendor["provided"]),
            "is",
            True,
            _to_bool(vendor["provided"]),
            "scale-up broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            f"{prefix}_ready",
            _to_bool(vendor["ready"]),
            "is",
            True,
            _to_bool(vendor["ready"]),
            "scale-up broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            f"{prefix}_adapter_matches",
            vendor["adapter"],
            "==",
            scaleup["adapter"],
            bool(vendor["adapter"] and scaleup["adapter"] and vendor["adapter"] == scaleup["adapter"]),
            "scale-up broker-readiness vendor market-data adapter does not match cutover adapter",
        ),
        _check(
            f"{prefix}_market_matches",
            vendor["market"],
            "==",
            scaleup["market"],
            bool(vendor["market"] and scaleup["market"] and vendor["market"] == scaleup["market"]),
            "scale-up broker-readiness vendor market-data market does not match cutover market",
        ),
        _check(
            f"{prefix}_manifest_run_type",
            vendor["manifest_run_type"],
            "==",
            "vendor_market_data_batch_pipeline",
            vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline",
            "scale-up broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            f"{prefix}_dataset_count",
            int(vendor["dataset_count"]),
            ">",
            0,
            int(vendor["dataset_count"]) > 0,
            "scale-up broker-readiness vendor market-data batch has no datasets",
        ),
        _check(
            f"{prefix}_failed_datasets",
            int(vendor["failed_datasets"]),
            "<=",
            0,
            int(vendor["failed_datasets"]) <= 0,
            "scale-up broker-readiness vendor market-data batch has failed datasets",
        ),
        _check(
            f"{prefix}_source_files",
            int(vendor["unique_source_files"]),
            ">",
            0,
            int(vendor["unique_source_files"]) > 0,
            "scale-up broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            f"{prefix}_header_fingerprints",
            int(vendor["unique_header_fingerprints"]),
            ">",
            0,
            int(vendor["unique_header_fingerprints"]) > 0,
            "scale-up broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            f"{prefix}_source_file_fingerprint_coverage",
            float(vendor["source_file_fingerprint_coverage"]),
            ">=",
            1.0,
            float(vendor["source_file_fingerprint_coverage"]) >= 1.0,
            "scale-up broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            f"{prefix}_min_mapping_coverage",
            float(vendor["min_mapping_coverage"]),
            ">=",
            1.0,
            float(vendor["min_mapping_coverage"]) >= 1.0,
            "scale-up broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            f"{prefix}_mapping_drafts",
            int(vendor["unique_mapping_drafts"]),
            ">",
            0,
            int(vendor["unique_mapping_drafts"]) > 0,
            "scale-up broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            f"{prefix}_mapping_sources",
            str(vendor["mapping_sources"]).strip(),
            "!=",
            "",
            bool(str(vendor["mapping_sources"]).strip()),
            "scale-up broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            f"{prefix}_comparison_accepted",
            _to_bool(vendor["comparison_accepted"]),
            "is",
            True,
            _to_bool(vendor["comparison_accepted"]),
            "scale-up broker-readiness vendor market-data comparison was not accepted",
        ),
        _check(
            f"{prefix}_comparison_failed_checks",
            int(vendor["comparison_failed_checks"]),
            "<=",
            0,
            int(vendor["comparison_failed_checks"]) <= 0,
            "scale-up broker-readiness vendor market-data comparison has failed checks",
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
            scaleup["broker_vendor_market_data_batch_lineage_match_required"]
        )
        lineage_matches = _to_bool(
            scaleup["broker_vendor_market_data_batch_lineage_matches"]
        )
        current_lineage_sha256 = _sha256_text(
            scaleup["vendor_market_data_batch_application_lineage_sha256"]
        )
        broker_lineage_sha256 = _sha256_text(
            scaleup["broker_vendor_market_data_batch_application_lineage_sha256"]
        )
        scaleup_carried_lineage_sha256 = _sha256_text(
            scaleup[
                "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        )
        cutover_carried_lineage_sha256 = _target_application_lineage_sha256(vendor)
        mapping_source_mode = _identity_key(vendor["mapping_source_mode"])
        checks.extend(
            [
                _check(
                    f"{prefix}_mapping_source_mode",
                    mapping_source_mode,
                    "==",
                    TARGET_APPLICATION_BATCH_MODE,
                    mapping_source_mode == TARGET_APPLICATION_BATCH_MODE,
                    "scale-up broker-readiness vendor target applications are missing strict source mode",
                ),
                _check(
                    f"{prefix}_mapping_application_count",
                    mapping_application_count,
                    "==",
                    dataset_count,
                    dataset_count > 0 and mapping_application_count == dataset_count,
                    "scale-up broker-readiness vendor target applications are not aligned one for one",
                ),
                _check(
                    f"{prefix}_unique_mapping_applications",
                    unique_mapping_applications,
                    "==",
                    dataset_count,
                    dataset_count > 0 and unique_mapping_applications == dataset_count,
                    "scale-up broker-readiness vendor target applications are not distinct per dataset",
                ),
                _check(
                    f"{prefix}_target_application_coverage",
                    target_application_coverage,
                    ">=",
                    1.0,
                    target_application_coverage >= 1.0,
                    "scale-up broker-readiness vendor target-application coverage is incomplete",
                ),
                _check(
                    f"{prefix}_application_lineage_datasets",
                    lineage_datasets,
                    "==",
                    dataset_count,
                    dataset_count > 0 and lineage_datasets == dataset_count,
                    "scale-up broker-readiness vendor datasets are missing target-application lineage",
                ),
                _check(
                    f"{prefix}_lineage_match_required",
                    lineage_match_required,
                    "is",
                    True,
                    lineage_match_required,
                    "target-application cutover requires the scale-up current/final lineage comparison",
                ),
                _check(
                    f"{prefix}_lineage_matches",
                    lineage_matches,
                    "is",
                    True,
                    lineage_match_required and lineage_matches,
                    "scale-up current and final target-application lineages do not match",
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
                    "scale-up current/final target-lineage digests are missing or disagree",
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
                    "scale-up carried target lineage does not match its broker-readiness proof",
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
                    "cutover carried target lineage does not match the scale-up broker-readiness proof",
                ),
            ]
        )
        if lineage_consistency_required:
            checks.append(
                _check(
                    f"{prefix}_application_lineage_consistent",
                    lineage_consistent,
                    "is",
                    True,
                    lineage_consistent,
                    "scale-up final dispatch/send/ack target lineage was not consistent",
                )
            )
            checks.extend(
                _broker_vendor_final_lineage_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_final_lineage_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_complete_final_lineage_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_extended_complete_final_lineage_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_checks(
                    scaleup,
                    cutover_lineage_sha256=cutover_carried_lineage_sha256,
                )
            )
    return checks


def _broker_vendor_final_lineage_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    prefix = f"scaleup_{source_prefix}"
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    final_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    final_current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    scaleup_broker_lineage_sha256 = _sha256_text(
        scaleup["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    scaleup_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{prefix}_final_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's final lineage comparison",
        ),
        _check(
            f"{prefix}_final_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not reconcile every final target-lineage view",
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
            "scale-up's final source lineage does not match final broker proof",
        ),
        _check(
            f"{prefix}_final_broker_lineage_sha256_matches",
            scaleup_broker_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and scaleup_broker_lineage_sha256
                and final_broker_lineage_sha256
                and scaleup_broker_lineage_sha256 == final_broker_lineage_sha256
            ),
            "scale-up's current/final broker digest does not match its final comparison",
        ),
        _check(
            f"{prefix}_final_application_lineage_sha256_matches",
            scaleup_lineage_sha256,
            "==",
            final_broker_lineage_sha256,
            bool(
                lineage_match_required
                and scaleup_lineage_sha256
                and final_broker_lineage_sha256
                and scaleup_lineage_sha256 == final_broker_lineage_sha256
            ),
            "scale-up's independently recomputed batch digest does not match final comparison",
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
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage does not "
                    "match final broker proof"
                ),
            )
        )
    scaleup_review_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    checks.extend(
        [
            _check(
                f"{prefix}_final_scaleup_review_carried_lineage_sha256_matches",
                scaleup_review_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_review_lineage_sha256
                    and final_broker_lineage_sha256
                    and scaleup_review_lineage_sha256 == final_broker_lineage_sha256
                ),
                "scale-up's carried review lineage does not match final broker proof",
            ),
            _check(
                f"{prefix}_cutover_review_carried_lineage_sha256_matches",
                cutover_lineage_sha256,
                "==",
                final_broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_lineage_sha256
                    and final_broker_lineage_sha256
                    and cutover_lineage_sha256 == final_broker_lineage_sha256
                ),
                "cutover's independently recomputed target lineage does not match final broker proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_final_lineage_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = SCALEUP_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_scaleup_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[
            f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_broker_application_lineage_sha256"
        ]
    )
    compatibility_scaleup_lineage_sha256 = _sha256_text(
        scaleup[
            f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_carried_application_lineage_sha256"
        ]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's complete final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every complete final target-lineage view",
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
            "scale-up final source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's final proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_carried_lineage_sha256_matches",
            compatibility_scaleup_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_lineage_sha256 == broker_lineage_sha256
            ),
            "cutover compatibility scale-up digest does not match scale-up's final proof",
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
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match final broker proof"
                ),
            )
        )
    scaleup_final_review_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_final_review_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
    )
    checks.extend(
        [
            _check(
                f"{check_prefix}_scaleup_final_review_carried_lineage_sha256_matches",
                scaleup_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's carried final-review lineage does not match final broker proof",
            ),
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
                "cutover's independently recomputed target lineage does not match scale-up's final proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_complete_final_lineage_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    compatibility_prefix = SCALEUP_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_scaleup_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_scaleup_final_review_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every extended complete-final target-lineage view",
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
            "scale-up complete-final source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_final_review_carried_lineage_sha256_matches",
            compatibility_scaleup_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility scale-up final review does not match scale-up's extended proof",
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match extended complete-final broker proof"
                ),
            )
        )
    scaleup_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_complete_final_review_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
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
                "scale-up's carried complete-final review lineage does not match final broker proof",
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
                "cutover's independently recomputed target lineage does not match scale-up's extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_extended_complete_final_lineage_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    compatibility_prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "scaleup_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_scaleup_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every latest extended complete-final target-lineage view",
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
            "scale-up extended complete-final source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_complete_final_review_carried_lineage_sha256_matches",
            compatibility_scaleup_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility scale-up complete-final review does not match scale-up's latest extended proof",
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    broker_readiness_extended_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup[
            f"{source_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    scaleup_extended_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_extended_complete_final_review_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
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
                "scale-up's broker-readiness extended review lineage does not match final broker proof",
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
                "scale-up's carried extended complete-final review lineage does not match final broker proof",
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
                "cutover's independently recomputed target lineage does not match scale-up's latest extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX
    compatibility_prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "scaleup_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_scaleup_extended_complete_final_review_lineage_sha256 = (
        _sha256_text(
            scaleup[f"{compatibility_prefix}_carried_application_lineage_sha256"]
        )
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every latest extended complete-final target-lineage view",
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
            "scale-up latest extended complete-final source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_scaleup_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility scale-up extended review does not match scale-up's latest extended proof",
        ),
    ]
    for field in SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
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
    ):
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    cutover_latest_extended_complete_final_review_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
    )
    checks.append(
        _check(
            f"{check_prefix}_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            cutover_latest_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and cutover_latest_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and cutover_latest_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover's independently recomputed target lineage does not match scale-up's latest extended proof",
        )
    )
    return checks


def _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX
    compatibility_prefix = SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "scaleup_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_latest_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's current latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every current latest extended complete-final target-lineage view",
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
            "scale-up current latest extended complete-final source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's current latest proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_latest_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_latest_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_latest_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility latest review does not match scale-up's current proof",
        ),
    ]
    for field in SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match current latest extended complete-final broker proof"
                ),
            )
        )
    for field in SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match current latest extended complete-final broker proof"
                ),
            )
        )
    scaleup_current_latest_lineage_sha256 = _sha256_text(
        scaleup[
            f"{source_prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
    )
    scaleup_current_latest_generic_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_current_latest_lineage_sha256 = _sha256_text(cutover_lineage_sha256)
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
                "scale-up's current latest review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_scaleup_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                scaleup_current_latest_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_current_latest_generic_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_current_latest_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's generic current latest review lineage does not match final broker proof",
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
                "cutover's independently recomputed target lineage does not match scale-up's current latest proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX
    )
    compatibility_prefix = (
        SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX
    )
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "scaleup_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_current_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target cutover requires scale-up's reconciled current latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every reconciled current latest extended complete-final target-lineage view",
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
            "scale-up reconciled current latest extended complete-final source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's reconciled current proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_current_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_current_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility current review does not match scale-up's reconciled current proof",
        ),
    ]
    for field in SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match reconciled current latest extended complete-final broker proof"
                ),
            )
        )
    for field in (
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match reconciled current latest extended complete-final broker proof"
                ),
            )
        )
    broker_readiness_reconciled_lineage_sha256 = _sha256_text(
        scaleup[
            f"{source_prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD}"
        ]
    )
    scaleup_reconciled_lineage_sha256 = _sha256_text(
        scaleup[
            f"{source_prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD}"
        ]
    )
    scaleup_reconciled_generic_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_reconciled_lineage_sha256 = _sha256_text(cutover_lineage_sha256)
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
                f"{check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                scaleup_reconciled_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_reconciled_generic_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_reconciled_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's generic reconciled current review lineage does not match final broker proof",
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
                "cutover's independently recomputed target lineage does not match scale-up's reconciled current proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX
    )
    compatibility_prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX
    )
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "scaleup_verified_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_reconciled_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "verified reconciled target cutover requires scale-up's verified reconciled lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every verified reconciled target-lineage view",
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
            "scale-up verified reconciled source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's verified reconciled proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_reconciled_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_reconciled_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_reconciled_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility reconciled review does not match scale-up's verified reconciled proof",
        ),
    ]
    for field in SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match verified reconciled broker proof"
                ),
            )
        )
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match verified reconciled broker proof"
                ),
            )
        )
    scaleup_verified_generic_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_verified_lineage_sha256 = _sha256_text(cutover_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                scaleup_verified_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_verified_generic_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_verified_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's generic verified reconciled review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                cutover_verified_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_verified_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_verified_lineage_sha256 == broker_lineage_sha256
                ),
                "cutover's independently recomputed target lineage does not match scale-up's verified reconciled proof",
            ),
        ]
    )
    return checks


def _broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_checks(
    scaleup: dict[str, Any],
    *,
    cutover_lineage_sha256: str,
) -> list[dict[str, object]]:
    source_prefix = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_FIELD_PREFIX
    )
    compatibility_prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX
    )
    check_prefix = (
        f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = _to_bool(
        scaleup[f"{source_prefix}_lineage_match_required"]
    )
    lineage_matches = _to_bool(scaleup[f"{source_prefix}_lineage_matches"])
    broker_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        scaleup[f"{compatibility_prefix}_broker_application_lineage_sha256"]
    )
    compatibility_cutover_verified_lineage_sha256 = _sha256_text(
        cutover_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "confirmed verified-reconciled target cutover requires scale-up's confirmed lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "scale-up did not match every confirmed verified-reconciled target-lineage view",
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
            "scale-up confirmed verified-reconciled source lineage does not match final broker proof",
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
            "cutover compatibility broker digest does not match scale-up's confirmed verified-reconciled proof",
        ),
        _check(
            f"{check_prefix}_compatibility_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_cutover_verified_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_cutover_verified_lineage_sha256
                and broker_lineage_sha256
                and compatibility_cutover_verified_lineage_sha256
                == broker_lineage_sha256
            ),
            "cutover compatibility verified review does not match scale-up's confirmed verified-reconciled proof",
        ),
    ]
    for field in SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS:
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
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match confirmed verified-reconciled broker proof"
                ),
            )
        )
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
        *SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_CONFIRMED_REVIEW_FIELDS,
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = _sha256_text(scaleup[f"{source_prefix}_{field}"])
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
                    f"scale-up's {stage.replace('_', '-')} target lineage "
                    "does not match confirmed verified-reconciled broker proof"
                ),
            )
        )
    scaleup_confirmed_generic_lineage_sha256 = _sha256_text(
        scaleup[f"{source_prefix}_carried_application_lineage_sha256"]
    )
    cutover_confirmed_lineage_sha256 = _sha256_text(cutover_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                scaleup_confirmed_generic_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_confirmed_generic_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_confirmed_generic_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's generic confirmed verified-reconciled review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                cutover_confirmed_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and cutover_confirmed_lineage_sha256
                    and broker_lineage_sha256
                    and cutover_confirmed_lineage_sha256
                    == broker_lineage_sha256
                ),
                "cutover's independently recomputed target lineage does not match scale-up's confirmed verified-reconciled proof",
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


def _scaleup_provenance_checks(
    provenance: dict[str, Any],
) -> list[dict[str, object]]:
    fields = scaleup_runtime_fields(provenance)
    if not _to_bool(
        fields.get("scaleup_manifest_required", False)
    ):
        return []
    checks = [
        _check(
            name,
            _to_bool(fields.get(name, False)),
            "is",
            True,
            _to_bool(fields.get(name, False)),
            reason,
        )
        for name, reason in (
            (
                "scaleup_manifest_provided",
                "scale-up manifest is missing",
            ),
            (
                "scaleup_manifest_current",
                "scale-up artifacts or recursive inputs have drifted",
            ),
            (
                "scaleup_contract_consistent",
                "scale-up config, summary, checks, plan, and manifest disagree",
            ),
            (
                "scaleup_non_authorizing",
                "scale-up proof contains a submission-authorizing claim",
            ),
            (
                "scaleup_source_ready",
                "scale-up plan is not ready",
            ),
            (
                "scaleup_provenance_gate_passed",
                "scale-up provenance gate did not pass",
            ),
        )
    ]
    if not _to_bool(
        fields.get("scaleup_proof_refresh_active", False)
    ):
        return checks
    checks.extend(
        [
            _check(
                name,
                _to_bool(fields.get(name, False)),
                "is",
                True,
                _to_bool(fields.get(name, False)),
                reason,
            )
            for name, reason in (
                (
                    "scaleup_proof_refresh_verified",
                    "scale-up proof-refresh evidence was not verified",
                ),
                (
                    "scaleup_proof_refresh_manifest_current",
                    "carried proof-refresh manifest is not current",
                ),
                (
                    "scaleup_proof_refresh_semantically_verified",
                    "carried proof-refresh evidence failed semantic verification",
                ),
                (
                    "scaleup_proof_refresh_source_manifest_current",
                    "current proof-refresh source manifest is not current",
                ),
                (
                    "scaleup_proof_refresh_source_semantically_verified",
                    "current proof-refresh source failed semantic verification",
                ),
                (
                    "scaleup_proof_refresh_source_provenance_gate_passed",
                    "current proof-refresh source provenance gate did not pass",
                ),
                (
                    "scaleup_proof_refresh_matches_current",
                    "scale-up proof-refresh lineage differs from its current source",
                ),
            )
        ]
    )
    return checks


def _broker_readiness_contract_identity_checks(
    provenance: dict[str, Any],
    runtime: dict[str, Any],
) -> list[dict[str, object]]:
    scaleup = scaleup_runtime_fields(provenance)
    scaleup_prefix = (
        "scaleup_broker_readiness_roundtrip_contract_identity_"
    )
    runtime_prefix = (
        "runtime_telemetry_broker_readiness_roundtrip_contract_identity_"
    )
    active = bool(
        _to_bool(scaleup.get(f"{scaleup_prefix}active", False))
        or _to_bool(runtime.get(f"{runtime_prefix}active", False))
        or _to_bool(
            runtime.get(
                (
                    "runtime_lineage_broker_readiness_"
                    "contract_identity_active"
                ),
                False,
            )
        )
    )
    if not active:
        return []

    scaleup_sha256 = _object_text(
        scaleup.get(f"{scaleup_prefix}sha256", "")
    ).strip()
    runtime_sha256 = _object_text(
        runtime.get(f"{runtime_prefix}sha256", "")
    ).strip()
    current_sha256 = _object_text(
        runtime.get(
            (
                "runtime_lineage_current_broker_readiness_"
                "contract_identity_sha256"
            ),
            "",
        )
    ).strip()
    checks = [
        _check(
            f"{scaleup_prefix}active",
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            "is",
            True,
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            (
                "scale-up did not retain the active terminal round-trip "
                "contract identity"
            ),
        )
    ]
    checks.extend(
        [
            _check(
                f"{scaleup_prefix}{suffix}",
                _to_bool(
                    scaleup.get(f"{scaleup_prefix}{suffix}", False)
                ),
                "is",
                True,
                _to_bool(
                    scaleup.get(f"{scaleup_prefix}{suffix}", False)
                ),
                reason,
            )
            for suffix, reason in (
                BROKER_READINESS_CONTRACT_IDENTITY_GATE_CHECKS
            )
        ]
    )
    checks.extend(
        [
            _check(
                f"{scaleup_prefix}sha256_present",
                scaleup_sha256,
                "present",
                True,
                bool(scaleup_sha256),
                "scale-up terminal round-trip contract identity digest is missing",
            ),
            _check(
                f"{scaleup_prefix}matches_current",
                _to_bool(
                    scaleup.get(
                        f"{scaleup_prefix}matches_current",
                        False,
                    )
                ),
                "is",
                True,
                _to_bool(
                    scaleup.get(
                        f"{scaleup_prefix}matches_current",
                        False,
                    )
                ),
                (
                    "scale-up terminal round-trip contract identity differs "
                    "from current broker readiness"
                ),
            ),
            _check(
                f"{runtime_prefix}active",
                _to_bool(runtime.get(f"{runtime_prefix}active", False)),
                "is",
                True,
                _to_bool(runtime.get(f"{runtime_prefix}active", False)),
                (
                    "runtime session did not carry the active terminal "
                    "round-trip contract identity"
                ),
            ),
            _check(
                f"{runtime_prefix}sha256_present",
                runtime_sha256,
                "present",
                True,
                bool(runtime_sha256),
                "runtime terminal round-trip contract identity digest is missing",
            ),
            _check(
                f"{runtime_prefix}sha256_matches_current",
                runtime_sha256,
                "==",
                current_sha256,
                bool(
                    runtime_sha256
                    and current_sha256
                    and runtime_sha256 == current_sha256
                ),
                (
                    "runtime terminal round-trip contract identity digest "
                    "differs from current broker readiness"
                ),
            ),
            _check(
                f"{runtime_prefix}lineage_verified",
                _to_bool(
                    runtime.get(
                        f"{runtime_prefix}lineage_verified",
                        False,
                    )
                ),
                "is",
                True,
                _to_bool(
                    runtime.get(
                        f"{runtime_prefix}lineage_verified",
                        False,
                    )
                ),
                (
                    "runtime terminal round-trip contract identity lineage "
                    "is not verified"
                ),
            ),
            _check(
                f"{runtime_prefix}matches_current",
                _to_bool(
                    runtime.get(
                        f"{runtime_prefix}matches_current",
                        False,
                    )
                ),
                "is",
                True,
                _to_bool(
                    runtime.get(
                        f"{runtime_prefix}matches_current",
                        False,
                    )
                ),
                (
                    "runtime terminal round-trip contract identity differs "
                    "from current scale-up"
                ),
            ),
            _check(
                (
                    "runtime_lineage_broker_readiness_"
                    "contract_identity_matches_current"
                ),
                _to_bool(
                    runtime.get(
                        (
                            "runtime_lineage_broker_readiness_"
                            "contract_identity_matches_current"
                        ),
                        False,
                    )
                ),
                "is",
                True,
                _to_bool(
                    runtime.get(
                        (
                            "runtime_lineage_broker_readiness_"
                            "contract_identity_matches_current"
                        ),
                        False,
                    )
                ),
                (
                    "runtime contract identity no longer matches the current "
                    "recursive broker-readiness source"
                ),
            ),
        ]
    )
    return checks


def _broker_readiness_route_contract_identity_checks(
    provenance: dict[str, Any],
    runtime: dict[str, Any],
) -> list[dict[str, object]]:
    scaleup = scaleup_runtime_fields(provenance)
    scaleup_prefix = (
        "scaleup_broker_readiness_route_contract_identity_"
    )
    runtime_prefix = (
        "runtime_telemetry_broker_readiness_route_contract_identity_"
    )
    runtime_current_field = (
        "runtime_telemetry_current_broker_readiness_"
        "route_contract_identity_sha256"
    )
    lineage_prefix = (
        "runtime_lineage_broker_readiness_route_contract_identity_"
    )
    lineage_current_field = (
        "runtime_lineage_current_broker_readiness_"
        "route_contract_identity_sha256"
    )
    scaleup_current_field = (
        "scaleup_broker_readiness_current_route_contract_identity_sha256"
    )
    active = bool(
        _to_bool(scaleup.get(f"{scaleup_prefix}active", False))
        or _to_bool(runtime.get(f"{runtime_prefix}active", False))
        or _to_bool(runtime.get(f"{lineage_prefix}active", False))
        or _object_text(
            scaleup.get(f"{scaleup_prefix}sha256", "")
        ).strip()
        or _object_text(scaleup.get(scaleup_current_field, "")).strip()
        or _object_text(runtime.get(f"{runtime_prefix}sha256", "")).strip()
        or _object_text(runtime.get(runtime_current_field, "")).strip()
        or _object_text(runtime.get(lineage_current_field, "")).strip()
    )
    if not active:
        return []

    scaleup_sha256 = _object_text(
        scaleup.get(f"{scaleup_prefix}sha256", "")
    ).strip()
    scaleup_current_sha256 = _object_text(
        scaleup.get(scaleup_current_field, "")
    ).strip()
    runtime_sha256 = _object_text(
        runtime.get(f"{runtime_prefix}sha256", "")
    ).strip()
    runtime_current_sha256 = _object_text(
        runtime.get(runtime_current_field, "")
    ).strip()
    lineage_current_sha256 = _object_text(
        runtime.get(lineage_current_field, "")
    ).strip()
    return [
        _check(
            f"{scaleup_prefix}active",
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            "is",
            True,
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            "scale-up did not retain the active broker route contract identity",
        ),
        _check(
            f"{scaleup_prefix}sha256_present",
            scaleup_sha256,
            "present",
            True,
            bool(scaleup_sha256),
            "scale-up broker route contract identity digest is missing",
        ),
        _check(
            f"{scaleup_prefix}sha256_matches_current",
            scaleup_sha256,
            "==",
            lineage_current_sha256,
            bool(
                scaleup_sha256
                and lineage_current_sha256
                and scaleup_sha256 == lineage_current_sha256
            ),
            (
                "scale-up broker route contract identity digest differs from "
                "the current recursive broker-readiness source"
            ),
        ),
        _check(
            (
                "scaleup_broker_readiness_current_route_contract_"
                "identity_sha256_matches_current"
            ),
            scaleup_current_sha256,
            "==",
            lineage_current_sha256,
            bool(
                scaleup_current_sha256
                and lineage_current_sha256
                and scaleup_current_sha256 == lineage_current_sha256
            ),
            (
                "scale-up claimed-current broker route contract identity "
                "differs from the current recursive broker-readiness source"
            ),
        ),
        _check(
            f"{scaleup_prefix}matches_current",
            _to_bool(
                scaleup.get(
                    f"{scaleup_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                scaleup.get(
                    f"{scaleup_prefix}matches_current",
                    False,
                )
            ),
            (
                "scale-up broker route contract identity current-source "
                "verdict failed"
            ),
        ),
        _check(
            f"{runtime_prefix}active",
            _to_bool(runtime.get(f"{runtime_prefix}active", False)),
            "is",
            True,
            _to_bool(runtime.get(f"{runtime_prefix}active", False)),
            "runtime session did not retain the active broker route identity",
        ),
        _check(
            f"{runtime_prefix}sha256_present",
            runtime_sha256,
            "present",
            True,
            bool(runtime_sha256),
            "runtime broker route contract identity digest is missing",
        ),
        _check(
            f"{runtime_prefix}sha256_matches_current",
            runtime_sha256,
            "==",
            lineage_current_sha256,
            bool(
                runtime_sha256
                and lineage_current_sha256
                and runtime_sha256 == lineage_current_sha256
            ),
            (
                "runtime broker route contract identity digest differs from "
                "the current recursive broker-readiness source"
            ),
        ),
        _check(
            (
                "runtime_telemetry_current_broker_readiness_route_contract_"
                "identity_sha256_matches_current"
            ),
            runtime_current_sha256,
            "==",
            lineage_current_sha256,
            bool(
                runtime_current_sha256
                and lineage_current_sha256
                and runtime_current_sha256 == lineage_current_sha256
            ),
            (
                "runtime telemetry claimed-current broker route identity "
                "differs from the current recursive broker-readiness source"
            ),
        ),
        _check(
            f"{runtime_prefix}matches_current",
            _to_bool(
                runtime.get(
                    f"{runtime_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                runtime.get(
                    f"{runtime_prefix}matches_current",
                    False,
                )
            ),
            "runtime broker route identity no longer matches current scale-up",
        ),
        _check(
            f"{lineage_prefix}active",
            _to_bool(runtime.get(f"{lineage_prefix}active", False)),
            "is",
            True,
            _to_bool(runtime.get(f"{lineage_prefix}active", False)),
            "runtime lineage did not retain the active broker route identity",
        ),
        _check(
            (
                "runtime_lineage_current_broker_readiness_route_contract_"
                "identity_sha256_present"
            ),
            lineage_current_sha256,
            "present",
            True,
            bool(lineage_current_sha256),
            (
                "runtime lineage did not recover the current broker route "
                "contract identity digest"
            ),
        ),
        _check(
            f"{lineage_prefix}matches_current",
            _to_bool(
                runtime.get(
                    f"{lineage_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                runtime.get(
                    f"{lineage_prefix}matches_current",
                    False,
                )
            ),
            (
                "runtime route contract identity no longer matches the "
                "current recursive broker-readiness source"
            ),
        ),
    ]


def _broker_readiness_route_enable_route_contract_identity_checks(
    provenance: dict[str, Any],
    runtime: dict[str, Any],
) -> list[dict[str, object]]:
    scaleup = scaleup_runtime_fields(provenance)
    scaleup_prefix = (
        "scaleup_broker_readiness_route_enable_"
        "route_contract_identity_"
    )
    runtime_prefix = (
        "runtime_telemetry_broker_readiness_route_enable_"
        "route_contract_identity_"
    )
    runtime_current_field = (
        "runtime_telemetry_current_broker_readiness_route_enable_"
        "route_contract_identity_sha256"
    )
    lineage_prefix = (
        "runtime_lineage_broker_readiness_route_enable_"
        "route_contract_identity_"
    )
    lineage_current_field = (
        "runtime_lineage_current_broker_readiness_route_enable_"
        "route_contract_identity_sha256"
    )
    scaleup_current_field = (
        "scaleup_broker_readiness_current_route_enable_"
        "route_contract_identity_sha256"
    )
    active = bool(
        _to_bool(scaleup.get(f"{scaleup_prefix}active", False))
        or _to_bool(runtime.get(f"{runtime_prefix}active", False))
        or _to_bool(runtime.get(f"{lineage_prefix}active", False))
        or _object_text(
            scaleup.get(f"{scaleup_prefix}sha256", "")
        ).strip()
        or _object_text(scaleup.get(scaleup_current_field, "")).strip()
        or _object_text(runtime.get(f"{runtime_prefix}sha256", "")).strip()
        or _object_text(runtime.get(runtime_current_field, "")).strip()
        or _object_text(runtime.get(lineage_current_field, "")).strip()
    )
    if not active:
        return []

    scaleup_sha256 = _object_text(
        scaleup.get(f"{scaleup_prefix}sha256", "")
    ).strip()
    scaleup_current_sha256 = _object_text(
        scaleup.get(scaleup_current_field, "")
    ).strip()
    runtime_sha256 = _object_text(
        runtime.get(f"{runtime_prefix}sha256", "")
    ).strip()
    runtime_current_sha256 = _object_text(
        runtime.get(runtime_current_field, "")
    ).strip()
    lineage_current_sha256 = _object_text(
        runtime.get(lineage_current_field, "")
    ).strip()
    return [
        _check(
            f"{scaleup_prefix}active",
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            "is",
            True,
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            (
                "scale-up did not retain the active broker route-enable "
                "route contract identity"
            ),
        ),
        _check(
            f"{scaleup_prefix}sha256_present",
            scaleup_sha256,
            "present",
            True,
            bool(scaleup_sha256),
            (
                "scale-up broker route-enable route contract identity "
                "digest is missing"
            ),
        ),
        _check(
            f"{scaleup_prefix}sha256_matches_current",
            scaleup_sha256,
            "==",
            lineage_current_sha256,
            bool(
                scaleup_sha256
                and lineage_current_sha256
                and scaleup_sha256 == lineage_current_sha256
            ),
            (
                "scale-up broker route-enable route contract identity "
                "digest differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            (
                "scaleup_broker_readiness_current_route_enable_"
                "route_contract_identity_sha256_matches_current"
            ),
            scaleup_current_sha256,
            "==",
            lineage_current_sha256,
            bool(
                scaleup_current_sha256
                and lineage_current_sha256
                and scaleup_current_sha256 == lineage_current_sha256
            ),
            (
                "scale-up claimed-current broker route-enable route "
                "contract identity differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            f"{scaleup_prefix}matches_current",
            _to_bool(
                scaleup.get(
                    f"{scaleup_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                scaleup.get(
                    f"{scaleup_prefix}matches_current",
                    False,
                )
            ),
            (
                "scale-up broker route-enable route contract identity "
                "current-source verdict failed"
            ),
        ),
        _check(
            f"{runtime_prefix}active",
            _to_bool(runtime.get(f"{runtime_prefix}active", False)),
            "is",
            True,
            _to_bool(runtime.get(f"{runtime_prefix}active", False)),
            (
                "runtime session did not retain the active broker "
                "route-enable route identity"
            ),
        ),
        _check(
            f"{runtime_prefix}sha256_present",
            runtime_sha256,
            "present",
            True,
            bool(runtime_sha256),
            (
                "runtime broker route-enable route contract identity "
                "digest is missing"
            ),
        ),
        _check(
            f"{runtime_prefix}sha256_matches_current",
            runtime_sha256,
            "==",
            lineage_current_sha256,
            bool(
                runtime_sha256
                and lineage_current_sha256
                and runtime_sha256 == lineage_current_sha256
            ),
            (
                "runtime broker route-enable route contract identity "
                "digest differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            (
                "runtime_telemetry_current_broker_readiness_route_enable_"
                "route_contract_identity_sha256_matches_current"
            ),
            runtime_current_sha256,
            "==",
            lineage_current_sha256,
            bool(
                runtime_current_sha256
                and lineage_current_sha256
                and runtime_current_sha256 == lineage_current_sha256
            ),
            (
                "runtime telemetry claimed-current broker route-enable "
                "route identity differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            f"{runtime_prefix}matches_current",
            _to_bool(
                runtime.get(
                    f"{runtime_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                runtime.get(
                    f"{runtime_prefix}matches_current",
                    False,
                )
            ),
            (
                "runtime broker route-enable route identity no longer "
                "matches current scale-up"
            ),
        ),
        _check(
            f"{lineage_prefix}active",
            _to_bool(runtime.get(f"{lineage_prefix}active", False)),
            "is",
            True,
            _to_bool(runtime.get(f"{lineage_prefix}active", False)),
            (
                "runtime lineage did not retain the active broker "
                "route-enable route identity"
            ),
        ),
        _check(
            (
                "runtime_lineage_current_broker_readiness_route_enable_"
                "route_contract_identity_sha256_present"
            ),
            lineage_current_sha256,
            "present",
            True,
            bool(lineage_current_sha256),
            (
                "runtime lineage did not recover the current broker "
                "route-enable route contract identity digest"
            ),
        ),
        _check(
            f"{lineage_prefix}matches_current",
            _to_bool(
                runtime.get(
                    f"{lineage_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                runtime.get(
                    f"{lineage_prefix}matches_current",
                    False,
                )
            ),
            (
                "runtime route-enable route contract identity no longer "
                "matches the current recursive broker-readiness source"
            ),
        ),
    ]


def _broker_readiness_route_enable_route_enable_route_contract_identity_checks(
    provenance: dict[str, Any],
    runtime: dict[str, Any],
) -> list[dict[str, object]]:
    scaleup = scaleup_runtime_fields(provenance)
    scaleup_prefix = (
        "scaleup_broker_readiness_route_enable_route_enable_"
        "route_contract_identity_"
    )
    runtime_prefix = (
        "runtime_telemetry_broker_readiness_route_enable_route_enable_"
        "route_contract_identity_"
    )
    runtime_current_field = (
        "runtime_telemetry_current_broker_readiness_"
        "route_enable_route_enable_route_contract_identity_sha256"
    )
    lineage_prefix = (
        "runtime_lineage_broker_readiness_route_enable_route_enable_"
        "route_contract_identity_"
    )
    lineage_current_field = (
        "runtime_lineage_current_broker_readiness_route_enable_route_enable_"
        "route_contract_identity_sha256"
    )
    scaleup_current_field = (
        "scaleup_broker_readiness_current_route_enable_route_enable_"
        "route_contract_identity_sha256"
    )
    active = bool(
        _to_bool(scaleup.get(f"{scaleup_prefix}active", False))
        or _to_bool(runtime.get(f"{runtime_prefix}active", False))
        or _to_bool(runtime.get(f"{lineage_prefix}active", False))
        or _object_text(
            scaleup.get(f"{scaleup_prefix}sha256", "")
        ).strip()
        or _object_text(scaleup.get(scaleup_current_field, "")).strip()
        or _object_text(runtime.get(f"{runtime_prefix}sha256", "")).strip()
        or _object_text(runtime.get(runtime_current_field, "")).strip()
        or _object_text(runtime.get(lineage_current_field, "")).strip()
    )
    if not active:
        return []

    scaleup_sha256 = _object_text(
        scaleup.get(f"{scaleup_prefix}sha256", "")
    ).strip()
    scaleup_current_sha256 = _object_text(
        scaleup.get(scaleup_current_field, "")
    ).strip()
    runtime_sha256 = _object_text(
        runtime.get(f"{runtime_prefix}sha256", "")
    ).strip()
    runtime_current_sha256 = _object_text(
        runtime.get(runtime_current_field, "")
    ).strip()
    lineage_current_sha256 = _object_text(
        runtime.get(lineage_current_field, "")
    ).strip()
    return [
        _check(
            f"{scaleup_prefix}active",
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            "is",
            True,
            _to_bool(scaleup.get(f"{scaleup_prefix}active", False)),
            (
                "scale-up did not retain the active broker route-enable "
                "route-enable route contract identity"
            ),
        ),
        _check(
            f"{scaleup_prefix}sha256_present",
            scaleup_sha256,
            "present",
            True,
            bool(scaleup_sha256),
            (
                "scale-up broker route-enable route-enable route contract "
                "identity digest is missing"
            ),
        ),
        _check(
            f"{scaleup_prefix}sha256_matches_current",
            scaleup_sha256,
            "==",
            lineage_current_sha256,
            bool(
                scaleup_sha256
                and lineage_current_sha256
                and scaleup_sha256 == lineage_current_sha256
            ),
            (
                "scale-up broker route-enable route-enable route contract "
                "identity digest differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            (
                "scaleup_broker_readiness_current_route_enable_route_enable_"
                "route_contract_identity_sha256_matches_current"
            ),
            scaleup_current_sha256,
            "==",
            lineage_current_sha256,
            bool(
                scaleup_current_sha256
                and lineage_current_sha256
                and scaleup_current_sha256 == lineage_current_sha256
            ),
            (
                "scale-up claimed-current broker route-enable route-enable "
                "route contract identity differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            f"{scaleup_prefix}matches_current",
            _to_bool(
                scaleup.get(
                    f"{scaleup_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                scaleup.get(
                    f"{scaleup_prefix}matches_current",
                    False,
                )
            ),
            (
                "scale-up broker route-enable route-enable route contract "
                "identity current-source verdict failed"
            ),
        ),
        _check(
            f"{runtime_prefix}active",
            _to_bool(runtime.get(f"{runtime_prefix}active", False)),
            "is",
            True,
            _to_bool(runtime.get(f"{runtime_prefix}active", False)),
            (
                "runtime session did not retain the active broker "
                "route-enable route-enable route identity"
            ),
        ),
        _check(
            f"{runtime_prefix}sha256_present",
            runtime_sha256,
            "present",
            True,
            bool(runtime_sha256),
            (
                "runtime broker route-enable route-enable route contract "
                "identity digest is missing"
            ),
        ),
        _check(
            f"{runtime_prefix}sha256_matches_current",
            runtime_sha256,
            "==",
            lineage_current_sha256,
            bool(
                runtime_sha256
                and lineage_current_sha256
                and runtime_sha256 == lineage_current_sha256
            ),
            (
                "runtime broker route-enable route-enable route contract "
                "identity digest differs from the current recursive "
                "broker-readiness source"
            ),
        ),
        _check(
            (
                "runtime_telemetry_current_broker_readiness_"
                "route_enable_route_enable_"
                "route_contract_identity_sha256_matches_current"
            ),
            runtime_current_sha256,
            "==",
            lineage_current_sha256,
            bool(
                runtime_current_sha256
                and lineage_current_sha256
                and runtime_current_sha256 == lineage_current_sha256
            ),
            (
                "runtime telemetry claimed-current broker route-enable "
                "route-enable route identity differs from the current "
                "recursive broker-readiness source"
            ),
        ),
        _check(
            f"{runtime_prefix}matches_current",
            _to_bool(
                runtime.get(
                    f"{runtime_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                runtime.get(
                    f"{runtime_prefix}matches_current",
                    False,
                )
            ),
            (
                "runtime broker route-enable route-enable route identity no "
                "longer matches current scale-up"
            ),
        ),
        _check(
            f"{lineage_prefix}active",
            _to_bool(runtime.get(f"{lineage_prefix}active", False)),
            "is",
            True,
            _to_bool(runtime.get(f"{lineage_prefix}active", False)),
            (
                "runtime lineage did not retain the active broker "
                "route-enable route-enable route identity"
            ),
        ),
        _check(
            (
                "runtime_lineage_current_broker_readiness_"
                "route_enable_route_enable_"
                "route_contract_identity_sha256_present"
            ),
            lineage_current_sha256,
            "present",
            True,
            bool(lineage_current_sha256),
            (
                "runtime lineage did not recover the current broker "
                "route-enable route-enable route contract identity digest"
            ),
        ),
        _check(
            f"{lineage_prefix}matches_current",
            _to_bool(
                runtime.get(
                    f"{lineage_prefix}matches_current",
                    False,
                )
            ),
            "is",
            True,
            _to_bool(
                runtime.get(
                    f"{lineage_prefix}matches_current",
                    False,
                )
            ),
            (
                "runtime route-enable route-enable route contract identity no "
                "longer matches the current recursive broker-readiness source"
            ),
        ),
    ]


def _authorization(
    scaleup: dict[str, Any],
    broker: dict[str, Any],
    runtime: dict[str, Any],
    operator: dict[str, Any],
    thresholds: CutoverGateThresholds,
    checks: pd.DataFrame,
    scaleup_provenance: dict[str, Any],
) -> pd.DataFrame:
    ready = bool(checks["passed"].astype(bool).all()) if not checks.empty else False
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": scaleup["target_mode"],
                "strategy": scaleup["strategy"],
                "market": scaleup["market"],
                "scenario_key": scaleup["scenario_key"],
                "adapter": scaleup["adapter"],
                "max_orders_per_session": scaleup["max_orders_per_session"],
                "max_notional_per_session": scaleup["max_notional_per_session"],
                "stop_loss": scaleup["stop_loss"],
                "proof_refresh_provided": scaleup["proof_refresh_provided"],
                "proof_refresh_ready": scaleup["proof_refresh_ready"],
                "proof_refresh_strategy": scaleup["proof_refresh_strategy"],
                "proof_refresh_market": scaleup["proof_refresh_market"],
                "proof_refresh_mixed_identity": scaleup["proof_refresh_mixed_identity"],
                "proof_source": scaleup["proof_source"],
                **scaleup_runtime_fields(scaleup_provenance),
                "scaleup_broker_schema_status": scaleup["broker_schema_status"],
                "scaleup_broker_schema_reviewed": scaleup["broker_schema_reviewed"],
                "scaleup_broker_schema_review_mode": scaleup["broker_schema_review_mode"],
                "scaleup_route_readiness_required": _route_readiness_required(thresholds),
                "scaleup_route_readiness_provided": scaleup["route_readiness_provided"],
                "scaleup_route_readiness_ready": scaleup["route_readiness_ready"],
                "scaleup_route_readiness_strategy": scaleup["route_readiness_strategy"],
                "scaleup_route_readiness_market": scaleup["route_readiness_market"],
                "scaleup_route_readiness_route_ready_pairs": scaleup["route_readiness_route_ready_pairs"],
                "scaleup_route_readiness_gap_pairs": scaleup["route_readiness_gap_pairs"],
                "scaleup_route_readiness_recommendation": scaleup["route_readiness_recommendation"],
                "scaleup_route_readiness_ops_launch_controls_present": scaleup[
                    "route_readiness_ops_launch_controls_present"
                ],
                "scaleup_route_readiness_ops_launch_controls_blocked_pairs": scaleup[
                    "route_readiness_ops_launch_controls_blocked_pairs"
                ],
                "scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": scaleup[
                    "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"
                ],
                "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": scaleup[
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"
                ],
                **_broker_route_readiness_authorization_fields(scaleup),
                **_resume_route_readiness_authorization_fields(
                    scaleup,
                    source_prefix="broker_resume_broker_route_readiness",
                    output_prefix="scaleup_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_authorization_fields(
                    scaleup,
                    source_prefix="broker_resume_incident_broker_route_readiness",
                    output_prefix="scaleup_broker_resume_incident_broker_route_readiness",
                ),
                "scaleup_shadow_broker_readiness_sessions": scaleup["shadow_broker_readiness_sessions"],
                "scaleup_shadow_broker_readiness_ready_sessions": scaleup[
                    "shadow_broker_readiness_ready_sessions"
                ],
                "scaleup_shadow_broker_vendor_data_readiness_sessions": scaleup[
                    "shadow_broker_vendor_data_readiness_sessions"
                ],
                "scaleup_shadow_broker_vendor_data_readiness_provided_sessions": scaleup[
                    "shadow_broker_vendor_data_readiness_provided_sessions"
                ],
                "scaleup_shadow_broker_vendor_data_readiness_ready_sessions": scaleup[
                    "shadow_broker_vendor_data_readiness_ready_sessions"
                ],
                "scaleup_shadow_broker_vendor_data_readiness_failed_checks": scaleup[
                    "shadow_broker_vendor_data_readiness_failed_checks"
                ],
                "scaleup_shadow_broker_adapter": scaleup["shadow_broker_adapter"],
                "scaleup_shadow_broker_adapter_count": scaleup["shadow_broker_adapter_count"],
                "scaleup_shadow_broker_route_readiness_sessions": scaleup[
                    "shadow_broker_route_readiness_sessions"
                ],
                "scaleup_shadow_broker_route_readiness_ready_sessions": scaleup[
                    "shadow_broker_route_readiness_ready_sessions"
                ],
                "scaleup_shadow_broker_route_readiness_strategy": scaleup[
                    "shadow_broker_route_readiness_strategy"
                ],
                "scaleup_shadow_broker_route_readiness_market": scaleup[
                    "shadow_broker_route_readiness_market"
                ],
                "scaleup_shadow_broker_route_readiness_gap_pairs": scaleup[
                    "shadow_broker_route_readiness_gap_pairs"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_sessions": scaleup[
                    "shadow_broker_dispatch_roundtrip_sessions"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_ready_sessions": scaleup[
                    "shadow_broker_dispatch_roundtrip_ready_sessions"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_strategy": scaleup[
                    "shadow_broker_dispatch_roundtrip_strategy"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_market": scaleup[
                    "shadow_broker_dispatch_roundtrip_market"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_scenario_count": scaleup[
                    "shadow_broker_dispatch_roundtrip_scenario_count"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks": scaleup[
                    "shadow_broker_dispatch_roundtrip_missing_request_acks"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders": scaleup[
                    "shadow_broker_dispatch_roundtrip_rejected_orders"
                ],
                "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks": scaleup[
                    "shadow_broker_dispatch_roundtrip_unmatched_acks"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_sessions": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_sessions"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_strategy": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_strategy"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_market": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_market"
                ],
                "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count": scaleup[
                    "shadow_broker_route_dispatch_roundtrip_scenario_count"
                ],
                **_broker_shadow_broker_authorization_fields(scaleup),
                **_broker_vendor_data_readiness_authorization_fields(scaleup),
                **_broker_vendor_market_data_batch_authorization_fields(scaleup),
                **_broker_vendor_final_lineage_authorization_fields(scaleup),
                **_broker_vendor_scaleup_final_lineage_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_complete_final_lineage_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_extended_complete_final_lineage_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_latest_extended_complete_final_lineage_43_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_authorization_fields(
                    scaleup
                ),
                **_broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_authorization_fields(
                    scaleup
                ),
                **_vendor_market_data_batch_authorization_fields(scaleup),
                "broker_readiness_ready": broker["ready"],
                "broker_schema_status": broker["schema_status"],
                "broker_schema_reviewed": broker["schema_reviewed"],
                "broker_schema_review_mode": broker["schema_review_mode"],
                "broker_recommendation": broker["recommendation"],
                "runtime_session_provided": runtime["provided"],
                "runtime_session_ready": runtime["ready"],
                "runtime_guard_action": runtime["guard_action"],
                "runtime_guard_halted": runtime["halted"],
                "runtime_strategy": runtime["strategy"],
                "runtime_market": runtime["market"],
                "runtime_target_mode": runtime["target_mode"],
                "runtime_strategy_portfolio_required": runtime["strategy_portfolio_required"],
                "runtime_strategy_portfolio_provided": runtime["strategy_portfolio_provided"],
                "runtime_strategy_portfolio_ready": runtime["strategy_portfolio_ready"],
                "runtime_strategy_portfolio_deployment_mode": runtime["strategy_portfolio_deployment_mode"],
                "runtime_strategy_portfolio_allocation_mode": runtime["strategy_portfolio_allocation_mode"],
                "runtime_strategy_portfolio_capital_currency": runtime["strategy_portfolio_capital_currency"],
                "runtime_strategy_portfolio_selected_profile": runtime["strategy_portfolio_selected_profile"],
                "runtime_strategy_portfolio_selected_strategy": runtime["strategy_portfolio_selected_strategy"],
                "runtime_strategy_portfolio_selected_market": runtime["strategy_portfolio_selected_market"],
                "runtime_strategy_portfolio_selected_eligible": runtime["strategy_portfolio_selected_eligible"],
                "runtime_strategy_portfolio_selected_allocation_weight": runtime[
                    "strategy_portfolio_selected_allocation_weight"
                ],
                "runtime_strategy_portfolio_selected_allocation_notional": runtime[
                    "strategy_portfolio_selected_allocation_notional"
                ],
                "runtime_strategy_portfolio_notional_cap_applied": runtime[
                    "strategy_portfolio_notional_cap_applied"
                ],
                "runtime_strategy_portfolio_min_strategy_count": runtime[
                    "strategy_portfolio_min_strategy_count"
                ],
                "runtime_strategy_portfolio_min_market_count": runtime[
                    "strategy_portfolio_min_market_count"
                ],
                "runtime_strategy_portfolio_max_strategy_weight": runtime[
                    "strategy_portfolio_max_strategy_weight"
                ],
                "runtime_strategy_portfolio_max_market_weight": runtime[
                    "strategy_portfolio_max_market_weight"
                ],
                "runtime_strategy_portfolio_allocated_strategy_count": runtime[
                    "strategy_portfolio_allocated_strategy_count"
                ],
                "runtime_strategy_portfolio_allocated_market_count": runtime[
                    "strategy_portfolio_allocated_market_count"
                ],
                "runtime_strategy_portfolio_top_strategy_by_weight": runtime[
                    "strategy_portfolio_top_strategy_by_weight"
                ],
                "runtime_strategy_portfolio_top_market_by_weight": runtime[
                    "strategy_portfolio_top_market_by_weight"
                ],
                "runtime_strategy_portfolio_max_strategy_allocation_weight": runtime[
                    "strategy_portfolio_max_strategy_allocation_weight"
                ],
                "runtime_strategy_portfolio_max_market_allocation_weight": runtime[
                    "strategy_portfolio_max_market_allocation_weight"
                ],
                **_runtime_strategy_portfolio_leadlag_output_fields(runtime),
                "runtime_pre_portfolio_max_notional_per_session": runtime[
                    "pre_portfolio_max_notional_per_session"
                ],
                **_runtime_lineage_output_fields(runtime),
                "authorizes_submission": False,
                "broker_resume_gate_provided": broker["resume_gate_provided"],
                "broker_resume_gate_ready": broker["resume_gate_ready"],
                "broker_resume_strategy": broker["resume_strategy"],
                "broker_resume_market": broker["resume_market"],
                "broker_resume_proof_refresh_ready": broker["resume_proof_refresh_ready"],
                "broker_resume_proof_refresh_strategy": broker["resume_proof_refresh_strategy"],
                "broker_resume_proof_refresh_market": broker["resume_proof_refresh_market"],
                "scaleup_dispatch_roundtrip_required": scaleup["dispatch_roundtrip_required"],
                "scaleup_dispatch_roundtrip_provided": scaleup["dispatch_roundtrip_provided"],
                "scaleup_dispatch_roundtrip_ready": scaleup["dispatch_roundtrip_ready"],
                "scaleup_dispatch_roundtrip_target_mode": scaleup["dispatch_roundtrip_target_mode"],
                "scaleup_dispatch_roundtrip_strategy": scaleup["dispatch_roundtrip_strategy"],
                "scaleup_dispatch_roundtrip_market": scaleup["dispatch_roundtrip_market"],
                "scaleup_dispatch_roundtrip_scenario_key": scaleup["dispatch_roundtrip_scenario_key"],
                "scaleup_dispatch_roundtrip_batch_id": scaleup["dispatch_roundtrip_batch_id"],
                "scaleup_dispatch_roundtrip_requests": scaleup["dispatch_roundtrip_requests"],
                "scaleup_dispatch_roundtrip_acked_orders": scaleup["dispatch_roundtrip_acked_orders"],
                "scaleup_dispatch_roundtrip_missing_request_acks": scaleup[
                    "dispatch_roundtrip_missing_request_acks"
                ],
                "scaleup_dispatch_roundtrip_rejected_orders": scaleup["dispatch_roundtrip_rejected_orders"],
                "scaleup_dispatch_roundtrip_unmatched_acks": scaleup["dispatch_roundtrip_unmatched_acks"],
                "scaleup_dispatch_roundtrip_failed_checks": scaleup["dispatch_roundtrip_failed_checks"],
                "scaleup_route_enable_dispatch_roundtrip_failed_checks": scaleup[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "scaleup_route_dispatch_roundtrip_required": _route_dispatch_roundtrip_active(
                    _dispatch_roundtrip_required(thresholds),
                    scaleup,
                ),
                "scaleup_route_dispatch_roundtrip_provided": scaleup["route_dispatch_roundtrip_provided"],
                "scaleup_route_dispatch_roundtrip_ready": scaleup["route_dispatch_roundtrip_ready"],
                "scaleup_route_dispatch_roundtrip_target_mode": scaleup["route_dispatch_roundtrip_target_mode"],
                "scaleup_route_dispatch_roundtrip_strategy": scaleup["route_dispatch_roundtrip_strategy"],
                "scaleup_route_dispatch_roundtrip_market": scaleup["route_dispatch_roundtrip_market"],
                "scaleup_route_dispatch_roundtrip_scenario_key": scaleup["route_dispatch_roundtrip_scenario_key"],
                "scaleup_route_dispatch_roundtrip_batch_id": scaleup["route_dispatch_roundtrip_batch_id"],
                "scaleup_route_dispatch_roundtrip_requests": scaleup["route_dispatch_roundtrip_requests"],
                "scaleup_route_dispatch_roundtrip_acked_orders": scaleup["route_dispatch_roundtrip_acked_orders"],
                "scaleup_route_dispatch_roundtrip_missing_request_acks": scaleup[
                    "route_dispatch_roundtrip_missing_request_acks"
                ],
                "scaleup_route_dispatch_roundtrip_rejected_orders": scaleup["route_dispatch_roundtrip_rejected_orders"],
                "scaleup_route_dispatch_roundtrip_unmatched_acks": scaleup["route_dispatch_roundtrip_unmatched_acks"],
                "broker_dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "broker_dispatch_roundtrip_provided": broker["dispatch_roundtrip_provided"],
                "broker_dispatch_roundtrip_ready": broker["dispatch_roundtrip_ready"],
                "broker_dispatch_roundtrip_target_mode": broker["dispatch_roundtrip_target_mode"],
                "broker_dispatch_roundtrip_strategy": broker["dispatch_roundtrip_strategy"],
                "broker_dispatch_roundtrip_market": broker["dispatch_roundtrip_market"],
                "broker_dispatch_roundtrip_scenario_key": broker["dispatch_roundtrip_scenario_key"],
                "broker_dispatch_roundtrip_batch_id": broker["dispatch_roundtrip_batch_id"],
                "broker_dispatch_roundtrip_requests": broker["dispatch_roundtrip_requests"],
                "broker_dispatch_roundtrip_acked_orders": broker["dispatch_roundtrip_acked_orders"],
                "broker_dispatch_roundtrip_missing_request_acks": broker[
                    "dispatch_roundtrip_missing_request_acks"
                ],
                "broker_dispatch_roundtrip_rejected_orders": broker["dispatch_roundtrip_rejected_orders"],
                "broker_dispatch_roundtrip_unmatched_acks": broker["dispatch_roundtrip_unmatched_acks"],
                "broker_dispatch_roundtrip_failed_checks": broker["dispatch_roundtrip_failed_checks"],
                "broker_route_enable_dispatch_roundtrip_failed_checks": broker[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ],
                "broker_route_dispatch_roundtrip_required": _route_dispatch_roundtrip_active(
                    _dispatch_roundtrip_required(thresholds),
                    broker,
                ),
                "broker_route_dispatch_roundtrip_provided": broker["route_dispatch_roundtrip_provided"],
                "broker_route_dispatch_roundtrip_ready": broker["route_dispatch_roundtrip_ready"],
                "broker_route_dispatch_roundtrip_target_mode": broker["route_dispatch_roundtrip_target_mode"],
                "broker_route_dispatch_roundtrip_strategy": broker["route_dispatch_roundtrip_strategy"],
                "broker_route_dispatch_roundtrip_market": broker["route_dispatch_roundtrip_market"],
                "broker_route_dispatch_roundtrip_scenario_key": broker["route_dispatch_roundtrip_scenario_key"],
                "broker_route_dispatch_roundtrip_batch_id": broker["route_dispatch_roundtrip_batch_id"],
                "broker_route_dispatch_roundtrip_requests": broker["route_dispatch_roundtrip_requests"],
                "broker_route_dispatch_roundtrip_acked_orders": broker["route_dispatch_roundtrip_acked_orders"],
                "broker_route_dispatch_roundtrip_missing_request_acks": broker[
                    "route_dispatch_roundtrip_missing_request_acks"
                ],
                "broker_route_dispatch_roundtrip_rejected_orders": broker["route_dispatch_roundtrip_rejected_orders"],
                "broker_route_dispatch_roundtrip_unmatched_acks": broker["route_dispatch_roundtrip_unmatched_acks"],
                "operator_review_provided": operator["provided"],
                "operator_approval_required": _operator_approval_required(thresholds),
                "operator_identity_ack_required": _operator_identity_ack_required(thresholds),
                "operator_limits_ack_required": _operator_limits_ack_required(thresholds),
                "operator_approved": operator["approved"],
                "operator_strategy": operator["strategy"],
                "operator_market": operator["market"],
                "operator_limits_ack": operator["limits_ack"],
            }
        ]
    )


def _broker_route_readiness_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    return {
        "scaleup_broker_route_readiness_required": scaleup["broker_route_readiness_required"],
        "scaleup_broker_route_readiness_provided": scaleup["broker_route_readiness_provided"],
        "scaleup_broker_route_readiness_ready": scaleup["broker_route_readiness_ready"],
        "scaleup_broker_route_readiness_strategy": scaleup["broker_route_readiness_strategy"],
        "scaleup_broker_route_readiness_market": scaleup["broker_route_readiness_market"],
        "scaleup_broker_route_readiness_route_ready_pairs": scaleup[
            "broker_route_readiness_route_ready_pairs"
        ],
        "scaleup_broker_route_readiness_gap_pairs": scaleup["broker_route_readiness_gap_pairs"],
        "scaleup_broker_route_readiness_recommendation": scaleup["broker_route_readiness_recommendation"],
        "scaleup_broker_route_readiness_ops_launch_controls_ready": scaleup[
            "broker_route_readiness_ops_launch_controls_ready"
        ],
        "scaleup_broker_route_readiness_ops_launch_control_failures": scaleup[
            "broker_route_readiness_ops_launch_control_failures"
        ],
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": scaleup[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"
        ],
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": scaleup[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"
        ],
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": scaleup[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
        ],
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": scaleup[
            "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
        ],
    }


def _resume_route_readiness_authorization_fields(
    scaleup: dict[str, Any],
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, Any]:
    return {
        f"{output_prefix}_required": scaleup[f"{source_prefix}_required"],
        f"{output_prefix}_provided": scaleup[f"{source_prefix}_provided"],
        f"{output_prefix}_ready": scaleup[f"{source_prefix}_ready"],
        f"{output_prefix}_strategy": scaleup[f"{source_prefix}_strategy"],
        f"{output_prefix}_market": scaleup[f"{source_prefix}_market"],
        f"{output_prefix}_route_ready_pairs": scaleup[f"{source_prefix}_route_ready_pairs"],
        f"{output_prefix}_gap_pairs": scaleup[f"{source_prefix}_gap_pairs"],
        f"{output_prefix}_recommendation": scaleup[f"{source_prefix}_recommendation"],
        f"{output_prefix}_ops_launch_controls_ready": scaleup[f"{source_prefix}_ops_launch_controls_ready"],
        f"{output_prefix}_ops_launch_control_failures": scaleup[
            f"{source_prefix}_ops_launch_control_failures"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_safe_runs": scaleup[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_breach_runs": scaleup[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": scaleup[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"
        ],
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": scaleup[
            f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"
        ],
    }


def _broker_shadow_broker_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    return {
        "scaleup_broker_shadow_broker_readiness_provided": scaleup[
            "broker_shadow_broker_readiness_provided"
        ],
        "scaleup_broker_shadow_broker_readiness_sessions": scaleup[
            "broker_shadow_broker_readiness_sessions"
        ],
        "scaleup_broker_shadow_broker_readiness_ready_sessions": scaleup[
            "broker_shadow_broker_readiness_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_vendor_data_readiness_sessions": scaleup[
            "broker_shadow_broker_vendor_data_readiness_sessions"
        ],
        "scaleup_broker_shadow_broker_vendor_data_readiness_provided_sessions": scaleup[
            "broker_shadow_broker_vendor_data_readiness_provided_sessions"
        ],
        "scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions": scaleup[
            "broker_shadow_broker_vendor_data_readiness_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks": scaleup[
            "broker_shadow_broker_vendor_data_readiness_failed_checks"
        ],
        "scaleup_broker_shadow_broker_adapter": scaleup["broker_shadow_broker_adapter"],
        "scaleup_broker_shadow_broker_adapter_count": scaleup["broker_shadow_broker_adapter_count"],
        "scaleup_broker_shadow_broker_route_readiness_sessions": scaleup[
            "broker_shadow_broker_route_readiness_sessions"
        ],
        "scaleup_broker_shadow_broker_route_readiness_ready_sessions": scaleup[
            "broker_shadow_broker_route_readiness_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_route_readiness_strategy": scaleup[
            "broker_shadow_broker_route_readiness_strategy"
        ],
        "scaleup_broker_shadow_broker_route_readiness_market": scaleup[
            "broker_shadow_broker_route_readiness_market"
        ],
        "scaleup_broker_shadow_broker_route_readiness_gap_pairs": scaleup[
            "broker_shadow_broker_route_readiness_gap_pairs"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_sessions": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_sessions"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_strategy": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_strategy"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_market": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_market"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_scenario_count"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders"
        ],
        "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": scaleup[
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_sessions"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_strategy"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_market": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_market"
        ],
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": scaleup[
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count"
        ],
    }


def _vendor_market_data_batch_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    vendor = scaleup["vendor_market_data_batch"]
    return {
        "scaleup_vendor_market_data_batch_provided": vendor["provided"],
        "scaleup_vendor_market_data_batch_ready": vendor["ready"],
        "scaleup_vendor_market_data_batch_adapter": vendor["adapter"],
        "scaleup_vendor_market_data_batch_kind": vendor["kind"],
        "scaleup_vendor_market_data_batch_manifest_run_type": vendor["manifest_run_type"],
        "scaleup_vendor_market_data_batch_market": vendor["market"],
        "scaleup_vendor_market_data_batch_dataset_count": vendor["dataset_count"],
        "scaleup_vendor_market_data_batch_ready_datasets": vendor["ready_datasets"],
        "scaleup_vendor_market_data_batch_failed_datasets": vendor["failed_datasets"],
        "scaleup_vendor_market_data_batch_ready_rate": vendor["ready_rate"],
        "scaleup_vendor_market_data_batch_unique_source_files": vendor["unique_source_files"],
        "scaleup_vendor_market_data_batch_unique_header_fingerprints": vendor["unique_header_fingerprints"],
        "scaleup_vendor_market_data_batch_source_file_fingerprint_coverage": vendor[
            "source_file_fingerprint_coverage"
        ],
        "scaleup_vendor_market_data_batch_min_mapping_coverage": vendor["min_mapping_coverage"],
        "scaleup_vendor_market_data_batch_unique_mapping_drafts": vendor["unique_mapping_drafts"],
        "scaleup_vendor_market_data_batch_mapping_sources": vendor["mapping_sources"],
        "scaleup_vendor_market_data_batch_comparison_accepted": vendor["comparison_accepted"],
        "scaleup_vendor_market_data_batch_comparison_failed_checks": vendor["comparison_failed_checks"],
        "scaleup_vendor_market_data_batch_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_market_data_batch_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    vendor = scaleup["broker_dispatch_roundtrip_vendor_market_data_batch"]
    field_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        "scaleup_broker_vendor_market_data_batch_lineage_match_required": scaleup[
            "broker_vendor_market_data_batch_lineage_match_required"
        ],
        "scaleup_broker_vendor_market_data_batch_lineage_matches": scaleup[
            "broker_vendor_market_data_batch_lineage_matches"
        ],
        "scaleup_vendor_market_data_batch_application_lineage_sha256": scaleup[
            "vendor_market_data_batch_application_lineage_sha256"
        ],
        "scaleup_broker_vendor_market_data_batch_application_lineage_sha256": scaleup[
            "broker_vendor_market_data_batch_application_lineage_sha256"
        ],
        f"{field_prefix}_application_lineage_sha256": scaleup[
            "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ],
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _target_application_lineage_sha256(vendor)
        ),
        f"{field_prefix}_comparison_accepted": vendor["comparison_accepted"],
        f"{field_prefix}_comparison_failed_checks": vendor["comparison_failed_checks"],
        f"{field_prefix}_datasets_json": json.dumps(vendor["datasets"], sort_keys=True),
    }


def _broker_vendor_final_lineage_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    source_prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    field_prefix = f"scaleup_{source_prefix}"
    fields: dict[str, Any] = {
        f"{field_prefix}_lineage_match_required": scaleup[
            f"{source_prefix}_lineage_match_required"
        ],
        f"{field_prefix}_lineage_matches": scaleup[
            f"{source_prefix}_lineage_matches"
        ],
        f"{field_prefix}_scaleup_review_carried_application_lineage_sha256": scaleup[
            f"{source_prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{field_prefix}_{field}"] = scaleup[f"{source_prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_final_lineage_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    source_prefix = SCALEUP_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{source_prefix}_lineage_match_required": scaleup[
            f"{source_prefix}_lineage_match_required"
        ],
        f"{source_prefix}_lineage_matches": scaleup[
            f"{source_prefix}_lineage_matches"
        ],
        f"{source_prefix}_scaleup_final_review_carried_application_lineage_sha256": scaleup[
            f"{source_prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in SCALEUP_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{source_prefix}_{field}"] = scaleup[f"{source_prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_complete_final_lineage_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in SCALEUP_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_extended_complete_final_lineage_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": scaleup[
            f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup[
            f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ],
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
        f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup[
            f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS,
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS,
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_authorization_fields(
    scaleup: dict[str, Any],
) -> dict[str, Any]:
    prefix = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": scaleup[
            f"{prefix}_lineage_match_required"
        ],
        f"{prefix}_lineage_matches": scaleup[f"{prefix}_lineage_matches"],
        f"{prefix}_carried_application_lineage_sha256": scaleup[
            f"{prefix}_carried_application_lineage_sha256"
        ],
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
        *SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_CONFIRMED_REVIEW_FIELDS,
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = scaleup[f"{prefix}_{field}"]
    return fields


def _broker_vendor_data_readiness_authorization_fields(scaleup: dict[str, Any]) -> dict[str, Any]:
    readiness = scaleup["broker_vendor_data_readiness"]
    return {
        "scaleup_broker_vendor_data_readiness_provided": readiness["provided"],
        "scaleup_broker_vendor_data_readiness_ready": readiness["ready"],
        "scaleup_broker_vendor_data_readiness_failed_checks": readiness["failed_checks"],
    }


def _summary(authorization: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(authorization["target_mode"]),
                "strategy": str(authorization["strategy"]),
                "market": str(authorization["market"]),
                "scenario_key": str(authorization["scenario_key"]),
                "adapter": str(authorization["adapter"]),
                "max_orders_per_session": int(authorization["max_orders_per_session"]),
                "max_notional_per_session": float(authorization["max_notional_per_session"]),
                "proof_refresh_ready": _to_bool(authorization["proof_refresh_ready"]),
                "proof_refresh_strategy": str(authorization["proof_refresh_strategy"]),
                "proof_refresh_market": str(authorization["proof_refresh_market"]),
                **_scaleup_provenance_summary_fields(
                    authorization
                ),
                "scaleup_broker_schema_status": str(authorization["scaleup_broker_schema_status"]),
                "scaleup_broker_schema_reviewed": _to_bool(authorization["scaleup_broker_schema_reviewed"]),
                "scaleup_broker_schema_review_mode": str(authorization["scaleup_broker_schema_review_mode"]),
                "scaleup_route_readiness_required": _to_bool(authorization["scaleup_route_readiness_required"]),
                "scaleup_route_readiness_provided": _to_bool(authorization["scaleup_route_readiness_provided"]),
                "scaleup_route_readiness_ready": _to_bool(authorization["scaleup_route_readiness_ready"]),
                "scaleup_route_readiness_strategy": str(authorization["scaleup_route_readiness_strategy"]),
                "scaleup_route_readiness_market": str(authorization["scaleup_route_readiness_market"]),
                "scaleup_route_readiness_route_ready_pairs": int(
                    authorization["scaleup_route_readiness_route_ready_pairs"]
                ),
                "scaleup_route_readiness_gap_pairs": int(authorization["scaleup_route_readiness_gap_pairs"]),
                "scaleup_route_readiness_ops_launch_controls_present": _to_bool(
                    authorization["scaleup_route_readiness_ops_launch_controls_present"]
                ),
                "scaleup_route_readiness_ops_launch_controls_blocked_pairs": int(
                    authorization["scaleup_route_readiness_ops_launch_controls_blocked_pairs"]
                ),
                "scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    authorization["scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
                ),
                "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    authorization[
                        "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"
                    ]
                ),
                **_broker_route_readiness_summary_fields(authorization),
                **_resume_route_readiness_summary_fields(
                    authorization,
                    prefix="scaleup_broker_resume_broker_route_readiness",
                ),
                **_resume_route_readiness_summary_fields(
                    authorization,
                    prefix="scaleup_broker_resume_incident_broker_route_readiness",
                ),
                "scaleup_shadow_broker_readiness_sessions": int(
                    authorization["scaleup_shadow_broker_readiness_sessions"]
                ),
                "scaleup_shadow_broker_readiness_ready_sessions": int(
                    authorization["scaleup_shadow_broker_readiness_ready_sessions"]
                ),
                "scaleup_shadow_broker_vendor_data_readiness_sessions": int(
                    authorization["scaleup_shadow_broker_vendor_data_readiness_sessions"]
                ),
                "scaleup_shadow_broker_vendor_data_readiness_provided_sessions": int(
                    authorization["scaleup_shadow_broker_vendor_data_readiness_provided_sessions"]
                ),
                "scaleup_shadow_broker_vendor_data_readiness_ready_sessions": int(
                    authorization["scaleup_shadow_broker_vendor_data_readiness_ready_sessions"]
                ),
                "scaleup_shadow_broker_vendor_data_readiness_failed_checks": int(
                    authorization["scaleup_shadow_broker_vendor_data_readiness_failed_checks"]
                ),
                "scaleup_shadow_broker_adapter": str(authorization["scaleup_shadow_broker_adapter"]),
                "scaleup_shadow_broker_adapter_count": int(
                    authorization["scaleup_shadow_broker_adapter_count"]
                ),
                "scaleup_shadow_broker_route_readiness_sessions": int(
                    authorization["scaleup_shadow_broker_route_readiness_sessions"]
                ),
                "scaleup_shadow_broker_route_readiness_ready_sessions": int(
                    authorization["scaleup_shadow_broker_route_readiness_ready_sessions"]
                ),
                "scaleup_shadow_broker_route_readiness_strategy": str(
                    authorization["scaleup_shadow_broker_route_readiness_strategy"]
                ),
                "scaleup_shadow_broker_route_readiness_market": str(
                    authorization["scaleup_shadow_broker_route_readiness_market"]
                ),
                "scaleup_shadow_broker_route_readiness_gap_pairs": int(
                    authorization["scaleup_shadow_broker_route_readiness_gap_pairs"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_sessions": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_sessions"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_ready_sessions"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_strategy": str(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_strategy"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_market": str(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_market"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_scenario_count": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_scenario_count"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_sessions": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_sessions"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_strategy": str(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_strategy"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_market": str(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_market"]
                ),
                "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
                **_broker_shadow_broker_summary_fields(authorization),
                **_broker_vendor_data_readiness_summary_fields(authorization),
                **_broker_vendor_market_data_batch_summary_fields(authorization),
                **_broker_vendor_final_lineage_summary_fields(authorization),
                **_broker_vendor_scaleup_final_lineage_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_complete_final_lineage_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_extended_complete_final_lineage_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_latest_extended_complete_final_lineage_43_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_summary_fields(
                    authorization
                ),
                **_broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_summary_fields(
                    authorization
                ),
                "scaleup_vendor_market_data_batch_provided": _to_bool(
                    authorization["scaleup_vendor_market_data_batch_provided"]
                ),
                "scaleup_vendor_market_data_batch_ready": _to_bool(
                    authorization["scaleup_vendor_market_data_batch_ready"]
                ),
                "scaleup_vendor_market_data_batch_adapter": str(
                    authorization["scaleup_vendor_market_data_batch_adapter"]
                ),
                "scaleup_vendor_market_data_batch_kind": str(
                    authorization["scaleup_vendor_market_data_batch_kind"]
                ),
                "scaleup_vendor_market_data_batch_market": str(
                    authorization["scaleup_vendor_market_data_batch_market"]
                ),
                "scaleup_vendor_market_data_batch_dataset_count": int(
                    authorization["scaleup_vendor_market_data_batch_dataset_count"]
                ),
                "scaleup_vendor_market_data_batch_ready_datasets": int(
                    authorization["scaleup_vendor_market_data_batch_ready_datasets"]
                ),
                "scaleup_vendor_market_data_batch_failed_datasets": int(
                    authorization["scaleup_vendor_market_data_batch_failed_datasets"]
                ),
                "scaleup_vendor_market_data_batch_ready_rate": _jsonable(
                    authorization["scaleup_vendor_market_data_batch_ready_rate"]
                ),
                "scaleup_vendor_market_data_batch_unique_source_files": int(
                    authorization["scaleup_vendor_market_data_batch_unique_source_files"]
                ),
                "scaleup_vendor_market_data_batch_unique_header_fingerprints": int(
                    authorization["scaleup_vendor_market_data_batch_unique_header_fingerprints"]
                ),
                "scaleup_vendor_market_data_batch_source_file_fingerprint_coverage": _jsonable(
                    authorization["scaleup_vendor_market_data_batch_source_file_fingerprint_coverage"]
                ),
                "scaleup_vendor_market_data_batch_min_mapping_coverage": _jsonable(
                    authorization["scaleup_vendor_market_data_batch_min_mapping_coverage"]
                ),
                "scaleup_vendor_market_data_batch_unique_mapping_drafts": int(
                    authorization["scaleup_vendor_market_data_batch_unique_mapping_drafts"]
                ),
                "scaleup_vendor_market_data_batch_mapping_sources": str(
                    authorization["scaleup_vendor_market_data_batch_mapping_sources"]
                ),
                "scaleup_vendor_market_data_batch_comparison_accepted": _to_bool(
                    authorization["scaleup_vendor_market_data_batch_comparison_accepted"]
                ),
                "scaleup_vendor_market_data_batch_comparison_failed_checks": int(
                    authorization["scaleup_vendor_market_data_batch_comparison_failed_checks"]
                ),
                "broker_readiness_ready": _to_bool(authorization["broker_readiness_ready"]),
                "broker_schema_status": str(authorization["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(authorization["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(authorization["broker_schema_review_mode"]),
                "runtime_session_ready": _to_bool(authorization["runtime_session_ready"]),
                "runtime_guard_action": str(authorization["runtime_guard_action"]),
                "runtime_guard_halted": _to_bool(authorization["runtime_guard_halted"]),
                "runtime_strategy_portfolio_required": _to_bool(
                    authorization["runtime_strategy_portfolio_required"]
                ),
                "runtime_strategy_portfolio_provided": _to_bool(
                    authorization["runtime_strategy_portfolio_provided"]
                ),
                "runtime_strategy_portfolio_ready": _to_bool(authorization["runtime_strategy_portfolio_ready"]),
                "runtime_strategy_portfolio_deployment_mode": str(
                    authorization["runtime_strategy_portfolio_deployment_mode"]
                ),
                "runtime_strategy_portfolio_allocation_mode": str(
                    authorization["runtime_strategy_portfolio_allocation_mode"]
                ),
                "runtime_strategy_portfolio_capital_currency": str(
                    authorization["runtime_strategy_portfolio_capital_currency"]
                ),
                "runtime_strategy_portfolio_selected_profile": str(
                    authorization["runtime_strategy_portfolio_selected_profile"]
                ),
                "runtime_strategy_portfolio_selected_strategy": str(
                    authorization["runtime_strategy_portfolio_selected_strategy"]
                ),
                "runtime_strategy_portfolio_selected_market": str(
                    authorization["runtime_strategy_portfolio_selected_market"]
                ),
                "runtime_strategy_portfolio_selected_eligible": _to_bool(
                    authorization["runtime_strategy_portfolio_selected_eligible"]
                ),
                "runtime_strategy_portfolio_selected_allocation_weight": float(
                    authorization["runtime_strategy_portfolio_selected_allocation_weight"]
                ),
                "runtime_strategy_portfolio_selected_allocation_notional": float(
                    authorization["runtime_strategy_portfolio_selected_allocation_notional"]
                ),
                "runtime_strategy_portfolio_notional_cap_applied": _to_bool(
                    authorization["runtime_strategy_portfolio_notional_cap_applied"]
                ),
                "runtime_strategy_portfolio_min_strategy_count": int(
                    authorization["runtime_strategy_portfolio_min_strategy_count"]
                ),
                "runtime_strategy_portfolio_min_market_count": int(
                    authorization["runtime_strategy_portfolio_min_market_count"]
                ),
                "runtime_strategy_portfolio_max_strategy_weight": float(
                    authorization["runtime_strategy_portfolio_max_strategy_weight"]
                ),
                "runtime_strategy_portfolio_max_market_weight": float(
                    authorization["runtime_strategy_portfolio_max_market_weight"]
                ),
                "runtime_strategy_portfolio_allocated_strategy_count": int(
                    authorization["runtime_strategy_portfolio_allocated_strategy_count"]
                ),
                "runtime_strategy_portfolio_allocated_market_count": int(
                    authorization["runtime_strategy_portfolio_allocated_market_count"]
                ),
                "runtime_strategy_portfolio_top_strategy_by_weight": str(
                    authorization["runtime_strategy_portfolio_top_strategy_by_weight"]
                ),
                "runtime_strategy_portfolio_top_market_by_weight": str(
                    authorization["runtime_strategy_portfolio_top_market_by_weight"]
                ),
                "runtime_strategy_portfolio_max_strategy_allocation_weight": float(
                    authorization["runtime_strategy_portfolio_max_strategy_allocation_weight"]
                ),
                "runtime_strategy_portfolio_max_market_allocation_weight": float(
                    authorization["runtime_strategy_portfolio_max_market_allocation_weight"]
                ),
                **_runtime_strategy_portfolio_leadlag_summary_fields(
                    authorization
                ),
                "runtime_pre_portfolio_max_notional_per_session": float(
                    authorization["runtime_pre_portfolio_max_notional_per_session"]
                ),
                **_runtime_lineage_summary_fields(authorization),
                "authorizes_submission": False,
                "broker_resume_gate_provided": _to_bool(authorization["broker_resume_gate_provided"]),
                "broker_resume_gate_ready": _to_bool(authorization["broker_resume_gate_ready"]),
                "broker_resume_proof_refresh_ready": _to_bool(
                    authorization["broker_resume_proof_refresh_ready"]
                ),
                "scaleup_dispatch_roundtrip_required": _to_bool(
                    authorization["scaleup_dispatch_roundtrip_required"]
                ),
                "scaleup_dispatch_roundtrip_provided": _to_bool(
                    authorization["scaleup_dispatch_roundtrip_provided"]
                ),
                "scaleup_dispatch_roundtrip_ready": _to_bool(
                    authorization["scaleup_dispatch_roundtrip_ready"]
                ),
                "broker_dispatch_roundtrip_required": _to_bool(
                    authorization["broker_dispatch_roundtrip_required"]
                ),
                "broker_dispatch_roundtrip_provided": _to_bool(
                    authorization["broker_dispatch_roundtrip_provided"]
                ),
                "broker_dispatch_roundtrip_ready": _to_bool(
                    authorization["broker_dispatch_roundtrip_ready"]
                ),
                "broker_dispatch_roundtrip_batch_id": str(
                    authorization["broker_dispatch_roundtrip_batch_id"]
                ),
                "broker_dispatch_roundtrip_requests": int(
                    authorization["broker_dispatch_roundtrip_requests"]
                ),
                "broker_dispatch_roundtrip_acked_orders": int(
                    authorization["broker_dispatch_roundtrip_acked_orders"]
                ),
                "broker_dispatch_roundtrip_missing_request_acks": int(
                    authorization["broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_dispatch_roundtrip_rejected_orders": int(
                    authorization["broker_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_dispatch_roundtrip_unmatched_acks": int(
                    authorization["broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "scaleup_dispatch_roundtrip_failed_checks": int(
                    authorization["scaleup_dispatch_roundtrip_failed_checks"]
                ),
                "broker_dispatch_roundtrip_failed_checks": int(
                    authorization["broker_dispatch_roundtrip_failed_checks"]
                ),
                "scaleup_route_enable_dispatch_roundtrip_failed_checks": int(
                    authorization["scaleup_route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "broker_route_enable_dispatch_roundtrip_failed_checks": int(
                    authorization["broker_route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "scaleup_route_dispatch_roundtrip_required": _to_bool(
                    authorization["scaleup_route_dispatch_roundtrip_required"]
                ),
                "scaleup_route_dispatch_roundtrip_provided": _to_bool(
                    authorization["scaleup_route_dispatch_roundtrip_provided"]
                ),
                "scaleup_route_dispatch_roundtrip_ready": _to_bool(
                    authorization["scaleup_route_dispatch_roundtrip_ready"]
                ),
                "scaleup_route_dispatch_roundtrip_batch_id": str(
                    authorization["scaleup_route_dispatch_roundtrip_batch_id"]
                ),
                "broker_route_dispatch_roundtrip_required": _to_bool(
                    authorization["broker_route_dispatch_roundtrip_required"]
                ),
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    authorization["broker_route_dispatch_roundtrip_provided"]
                ),
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    authorization["broker_route_dispatch_roundtrip_ready"]
                ),
                "broker_route_dispatch_roundtrip_batch_id": str(
                    authorization["broker_route_dispatch_roundtrip_batch_id"]
                ),
                "broker_route_dispatch_roundtrip_requests": int(
                    authorization["broker_route_dispatch_roundtrip_requests"]
                ),
                "broker_route_dispatch_roundtrip_acked_orders": int(
                    authorization["broker_route_dispatch_roundtrip_acked_orders"]
                ),
                "broker_route_dispatch_roundtrip_missing_request_acks": int(
                    authorization["broker_route_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_route_dispatch_roundtrip_rejected_orders": int(
                    authorization["broker_route_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_route_dispatch_roundtrip_unmatched_acks": int(
                    authorization["broker_route_dispatch_roundtrip_unmatched_acks"]
                ),
                "operator_review_provided": _to_bool(authorization["operator_review_provided"]),
                "operator_approval_required": _to_bool(authorization["operator_approval_required"]),
                "operator_identity_ack_required": _to_bool(
                    authorization["operator_identity_ack_required"]
                ),
                "operator_limits_ack_required": _to_bool(authorization["operator_limits_ack_required"]),
                "failed_checks": failed,
                "recommendation": "allow_live_dryrun_cutover" if ready else "keep_cutover_disabled",
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


def _action_queue(authorization: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in _failed_check_rows(checks).iterrows():
        check = _object_text(row.get("check")).strip()
        next_gate = _next_gate(check)
        rows.append(
            {
                "queue_status": "blocked",
                "source": "cutover_checks",
                "component": _component(check),
                "check": check,
                "actual": row.get("value"),
                "operator": _object_text(row.get("operator")).strip(),
                "expected": row.get("threshold"),
                "target_mode": _object_text(authorization.get("target_mode")).strip(),
                "strategy": _object_text(authorization.get("strategy")).strip(),
                "market": _object_text(authorization.get("market")).strip(),
                "scenario_key": _object_text(authorization.get("scenario_key")).strip(),
                "adapter": _object_text(authorization.get("adapter")).strip(),
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
    if (
        "broker_readiness_roundtrip_contract_identity" in check
        or "broker_readiness_route_contract_identity" in check
        or (
            "broker_readiness_route_enable_route_contract_identity"
            in check
        )
        or (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity"
            in check
        )
    ):
        return "broker_readiness"
    if check.startswith("runtime_lineage_broker_readiness_"):
        return "broker_readiness"
    if check.startswith("proof_refresh_") or check.startswith(
        "scaleup_proof_refresh_"
    ):
        return "proof_refresh"
    if "route_readiness" in check:
        return "route_readiness"
    if "dispatch_roundtrip" in check or check in {
        "dispatch_roundtrip_batch_matches",
        "route_dispatch_roundtrip_batch_matches",
    }:
        return "broker_dispatch_roundtrip"
    if "vendor_market_data_batch" in check:
        return "vendor_market_data"
    if "broker_vendor_data_readiness" in check:
        return "broker_vendor_data_readiness"
    if check.startswith("broker_resume_"):
        return "resume_gate"
    if check.startswith("broker_"):
        return "broker_readiness"
    if check.startswith("runtime_"):
        return "runtime_session"
    if check.startswith("operator_"):
        return "operator_review"
    if check.startswith("scaleup_"):
        return "scaleup_plan"
    return "cutover_gate"


def _next_gate(check: str) -> str:
    component = _component(check)
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
    if component == "resume_gate":
        return "review-resume-gate"
    if component == "broker_readiness":
        return "review-broker-readiness"
    if component == "runtime_session":
        return "monitor-runtime-session"
    if component == "scaleup_plan":
        return "plan-scaleup"
    return "review-cutover-gate"


def _action_recommendation(check: str) -> str:
    component = _component(check)
    if component == "proof_refresh":
        return "refresh_or_repair_scaleup_proof_freshness"
    if component == "route_readiness":
        return "rerun_route_readiness_before_cutover"
    if component == "broker_dispatch_roundtrip":
        return "rerun_broker_dispatch_roundtrip_before_cutover"
    if component == "vendor_market_data":
        return "refresh_vendor_market_data_batch_proof"
    if component == "broker_vendor_data_readiness":
        return "refresh_broker_vendor_data_readiness_wrapper"
    if component == "resume_gate":
        return "repair_resume_gate_authorization_for_cutover"
    if component == "broker_readiness":
        return "repair_broker_readiness_before_cutover"
    if component == "runtime_session":
        return "rerun_runtime_session_monitor_before_cutover"
    if component == "operator_review":
        return "capture_cutover_operator_review"
    if component == "scaleup_plan":
        return "repair_scaleup_plan_before_cutover"
    return "repair_cutover_gate_inputs"


def _broker_route_readiness_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    return {
        "scaleup_broker_route_readiness_required": _to_bool(
            authorization["scaleup_broker_route_readiness_required"]
        ),
        "scaleup_broker_route_readiness_provided": _to_bool(
            authorization["scaleup_broker_route_readiness_provided"]
        ),
        "scaleup_broker_route_readiness_ready": _to_bool(
            authorization["scaleup_broker_route_readiness_ready"]
        ),
        "scaleup_broker_route_readiness_strategy": str(
            authorization["scaleup_broker_route_readiness_strategy"]
        ),
        "scaleup_broker_route_readiness_market": str(authorization["scaleup_broker_route_readiness_market"]),
        "scaleup_broker_route_readiness_route_ready_pairs": int(
            authorization["scaleup_broker_route_readiness_route_ready_pairs"]
        ),
        "scaleup_broker_route_readiness_gap_pairs": int(
            authorization["scaleup_broker_route_readiness_gap_pairs"]
        ),
        "scaleup_broker_route_readiness_recommendation": str(
            authorization["scaleup_broker_route_readiness_recommendation"]
        ),
        "scaleup_broker_route_readiness_ops_launch_controls_ready": _to_bool(
            authorization["scaleup_broker_route_readiness_ops_launch_controls_ready"]
        ),
        "scaleup_broker_route_readiness_ops_launch_control_failures": str(
            authorization["scaleup_broker_route_readiness_ops_launch_control_failures"]
        ),
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            authorization["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            authorization["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            authorization[
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
            ]
        ),
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            authorization[
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
            ]
        ),
    }


def _resume_route_readiness_summary_fields(authorization: pd.Series, *, prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_required": _to_bool(authorization[f"{prefix}_required"]),
        f"{prefix}_provided": _to_bool(authorization[f"{prefix}_provided"]),
        f"{prefix}_ready": _to_bool(authorization[f"{prefix}_ready"]),
        f"{prefix}_strategy": str(authorization[f"{prefix}_strategy"]),
        f"{prefix}_market": str(authorization[f"{prefix}_market"]),
        f"{prefix}_route_ready_pairs": int(authorization[f"{prefix}_route_ready_pairs"]),
        f"{prefix}_gap_pairs": int(authorization[f"{prefix}_gap_pairs"]),
        f"{prefix}_recommendation": str(authorization[f"{prefix}_recommendation"]),
        f"{prefix}_ops_launch_controls_ready": _to_bool(authorization[f"{prefix}_ops_launch_controls_ready"]),
        f"{prefix}_ops_launch_control_failures": str(authorization[f"{prefix}_ops_launch_control_failures"]),
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _resume_route_readiness_config(authorization: pd.Series, *, prefix: str) -> dict[str, Any]:
    return {
        "required": _to_bool(authorization[f"{prefix}_required"]),
        "provided": _to_bool(authorization[f"{prefix}_provided"]),
        "ready": _to_bool(authorization[f"{prefix}_ready"]),
        "strategy": str(authorization[f"{prefix}_strategy"]),
        "market": str(authorization[f"{prefix}_market"]),
        "route_ready_pairs": int(authorization[f"{prefix}_route_ready_pairs"]),
        "gap_pairs": int(authorization[f"{prefix}_gap_pairs"]),
        "recommendation": str(authorization[f"{prefix}_recommendation"]),
        "ops_launch_controls_ready": _to_bool(authorization[f"{prefix}_ops_launch_controls_ready"]),
        "ops_launch_control_failures": str(authorization[f"{prefix}_ops_launch_control_failures"]),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            authorization[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _broker_shadow_broker_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    return {
        "scaleup_broker_shadow_broker_readiness_provided": _to_bool(
            authorization["scaleup_broker_shadow_broker_readiness_provided"]
        ),
        "scaleup_broker_shadow_broker_readiness_sessions": int(
            authorization["scaleup_broker_shadow_broker_readiness_sessions"]
        ),
        "scaleup_broker_shadow_broker_readiness_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_readiness_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_vendor_data_readiness_sessions": int(
            authorization["scaleup_broker_shadow_broker_vendor_data_readiness_sessions"]
        ),
        "scaleup_broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            authorization["scaleup_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
        ),
        "scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            authorization["scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks"]
        ),
        "scaleup_broker_shadow_broker_adapter": str(authorization["scaleup_broker_shadow_broker_adapter"]),
        "scaleup_broker_shadow_broker_adapter_count": int(
            authorization["scaleup_broker_shadow_broker_adapter_count"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_readiness_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_readiness_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_strategy": str(
            authorization["scaleup_broker_shadow_broker_route_readiness_strategy"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_market": str(
            authorization["scaleup_broker_shadow_broker_route_readiness_market"]
        ),
        "scaleup_broker_shadow_broker_route_readiness_gap_pairs": int(
            authorization["scaleup_broker_shadow_broker_route_readiness_gap_pairs"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_sessions": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_sessions"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_strategy": str(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_strategy"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_market": str(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_market"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
        ),
        "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy": str(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_market": str(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_market"]
        ),
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
        ),
    }


def _broker_vendor_market_data_batch_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    field_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": _to_bool(authorization[f"{field_prefix}_provided"]),
        f"{field_prefix}_ready": _to_bool(authorization[f"{field_prefix}_ready"]),
        f"{field_prefix}_adapter": str(authorization[f"{field_prefix}_adapter"]),
        f"{field_prefix}_kind": str(authorization[f"{field_prefix}_kind"]),
        f"{field_prefix}_manifest_run_type": str(authorization[f"{field_prefix}_manifest_run_type"]),
        f"{field_prefix}_market": str(authorization[f"{field_prefix}_market"]),
        f"{field_prefix}_dataset_count": int(authorization[f"{field_prefix}_dataset_count"]),
        f"{field_prefix}_ready_datasets": int(authorization[f"{field_prefix}_ready_datasets"]),
        f"{field_prefix}_failed_datasets": int(authorization[f"{field_prefix}_failed_datasets"]),
        f"{field_prefix}_ready_rate": _jsonable(authorization[f"{field_prefix}_ready_rate"]),
        f"{field_prefix}_unique_source_files": int(authorization[f"{field_prefix}_unique_source_files"]),
        f"{field_prefix}_unique_header_fingerprints": int(
            authorization[f"{field_prefix}_unique_header_fingerprints"]
        ),
        f"{field_prefix}_source_file_fingerprint_coverage": _jsonable(
            authorization[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        f"{field_prefix}_min_mapping_coverage": _jsonable(
            authorization[f"{field_prefix}_min_mapping_coverage"]
        ),
        f"{field_prefix}_unique_mapping_drafts": int(authorization[f"{field_prefix}_unique_mapping_drafts"]),
        f"{field_prefix}_mapping_sources": str(authorization[f"{field_prefix}_mapping_sources"]),
        f"{field_prefix}_mapping_source_mode": str(
            authorization[f"{field_prefix}_mapping_source_mode"]
        ),
        f"{field_prefix}_mapping_application_count": int(
            authorization[f"{field_prefix}_mapping_application_count"]
        ),
        f"{field_prefix}_unique_mapping_applications": int(
            authorization[f"{field_prefix}_unique_mapping_applications"]
        ),
        f"{field_prefix}_target_application_coverage": _jsonable(
            authorization[f"{field_prefix}_target_application_coverage"]
        ),
        f"{field_prefix}_application_lineage_consistency_required": _to_bool(
            authorization[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        f"{field_prefix}_application_lineage_consistent": _to_bool(
            authorization[f"{field_prefix}_application_lineage_consistent"]
        ),
        "scaleup_broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            authorization[
                "scaleup_broker_vendor_market_data_batch_lineage_match_required"
            ]
        ),
        "scaleup_broker_vendor_market_data_batch_lineage_matches": _to_bool(
            authorization["scaleup_broker_vendor_market_data_batch_lineage_matches"]
        ),
        "scaleup_vendor_market_data_batch_application_lineage_sha256": str(
            authorization[
                "scaleup_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
        "scaleup_broker_vendor_market_data_batch_application_lineage_sha256": str(
            authorization[
                "scaleup_broker_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
        f"{field_prefix}_application_lineage_sha256": str(
            authorization[f"{field_prefix}_application_lineage_sha256"]
        ),
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
        f"{field_prefix}_comparison_accepted": _to_bool(authorization[f"{field_prefix}_comparison_accepted"]),
        f"{field_prefix}_comparison_failed_checks": int(
            authorization[f"{field_prefix}_comparison_failed_checks"]
        ),
        f"{field_prefix}_datasets_json": str(authorization[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_final_lineage_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    field_prefix = f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}"
    fields: dict[str, Any] = {
        f"{field_prefix}_lineage_match_required": _to_bool(
            authorization[f"{field_prefix}_lineage_match_required"]
        ),
        f"{field_prefix}_lineage_matches": _to_bool(
            authorization[f"{field_prefix}_lineage_matches"]
        ),
        f"{field_prefix}_scaleup_review_carried_application_lineage_sha256": str(
            authorization[
                f"{field_prefix}_scaleup_review_carried_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{field_prefix}_{field}"] = str(
            authorization[f"{field_prefix}_{field}"]
        )
    return fields


def _broker_vendor_scaleup_final_lineage_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_scaleup_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_final_review_carried_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_complete_final_lineage_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_extended_complete_final_lineage_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        f"{prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS,
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD}": str(
            authorization[
                f"{prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD}"
            ]
        ),
        f"{prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD}": str(
            authorization[
                f"{prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD}"
            ]
        ),
        f"{prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_FIELD_PREFIX
    )
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            authorization[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            authorization[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
        *SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_CONFIRMED_REVIEW_FIELDS,
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(authorization[f"{prefix}_{field}"])
    return fields


def _broker_vendor_data_readiness_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    return {
        "scaleup_broker_vendor_data_readiness_provided": _to_bool(
            authorization["scaleup_broker_vendor_data_readiness_provided"]
        ),
        "scaleup_broker_vendor_data_readiness_ready": _to_bool(
            authorization["scaleup_broker_vendor_data_readiness_ready"]
        ),
        "scaleup_broker_vendor_data_readiness_failed_checks": int(
            authorization["scaleup_broker_vendor_data_readiness_failed_checks"]
        ),
    }


def _config(
    authorization: pd.Series,
    thresholds: CutoverGateThresholds,
    checks: pd.DataFrame,
    action_queue: pd.DataFrame,
) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    statuses = action_queue["queue_status"].astype(str) if not action_queue.empty else pd.Series(dtype=str)
    next_gate = _first_action_value(action_queue, "next_gate")
    return {
        "schema_version": 1,
        "authorizes_submission": False,
        "ready": _to_bool(authorization["ready"]),
        "failed_check_count": len(failed_check_records),
        "target_mode": str(authorization["target_mode"]),
        "strategy": str(authorization["strategy"]),
        "market": str(authorization["market"]),
        "scenario_key": str(authorization["scenario_key"]),
        "adapter": str(authorization["adapter"]),
        "limits": {
            "max_orders_per_session": int(authorization["max_orders_per_session"]),
            "max_notional_per_session": float(authorization["max_notional_per_session"]),
            "stop_loss": _jsonable(authorization["stop_loss"]),
        },
        "proof_freshness": {
            "provided": _to_bool(authorization["proof_refresh_provided"]),
            "ready": _to_bool(authorization["proof_refresh_ready"]),
            "strategy": str(authorization["proof_refresh_strategy"]),
            "market": str(authorization["proof_refresh_market"]),
            "mixed_identity": _to_bool(authorization["proof_refresh_mixed_identity"]),
            "proof_source": str(authorization["proof_source"]),
        },
        "scaleup_provenance": _scaleup_provenance_config(
            authorization
        ),
        "scaleup_route_readiness": {
            "required": _to_bool(authorization["scaleup_route_readiness_required"]),
            "provided": _to_bool(authorization["scaleup_route_readiness_provided"]),
            "ready": _to_bool(authorization["scaleup_route_readiness_ready"]),
            "strategy": str(authorization["scaleup_route_readiness_strategy"]),
            "market": str(authorization["scaleup_route_readiness_market"]),
            "route_ready_pairs": int(authorization["scaleup_route_readiness_route_ready_pairs"]),
            "gap_pairs": int(authorization["scaleup_route_readiness_gap_pairs"]),
            "ops_launch_controls_present": _to_bool(
                authorization["scaleup_route_readiness_ops_launch_controls_present"]
            ),
            "ops_launch_controls_blocked_pairs": int(
                authorization["scaleup_route_readiness_ops_launch_controls_blocked_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_breach_pairs": int(
                authorization["scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                authorization[
                    "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"
                ]
            ),
            "recommendation": str(authorization["scaleup_route_readiness_recommendation"]),
        },
        "scaleup_broker_route_readiness": _broker_route_readiness_config(authorization),
        "scaleup_broker_resume_gate": {
            "broker_route_readiness": _resume_route_readiness_config(
                authorization,
                prefix="scaleup_broker_resume_broker_route_readiness",
            ),
            "incident_broker_route_readiness": _resume_route_readiness_config(
                authorization,
                prefix="scaleup_broker_resume_incident_broker_route_readiness",
            ),
        },
        "scaleup_shadow_broker_readiness": {
            "provided": int(authorization["scaleup_shadow_broker_readiness_sessions"]) > 0,
            "sessions": int(authorization["scaleup_shadow_broker_readiness_sessions"]),
            "ready_sessions": int(authorization["scaleup_shadow_broker_readiness_ready_sessions"]),
            "adapter": str(authorization["scaleup_shadow_broker_adapter"]),
            "adapter_count": int(authorization["scaleup_shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(authorization["scaleup_shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(
                    authorization["scaleup_shadow_broker_vendor_data_readiness_provided_sessions"]
                ),
                "ready_sessions": int(
                    authorization["scaleup_shadow_broker_vendor_data_readiness_ready_sessions"]
                ),
                "failed_checks": int(authorization["scaleup_shadow_broker_vendor_data_readiness_failed_checks"]),
            },
            "route_readiness": {
                "sessions": int(authorization["scaleup_shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(authorization["scaleup_shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(authorization["scaleup_shadow_broker_route_readiness_strategy"]),
                "market": str(authorization["scaleup_shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(authorization["scaleup_shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(authorization["scaleup_shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(authorization["scaleup_shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(authorization["scaleup_shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(authorization["scaleup_shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(authorization["scaleup_shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "max_unmatched_acks": int(
                    authorization["scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(authorization["scaleup_shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "strategy": str(authorization["scaleup_shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(authorization["scaleup_shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(
                    authorization["scaleup_shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
            },
        },
        "scaleup_broker_shadow_broker_readiness": _broker_shadow_broker_config(authorization),
        "scaleup_broker_vendor_data_readiness": _broker_vendor_data_readiness_config(authorization),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch": (
            _broker_vendor_market_data_batch_config(authorization)
        ),
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": {
            "required": _to_bool(
                authorization[
                    "scaleup_broker_vendor_market_data_batch_lineage_match_required"
                ]
            ),
            "matches": _to_bool(
                authorization[
                    "scaleup_broker_vendor_market_data_batch_lineage_matches"
                ]
            ),
            "current_application_lineage_sha256": str(
                authorization[
                    "scaleup_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "broker_application_lineage_sha256": str(
                authorization[
                    "scaleup_broker_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "scaleup_carried_application_lineage_sha256": str(
                authorization[
                    "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
            "cutover_carried_application_lineage_sha256": str(
                authorization[
                    "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                ]
            ),
        },
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
            _broker_vendor_cutover_final_lineage_config(authorization)
        ),
        CUTOVER_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_cutover_complete_final_lineage_config(authorization)
        ),
        CUTOVER_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_cutover_complete_final_lineage_28_config(
                authorization
            )
        ),
        CUTOVER_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
            _broker_vendor_cutover_extended_complete_final_lineage_config(
                authorization
            )
        ),
        CUTOVER_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_44_COMPARISON_KEY: (
            _broker_vendor_cutover_latest_extended_complete_final_lineage_44_config(
                authorization
            )
        ),
        CUTOVER_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_52_COMPARISON_KEY: (
            _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_config(
                authorization
            )
        ),
        CUTOVER_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_60_COMPARISON_KEY: (
            _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_config(
                authorization
            )
        ),
        CUTOVER_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_68_COMPARISON_KEY: (
            _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_config(
                authorization
            )
        ),
        CUTOVER_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_76_COMPARISON_KEY: (
            _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_config(
                authorization
            )
        ),
        "scaleup_vendor_market_data_batch": _vendor_market_data_batch_config(authorization),
        "scaleup_dispatch_roundtrip": {
            "required": _to_bool(authorization["scaleup_dispatch_roundtrip_required"]),
            "provided": _to_bool(authorization["scaleup_dispatch_roundtrip_provided"]),
            "ready": _to_bool(authorization["scaleup_dispatch_roundtrip_ready"]),
            "target_mode": str(authorization["scaleup_dispatch_roundtrip_target_mode"]),
            "strategy": str(authorization["scaleup_dispatch_roundtrip_strategy"]),
            "market": str(authorization["scaleup_dispatch_roundtrip_market"]),
            "scenario_key": str(authorization["scaleup_dispatch_roundtrip_scenario_key"]),
            "dispatch_batch_id": str(authorization["scaleup_dispatch_roundtrip_batch_id"]),
            "requests": int(authorization["scaleup_dispatch_roundtrip_requests"]),
            "acked_orders": int(authorization["scaleup_dispatch_roundtrip_acked_orders"]),
            "missing_request_acks": int(authorization["scaleup_dispatch_roundtrip_missing_request_acks"]),
            "rejected_orders": int(authorization["scaleup_dispatch_roundtrip_rejected_orders"]),
            "unmatched_acks": int(authorization["scaleup_dispatch_roundtrip_unmatched_acks"]),
            "failed_checks": int(authorization["scaleup_dispatch_roundtrip_failed_checks"]),
            "route_enable_dispatch_roundtrip": {
                "failed_checks": int(authorization["scaleup_route_enable_dispatch_roundtrip_failed_checks"]),
            },
            "route_proof": {
                "required": _to_bool(authorization["scaleup_route_dispatch_roundtrip_required"]),
                "provided": _to_bool(authorization["scaleup_route_dispatch_roundtrip_provided"]),
                "ready": _to_bool(authorization["scaleup_route_dispatch_roundtrip_ready"]),
                "target_mode": str(authorization["scaleup_route_dispatch_roundtrip_target_mode"]),
                "strategy": str(authorization["scaleup_route_dispatch_roundtrip_strategy"]),
                "market": str(authorization["scaleup_route_dispatch_roundtrip_market"]),
                "scenario_key": str(authorization["scaleup_route_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(authorization["scaleup_route_dispatch_roundtrip_batch_id"]),
                "requests": int(authorization["scaleup_route_dispatch_roundtrip_requests"]),
                "acked_orders": int(authorization["scaleup_route_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(authorization["scaleup_route_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(authorization["scaleup_route_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(authorization["scaleup_route_dispatch_roundtrip_unmatched_acks"]),
            },
        },
        "broker_readiness": {
            "ready": _to_bool(authorization["broker_readiness_ready"]),
            "adapter_schema_status": str(authorization["broker_schema_status"]),
            "schema_reviewed": _to_bool(authorization["broker_schema_reviewed"]),
            "schema_review_mode": str(authorization["broker_schema_review_mode"]),
            "recommendation": str(authorization["broker_recommendation"]),
            "resume_gate": {
                "provided": _to_bool(authorization["broker_resume_gate_provided"]),
                "ready": _to_bool(authorization["broker_resume_gate_ready"]),
                "strategy": str(authorization["broker_resume_strategy"]),
                "market": str(authorization["broker_resume_market"]),
                "proof_refresh_ready": _to_bool(
                    authorization["broker_resume_proof_refresh_ready"]
                ),
                "proof_refresh_strategy": str(authorization["broker_resume_proof_refresh_strategy"]),
                "proof_refresh_market": str(authorization["broker_resume_proof_refresh_market"]),
            },
            "dispatch_roundtrip": {
                "required": _to_bool(authorization["broker_dispatch_roundtrip_required"]),
                "provided": _to_bool(authorization["broker_dispatch_roundtrip_provided"]),
                "ready": _to_bool(authorization["broker_dispatch_roundtrip_ready"]),
                "target_mode": str(authorization["broker_dispatch_roundtrip_target_mode"]),
                "strategy": str(authorization["broker_dispatch_roundtrip_strategy"]),
                "market": str(authorization["broker_dispatch_roundtrip_market"]),
                "scenario_key": str(authorization["broker_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(authorization["broker_dispatch_roundtrip_batch_id"]),
                "requests": int(authorization["broker_dispatch_roundtrip_requests"]),
                "acked_orders": int(authorization["broker_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(authorization["broker_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(authorization["broker_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(authorization["broker_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": int(authorization["broker_dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip": {
                    "failed_checks": int(authorization["broker_route_enable_dispatch_roundtrip_failed_checks"]),
                },
                "route_proof": {
                    "required": _to_bool(authorization["broker_route_dispatch_roundtrip_required"]),
                    "provided": _to_bool(authorization["broker_route_dispatch_roundtrip_provided"]),
                    "ready": _to_bool(authorization["broker_route_dispatch_roundtrip_ready"]),
                    "target_mode": str(authorization["broker_route_dispatch_roundtrip_target_mode"]),
                    "strategy": str(authorization["broker_route_dispatch_roundtrip_strategy"]),
                    "market": str(authorization["broker_route_dispatch_roundtrip_market"]),
                    "scenario_key": str(authorization["broker_route_dispatch_roundtrip_scenario_key"]),
                    "dispatch_batch_id": str(authorization["broker_route_dispatch_roundtrip_batch_id"]),
                    "requests": int(authorization["broker_route_dispatch_roundtrip_requests"]),
                    "acked_orders": int(authorization["broker_route_dispatch_roundtrip_acked_orders"]),
                    "missing_request_acks": int(
                        authorization["broker_route_dispatch_roundtrip_missing_request_acks"]
                    ),
                    "rejected_orders": int(authorization["broker_route_dispatch_roundtrip_rejected_orders"]),
                    "unmatched_acks": int(authorization["broker_route_dispatch_roundtrip_unmatched_acks"]),
                },
            },
        },
        "runtime_session": {
            "provided": _to_bool(authorization["runtime_session_provided"]),
            "ready": _to_bool(authorization["runtime_session_ready"]),
            "guard_action": str(authorization["runtime_guard_action"]),
            "guard_halted": _to_bool(authorization["runtime_guard_halted"]),
            "target_mode": str(authorization["runtime_target_mode"]),
            "strategy": str(authorization["runtime_strategy"]),
            "market": str(authorization["runtime_market"]),
            "strategy_portfolio": {
                "required": _to_bool(authorization["runtime_strategy_portfolio_required"]),
                "provided": _to_bool(authorization["runtime_strategy_portfolio_provided"]),
                "ready": _to_bool(authorization["runtime_strategy_portfolio_ready"]),
                "deployment_mode": str(authorization["runtime_strategy_portfolio_deployment_mode"]),
                "allocation_mode": str(authorization["runtime_strategy_portfolio_allocation_mode"]),
                "capital_currency": str(authorization["runtime_strategy_portfolio_capital_currency"]),
                "selected_profile": str(authorization["runtime_strategy_portfolio_selected_profile"]),
                "selected_strategy": str(authorization["runtime_strategy_portfolio_selected_strategy"]),
                "selected_market": str(authorization["runtime_strategy_portfolio_selected_market"]),
                "selected_eligible": _to_bool(
                    authorization["runtime_strategy_portfolio_selected_eligible"]
                ),
                "selected_allocation_weight": float(
                    authorization["runtime_strategy_portfolio_selected_allocation_weight"]
                ),
                "selected_allocation_notional": float(
                    authorization["runtime_strategy_portfolio_selected_allocation_notional"]
                ),
                "notional_cap_applied": _to_bool(
                    authorization["runtime_strategy_portfolio_notional_cap_applied"]
                ),
                "min_strategy_count": int(authorization["runtime_strategy_portfolio_min_strategy_count"]),
                "min_market_count": int(authorization["runtime_strategy_portfolio_min_market_count"]),
                "max_strategy_weight": float(authorization["runtime_strategy_portfolio_max_strategy_weight"]),
                "max_market_weight": float(authorization["runtime_strategy_portfolio_max_market_weight"]),
                "allocated_strategy_count": int(
                    authorization["runtime_strategy_portfolio_allocated_strategy_count"]
                ),
                "allocated_market_count": int(
                    authorization["runtime_strategy_portfolio_allocated_market_count"]
                ),
                "top_strategy_by_weight": str(
                    authorization["runtime_strategy_portfolio_top_strategy_by_weight"]
                ),
                "top_market_by_weight": str(
                    authorization["runtime_strategy_portfolio_top_market_by_weight"]
                ),
                "max_strategy_allocation_weight": float(
                    authorization["runtime_strategy_portfolio_max_strategy_allocation_weight"]
                ),
                "max_market_allocation_weight": float(
                    authorization["runtime_strategy_portfolio_max_market_allocation_weight"]
                ),
                **_runtime_strategy_portfolio_leadlag_config(authorization),
                "pre_portfolio_max_notional_per_session": float(
                    authorization["runtime_pre_portfolio_max_notional_per_session"]
                ),
            },
        },
        "runtime_lineage": _runtime_lineage_config(authorization),
        "operator_review": {
            "provided": _to_bool(authorization["operator_review_provided"]),
            "approval_required": _to_bool(authorization["operator_approval_required"]),
            "identity_ack_required": _to_bool(authorization["operator_identity_ack_required"]),
            "limits_ack_required": _to_bool(authorization["operator_limits_ack_required"]),
            "approved": _to_bool(authorization["operator_approved"]),
            "strategy": str(authorization["operator_strategy"]),
            "market": str(authorization["operator_market"]),
            "limits_ack": _to_bool(authorization["operator_limits_ack"]),
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
        "# Cutover Gate Runbook",
        "",
        f"- Ready: {ready_label}",
        f"- Target mode: {_object_text(summary_row.get('target_mode')).strip()}",
        f"- Strategy: {_object_text(summary_row.get('strategy')).strip()}",
        f"- Market: {_object_text(summary_row.get('market')).strip()}",
        f"- Scenario: {_object_text(summary_row.get('scenario_key')).strip()}",
        f"- Adapter: {_object_text(summary_row.get('adapter')).strip()}",
        f"- Broker readiness ready: {_object_text(summary_row.get('broker_readiness_ready')).strip()}",
        f"- Runtime session ready: {_object_text(summary_row.get('runtime_session_ready')).strip()}",
        f"- Runtime guard action: {_object_text(summary_row.get('runtime_guard_action')).strip()}",
        f"- Runtime lineage current: {'yes' if _to_bool(summary_row.get('runtime_lineage_gate_passed')) else 'no'}",
        f"- Broker contract identity active: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_contract_identity_active')) else 'no'}",
        f"- Broker contract identity digest: {_code(summary_row.get('runtime_telemetry_broker_readiness_roundtrip_contract_identity_sha256'))}",
        f"- Current broker contract identity digest: {_code(summary_row.get('runtime_lineage_current_broker_readiness_contract_identity_sha256'))}",
        f"- Broker contract identity matches current: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_contract_identity_matches_current')) else 'no'}",
        f"- Broker route contract identity active: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_route_contract_identity_active')) else 'no'}",
        f"- Broker route contract identity digest: {_code(summary_row.get('runtime_telemetry_broker_readiness_route_contract_identity_sha256'))}",
        f"- Current broker route contract identity digest: {_code(summary_row.get('runtime_lineage_current_broker_readiness_route_contract_identity_sha256'))}",
        f"- Broker route contract identity matches current: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_route_contract_identity_matches_current')) else 'no'}",
        f"- Broker route-enable route contract identity active: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_route_enable_route_contract_identity_active')) else 'no'}",
        f"- Broker route-enable route contract identity digest: {_code(summary_row.get('runtime_telemetry_broker_readiness_route_enable_route_contract_identity_sha256'))}",
        f"- Current broker route-enable route contract identity digest: {_code(summary_row.get('runtime_lineage_current_broker_readiness_route_enable_route_contract_identity_sha256'))}",
        f"- Broker route-enable route contract identity matches current: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_route_enable_route_contract_identity_matches_current')) else 'no'}",
        f"- Broker route-enable route-enable route contract identity active: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_route_enable_route_enable_route_contract_identity_active')) else 'no'}",
        f"- Broker route-enable route-enable route contract identity digest: {_code(summary_row.get('runtime_telemetry_broker_readiness_route_enable_route_enable_route_contract_identity_sha256'))}",
        f"- Current broker route-enable route-enable route contract identity digest: {_code(summary_row.get('runtime_lineage_current_broker_readiness_route_enable_route_enable_route_contract_identity_sha256'))}",
        f"- Broker route-enable route-enable route contract identity matches current: {'yes' if _to_bool(summary_row.get('runtime_lineage_broker_readiness_route_enable_route_enable_route_contract_identity_matches_current')) else 'no'}",
        f"- Research family: {_object_text(summary_row.get('runtime_scaleup_research_family_id')).strip()}",
        f"- Lead-lag lineage required: {'yes' if _to_bool(summary_row.get('runtime_strategy_portfolio_leadlag_edge_lineage_required')) else 'no'}",
        f"- Lead-lag lineage matches scale-up: {'yes' if _to_bool(summary_row.get('runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup')) else 'no'}",
        f"- Lead-lag lineage contract: {_code(summary_row.get('runtime_strategy_portfolio_leadlag_edge_lineage_contract_version'))} / {_code(summary_row.get('runtime_strategy_portfolio_leadlag_edge_lineage_contract_sha256'))}",
        "- Submission authorization: no",
        f"- Operator review provided: {_object_text(summary_row.get('operator_review_provided')).strip()}",
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
        return "No cutover-gate actions."
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


def _broker_route_readiness_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        "required": _to_bool(authorization["scaleup_broker_route_readiness_required"]),
        "provided": _to_bool(authorization["scaleup_broker_route_readiness_provided"]),
        "ready": _to_bool(authorization["scaleup_broker_route_readiness_ready"]),
        "strategy": str(authorization["scaleup_broker_route_readiness_strategy"]),
        "market": str(authorization["scaleup_broker_route_readiness_market"]),
        "route_ready_pairs": int(authorization["scaleup_broker_route_readiness_route_ready_pairs"]),
        "gap_pairs": int(authorization["scaleup_broker_route_readiness_gap_pairs"]),
        "recommendation": str(authorization["scaleup_broker_route_readiness_recommendation"]),
        "ops_launch_controls_ready": _to_bool(
            authorization["scaleup_broker_route_readiness_ops_launch_controls_ready"]
        ),
        "ops_launch_control_failures": str(
            authorization["scaleup_broker_route_readiness_ops_launch_control_failures"]
        ),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            authorization["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            authorization["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            authorization[
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
            ]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            authorization[
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
            ]
        ),
    }


def _broker_shadow_broker_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(authorization["scaleup_broker_shadow_broker_readiness_provided"]),
        "sessions": int(authorization["scaleup_broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(authorization["scaleup_broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(authorization["scaleup_broker_shadow_broker_adapter"]),
        "adapter_count": int(authorization["scaleup_broker_shadow_broker_adapter_count"]),
        "broker_vendor_data_readiness": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_vendor_data_readiness_sessions"]),
            "provided_sessions": int(
                authorization["scaleup_broker_shadow_broker_vendor_data_readiness_provided_sessions"]
            ),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions"]
            ),
            "failed_checks": int(
                authorization["scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks"]
            ),
        },
        "route_readiness": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_route_readiness_ready_sessions"]
            ),
            "strategy": str(authorization["scaleup_broker_shadow_broker_route_readiness_strategy"]),
            "market": str(authorization["scaleup_broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(authorization["scaleup_broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
            ),
            "strategy": str(authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count"]
            ),
            "max_missing_request_acks": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
            ),
            "max_unmatched_acks": int(
                authorization["scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
            ),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(
                authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
            ),
            "strategy": str(
                authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy"]
            ),
            "market": str(authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(
                authorization["scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
            ),
        },
    }


def _vendor_market_data_batch_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(authorization["scaleup_vendor_market_data_batch_provided"]),
        "ready": _to_bool(authorization["scaleup_vendor_market_data_batch_ready"]),
        "adapter": str(authorization["scaleup_vendor_market_data_batch_adapter"]),
        "kind": str(authorization["scaleup_vendor_market_data_batch_kind"]),
        "market": str(authorization["scaleup_vendor_market_data_batch_market"]),
        "dataset_count": int(authorization["scaleup_vendor_market_data_batch_dataset_count"]),
        "ready_datasets": int(authorization["scaleup_vendor_market_data_batch_ready_datasets"]),
        "failed_datasets": int(authorization["scaleup_vendor_market_data_batch_failed_datasets"]),
        "ready_rate": _jsonable(authorization["scaleup_vendor_market_data_batch_ready_rate"]),
        "unique_source_files": int(authorization["scaleup_vendor_market_data_batch_unique_source_files"]),
        "unique_header_fingerprints": int(
            authorization["scaleup_vendor_market_data_batch_unique_header_fingerprints"]
        ),
        "source_file_fingerprint_coverage": _jsonable(
            authorization["scaleup_vendor_market_data_batch_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(authorization["scaleup_vendor_market_data_batch_min_mapping_coverage"]),
        "unique_mapping_drafts": int(authorization["scaleup_vendor_market_data_batch_unique_mapping_drafts"]),
        "mapping_sources": str(authorization["scaleup_vendor_market_data_batch_mapping_sources"]),
        "comparison": {
            "accepted": _to_bool(authorization["scaleup_vendor_market_data_batch_comparison_accepted"]),
            "failed_checks": int(authorization["scaleup_vendor_market_data_batch_comparison_failed_checks"]),
        },
        "datasets": _json_list(authorization["scaleup_vendor_market_data_batch_datasets_json"]),
    }


def _broker_vendor_market_data_batch_config(authorization: pd.Series) -> dict[str, Any]:
    field_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(authorization[f"{field_prefix}_provided"]),
        "ready": _to_bool(authorization[f"{field_prefix}_ready"]),
        "adapter": str(authorization[f"{field_prefix}_adapter"]),
        "kind": str(authorization[f"{field_prefix}_kind"]),
        "manifest_run_type": str(authorization[f"{field_prefix}_manifest_run_type"]),
        "market": str(authorization[f"{field_prefix}_market"]),
        "dataset_count": int(authorization[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(authorization[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(authorization[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(authorization[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(authorization[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(authorization[f"{field_prefix}_unique_header_fingerprints"]),
        "source_file_fingerprint_coverage": _jsonable(
            authorization[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(authorization[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(authorization[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": str(authorization[f"{field_prefix}_mapping_sources"]),
        "mapping_source_mode": str(authorization[f"{field_prefix}_mapping_source_mode"]),
        "mapping_application_count": int(
            authorization[f"{field_prefix}_mapping_application_count"]
        ),
        "unique_mapping_applications": int(
            authorization[f"{field_prefix}_unique_mapping_applications"]
        ),
        "target_application_coverage": _jsonable(
            authorization[f"{field_prefix}_target_application_coverage"]
        ),
        "application_lineage_consistency_required": _to_bool(
            authorization[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        "application_lineage_consistent": _to_bool(
            authorization[f"{field_prefix}_application_lineage_consistent"]
        ),
        "application_lineage_sha256": str(
            authorization[f"{field_prefix}_application_lineage_sha256"]
        ),
        "comparison": {
            "accepted": _to_bool(authorization[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(authorization[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(authorization[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_cutover_final_lineage_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    field_prefix = f"scaleup_{BROKER_FINAL_LINEAGE_FIELD_PREFIX}"
    config: dict[str, Any] = {
        "required": _to_bool(
            authorization[f"{field_prefix}_lineage_match_required"]
        ),
        "matches": _to_bool(authorization[f"{field_prefix}_lineage_matches"]),
        "scaleup_review_carried_application_lineage_sha256": str(
            authorization[
                f"{field_prefix}_scaleup_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(authorization[f"{field_prefix}_{field}"])
    return config


def _broker_vendor_cutover_complete_final_lineage_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "scaleup_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_complete_final_lineage_28_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "scaleup_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_extended_complete_final_lineage_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_latest_extended_complete_final_lineage_44_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "carried_application_lineage_sha256": str(
            authorization[
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ]
        ),
    }
    for field in SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_DIGEST_FIELDS:
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_current_latest_extended_complete_final_lineage_52_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX
    cutover_lineage_sha256 = str(
        authorization[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            authorization[
                f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            ]
        ),
        "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover_lineage_sha256,
        "carried_application_lineage_sha256": cutover_lineage_sha256,
    }
    for field in (
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS,
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS,
    ):
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_reconciled_current_latest_extended_complete_final_lineage_60_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX
    )
    cutover_lineage_sha256 = str(
        authorization[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD: str(
            authorization[
                f"{prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD}"
            ]
        ),
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD: str(
            authorization[
                f"{prefix}_{SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD}"
            ]
        ),
        "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover_lineage_sha256,
        "carried_application_lineage_sha256": cutover_lineage_sha256,
    }
    for field in (
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS,
    ):
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_verified_reconciled_current_latest_extended_complete_final_lineage_68_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX
    )
    cutover_lineage_sha256 = str(
        authorization[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover_lineage_sha256,
        "carried_application_lineage_sha256": cutover_lineage_sha256,
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
    ):
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_76_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_FIELD_PREFIX
    )
    cutover_lineage_sha256 = str(
        authorization[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
    )
    config: dict[str, Any] = {
        "required": _to_bool(authorization[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(authorization[f"{prefix}_lineage_matches"]),
        "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover_lineage_sha256,
        "carried_application_lineage_sha256": cutover_lineage_sha256,
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
        *SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_CONFIRMED_REVIEW_FIELDS,
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD,
    ):
        config[field] = str(authorization[f"{prefix}_{field}"])
    return config


def _broker_vendor_data_readiness_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        "provided": _to_bool(authorization["scaleup_broker_vendor_data_readiness_provided"]),
        "ready": _to_bool(authorization["scaleup_broker_vendor_data_readiness_ready"]),
        "failed_checks": int(authorization["scaleup_broker_vendor_data_readiness_failed_checks"]),
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
) -> dict[str, Any]:
    row = pd.Series(dtype=object) if row is None else row
    active_config = _broker_vendor_data_readiness_source_active(readiness)
    return {
        "provided": _to_bool(
            readiness.get(
                "provided",
                row.get("broker_vendor_data_readiness_provided", active_config),
            )
        ),
        "ready": _to_bool(
            readiness.get("ready", row.get("broker_vendor_data_readiness_ready", False))
        ),
        "failed_checks": _broker_vendor_data_readiness_failed_checks(
            readiness,
            fallback=_number(row, "broker_vendor_data_readiness_failed_checks", 0.0),
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


def _broker_vendor_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, Any] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get(
                "required",
                row.get(f"{prefix}_lineage_match_required", False),
            )
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get(
                "matches",
                row.get(f"{prefix}_lineage_matches", False),
            )
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(f"{prefix}_application_lineage_sha256", ""),
            )
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = SCALEUP_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
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
                    f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in SCALEUP_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_complete_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = SCALEUP_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
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
                    f"{summary_prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in SCALEUP_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_extended_complete_final_lineage_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
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
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_FIELD_PREFIX
    summary_prefix = (
        SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_SUMMARY_FIELD_PREFIX
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
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": _sha256_text(
            _first_text(
                comparison.get("carried_application_lineage_sha256", ""),
                row.get(
                    f"{summary_prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
                    "",
                ),
            )
        ),
    }
    for field in SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_FIELD_PREFIX
    summary_prefix = (
        SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_SUMMARY_FIELD_PREFIX
    )
    scaleup_current_field = (
        "scaleup_current_latest_extended_complete_final_review_"
        "carried_application_lineage_sha256"
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
                row.get(f"{summary_prefix}_{scaleup_current_field}", ""),
            )
        ),
        f"{prefix}_{scaleup_current_field}": _sha256_text(
            _first_text(
                comparison.get(scaleup_current_field, ""),
                row.get(f"{summary_prefix}_{scaleup_current_field}", ""),
            )
        ),
    }
    for field in (
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_DIGEST_FIELDS,
        *SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_FIELD_PREFIX
    )
    summary_prefix = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SUMMARY_FIELD_PREFIX
    )
    scaleup_review_field = (
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD
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
                row.get(f"{summary_prefix}_{scaleup_review_field}", ""),
            )
        ),
    }
    for field in (
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_DIGEST_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_STAGE_FIELDS,
        *SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_CURRENT_STAGE_FIELDS,
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_FIELD_PREFIX
    )
    summary_prefix = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SUMMARY_FIELD_PREFIX
    )
    scaleup_review_field = (
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD
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
                row.get(f"{summary_prefix}_{scaleup_review_field}", ""),
            )
        ),
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_state_fields(
    comparison: dict[str, Any],
    row: pd.Series,
) -> dict[str, Any]:
    prefix = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_FIELD_PREFIX
    )
    summary_prefix = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SUMMARY_FIELD_PREFIX
    )
    scaleup_review_field = (
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD
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
                row.get(f"{summary_prefix}_{scaleup_review_field}", ""),
            )
        ),
    }
    for field in (
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_DIGEST_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_CURRENT_STAGE_FIELDS,
        *SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_REVIEW_FIELDS,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ACK_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_ROUNDTRIP_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_BROKER_READINESS_REVIEW_FIELD,
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_SCALEUP_REVIEW_FIELD,
        *SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_CONFIRMED_REVIEW_FIELDS,
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_SCALEUP_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(
            _first_text(
                comparison.get(field, ""),
                row.get(f"{summary_prefix}_{field}", ""),
            )
        )
    return fields


def _scaleup_state(row: pd.Series, config: dict[str, Any], checks: pd.DataFrame) -> dict[str, Any]:
    limits = config.get("limits", {}) or {}
    proof = config.get("proof_freshness", {}) or {}
    identity = config.get("identity", {}) or {}
    broker_readiness = config.get("broker_readiness", {}) or {}
    data_readiness_comparison = config.get("data_readiness_comparison", {}) or {}
    vendor_market_data_batch = data_readiness_comparison.get("vendor_market_data_batch", {}) or {}
    route_readiness = config.get("route_readiness", {}) or {}
    shadow_broker = config.get("shadow_broker_readiness", {}) or {}
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    broker_route_readiness = broker_readiness.get("route_readiness", {}) or {}
    broker_shadow_broker = broker_readiness.get("shadow_broker_readiness", {}) or {}
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    lineage_comparison = dispatch.get("vendor_market_data_batch_lineage_comparison", {}) or {}
    if not isinstance(lineage_comparison, dict):
        lineage_comparison = {}
    final_lineage_comparison = dispatch.get(
        BROKER_FINAL_LINEAGE_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(final_lineage_comparison, dict):
        final_lineage_comparison = {}
    scaleup_final_lineage_comparison = dispatch.get(
        SCALEUP_FINAL_LINEAGE_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(scaleup_final_lineage_comparison, dict):
        scaleup_final_lineage_comparison = {}
    scaleup_complete_final_lineage_comparison = dispatch.get(
        SCALEUP_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(scaleup_complete_final_lineage_comparison, dict):
        scaleup_complete_final_lineage_comparison = {}
    scaleup_extended_complete_final_lineage_comparison = dispatch.get(
        SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(scaleup_extended_complete_final_lineage_comparison, dict):
        scaleup_extended_complete_final_lineage_comparison = {}
    scaleup_latest_extended_complete_final_lineage_43_comparison = dispatch.get(
        SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(
        scaleup_latest_extended_complete_final_lineage_43_comparison,
        dict,
    ):
        scaleup_latest_extended_complete_final_lineage_43_comparison = {}
    scaleup_current_latest_extended_complete_final_lineage_51_comparison = dispatch.get(
        SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(
        scaleup_current_latest_extended_complete_final_lineage_51_comparison,
        dict,
    ):
        scaleup_current_latest_extended_complete_final_lineage_51_comparison = {}
    scaleup_reconciled_current_latest_extended_complete_final_lineage_59_comparison = dispatch.get(
        SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(
        scaleup_reconciled_current_latest_extended_complete_final_lineage_59_comparison,
        dict,
    ):
        scaleup_reconciled_current_latest_extended_complete_final_lineage_59_comparison = {}
    scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_comparison = dispatch.get(
        SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(
        scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_comparison,
        dict,
    ):
        scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_comparison = {}
    scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_comparison = dispatch.get(
        SCALEUP_CONFIRMED_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_75_COMPARISON_KEY,
        {},
    ) or {}
    if not isinstance(
        scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_comparison,
        dict,
    ):
        scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_comparison = {}
    broker_vendor_data_readiness = broker_readiness.get("broker_vendor_data_readiness", {}) or {}
    broker_vendor_market_data_batch = _broker_vendor_market_data_batch_source(dispatch)
    broker_vendor_market_data_batch_state = _vendor_market_data_batch_state(
        broker_vendor_market_data_batch,
        row=row,
        field_prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    resume_gate = broker_readiness.get("resume_gate", {}) or {}
    if not isinstance(resume_gate, dict):
        resume_gate = {}
    resume_broker_route = resume_gate.get("broker_route_readiness", {}) or {}
    resume_incident_broker_route = resume_gate.get("incident_broker_route_readiness", {}) or {}
    route_enable = dispatch.get("route_enable_dispatch_roundtrip", {}) or {}
    route = dispatch.get("route_proof", {}) or {}
    strategy = _strategy_key(_first_text(row.get("strategy", ""), config.get("strategy", ""), identity.get("strategy", "")))
    market = _identity_key(_first_text(row.get("market", ""), config.get("market", ""), identity.get("market", "")))
    proof_strategy = _strategy_key(_first_text(proof.get("strategy", ""), row.get("proof_refresh_strategy", "")))
    proof_market = _identity_key(_first_text(proof.get("market", ""), row.get("proof_refresh_market", "")))
    proof_active = _proof_active(row, proof)
    return {
        "ready": _to_bool(row.get("ready", config.get("ready", False))),
        "target_mode": _identity_key(_first_text(row.get("target_mode", ""), config.get("target_mode", ""))),
        "strategy": strategy,
        "market": market,
        "scenario_key": _first_text(row.get("scenario_key", ""), config.get("scenario_key", "")),
        "adapter": _first_text(row.get("adapter", ""), config.get("adapter", "")),
        "failed_checks": _failed_scaleup_checks(row, checks),
        "max_orders_per_session": int(
            _number_from(limits, "max_orders_per_session", _number(row, "max_orders_per_session", 0.0))
        ),
        "max_notional_per_session": float(
            _number_from(limits, "max_notional_per_session", _number(row, "max_notional_per_session", 0.0))
        ),
        "stop_loss": _nullable_number(limits.get("stop_loss")),
        "proof_refresh_active": proof_active,
        "proof_refresh_provided": _to_bool(proof.get("provided", row.get("proof_refresh_provided", False))),
        "proof_refresh_ready": _to_bool(proof.get("ready", row.get("proof_refresh_ready", False))),
        "proof_refresh_strategy": proof_strategy or strategy,
        "proof_refresh_market": proof_market or market,
        "proof_refresh_mixed_identity": _to_bool(
            proof.get("mixed_identity", row.get("proof_refresh_mixed_identity", False))
        ),
        "proof_source": _first_text(proof.get("proof_source", ""), row.get("proof_source", "")),
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
        "vendor_market_data_batch": _vendor_market_data_batch_state(vendor_market_data_batch),
        "broker_dispatch_roundtrip_vendor_market_data_batch": broker_vendor_market_data_batch_state,
        "broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            lineage_comparison.get(
                "required",
                row.get("broker_vendor_market_data_batch_lineage_match_required", False),
            )
        ),
        "broker_vendor_market_data_batch_lineage_matches": _to_bool(
            lineage_comparison.get(
                "matches",
                row.get("broker_vendor_market_data_batch_lineage_matches", False),
            )
        ),
        "vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                lineage_comparison.get("current_application_lineage_sha256", ""),
                row.get("vendor_market_data_batch_application_lineage_sha256", ""),
            )
        ),
        "broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            _first_text(
                lineage_comparison.get("broker_application_lineage_sha256", ""),
                row.get("broker_vendor_market_data_batch_application_lineage_sha256", ""),
            )
        ),
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256": (
            _sha256_text(
                _first_text(
                    lineage_comparison.get("carried_application_lineage_sha256", ""),
                    broker_vendor_market_data_batch_state.get("application_lineage_sha256", ""),
                    row.get(
                        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
                        "",
                    ),
                )
            )
        ),
        **_broker_vendor_final_lineage_state_fields(
            final_lineage_comparison,
            row,
        ),
        **_broker_vendor_scaleup_final_lineage_state_fields(
            scaleup_final_lineage_comparison,
            row,
        ),
        **_broker_vendor_scaleup_complete_final_lineage_state_fields(
            scaleup_complete_final_lineage_comparison,
            row,
        ),
        **_broker_vendor_scaleup_extended_complete_final_lineage_state_fields(
            scaleup_extended_complete_final_lineage_comparison,
            row,
        ),
        **_broker_vendor_scaleup_latest_extended_complete_final_lineage_43_state_fields(
            scaleup_latest_extended_complete_final_lineage_43_comparison,
            row,
        ),
        **_broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_state_fields(
            scaleup_current_latest_extended_complete_final_lineage_51_comparison,
            row,
        ),
        **_broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_state_fields(
            scaleup_reconciled_current_latest_extended_complete_final_lineage_59_comparison,
            row,
        ),
        **_broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_state_fields(
            scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_comparison,
            row,
        ),
        **_broker_vendor_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_state_fields(
            scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_75_comparison,
            row,
        ),
        "broker_vendor_data_readiness": _broker_vendor_data_readiness_state(
            broker_vendor_data_readiness,
            row=row,
        ),
        "route_readiness_required": _to_bool(
            route_readiness.get("required", row.get("route_readiness_required", False))
        ),
        "route_readiness_provided": _to_bool(
            route_readiness.get("provided", row.get("route_readiness_provided", False))
        ),
        "route_readiness_ready": _to_bool(
            route_readiness.get("ready", row.get("route_readiness_ready", False))
        ),
        "route_readiness_strategy": _strategy_key(
            _first_text(route_readiness.get("strategy", ""), row.get("route_readiness_strategy", ""))
        ),
        "route_readiness_market": _identity_key(
            _first_text(route_readiness.get("market", ""), row.get("route_readiness_market", ""))
        ),
        "route_readiness_route_ready_pairs": int(
            _number_from(
                route_readiness,
                "route_ready_pairs",
                _number(row, "route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "route_readiness_gap_pairs": int(
            _number_from(route_readiness, "gap_pairs", _number(row, "route_readiness_gap_pairs", 0.0))
        ),
        "route_readiness_recommendation": _first_text(
            route_readiness.get("recommendation", ""),
            row.get("route_readiness_recommendation", ""),
        ),
        "route_readiness_ops_launch_controls_present": _to_bool(
            route_readiness.get(
                "ops_launch_controls_present",
                row.get("route_readiness_ops_launch_controls_present", False),
            )
        ),
        "route_readiness_ops_launch_controls_blocked_pairs": int(
            _number_from(
                route_readiness,
                "ops_launch_controls_blocked_pairs",
                _number(row, "route_readiness_ops_launch_controls_blocked_pairs", 0.0),
            )
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_breach_pairs",
                _number(row, "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs", 0.0),
            )
        ),
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
            _number_from(
                route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                _number(
                    row,
                    "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                    0.0,
                ),
            )
        ),
        "broker_route_readiness_required": _to_bool(
            broker_route_readiness.get(
                "required",
                row.get("broker_route_readiness_required", False),
            )
        ),
        "broker_route_readiness_provided": _to_bool(
            broker_route_readiness.get(
                "provided",
                row.get("broker_route_readiness_provided", False),
            )
        ),
        "broker_route_readiness_ready": _to_bool(
            broker_route_readiness.get("ready", row.get("broker_route_readiness_ready", False))
        ),
        "broker_route_readiness_strategy": _strategy_key(
            _first_text(
                broker_route_readiness.get("strategy", ""),
                row.get("broker_route_readiness_strategy", ""),
            )
        ),
        "broker_route_readiness_market": _identity_key(
            _first_text(
                broker_route_readiness.get("market", ""),
                row.get("broker_route_readiness_market", ""),
            )
        ),
        "broker_route_readiness_route_ready_pairs": int(
            _number_from(
                broker_route_readiness,
                "route_ready_pairs",
                _number(row, "broker_route_readiness_route_ready_pairs", 0.0),
            )
        ),
        "broker_route_readiness_gap_pairs": int(
            _number_from(
                broker_route_readiness,
                "gap_pairs",
                _number(row, "broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_route_readiness_recommendation": _first_text(
            broker_route_readiness.get("recommendation", ""),
            row.get("broker_route_readiness_recommendation", ""),
        ),
        "broker_route_readiness_ops_launch_controls_ready": _to_bool(
            broker_route_readiness.get(
                "ops_launch_controls_ready",
                row.get("broker_route_readiness_ops_launch_controls_ready", False),
            )
        ),
        "broker_route_readiness_ops_launch_control_failures": _first_text(
            broker_route_readiness.get("ops_launch_control_failures", ""),
            row.get("broker_route_readiness_ops_launch_control_failures", ""),
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_safe_runs",
                _number(row, "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_breach_runs",
                _number(row, "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            )
        ),
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(
                broker_route_readiness,
                "ops_broker_roundtrip_portfolio_concentration_ok_runs",
                _number(
                    row,
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
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
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    0.0,
                ),
            )
        ),
        **_resume_route_readiness_state_fields(
            row,
            resume_broker_route,
            source_prefix="broker_resume_broker_route_readiness",
        ),
        **_resume_route_readiness_state_fields(
            row,
            resume_incident_broker_route,
            source_prefix="broker_resume_incident_broker_route_readiness",
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
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number_from(
                route_enable,
                "failed_checks",
                _number(row, "broker_route_enable_dispatch_roundtrip_failed_checks", 0.0),
            )
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
        "shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("shadow_broker_adapter", ""))
        ),
        "shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "shadow_broker_adapter_count", 0.0),
            )
        ),
        "shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("shadow_broker_route_readiness_market", ""),
            )
        ),
        "shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        **_broker_shadow_broker_state_fields(row, broker_shadow_broker),
    }


def _broker_shadow_broker_state_fields(row: pd.Series, shadow_broker: dict[str, Any]) -> dict[str, Any]:
    shadow_broker_vendor_readiness = shadow_broker.get("broker_vendor_data_readiness", {}) or {}
    shadow_broker_route = shadow_broker.get("route_readiness", {}) or {}
    shadow_broker_dispatch = shadow_broker.get("dispatch_roundtrip", {}) or {}
    shadow_broker_route_dispatch = shadow_broker.get("route_dispatch_roundtrip", {}) or {}
    return {
        "broker_shadow_broker_readiness_provided": _to_bool(
            shadow_broker.get("provided", row.get("broker_shadow_broker_readiness_provided", False))
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number_from(
                shadow_broker,
                "sessions",
                _number(row, "broker_shadow_broker_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number_from(
                shadow_broker,
                "ready_sessions",
                _number(row, "broker_shadow_broker_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "sessions",
                _number(row, "broker_shadow_broker_vendor_data_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "provided_sessions",
                _number(row, "broker_shadow_broker_vendor_data_readiness_provided_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "ready_sessions",
                _number(row, "broker_shadow_broker_vendor_data_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            _number_from(
                shadow_broker_vendor_readiness,
                "failed_checks",
                _number(row, "broker_shadow_broker_vendor_data_readiness_failed_checks", 0.0),
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(
            _first_text(shadow_broker.get("adapter", ""), row.get("broker_shadow_broker_adapter", ""))
        ),
        "broker_shadow_broker_adapter_count": int(
            _number_from(
                shadow_broker,
                "adapter_count",
                _number(row, "broker_shadow_broker_adapter_count", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number_from(
                shadow_broker_route,
                "sessions",
                _number(row, "broker_shadow_broker_route_readiness_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number_from(
                shadow_broker_route,
                "ready_sessions",
                _number(row, "broker_shadow_broker_route_readiness_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            _first_text(
                shadow_broker_route.get("strategy", ""),
                row.get("broker_shadow_broker_route_readiness_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            _first_text(
                shadow_broker_route.get("market", ""),
                row.get("broker_shadow_broker_route_readiness_market", ""),
            )
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number_from(
                shadow_broker_route,
                "max_gap_pairs",
                _number(row, "broker_shadow_broker_route_readiness_gap_pairs", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "sessions",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_dispatch,
                "ready_sessions",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_dispatch.get("strategy", ""),
                row.get("broker_shadow_broker_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_dispatch.get("market", ""),
                row.get("broker_shadow_broker_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_dispatch,
                "scenario_count",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_missing_request_acks",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_missing_request_acks", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number_from(
                shadow_broker_dispatch,
                "max_rejected_orders",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_rejected_orders", 0.0),
            )
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number_from(
                shadow_broker_dispatch,
                "max_unmatched_acks",
                _number(row, "broker_shadow_broker_dispatch_roundtrip_unmatched_acks", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "sessions",
                _number(row, "broker_shadow_broker_route_dispatch_roundtrip_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number_from(
                shadow_broker_route_dispatch,
                "ready_sessions",
                _number(row, "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions", 0.0),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            _first_text(
                shadow_broker_route_dispatch.get("strategy", ""),
                row.get("broker_shadow_broker_route_dispatch_roundtrip_strategy", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            _first_text(
                shadow_broker_route_dispatch.get("market", ""),
                row.get("broker_shadow_broker_route_dispatch_roundtrip_market", ""),
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number_from(
                shadow_broker_route_dispatch,
                "scenario_count",
                _number(row, "broker_shadow_broker_route_dispatch_roundtrip_scenario_count", 0.0),
            )
        ),
    }


def _broker_vendor_market_data_batch_source(dispatch: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        "vendor_market_data_batch",
        "roundtrip_vendor_market_data_batch",
    ):
        vendor = dispatch.get(key, {}) or {}
        if vendor_market_data_batch_source_active(vendor):
            return vendor
    return {}


def _broker_vendor_data_readiness_source(config: dict[str, Any]) -> dict[str, Any]:
    candidates: list[object] = []
    dispatch = config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(dispatch.get("broker_vendor_data_readiness"))
    candidates.append(config.get("broker_vendor_data_readiness"))
    for candidate in candidates:
        if isinstance(candidate, dict) and _broker_vendor_data_readiness_source_active(candidate):
            return candidate
    return {}


def _broker_vendor_data_readiness_source_active(readiness: object) -> bool:
    if not isinstance(readiness, dict) or not readiness:
        return False
    return bool(
        _to_bool(readiness.get("provided", True))
        or _to_bool(readiness.get("ready", False))
        or _broker_vendor_data_readiness_failed_checks(readiness) > 0
    )


def _with_broker_readiness_config_vendor_market_data_batch(
    scaleup_config: dict[str, Any],
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any]:
    broker_readiness = scaleup_config.get("broker_readiness", {}) or {}
    if not isinstance(broker_readiness, dict):
        return scaleup_config
    dispatch = broker_readiness.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return scaleup_config
    sidecar_broker = broker_readiness_config.get("broker_readiness", broker_readiness_config) or {}
    if not isinstance(sidecar_broker, dict):
        return scaleup_config
    sidecar_dispatch = sidecar_broker.get("dispatch_roundtrip", {}) or {}
    if not isinstance(sidecar_dispatch, dict):
        return scaleup_config

    vendor = _broker_vendor_market_data_batch_source(sidecar_dispatch)
    should_hydrate_vendor = (
        not vendor_market_data_batch_source_active(_broker_vendor_market_data_batch_source(dispatch))
        and vendor_market_data_batch_source_active(vendor)
    )
    readiness = _broker_vendor_data_readiness_source(sidecar_broker)
    should_hydrate_readiness = (
        not _broker_vendor_data_readiness_source_active(
            broker_readiness.get("broker_vendor_data_readiness", {}) or {}
        )
        and _broker_vendor_data_readiness_source_active(readiness)
    )
    lineage_comparison = sidecar_dispatch.get(
        "vendor_market_data_batch_lineage_comparison",
        {},
    ) or {}
    should_hydrate_lineage = bool(
        not isinstance(
            dispatch.get("vendor_market_data_batch_lineage_comparison"),
            dict,
        )
        or not dispatch.get("vendor_market_data_batch_lineage_comparison")
    ) and isinstance(lineage_comparison, dict) and bool(lineage_comparison)
    final_lineage_comparison = sidecar_dispatch.get(
        BROKER_FINAL_LINEAGE_COMPARISON_KEY,
        {},
    ) or {}
    should_hydrate_final_lineage = bool(
        not isinstance(dispatch.get(BROKER_FINAL_LINEAGE_COMPARISON_KEY), dict)
        or not dispatch.get(BROKER_FINAL_LINEAGE_COMPARISON_KEY)
    ) and isinstance(final_lineage_comparison, dict) and bool(
        final_lineage_comparison
    )
    if (
        not should_hydrate_vendor
        and not should_hydrate_readiness
        and not should_hydrate_lineage
        and not should_hydrate_final_lineage
    ):
        return scaleup_config

    out = dict(scaleup_config)
    out_broker = dict(broker_readiness)
    out_dispatch = dict(dispatch)
    if should_hydrate_vendor:
        out_dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = dict(vendor)
    if should_hydrate_lineage:
        out_dispatch["vendor_market_data_batch_lineage_comparison"] = dict(
            lineage_comparison
        )
    if should_hydrate_final_lineage:
        out_dispatch[BROKER_FINAL_LINEAGE_COMPARISON_KEY] = dict(
            final_lineage_comparison
        )
    if should_hydrate_readiness:
        out_broker["broker_vendor_data_readiness"] = dict(readiness)
    out_broker["dispatch_roundtrip"] = out_dispatch
    out["broker_readiness"] = out_broker
    return out


def _broker_state(summary: pd.DataFrame) -> dict[str, Any]:
    row = summary.iloc[0] if not summary.empty else pd.Series(dtype=object)
    return {
        "provided": not summary.empty,
        "ready": _to_bool(row.get("ready", False)),
        "adapter": _first_text(row.get("adapter", "")),
        "schema_status": _first_text(row.get("adapter_schema_status", "")),
        "schema_reviewed": _to_bool(row.get("schema_reviewed", False)),
        "schema_review_mode": _first_text(row.get("schema_review_mode", "")),
        "recommendation": _first_text(row.get("recommendation", "")),
        "runtime_session_provided": _to_bool(row.get("runtime_session_provided", False)),
        "runtime_session_ready": _to_bool(row.get("runtime_session_ready", False)),
        "runtime_guard_action": _identity_key(row.get("runtime_guard_action", "")),
        "runtime_guard_halted": _to_bool(row.get("runtime_guard_halted", False)),
        "runtime_target_mode": _identity_key(row.get("runtime_target_mode", "")),
        "runtime_strategy": _strategy_key(row.get("runtime_strategy", "")),
        "runtime_market": _identity_key(row.get("runtime_market", "")),
        **_strategy_portfolio_state(row, "runtime_strategy_portfolio", "strategy_portfolio"),
        "resume_gate_provided": _to_bool(row.get("resume_gate_provided", False)),
        "resume_gate_ready": _to_bool(row.get("resume_gate_ready", False)),
        "resume_strategy": _strategy_key(row.get("resume_strategy", "")),
        "resume_market": _identity_key(row.get("resume_market", "")),
        "resume_proof_refresh_ready": _to_bool(row.get("resume_proof_refresh_ready", False)),
        "resume_proof_refresh_strategy": _strategy_key(row.get("resume_proof_refresh_strategy", "")),
        "resume_proof_refresh_market": _identity_key(row.get("resume_proof_refresh_market", "")),
        "dispatch_roundtrip_provided": _to_bool(row.get("dispatch_roundtrip_provided", False)),
        "dispatch_roundtrip_ready": _to_bool(row.get("dispatch_roundtrip_ready", False)),
        "dispatch_roundtrip_target_mode": _identity_key(row.get("dispatch_roundtrip_target_mode", "")),
        "dispatch_roundtrip_strategy": _strategy_key(row.get("dispatch_roundtrip_strategy", "")),
        "dispatch_roundtrip_market": _identity_key(row.get("dispatch_roundtrip_market", "")),
        "dispatch_roundtrip_scenario_key": _first_text(row.get("dispatch_roundtrip_scenario_key", "")),
        "dispatch_roundtrip_batch_id": _first_text(row.get("dispatch_roundtrip_batch_id", "")),
        "dispatch_roundtrip_requests": int(_number(row, "dispatch_roundtrip_requests", 0.0)),
        "dispatch_roundtrip_acked_orders": int(_number(row, "dispatch_roundtrip_acked_orders", 0.0)),
        "dispatch_roundtrip_missing_request_acks": int(
            _number(row, "dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        "dispatch_roundtrip_rejected_orders": int(_number(row, "dispatch_roundtrip_rejected_orders", 0.0)),
        "dispatch_roundtrip_unmatched_acks": int(_number(row, "dispatch_roundtrip_unmatched_acks", 0.0)),
        "dispatch_roundtrip_failed_checks": int(_number(row, "dispatch_roundtrip_failed_checks", 0.0)),
        "route_enable_dispatch_roundtrip_failed_checks": int(
            _number(row, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
        ),
        "route_dispatch_roundtrip_required": _to_bool(row.get("route_dispatch_roundtrip_required", False)),
        "route_dispatch_roundtrip_provided": _to_bool(row.get("route_dispatch_roundtrip_provided", False)),
        "route_dispatch_roundtrip_ready": _to_bool(row.get("route_dispatch_roundtrip_ready", False)),
        "route_dispatch_roundtrip_target_mode": _identity_key(row.get("route_dispatch_roundtrip_target_mode", "")),
        "route_dispatch_roundtrip_strategy": _strategy_key(row.get("route_dispatch_roundtrip_strategy", "")),
        "route_dispatch_roundtrip_market": _identity_key(row.get("route_dispatch_roundtrip_market", "")),
        "route_dispatch_roundtrip_scenario_key": _first_text(row.get("route_dispatch_roundtrip_scenario_key", "")),
        "route_dispatch_roundtrip_batch_id": _first_text(row.get("route_dispatch_roundtrip_batch_id", "")),
        "route_dispatch_roundtrip_requests": int(_number(row, "route_dispatch_roundtrip_requests", 0.0)),
        "route_dispatch_roundtrip_acked_orders": int(_number(row, "route_dispatch_roundtrip_acked_orders", 0.0)),
        "route_dispatch_roundtrip_missing_request_acks": int(
            _number(row, "route_dispatch_roundtrip_missing_request_acks", 0.0)
        ),
        "route_dispatch_roundtrip_rejected_orders": int(
            _number(row, "route_dispatch_roundtrip_rejected_orders", 0.0)
        ),
        "route_dispatch_roundtrip_unmatched_acks": int(
            _number(row, "route_dispatch_roundtrip_unmatched_acks", 0.0)
        ),
    }


def _runtime_state(
    summary: pd.DataFrame,
    broker: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    lineage_fields = runtime_session_lineage_fields(lineage)
    if not summary.empty:
        row = summary.iloc[0]
        return {
            "provided": True,
            "ready": _to_bool(row.get("ready", False)),
            "guard_action": _identity_key(row.get("guard_action", "")),
            "halted": _to_bool(row.get("halted", False)),
            "target_mode": _identity_key(row.get("target_mode", "")),
            "strategy": _strategy_key(row.get("strategy", "")),
            "market": _identity_key(row.get("market", "")),
            **_strategy_portfolio_state(row, "strategy_portfolio"),
            **lineage_fields,
        }
    return {
        "provided": bool(broker["runtime_session_provided"]),
        "ready": bool(broker["runtime_session_ready"]),
        "guard_action": broker["runtime_guard_action"],
        "halted": bool(broker["runtime_guard_halted"]),
        "target_mode": broker["runtime_target_mode"],
        "strategy": broker["runtime_strategy"],
        "market": broker["runtime_market"],
        "strategy_portfolio_required": broker["strategy_portfolio_required"],
        "strategy_portfolio_provided": broker["strategy_portfolio_provided"],
        "strategy_portfolio_ready": broker["strategy_portfolio_ready"],
        "strategy_portfolio_deployment_mode": broker["strategy_portfolio_deployment_mode"],
        "strategy_portfolio_allocation_mode": broker["strategy_portfolio_allocation_mode"],
        "strategy_portfolio_capital_currency": broker["strategy_portfolio_capital_currency"],
        "strategy_portfolio_selected_profile": broker["strategy_portfolio_selected_profile"],
        "strategy_portfolio_selected_strategy": broker["strategy_portfolio_selected_strategy"],
        "strategy_portfolio_selected_market": broker["strategy_portfolio_selected_market"],
        "strategy_portfolio_selected_eligible": broker["strategy_portfolio_selected_eligible"],
        "strategy_portfolio_selected_allocation_weight": broker["strategy_portfolio_selected_allocation_weight"],
        "strategy_portfolio_selected_allocation_notional": broker[
            "strategy_portfolio_selected_allocation_notional"
        ],
        "strategy_portfolio_notional_cap_applied": broker["strategy_portfolio_notional_cap_applied"],
        "strategy_portfolio_min_strategy_count": broker["strategy_portfolio_min_strategy_count"],
        "strategy_portfolio_min_market_count": broker["strategy_portfolio_min_market_count"],
        "strategy_portfolio_max_strategy_weight": broker["strategy_portfolio_max_strategy_weight"],
        "strategy_portfolio_max_market_weight": broker["strategy_portfolio_max_market_weight"],
        "strategy_portfolio_allocated_strategy_count": broker["strategy_portfolio_allocated_strategy_count"],
        "strategy_portfolio_allocated_market_count": broker["strategy_portfolio_allocated_market_count"],
        "strategy_portfolio_top_strategy_by_weight": broker["strategy_portfolio_top_strategy_by_weight"],
        "strategy_portfolio_top_market_by_weight": broker["strategy_portfolio_top_market_by_weight"],
        "strategy_portfolio_max_strategy_allocation_weight": broker[
            "strategy_portfolio_max_strategy_allocation_weight"
        ],
        "strategy_portfolio_max_market_allocation_weight": broker[
            "strategy_portfolio_max_market_allocation_weight"
        ],
        "pre_portfolio_max_notional_per_session": broker["pre_portfolio_max_notional_per_session"],
        **lineage_fields,
    }


def _runtime_lineage_output_fields(runtime: dict[str, Any]) -> dict[str, Any]:
    return {column: runtime[column] for column in RUNTIME_LINEAGE_OUTPUT_COLUMNS}


def _scaleup_provenance_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    return {
        column: authorization[column]
        for column in SCALEUP_PROVENANCE_OUTPUT_COLUMNS
    }


def _scaleup_provenance_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    return {
        column: _jsonable_check_value(authorization[column])
        for column in SCALEUP_PROVENANCE_OUTPUT_COLUMNS
    }


def _runtime_strategy_portfolio_leadlag_output_fields(
    runtime: dict[str, Any],
) -> dict[str, Any]:
    return {
        f"runtime_strategy_portfolio_{field}": runtime[
            f"strategy_portfolio_{field}"
        ]
        for field in STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    }


def _runtime_strategy_portfolio_leadlag_summary_fields(
    authorization: pd.Series,
) -> dict[str, Any]:
    return {
        f"runtime_strategy_portfolio_{field}": authorization[
            f"runtime_strategy_portfolio_{field}"
        ]
        for field in STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    }


def _runtime_strategy_portfolio_leadlag_config(
    authorization: pd.Series,
) -> dict[str, Any]:
    return {
        field: _jsonable_check_value(
            authorization[f"runtime_strategy_portfolio_{field}"]
        )
        for field in STRATEGY_PORTFOLIO_LEADLAG_FIELDS
    }


def _runtime_lineage_summary_fields(authorization: pd.Series) -> dict[str, Any]:
    return {
        column: authorization[column]
        for column in RUNTIME_LINEAGE_OUTPUT_COLUMNS
    }


def _runtime_lineage_config(authorization: pd.Series) -> dict[str, Any]:
    return {
        column: _jsonable_check_value(authorization[column])
        for column in RUNTIME_LINEAGE_OUTPUT_COLUMNS
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
            raise ValueError(f"cutover output_dir must not overwrite the {label} source directory")


def _runtime_strategy_portfolio_active(runtime: dict[str, Any]) -> bool:
    return bool(
        runtime["strategy_portfolio_required"]
        or runtime["strategy_portfolio_provided"]
        or _runtime_strategy_portfolio_leadlag_active(runtime)
    )


def _runtime_strategy_portfolio_leadlag_active(runtime: dict[str, Any]) -> bool:
    return bool(
        runtime["strategy_portfolio_leadlag_edge_lineage_required"]
        or _identity_key(runtime["strategy_portfolio_selected_profile"])
        == "leadlag"
    )


def _strategy_portfolio_state(row: pd.Series, *prefixes: str) -> dict[str, Any]:
    fields = {
        "strategy_portfolio_required": _first_bool_field(row, "required", prefixes),
        "strategy_portfolio_provided": _first_bool_field(row, "provided", prefixes),
        "strategy_portfolio_ready": _first_bool_field(row, "ready", prefixes),
        "strategy_portfolio_deployment_mode": _first_text_field(row, "deployment_mode", prefixes),
        "strategy_portfolio_allocation_mode": _first_text_field(row, "allocation_mode", prefixes),
        "strategy_portfolio_capital_currency": _first_text_field(row, "capital_currency", prefixes),
        "strategy_portfolio_selected_profile": _first_text_field(row, "selected_profile", prefixes),
        "strategy_portfolio_selected_strategy": _strategy_key(
            _first_text_field(row, "selected_strategy", prefixes)
        ),
        "strategy_portfolio_selected_market": _identity_key(_first_text_field(row, "selected_market", prefixes)),
        "strategy_portfolio_selected_eligible": _first_bool_field(row, "selected_eligible", prefixes),
        "strategy_portfolio_selected_allocation_weight": _first_number_field(
            row,
            "selected_allocation_weight",
            prefixes,
        ),
        "strategy_portfolio_selected_allocation_notional": _first_number_field(
            row,
            "selected_allocation_notional",
            prefixes,
        ),
        "strategy_portfolio_notional_cap_applied": _first_bool_field(row, "notional_cap_applied", prefixes),
        "strategy_portfolio_min_strategy_count": int(
            _first_number_field(row, "min_strategy_count", prefixes)
        ),
        "strategy_portfolio_min_market_count": int(_first_number_field(row, "min_market_count", prefixes)),
        "strategy_portfolio_max_strategy_weight": _first_number_field(
            row,
            "max_strategy_weight",
            prefixes,
        ),
        "strategy_portfolio_max_market_weight": _first_number_field(
            row,
            "max_market_weight",
            prefixes,
        ),
        "strategy_portfolio_allocated_strategy_count": int(
            _first_number_field(row, "allocated_strategy_count", prefixes)
        ),
        "strategy_portfolio_allocated_market_count": int(
            _first_number_field(row, "allocated_market_count", prefixes)
        ),
        "strategy_portfolio_top_strategy_by_weight": _strategy_key(
            _first_text_field(row, "top_strategy_by_weight", prefixes)
        ),
        "strategy_portfolio_top_market_by_weight": _identity_key(
            _first_text_field(row, "top_market_by_weight", prefixes)
        ),
        "strategy_portfolio_max_strategy_allocation_weight": _first_number_field(
            row,
            "max_strategy_allocation_weight",
            prefixes,
        ),
        "strategy_portfolio_max_market_allocation_weight": _first_number_field(
            row,
            "max_market_allocation_weight",
            prefixes,
        ),
        "pre_portfolio_max_notional_per_session": _first_number_field(
            row,
            "pre_portfolio_max_notional_per_session",
            prefixes,
            allow_unprefixed=True,
        ),
    }
    fields.update(_strategy_portfolio_leadlag_state(row, prefixes))
    return fields


def _strategy_portfolio_leadlag_state(
    row: pd.Series,
    prefixes: tuple[str, ...],
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "strategy_portfolio_leadlag_edge_lineage_required": _first_bool_field(
            row,
            "leadlag_edge_lineage_required",
            prefixes,
        ),
        "strategy_portfolio_leadlag_edge_lineage_matches_scaleup": _first_bool_field(
            row,
            "leadlag_edge_lineage_matches_scaleup",
            prefixes,
        ),
    }
    for field in LEADLAG_LINEAGE_BOOLEAN_FIELDS:
        fields[f"strategy_portfolio_{field}"] = _first_bool_field(
            row,
            field,
            prefixes,
        )
    for field in LEADLAG_LINEAGE_INTEGER_FIELDS:
        fields[f"strategy_portfolio_{field}"] = int(
            _first_number_field(row, field, prefixes)
        )
    for field in LEADLAG_LINEAGE_TEXT_FIELDS:
        fields[f"strategy_portfolio_{field}"] = _first_text_field(
            row,
            field,
            prefixes,
        )
    for field in LEADLAG_LINEAGE_NUMERIC_FIELDS:
        fields[f"strategy_portfolio_{field}"] = _first_number_field(
            row,
            field,
            prefixes,
        )
    return fields


def _first_bool_field(row: pd.Series, suffix: str, prefixes: tuple[str, ...]) -> bool:
    value = _first_existing_field(row, suffix, prefixes)
    return _to_bool(value)


def _first_text_field(row: pd.Series, suffix: str, prefixes: tuple[str, ...]) -> str:
    value = _first_existing_field(row, suffix, prefixes)
    return _first_text(value)


def _first_number_field(
    row: pd.Series,
    suffix: str,
    prefixes: tuple[str, ...],
    *,
    allow_unprefixed: bool = False,
) -> float:
    value = _first_existing_field(row, suffix, prefixes, allow_unprefixed=allow_unprefixed)
    if _is_missing(value):
        return 0.0
    numeric = pd.to_numeric(value, errors="coerce")
    return 0.0 if _is_missing(numeric) else float(numeric)


def _first_existing_field(
    row: pd.Series,
    suffix: str,
    prefixes: tuple[str, ...],
    *,
    allow_unprefixed: bool = False,
) -> object:
    if row.empty:
        return None
    names = [f"{prefix}_{suffix}" for prefix in prefixes]
    if allow_unprefixed:
        names.append(suffix)
    for name in names:
        if name in row.index and not _is_missing(row.get(name)):
            return row.get(name)
    return None


def _operator_state(review: pd.DataFrame, scaleup: dict[str, Any]) -> dict[str, Any]:
    row = review.iloc[-1] if not review.empty else pd.Series(dtype=object)
    strategy = _strategy_key(_first_text(row.get("strategy", ""), row.get("approved_strategy", ""), row.get("ack_strategy", "")))
    market = _identity_key(_first_text(row.get("market", ""), row.get("approved_market", ""), row.get("ack_market", "")))
    limits_ack = _to_bool(row.get("limits_acknowledged", row.get("risk_limits_acknowledged", False)))
    if not limits_ack:
        acknowledged_orders = _number(row, "max_orders_per_session", fallback=None)
        acknowledged_notional = _number(row, "max_notional_per_session", fallback=None)
        limits_ack = (
            acknowledged_orders == float(scaleup["max_orders_per_session"])
            and acknowledged_notional == float(scaleup["max_notional_per_session"])
        )
    return {
        "provided": not review.empty,
        "approved": _operator_approved(row),
        "strategy": strategy,
        "market": market,
        "identity_ack": bool(strategy and market and strategy == scaleup["strategy"] and market == scaleup["market"]),
        "limits_ack": bool(limits_ack),
    }


def _operator_approved(row: pd.Series) -> bool:
    if row.empty:
        return False
    for column in ("approved", "cutover_approved", "allow_cutover"):
        if column in row.index:
            return _to_bool(row[column])
    return False


def _operator_approval_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_operator_approval or thresholds.target_mode == "live_dryrun")


def _operator_identity_ack_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_operator_identity_ack or thresholds.target_mode == "live_dryrun")


def _operator_limits_ack_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_operator_limits_ack or thresholds.target_mode == "live_dryrun")


def _route_readiness_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_route_readiness or thresholds.target_mode == "live_dryrun")


def _dispatch_roundtrip_required(thresholds: CutoverGateThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_dispatch_roundtrip_active(dispatch_roundtrip_required: bool, source: dict[str, Any]) -> bool:
    return bool(
        dispatch_roundtrip_required
        or source["route_dispatch_roundtrip_required"]
        or source["route_dispatch_roundtrip_provided"]
    )


def _read_required(path: str | Path, name: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"required cutover input not found: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required cutover input is empty: {name}")
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


def _sidecar_path(path: str | Path | None, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    if candidate.is_dir():
        direct = candidate / filename
        if direct.exists():
            return direct
        return next(
            (nested for folder in fallback_dirs if (nested := candidate / folder / filename).exists()),
            None,
        )
    file_path = candidate if candidate.name == filename else candidate.with_name(filename)
    return file_path if file_path.exists() else None


def _optional_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    return pd.DataFrame() if frame is None else frame.copy().reset_index(drop=True)


def _require_nonempty(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty:
        raise ValueError(f"{name} is empty")
    return frame.copy().reset_index(drop=True)


def _failed_scaleup_checks(row: pd.Series, checks: pd.DataFrame) -> int:
    if "failed_checks" in row.index and not _is_missing(row["failed_checks"]):
        return int(float(row["failed_checks"]))
    if checks.empty or "passed" not in checks.columns:
        return 0
    return int((~checks["passed"].map(_to_bool)).sum())


def _proof_active(row: pd.Series, proof: dict[str, Any]) -> bool:
    return any(
        _to_bool(value)
        for value in (
            proof.get("required", False),
            proof.get("provided", False),
            proof.get("ready", False),
            proof.get("mixed_identity", False),
            row.get("proof_refresh_provided", False),
            row.get("proof_refresh_ready", False),
            row.get("proof_refresh_mixed_identity", False),
        )
    ) or any(
        _object_text(value)
        for value in (
            proof.get("strategy", ""),
            proof.get("market", ""),
            proof.get("proof_source", ""),
            row.get("proof_refresh_strategy", ""),
            row.get("proof_refresh_market", ""),
            row.get("proof_source", ""),
        )
    )


def _validate_thresholds(thresholds: CutoverGateThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_failed_scaleup_checks < 0:
        raise ValueError("max_failed_scaleup_checks must be non-negative")


def _number(row: pd.Series, column: str, fallback: float | None = 0.0) -> float | None:
    if row.empty or column not in row.index:
        return fallback
    value = pd.to_numeric(row[column], errors="coerce")
    if pd.isna(value):
        return fallback
    return float(value)


def _number_from(mapping: dict[str, Any], key: str, fallback: float | None) -> float:
    value = mapping.get(key, fallback)
    if value is None or _is_missing(value):
        return float(fallback or 0.0)
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
    text = _object_text(value)
    return text.lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _object_text(value: object) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _to_bool(value: object) -> bool:
    if _is_missing(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "ready", "passed", "continue"}
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
