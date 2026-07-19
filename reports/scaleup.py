from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import (
    file_sha256,
    manifest_dependency_paths,
    verify_experiment_manifest,
    write_experiment_manifest,
)


STRATEGY_PORTFOLIO_REQUIRED_ARTIFACTS = (
    "strategy_portfolio_allocations.csv",
    "strategy_portfolio_checks.csv",
    "strategy_portfolio_summary.csv",
    "strategy_portfolio_action_queue.csv",
    "strategy_portfolio_config.json",
    "strategy_portfolio_runbook.md",
)
STRATEGY_SCORECARD_REQUIRED_ARTIFACTS = (
    "strategy_scorecard.csv",
    "strategy_scorecard_gaps.csv",
    "strategy_scorecard_summary.csv",
    "strategy_scorecard_action_queue.csv",
    "strategy_scorecard_next_actions.json",
    "strategy_scorecard_runbook.md",
)
RESEARCH_FAMILY_REQUIRED_ARTIFACTS = (
    "research_family_studies.csv",
    "research_family_checks.csv",
    "research_family_summary.csv",
    "research_family_action_queue.csv",
    "research_family_launch_attempt_census.csv",
    "research_family_config.json",
    "research_family_runbook.md",
)


LAUNCH_PIPELINE_SUMMARIES: tuple[tuple[str, str], ...] = (
    ("leadlag", "leadlag_launch_pipeline_summary.csv"),
    ("imbalance", "imbalance_launch_pipeline_summary.csv"),
    ("parity", "parity_launch_pipeline_summary.csv"),
    ("settlement", "settlement_launch_pipeline_summary.csv"),
    ("surface_mm", "surface_mm_launch_pipeline_summary.csv"),
)

ROUTE_READINESS_RESUME_ROUTE_BREACH_PAIR_FIELDS: tuple[str, ...] = (
    "ops_broker_roundtrip_resume_route_breach_pairs",
    "ops_broker_roundtrip_resume_route_gap_breach_pairs",
    "ops_broker_roundtrip_resume_route_launch_control_breach_pairs",
    "ops_broker_roundtrip_resume_route_portfolio_breach_pairs",
    "ops_broker_roundtrip_resume_route_concentration_breach_pairs",
)

ROUTE_READINESS_PROVIDER_SIDECAR_BREACH_PAIR_FIELDS: tuple[str, ...] = (
    "ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
)

BROKER_ROUTE_READINESS_RESUME_ROUTE_RUN_FIELDS: tuple[str, ...] = (
    "ops_broker_roundtrip_resume_route_ready_runs",
    "ops_broker_roundtrip_resume_route_breach_runs",
    "ops_broker_roundtrip_resume_route_gap_breach_runs",
    "ops_broker_roundtrip_resume_route_launch_control_breach_runs",
    "ops_broker_roundtrip_resume_route_portfolio_breach_runs",
    "ops_broker_roundtrip_resume_route_concentration_breach_runs",
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
BROKER_READINESS_FINAL_LINEAGE_COMPARISON_KEY = (
    "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_FINAL_LINEAGE_FIELD_PREFIX = (
    "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
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
)
SCALEUP_FINAL_LINEAGE_COMPARISON_KEY = (
    "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    *BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS,
    "broker_readiness_review_carried_application_lineage_sha256",
    "scaleup_final_review_carried_application_lineage_sha256",
    "cutover_final_review_carried_application_lineage_sha256",
    "route_final_review_carried_application_lineage_sha256",
    "dispatch_final_review_carried_application_lineage_sha256",
    "send_final_review_carried_application_lineage_sha256",
    "ack_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX = (
    "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX = (
    "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS: tuple[str, ...] = (
    *BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "scaleup_complete_final_review_carried_application_lineage_sha256",
    "cutover_complete_final_review_carried_application_lineage_sha256",
    "route_complete_final_review_carried_application_lineage_sha256",
    "dispatch_complete_final_review_carried_application_lineage_sha256",
    "send_complete_final_review_carried_application_lineage_sha256",
    "ack_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
)
BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_COMPARISON_KEY = (
    "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_FIELD_PREFIX = (
    "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_SUMMARY_FIELD_PREFIX = (
    "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS: tuple[
    str, ...
] = (
    *BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY = (
    "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_COMPARISON_KEY = (
    "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_COMPARISON_KEY = (
    "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_FIELD_PREFIX = (
    "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_SUMMARY_FIELD_PREFIX = (
    "roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS: tuple[
    str, ...
] = (
    *BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS,
    "route_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    "send_extended_complete_final_review_carried_application_lineage_sha256",
    "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS: tuple[
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
SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_COMPARISON_KEY = (
    "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_COMPARISON_KEY = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_FIELD_PREFIX = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_SUMMARY_FIELD_PREFIX = (
    "roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS: tuple[
    str, ...
] = BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS: tuple[
    str, ...
] = BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS: tuple[
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
BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_COMPARISON_KEY = (
    "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_COMPARISON_KEY = (
    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_FIELD_PREFIX = (
    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_SUMMARY_FIELD_PREFIX = (
    "roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS: tuple[
    str, ...
] = BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS: tuple[
    str, ...
] = BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS: tuple[
    str, ...
] = BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS: tuple[
    str, ...
] = (
    "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD = (
    "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD = (
    "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD = (
    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
)
SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_COMPARISON_KEY = (
    "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
)


@dataclass(frozen=True)
class ScaleUpThresholds:
    target_mode: str = "shadow"
    max_scale_multiplier: float = 1.0
    min_shadow_sessions: int = 1
    min_shadow_acceptance_rate: float = 1.0
    min_median_order_fill_rate: float = 0.0
    min_worst_order_fill_rate: float | None = None
    max_worst_adverse_slippage: float | None = None
    max_total_failed_component_checks: int = 0
    max_total_unmatched_fills: int = 0
    max_total_mismatched_orders: int = 0
    max_total_overfilled_orders: int = 0
    max_telemetry_age_ns: float | None = None
    max_lifecycle_orders: int | None = None
    max_replace_orders: int | None = None
    max_open_order_count: int | None = None
    max_open_order_qty: float | None = None
    max_open_order_notional: float | None = None
    max_open_order_age_ns: float | None = None
    max_gross_position_qty: float | None = None
    max_abs_net_position_qty: float | None = None
    max_orders_per_session: int | None = None
    max_session_notional: float | None = None
    max_gross_notional: float | None = None
    max_abs_net_delta: float | None = None
    max_abs_net_vega: float | None = None
    stop_loss: float | None = None
    allowed_adapters: tuple[str, ...] = ()
    require_proof_refresh: bool = False
    require_instrument_metadata: bool = False
    require_data_readiness: bool = False
    require_data_readiness_comparison: bool = False
    require_strategy_portfolio: bool = False
    require_route_readiness: bool = False
    require_broker_readiness: bool = False
    require_resume_gate: bool = False
    require_dispatch_roundtrip: bool = False
    min_instrument_parse_coverage: float = 1.0
    expected_strategy: str | None = None
    expected_market: str | None = None


@dataclass(frozen=True)
class ScaleUpPlanReport:
    plan: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def evaluate_scaleup_plan(
    *,
    evidence_summary: pd.DataFrame,
    shadow_comparison_summary: pd.DataFrame,
    launch_summary: pd.DataFrame,
    order_exposure_summary: pd.DataFrame | None = None,
    proof_refresh_summary: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    data_readiness_summary: pd.DataFrame | None = None,
    data_readiness_comparison_summary: pd.DataFrame | None = None,
    strategy_portfolio_summary: pd.DataFrame | None = None,
    strategy_portfolio_allocations: pd.DataFrame | None = None,
    route_readiness_summary: pd.DataFrame | None = None,
    broker_readiness_summary: pd.DataFrame | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ScaleUpPlanReport:
    return _evaluate_scaleup_plan(
        evidence_summary=evidence_summary,
        shadow_comparison_summary=shadow_comparison_summary,
        launch_summary=launch_summary,
        order_exposure_summary=order_exposure_summary,
        proof_refresh_summary=proof_refresh_summary,
        instrument_metadata_summary=instrument_metadata_summary,
        data_readiness_summary=data_readiness_summary,
        data_readiness_comparison_summary=data_readiness_comparison_summary,
        strategy_portfolio_summary=strategy_portfolio_summary,
        strategy_portfolio_allocations=strategy_portfolio_allocations,
        route_readiness_summary=route_readiness_summary,
        broker_readiness_summary=broker_readiness_summary,
        thresholds=thresholds,
        strategy_portfolio_provenance=None,
    )


def _evaluate_scaleup_plan(
    *,
    evidence_summary: pd.DataFrame,
    shadow_comparison_summary: pd.DataFrame,
    launch_summary: pd.DataFrame,
    order_exposure_summary: pd.DataFrame | None = None,
    proof_refresh_summary: pd.DataFrame | None = None,
    instrument_metadata_summary: pd.DataFrame | None = None,
    data_readiness_summary: pd.DataFrame | None = None,
    data_readiness_comparison_summary: pd.DataFrame | None = None,
    strategy_portfolio_summary: pd.DataFrame | None = None,
    strategy_portfolio_allocations: pd.DataFrame | None = None,
    route_readiness_summary: pd.DataFrame | None = None,
    broker_readiness_summary: pd.DataFrame | None = None,
    thresholds: ScaleUpThresholds | None = None,
    strategy_portfolio_provenance: dict[str, Any] | None = None,
) -> ScaleUpPlanReport:
    thresholds = thresholds or ScaleUpThresholds()
    _validate_thresholds(thresholds)
    _require(evidence_summary, ["ready"], "strategy_evidence_summary")
    _require(shadow_comparison_summary, ["accepted", "session_count", "acceptance_rate"], "shadow_comparison_summary")
    _require(launch_summary, ["ready", "mode", "adapter", "scenario_key", "accepted_orders"], "launch_summary")
    exposure = order_exposure_summary if order_exposure_summary is not None else pd.DataFrame()
    proof_refresh = proof_refresh_summary if proof_refresh_summary is not None else pd.DataFrame()
    instrument_metadata = instrument_metadata_summary if instrument_metadata_summary is not None else pd.DataFrame()
    data_readiness = data_readiness_summary if data_readiness_summary is not None else pd.DataFrame()
    data_readiness_comparison = (
        data_readiness_comparison_summary if data_readiness_comparison_summary is not None else pd.DataFrame()
    )
    strategy_portfolio = strategy_portfolio_summary if strategy_portfolio_summary is not None else pd.DataFrame()
    strategy_portfolio_allocations = (
        strategy_portfolio_allocations if strategy_portfolio_allocations is not None else pd.DataFrame()
    )
    route_readiness = route_readiness_summary if route_readiness_summary is not None else pd.DataFrame()
    broker_readiness = broker_readiness_summary if broker_readiness_summary is not None else pd.DataFrame()
    strategy_portfolio_state = _strategy_portfolio_state(
        strategy_portfolio,
        strategy_portfolio_allocations,
        evidence_summary.iloc[0],
        thresholds,
        provenance=strategy_portfolio_provenance,
    )

    rows = {
        "evidence": evidence_summary.iloc[0],
        "shadow": shadow_comparison_summary.iloc[0],
        "launch": launch_summary.iloc[0],
        "exposure": exposure.iloc[0] if not exposure.empty else pd.Series(dtype=object),
        "proof_refresh": proof_refresh.iloc[0] if not proof_refresh.empty else pd.Series(dtype=object),
        "instrument_metadata": instrument_metadata.iloc[0] if not instrument_metadata.empty else pd.Series(dtype=object),
        "data_readiness": data_readiness.iloc[0] if not data_readiness.empty else pd.Series(dtype=object),
        "data_readiness_comparison": data_readiness_comparison.iloc[0]
        if not data_readiness_comparison.empty
        else pd.Series(dtype=object),
        "strategy_portfolio": strategy_portfolio_state,
        "route_readiness": route_readiness.iloc[0] if not route_readiness.empty else pd.Series(dtype=object),
        "broker_readiness": broker_readiness.iloc[0] if not broker_readiness.empty else pd.Series(dtype=object),
    }
    checks = _checks(rows, thresholds)
    ready = bool(checks["passed"].all()) if not checks.empty else False
    plan = _plan(rows, thresholds, ready)
    summary = _summary(plan.iloc[0], checks)
    config = _config(plan.iloc[0], checks, thresholds)
    return ScaleUpPlanReport(plan=plan, checks=checks, summary=summary, config=config)


def write_scaleup_plan(
    *,
    evidence_dir: str | Path,
    shadow_comparison_dir: str | Path,
    launch_dir: str | Path,
    output_dir: str | Path,
    order_exposure_dir: str | Path | None = None,
    proof_refresh_dir: str | Path | None = None,
    instrument_metadata_dir: str | Path | None = None,
    data_readiness_dir: str | Path | None = None,
    data_readiness_comparison_dir: str | Path | None = None,
    strategy_portfolio_dir: str | Path | None = None,
    route_readiness_dir: str | Path | None = None,
    broker_readiness_dir: str | Path | None = None,
    thresholds: ScaleUpThresholds | None = None,
) -> ScaleUpPlanReport:
    evidence_path = _summary_path(evidence_dir, "strategy_evidence_summary.csv")
    shadow_path = _summary_path(shadow_comparison_dir, "shadow_session_comparison_summary.csv")
    launch_path = _summary_path(launch_dir, "launch_summary.csv", fallback_dirs=("03_launch", "02_launch"))
    launch_pipeline_path = _launch_pipeline_summary_path(launch_dir)
    exposure_path = _optional_summary_input(order_exposure_dir, "order_exposure_summary.csv")
    proof_refresh_path = _optional_summary_input(proof_refresh_dir, "proof_refresh_summary.csv")
    instrument_metadata_path = _optional_summary_input(instrument_metadata_dir, "instrument_metadata_summary.csv")
    data_readiness_path = _optional_summary_input(data_readiness_dir, "data_readiness_summary.csv")
    data_readiness_comparison_path = _optional_summary_input(
        data_readiness_comparison_dir,
        "data_readiness_comparison_summary.csv",
    )
    strategy_portfolio_path = _optional_summary_input(strategy_portfolio_dir, "strategy_portfolio_summary.csv")
    strategy_portfolio_allocations_path = _optional_summary_input(
        strategy_portfolio_dir,
        "strategy_portfolio_allocations.csv",
    )
    vendor_market_data_batch_config_path = _optional_vendor_market_data_batch_config(
        data_readiness_comparison_path or data_readiness_comparison_dir
    )
    route_readiness_path = _optional_summary_input(route_readiness_dir, "route_readiness_summary.csv")

    evidence = _read_summary(evidence_path, "strategy_evidence_summary.csv")
    shadow = _read_summary(shadow_path, "shadow_session_comparison_summary.csv")
    launch = _read_summary(launch_path, "launch_summary.csv")
    launch_pipeline = (
        _read_launch_pipeline_summary(launch_pipeline_path)
        if launch_pipeline_path is not None
        else None
    )
    launch = _with_launch_pipeline_identity(
        launch,
        launch_pipeline,
    )
    exposure = _read_optional_summary(exposure_path, "order_exposure_summary.csv") if exposure_path else None
    proof_refresh = (
        _read_optional_summary(proof_refresh_path, "proof_refresh_summary.csv") if proof_refresh_path else None
    )
    instrument_metadata = (
        _read_optional_summary(instrument_metadata_path, "instrument_metadata_summary.csv")
        if instrument_metadata_path
        else None
    )
    resolved_broker_readiness_dir = broker_readiness_dir or _auto_broker_readiness_dir(launch_dir)
    broker_readiness_path = _optional_summary_input(
        resolved_broker_readiness_dir,
        "broker_readiness_summary.csv",
    )
    broker_readiness_config_path = _optional_sidecar_input(
        resolved_broker_readiness_dir,
        "broker_readiness_config.json",
    )
    broker_readiness = (
        _read_optional_summary(broker_readiness_path, "broker_readiness_summary.csv")
        if broker_readiness_path
        else None
    )
    if broker_readiness is None or broker_readiness.empty:
        broker_readiness = _broker_readiness_from_launch_pipeline_summary(launch_pipeline)
    if broker_readiness_config_path is not None:
        broker_readiness = _with_broker_vendor_market_data_batch_config(
            broker_readiness,
            json.loads(broker_readiness_config_path.read_text(encoding="utf-8")),
        )
    data_readiness = (
        _read_optional_summary(data_readiness_path, "data_readiness_summary.csv")
        if data_readiness_path
        else None
    )
    data_readiness_comparison = (
        _read_optional_summary(data_readiness_comparison_path, "data_readiness_comparison_summary.csv")
        if data_readiness_comparison_path
        else None
    )
    strategy_portfolio = (
        _read_optional_summary(strategy_portfolio_path, "strategy_portfolio_summary.csv")
        if strategy_portfolio_path
        else None
    )
    strategy_portfolio_allocations = (
        _read_optional_summary(strategy_portfolio_allocations_path, "strategy_portfolio_allocations.csv")
        if strategy_portfolio_allocations_path
        else None
    )
    strategy_portfolio_provenance = load_strategy_portfolio_provenance(
        strategy_portfolio_path,
        strategy_portfolio,
        strategy_portfolio_allocations,
    )
    route_readiness = (
        _read_optional_summary(route_readiness_path, "route_readiness_summary.csv")
        if route_readiness_path
        else None
    )
    thresholds = thresholds or ScaleUpThresholds()
    report = _evaluate_scaleup_plan(
        evidence_summary=evidence,
        shadow_comparison_summary=shadow,
        launch_summary=launch,
        order_exposure_summary=exposure,
        proof_refresh_summary=proof_refresh,
        instrument_metadata_summary=instrument_metadata,
        data_readiness_summary=data_readiness,
        data_readiness_comparison_summary=data_readiness_comparison,
        strategy_portfolio_summary=strategy_portfolio,
        strategy_portfolio_allocations=strategy_portfolio_allocations,
        route_readiness_summary=route_readiness,
        broker_readiness_summary=broker_readiness,
        thresholds=thresholds,
        strategy_portfolio_provenance=strategy_portfolio_provenance,
    )
    if vendor_market_data_batch_config_path is not None:
        _apply_vendor_market_data_batch_config(
            report.config,
            json.loads(vendor_market_data_batch_config_path.read_text(encoding="utf-8")),
        )
    out = Path(output_dir)
    if (
        strategy_portfolio_provenance.get("manifest_provided", False)
        and out.resolve()
        == Path(str(strategy_portfolio_provenance["root"])).resolve()
    ):
        raise ValueError(
            "scale-up output must not overwrite the source strategy "
            "portfolio bundle"
        )
    out.mkdir(parents=True, exist_ok=True)
    report.plan.to_csv(out / "scaleup_plan.csv", index=False)
    report.checks.to_csv(out / "scaleup_checks.csv", index=False)
    report.summary.to_csv(out / "scaleup_summary.csv", index=False)
    (out / "scaleup_config.json").write_text(json.dumps(report.config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inputs: dict[str, Any] = {
        "evidence": evidence_path,
        "shadow_comparison": shadow_path,
        "launch": launch_path,
    }
    if launch_pipeline_path is not None:
        inputs["launch_pipeline"] = launch_pipeline_path
    if exposure_path is not None:
        inputs["order_exposure"] = exposure_path
    if proof_refresh_path is not None:
        inputs["proof_refresh"] = proof_refresh_path
    if instrument_metadata_path is not None:
        inputs["instrument_metadata"] = instrument_metadata_path
    if data_readiness_path is not None:
        inputs["data_readiness"] = data_readiness_path
    if data_readiness_comparison_path is not None:
        inputs["data_readiness_comparison"] = data_readiness_comparison_path
    if strategy_portfolio_path is not None:
        inputs["strategy_portfolio"] = strategy_portfolio_path
    if strategy_portfolio_allocations_path is not None:
        inputs["strategy_portfolio_allocations"] = strategy_portfolio_allocations_path
    if strategy_portfolio_provenance.get("manifest_provided", False):
        portfolio_root = Path(str(strategy_portfolio_provenance["root"]))
        inputs["strategy_portfolio_manifest"] = Path(
            str(strategy_portfolio_provenance["manifest_path"])
        )
        for artifact in STRATEGY_PORTFOLIO_REQUIRED_ARTIFACTS:
            artifact_path = portfolio_root / artifact
            if artifact_path.is_file() and artifact not in {
                "strategy_portfolio_summary.csv",
                "strategy_portfolio_allocations.csv",
            }:
                inputs[f"strategy_portfolio_artifact:{artifact}"] = artifact_path
        dependency_paths = [
            Path(str(path))
            for path in strategy_portfolio_provenance.get(
                "dependency_paths",
                [],
            )
            if str(path).strip()
        ]
        if dependency_paths:
            inputs["strategy_portfolio_dependencies"] = dependency_paths
    if vendor_market_data_batch_config_path is not None:
        inputs["vendor_market_data_batch_config"] = vendor_market_data_batch_config_path
    if route_readiness_path is not None:
        inputs["route_readiness"] = route_readiness_path
    if broker_readiness_path is not None:
        inputs["broker_readiness"] = broker_readiness_path
    if broker_readiness_config_path is not None:
        inputs["broker_readiness_config"] = broker_readiness_config_path
    write_experiment_manifest(
        out,
        run_type="scaleup_plan",
        parameters={"thresholds": asdict(thresholds)},
        inputs=inputs,
        extra={
            "ready": bool(report.ready),
            "strategy_portfolio_manifest_required": bool(
                strategy_portfolio_provenance.get(
                    "manifest_required",
                    False,
                )
            ),
            "strategy_portfolio_manifest_current": bool(
                strategy_portfolio_provenance.get(
                    "manifest_current",
                    False,
                )
            ),
            "strategy_portfolio_manifest_sha256": str(
                strategy_portfolio_provenance.get("manifest_sha256", "")
            ),
            "research_family_bound": bool(
                strategy_portfolio_provenance.get(
                    "research_family_bound",
                    False,
                )
            ),
            "research_family_id": str(
                strategy_portfolio_provenance.get("research_family_id", "")
            ),
            "research_family_registration_id": str(
                strategy_portfolio_provenance.get(
                    "research_family_registration_id",
                    "",
                )
            ),
            "research_family_manifest_sha256": str(
                strategy_portfolio_provenance.get(
                    "research_family_manifest_sha256",
                    "",
                )
            ),
            "authorizes_submission": False,
        },
    )
    return ScaleUpPlanReport(report.plan, report.checks, report.summary, report.config, out)


def _checks(rows: dict[str, pd.Series], thresholds: ScaleUpThresholds) -> pd.DataFrame:
    evidence = rows["evidence"]
    shadow = rows["shadow"]
    launch = rows["launch"]
    exposure = rows["exposure"]
    proof_refresh = rows["proof_refresh"]
    instrument_metadata = rows["instrument_metadata"]
    data_readiness = rows["data_readiness"]
    data_readiness_comparison = rows["data_readiness_comparison"]
    strategy_portfolio = rows["strategy_portfolio"]
    route_readiness = rows["route_readiness"]
    broker_readiness = rows["broker_readiness"]
    adapter = str(launch.get("adapter", ""))
    scenario_match = str(launch.get("scenario_key", "")) == str(shadow.get("scenario_key", launch.get("scenario_key", "")))
    evidence_strategy = _strategy_key(evidence.get("strategy", ""))
    evidence_market = _identity_key(evidence.get("market", ""))
    expected_proof_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
    expected_proof_market = _identity_key(thresholds.expected_market) or evidence_market
    checks = [
        _check("evidence_ready", _to_bool(evidence.get("ready", False)), "is", True, _to_bool(evidence.get("ready", False)), "strategy evidence review is not ready"),
        _check("shadow_comparison_accepted", _to_bool(shadow.get("accepted", False)), "is", True, _to_bool(shadow.get("accepted", False)), "shadow comparison is not accepted"),
        _check("launch_ready", _to_bool(launch.get("ready", False)), "is", True, _to_bool(launch.get("ready", False)), "launch bundle is not ready"),
        _check("scenario_match", scenario_match, "is", True, scenario_match, "launch and shadow scenario keys differ"),
        _threshold_check("session_count", _number(shadow, "session_count"), ">=", thresholds.min_shadow_sessions),
        _threshold_check("acceptance_rate", _number(shadow, "acceptance_rate"), ">=", thresholds.min_shadow_acceptance_rate),
        _threshold_check("median_order_fill_rate", _number(shadow, "median_order_fill_rate"), ">=", thresholds.min_median_order_fill_rate),
        _threshold_check("total_failed_component_checks", _number(shadow, "total_failed_component_checks"), "<=", thresholds.max_total_failed_component_checks),
        _threshold_check("total_unmatched_fills", _number(shadow, "total_unmatched_fills"), "<=", thresholds.max_total_unmatched_fills),
        _threshold_check("total_mismatched_orders", _number(shadow, "total_mismatched_orders"), "<=", thresholds.max_total_mismatched_orders),
        _threshold_check("total_overfilled_orders", _number(shadow, "total_overfilled_orders"), "<=", thresholds.max_total_overfilled_orders),
    ]
    if thresholds.expected_strategy is not None:
        expected_strategy = _strategy_key(thresholds.expected_strategy)
        checks.append(
            _check(
                "evidence_strategy_matches",
                evidence_strategy,
                "==",
                expected_strategy,
                bool(evidence_strategy and evidence_strategy == expected_strategy),
                "strategy evidence identity does not match expected strategy",
            )
        )
    if thresholds.expected_market is not None:
        expected_market = _identity_key(thresholds.expected_market)
        checks.append(
            _check(
                "evidence_market_matches",
                evidence_market,
                "==",
                expected_market,
                bool(evidence_market and evidence_market == expected_market),
                "strategy evidence identity does not match expected market",
            )
        )
    if _to_bool(launch.get("launch_pipeline_provided", False)) and not _to_bool(
        launch.get("surface_launch_pipeline_provided", False)
    ):
        launch_pipeline_ready = _to_bool(launch.get("launch_pipeline_ready", False))
        launch_pipeline_strategy = _strategy_key(launch.get("launch_pipeline_strategy", ""))
        launch_pipeline_market = _identity_key(launch.get("launch_pipeline_market", ""))
        checks.append(
            _check(
                "launch_pipeline_ready",
                launch_pipeline_ready,
                "is",
                True,
                launch_pipeline_ready,
                "launch pipeline root summary is not ready",
            )
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "launch_pipeline_strategy_matches",
                    launch_pipeline_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(launch_pipeline_strategy and launch_pipeline_strategy == expected_proof_strategy),
                    "launch pipeline strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "launch_pipeline_market_matches",
                    launch_pipeline_market,
                    "==",
                    expected_proof_market,
                    bool(launch_pipeline_market and launch_pipeline_market == expected_proof_market),
                    "launch pipeline market does not match scale-up market",
                )
            )
    if _to_bool(launch.get("surface_launch_pipeline_provided", False)):
        surface_launch_ready = _to_bool(launch.get("surface_launch_pipeline_ready", False))
        surface_launch_strategy = _strategy_key(launch.get("surface_launch_strategy", ""))
        surface_launch_market = _identity_key(launch.get("surface_launch_market", ""))
        checks.append(
            _check(
                "surface_launch_pipeline_ready",
                surface_launch_ready,
                "is",
                True,
                surface_launch_ready,
                "surface launch pipeline root summary is not ready",
            )
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "surface_launch_strategy_matches",
                    surface_launch_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(surface_launch_strategy and surface_launch_strategy == expected_proof_strategy),
                    "surface launch pipeline strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "surface_launch_market_matches",
                    surface_launch_market,
                    "==",
                    expected_proof_market,
                    bool(surface_launch_market and surface_launch_market == expected_proof_market),
                    "surface launch pipeline market does not match scale-up market",
                )
            )
    if thresholds.allowed_adapters:
        checks.append(
            _check(
                "adapter_allowed",
                adapter,
                "in",
                ";".join(thresholds.allowed_adapters),
                adapter in thresholds.allowed_adapters,
                "launch adapter is not in allowed adapter list",
            )
        )
    if thresholds.min_worst_order_fill_rate is not None:
        checks.append(_threshold_check("worst_order_fill_rate", _number(shadow, "worst_order_fill_rate"), ">=", thresholds.min_worst_order_fill_rate))
    if thresholds.max_worst_adverse_slippage is not None:
        checks.append(_threshold_check("worst_adverse_slippage", _number(shadow, "worst_adverse_slippage"), "<=", thresholds.max_worst_adverse_slippage))
    if thresholds.max_orders_per_session is not None:
        checks.append(_threshold_check("accepted_orders", _number(launch, "accepted_orders"), "<=", thresholds.max_orders_per_session))
    if thresholds.max_session_notional is not None:
        checks.append(_threshold_check("launch_total_notional", _number(launch, "total_notional"), "<=", thresholds.max_session_notional))
    shadow_proof_sessions = int(_number(shadow, "runtime_proof_refresh_sessions", fallback=0.0))
    if shadow_proof_sessions > 0:
        shadow_proof_strategy = _strategy_key(shadow.get("proof_refresh_strategy", ""))
        shadow_proof_market = _identity_key(shadow.get("proof_refresh_market", ""))
        checks.extend(
            [
                _check(
                    "shadow_proof_refresh_ready",
                    int(_number(shadow, "runtime_proof_refresh_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_proof_sessions,
                    int(_number(shadow, "runtime_proof_refresh_ready_sessions", fallback=0.0))
                    == shadow_proof_sessions,
                    "not every accepted shadow runtime proof-refresh evidence item is ready",
                ),
                _check(
                    "shadow_proof_refresh_identity_consistent",
                    int(_number(shadow, "runtime_proof_refresh_mixed_identity_sessions", fallback=0.0)),
                    "==",
                    0,
                    int(_number(shadow, "runtime_proof_refresh_mixed_identity_sessions", fallback=0.0)) == 0,
                    "shadow comparison reported mixed proof-refresh identity",
                ),
            ]
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "shadow_proof_refresh_strategy_matches",
                    shadow_proof_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(shadow_proof_strategy and shadow_proof_strategy == expected_proof_strategy),
                    "shadow proof-refresh strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "shadow_proof_refresh_market_matches",
                    shadow_proof_market,
                    "==",
                    expected_proof_market,
                    bool(shadow_proof_market and shadow_proof_market == expected_proof_market),
                    "shadow proof-refresh market does not match scale-up market",
                )
            )
    shadow_broker_sessions = int(_number(shadow, "broker_readiness_sessions", fallback=0.0))
    if shadow_broker_sessions > 0:
        accepted_sessions = int(_number(shadow, "accepted_sessions", fallback=0.0))
        checks.extend(
            [
                _check(
                    "shadow_broker_readiness_present_for_accepted_sessions",
                    shadow_broker_sessions,
                    "==",
                    accepted_sessions,
                    shadow_broker_sessions == accepted_sessions,
                    "shadow comparison has broker-readiness proof for only some accepted sessions",
                ),
                _check(
                    "shadow_broker_readiness_ready",
                    int(_number(shadow, "broker_readiness_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_broker_sessions,
                    int(_number(shadow, "broker_readiness_ready_sessions", fallback=0.0))
                    == shadow_broker_sessions,
                    "shadow broker-readiness evidence is not ready for every accepted session",
                ),
                _check(
                    "shadow_broker_adapter_consistent",
                    int(_number(shadow, "broker_adapter_count", fallback=0.0)),
                    "==",
                    1,
                    int(_number(shadow, "broker_adapter_count", fallback=0.0)) == 1
                    and int(_number(shadow, "missing_broker_adapter_sessions", fallback=0.0)) == 0,
                    "shadow broker adapter identity is missing or mixed",
                ),
            ]
        )
    shadow_broker_vendor_sessions = int(_number(shadow, "broker_vendor_data_readiness_sessions", fallback=0.0))
    if shadow_broker_vendor_sessions > 0:
        checks.extend(
            [
                _check(
                    "shadow_broker_vendor_data_readiness_present_for_broker_sessions",
                    shadow_broker_vendor_sessions,
                    "==",
                    shadow_broker_sessions,
                    shadow_broker_vendor_sessions == shadow_broker_sessions,
                    "shadow broker vendor-data wrapper proof is present for only some broker-readiness sessions",
                ),
                _check(
                    "shadow_broker_vendor_data_readiness_provided",
                    int(_number(shadow, "broker_vendor_data_readiness_provided_sessions", fallback=0.0)),
                    "==",
                    shadow_broker_sessions,
                    int(_number(shadow, "broker_vendor_data_readiness_provided_sessions", fallback=0.0))
                    == shadow_broker_sessions,
                    "shadow broker vendor-data wrapper proof is missing for some broker-readiness sessions",
                ),
                _check(
                    "shadow_broker_vendor_data_readiness_ready",
                    int(_number(shadow, "broker_vendor_data_readiness_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_broker_sessions,
                    int(_number(shadow, "broker_vendor_data_readiness_ready_sessions", fallback=0.0))
                    == shadow_broker_sessions,
                    "shadow broker vendor-data wrapper proof is not ready for every broker-readiness session",
                ),
                _threshold_check(
                    "shadow_broker_vendor_data_readiness_failed_checks",
                    _number(shadow, "max_broker_vendor_data_readiness_failed_checks", fallback=0.0),
                    "<=",
                    0,
                ),
            ]
        )
    shadow_broker_route_sessions = int(_number(shadow, "broker_route_readiness_sessions", fallback=0.0))
    if shadow_broker_route_sessions > 0:
        shadow_route_strategy = _strategy_key(shadow.get("broker_route_readiness_strategy", ""))
        shadow_route_market = _identity_key(shadow.get("broker_route_readiness_market", ""))
        checks.extend(
            [
                _check(
                    "shadow_broker_route_readiness_provided",
                    int(_number(shadow, "broker_route_readiness_provided_sessions", fallback=0.0)),
                    ">=",
                    int(_number(shadow, "broker_route_readiness_required_sessions", fallback=0.0)),
                    int(_number(shadow, "broker_route_readiness_provided_sessions", fallback=0.0))
                    >= int(_number(shadow, "broker_route_readiness_required_sessions", fallback=0.0)),
                    "shadow broker route-readiness proof is required but missing for some sessions",
                ),
                _check(
                    "shadow_broker_route_readiness_ready",
                    int(_number(shadow, "broker_route_readiness_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_broker_route_sessions,
                    int(_number(shadow, "broker_route_readiness_ready_sessions", fallback=0.0))
                    == shadow_broker_route_sessions,
                    "shadow broker route-readiness proof is not ready for every session",
                ),
                _check(
                    "shadow_broker_route_readiness_strategy_matches",
                    shadow_route_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(shadow_route_strategy and shadow_route_strategy == expected_proof_strategy),
                    "shadow broker route-readiness strategy does not match scale-up strategy",
                ),
                _check(
                    "shadow_broker_route_readiness_market_matches",
                    shadow_route_market,
                    "==",
                    expected_proof_market,
                    bool(shadow_route_market and shadow_route_market == expected_proof_market),
                    "shadow broker route-readiness market does not match scale-up market",
                ),
                _threshold_check(
                    "shadow_broker_route_readiness_gap_pairs",
                    _number(shadow, "max_broker_route_readiness_gap_pairs", fallback=0.0),
                    "<=",
                    0,
                ),
            ]
        )
    shadow_broker_dispatch_sessions = int(_number(shadow, "broker_dispatch_roundtrip_sessions", fallback=0.0))
    if shadow_broker_dispatch_sessions > 0:
        shadow_dispatch_strategy = _strategy_key(shadow.get("broker_dispatch_roundtrip_strategy", ""))
        shadow_dispatch_market = _identity_key(shadow.get("broker_dispatch_roundtrip_market", ""))
        checks.extend(
            [
                _check(
                    "shadow_broker_dispatch_roundtrip_ready",
                    int(_number(shadow, "broker_dispatch_roundtrip_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_broker_dispatch_sessions,
                    int(_number(shadow, "broker_dispatch_roundtrip_ready_sessions", fallback=0.0))
                    == shadow_broker_dispatch_sessions,
                    "shadow broker dispatch round-trip proof is not ready for every session",
                ),
                _check(
                    "shadow_broker_dispatch_roundtrip_strategy_matches",
                    shadow_dispatch_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(shadow_dispatch_strategy and shadow_dispatch_strategy == expected_proof_strategy),
                    "shadow broker dispatch round-trip strategy does not match scale-up strategy",
                ),
                _check(
                    "shadow_broker_dispatch_roundtrip_market_matches",
                    shadow_dispatch_market,
                    "==",
                    expected_proof_market,
                    bool(shadow_dispatch_market and shadow_dispatch_market == expected_proof_market),
                    "shadow broker dispatch round-trip market does not match scale-up market",
                ),
                _check(
                    "shadow_broker_dispatch_roundtrip_scenario_consistent",
                    int(_number(shadow, "broker_dispatch_roundtrip_scenario_count", fallback=0.0)),
                    "==",
                    1,
                    int(_number(shadow, "broker_dispatch_roundtrip_scenario_count", fallback=0.0)) == 1
                    and int(_number(shadow, "missing_broker_dispatch_roundtrip_scenario_sessions", fallback=0.0))
                    == 0,
                    "shadow broker dispatch round-trip scenario is missing or mixed",
                ),
                _threshold_check(
                    "shadow_broker_dispatch_roundtrip_missing_request_acks",
                    _number(shadow, "max_broker_dispatch_roundtrip_missing_request_acks", fallback=0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "shadow_broker_dispatch_roundtrip_rejected_orders",
                    _number(shadow, "max_broker_dispatch_roundtrip_rejected_orders", fallback=0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "shadow_broker_dispatch_roundtrip_unmatched_acks",
                    _number(shadow, "max_broker_dispatch_roundtrip_unmatched_acks", fallback=0.0),
                    "<=",
                    0,
                ),
            ]
        )
    shadow_broker_route_dispatch_sessions = int(
        _number(shadow, "broker_route_dispatch_roundtrip_sessions", fallback=0.0)
    )
    if shadow_broker_route_dispatch_sessions > 0:
        shadow_route_dispatch_strategy = _strategy_key(shadow.get("broker_route_dispatch_roundtrip_strategy", ""))
        shadow_route_dispatch_market = _identity_key(shadow.get("broker_route_dispatch_roundtrip_market", ""))
        checks.extend(
            [
                _check(
                    "shadow_broker_route_dispatch_roundtrip_ready",
                    int(_number(shadow, "broker_route_dispatch_roundtrip_ready_sessions", fallback=0.0)),
                    "==",
                    shadow_broker_route_dispatch_sessions,
                    int(_number(shadow, "broker_route_dispatch_roundtrip_ready_sessions", fallback=0.0))
                    == shadow_broker_route_dispatch_sessions,
                    "shadow broker route dispatch round-trip proof is not ready for every session",
                ),
                _check(
                    "shadow_broker_route_dispatch_roundtrip_strategy_matches",
                    shadow_route_dispatch_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(
                        shadow_route_dispatch_strategy
                        and shadow_route_dispatch_strategy == expected_proof_strategy
                    ),
                    "shadow broker route dispatch round-trip strategy does not match scale-up strategy",
                ),
                _check(
                    "shadow_broker_route_dispatch_roundtrip_market_matches",
                    shadow_route_dispatch_market,
                    "==",
                    expected_proof_market,
                    bool(shadow_route_dispatch_market and shadow_route_dispatch_market == expected_proof_market),
                    "shadow broker route dispatch round-trip market does not match scale-up market",
                ),
                _check(
                    "shadow_broker_route_dispatch_roundtrip_scenario_consistent",
                    int(_number(shadow, "broker_route_dispatch_roundtrip_scenario_count", fallback=0.0)),
                    "==",
                    1,
                    int(_number(shadow, "broker_route_dispatch_roundtrip_scenario_count", fallback=0.0)) == 1
                    and int(
                        _number(
                            shadow,
                            "missing_broker_route_dispatch_roundtrip_scenario_sessions",
                            fallback=0.0,
                        )
                    )
                    == 0,
                    "shadow broker route dispatch round-trip scenario is missing or mixed",
                ),
            ]
        )
    if not exposure.empty:
        checks.append(_check("order_exposure_passed", _to_bool(exposure.get("passed", False)), "is", True, _to_bool(exposure.get("passed", False)), "order exposure report did not pass"))
        if thresholds.max_gross_notional is not None:
            checks.append(_threshold_check("gross_notional", _number(exposure, "gross_notional"), "<=", thresholds.max_gross_notional))
        if thresholds.max_abs_net_delta is not None:
            checks.append(_threshold_check("abs_net_delta", abs(_number(exposure, "net_delta")), "<=", thresholds.max_abs_net_delta))
        if thresholds.max_abs_net_vega is not None:
            checks.append(_threshold_check("abs_net_vega", abs(_number(exposure, "net_vega")), "<=", thresholds.max_abs_net_vega))
    if thresholds.require_proof_refresh:
        checks.append(
            _check(
                "proof_refresh_available",
                not proof_refresh.empty,
                "is",
                True,
                not proof_refresh.empty,
                "proof refresh gate is required but no proof refresh summary was supplied",
            )
        )
    if not proof_refresh.empty:
        proof_refresh_ready = _to_bool(proof_refresh.get("ready", False))
        proof_refresh_strategy = _strategy_key(proof_refresh.get("strategy", ""))
        proof_refresh_market = _identity_key(proof_refresh.get("market", ""))
        proof_refresh_mixed_identity = _to_bool(proof_refresh.get("mixed_identity", False))
        checks.append(
            _check(
                "proof_refresh_ready",
                proof_refresh_ready,
                "is",
                True,
                proof_refresh_ready,
                "proof refresh gate is not ready",
            )
        )
        checks.append(
            _check(
                "proof_refresh_identity_consistent",
                proof_refresh_mixed_identity,
                "is",
                False,
                not proof_refresh_mixed_identity,
                "proof refresh gate reported mixed strategy or market identity",
            )
        )
        if expected_proof_strategy:
            checks.append(
                _check(
                    "proof_refresh_strategy_matches",
                    proof_refresh_strategy,
                    "==",
                    expected_proof_strategy,
                    bool(proof_refresh_strategy and proof_refresh_strategy == expected_proof_strategy),
                    "proof refresh strategy does not match scale-up strategy",
                )
            )
        if expected_proof_market:
            checks.append(
                _check(
                    "proof_refresh_market_matches",
                    proof_refresh_market,
                    "==",
                    expected_proof_market,
                    bool(proof_refresh_market and proof_refresh_market == expected_proof_market),
                    "proof refresh market does not match scale-up market",
                )
            )
    if thresholds.require_instrument_metadata:
        checks.append(
            _check(
                "instrument_metadata_available",
                not instrument_metadata.empty,
                "is",
                True,
                not instrument_metadata.empty,
                "instrument metadata report is required but no summary was supplied",
            )
        )
    if not instrument_metadata.empty:
        metadata_passed = _to_bool(instrument_metadata.get("passed", False))
        parse_coverage = _number(instrument_metadata, "parse_coverage", fallback=0.0)
        checks.append(
            _check(
                "instrument_metadata_passed",
                metadata_passed,
                "is",
                True,
                metadata_passed,
                "instrument metadata report did not pass",
            )
        )
        checks.append(
            _threshold_check(
                "instrument_parse_coverage",
                parse_coverage,
                ">=",
                thresholds.min_instrument_parse_coverage,
            )
        )
    if thresholds.require_data_readiness:
        checks.append(
            _check(
                "data_readiness_available",
                not data_readiness.empty,
                "is",
                True,
                not data_readiness.empty,
                "data readiness review is required but no summary was supplied",
            )
        )
    if not data_readiness.empty:
        data_ready = _to_bool(data_readiness.get("ready", False))
        checks.append(
            _check(
                "data_readiness_ready",
                data_ready,
                "is",
                True,
                data_ready,
                "data readiness review is not ready",
            )
        )
    if thresholds.require_data_readiness_comparison:
        checks.append(
            _check(
                "data_readiness_comparison_available",
                not data_readiness_comparison.empty,
                "is",
                True,
                not data_readiness_comparison.empty,
                "data readiness comparison is required but no summary was supplied",
            )
        )
    if not data_readiness_comparison.empty:
        data_comparison_accepted = _to_bool(data_readiness_comparison.get("accepted", False))
        checks.append(
            _check(
                "data_readiness_comparison_accepted",
                data_comparison_accepted,
                "is",
                True,
                data_comparison_accepted,
                "data readiness comparison is not accepted",
            )
        )
    if thresholds.require_strategy_portfolio:
        checks.append(
            _check(
                "strategy_portfolio_available",
                _to_bool(strategy_portfolio.get("provided", False)),
                "is",
                True,
                _to_bool(strategy_portfolio.get("provided", False)),
                "strategy portfolio allocation is required but no summary was supplied",
            )
        )
    if _to_bool(strategy_portfolio.get("provided", False)):
        if _to_bool(strategy_portfolio.get("manifest_required", False)):
            checks.extend(
                [
                    _check(
                        "strategy_portfolio_manifest_provided",
                        _to_bool(strategy_portfolio.get("manifest_provided", False)),
                        "is",
                        True,
                        _to_bool(strategy_portfolio.get("manifest_provided", False)),
                        "strategy portfolio manifest is required but missing",
                    ),
                    _check(
                        "strategy_portfolio_manifest_current",
                        str(strategy_portfolio.get("manifest_error", ""))
                        or _to_bool(strategy_portfolio.get("manifest_current", False)),
                        "is",
                        True,
                        _to_bool(strategy_portfolio.get("manifest_current", False)),
                        "strategy portfolio manifest is stale or invalid",
                    ),
                    _check(
                        "strategy_portfolio_contract_consistent",
                        str(strategy_portfolio.get("contract_error", ""))
                        or _to_bool(strategy_portfolio.get("contract_consistent", False)),
                        "is",
                        True,
                        _to_bool(strategy_portfolio.get("contract_consistent", False)),
                        "strategy portfolio summary, allocations, config, and manifest disagree",
                    ),
                    _check(
                        "strategy_portfolio_non_authorizing",
                        _to_bool(strategy_portfolio.get("non_authorizing", False)),
                        "is",
                        True,
                        _to_bool(strategy_portfolio.get("non_authorizing", False)),
                        "strategy portfolio unexpectedly claims submission authority",
                    ),
                    _check(
                        "strategy_portfolio_provenance_gate_passed",
                        _to_bool(strategy_portfolio.get("provenance_gate_passed", False)),
                        "is",
                        True,
                        _to_bool(strategy_portfolio.get("provenance_gate_passed", False)),
                        "strategy portfolio provenance is not current and complete",
                    ),
                ]
            )
        if _to_bool(strategy_portfolio.get("research_family_bound", False)):
            checks.extend(
                [
                    _check(
                        "strategy_portfolio_scorecard_provenance_current",
                        bool(
                            _to_bool(strategy_portfolio.get("scorecard_manifest_current", False))
                            and _to_bool(
                                strategy_portfolio.get("scorecard_contract_consistent", False)
                            )
                            and _to_bool(
                                strategy_portfolio.get("scorecard_non_authorizing", False)
                            )
                            and _to_bool(
                                strategy_portfolio.get(
                                    "scorecard_provenance_gate_passed",
                                    False,
                                )
                            )
                        ),
                        "is",
                        True,
                        bool(
                            _to_bool(strategy_portfolio.get("scorecard_manifest_current", False))
                            and _to_bool(
                                strategy_portfolio.get("scorecard_provenance_gate_passed", False)
                            )
                        ),
                        "carried strategy scorecard provenance is not current",
                    ),
                    _check(
                        "strategy_portfolio_research_family_provenance_current",
                        _to_bool(
                            strategy_portfolio.get(
                                "research_family_provenance_current",
                                False,
                            )
                        ),
                        "is",
                        True,
                        _to_bool(
                            strategy_portfolio.get(
                                "research_family_provenance_current",
                                False,
                            )
                        ),
                        "carried registered research-family closure is not current",
                    ),
                ]
            )
        portfolio_ready = _to_bool(strategy_portfolio.get("ready", False))
        allocation_available = _to_bool(strategy_portfolio.get("selected_allocation_provided", False))
        allocation_eligible = _to_bool(strategy_portfolio.get("selected_eligible", False))
        allocation_notional = _number(strategy_portfolio, "selected_allocation_notional", fallback=0.0)
        checks.extend(
            [
                _check(
                    "strategy_portfolio_ready",
                    portfolio_ready,
                    "is",
                    True,
                    portfolio_ready,
                    "strategy portfolio allocation is not ready",
                ),
                _check(
                    "strategy_portfolio_allocation_available",
                    allocation_available,
                    "is",
                    True,
                    allocation_available,
                    "strategy portfolio has no row for the scale-up strategy and market",
                ),
                _check(
                    "strategy_portfolio_allocation_eligible",
                    allocation_eligible,
                    "is",
                    True,
                    allocation_eligible,
                    "strategy portfolio allocation row is not eligible",
                ),
                _check(
                    "strategy_portfolio_allocation_positive",
                    allocation_notional,
                    ">",
                    0.0,
                    allocation_notional > 0.0,
                    "strategy portfolio allocation notional must be positive",
                ),
            ]
        )
    route_readiness_required = _route_readiness_required(thresholds)
    if route_readiness_required:
        checks.append(
            _check(
                "route_readiness_available",
                not route_readiness.empty,
                "is",
                True,
                not route_readiness.empty,
                "route readiness review is required but no summary was supplied",
            )
        )
    if not route_readiness.empty:
        route_ready = _to_bool(route_readiness.get("ready", False))
        route_strategy = _strategy_key(route_readiness.get("strategy", ""))
        route_market = _identity_key(route_readiness.get("market", ""))
        expected_route_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_route_market = _identity_key(thresholds.expected_market) or evidence_market
        checks.append(
            _check(
                "route_readiness_ready",
                route_ready,
                "is",
                True,
                route_ready,
                "route readiness review is not ready",
            )
        )
        if expected_route_strategy:
            checks.append(
                _check(
                    "route_readiness_strategy_matches",
                    route_strategy,
                    "==",
                    expected_route_strategy,
                    bool(route_strategy and route_strategy == expected_route_strategy),
                    "route readiness strategy does not match scale-up strategy",
                )
            )
        if expected_route_market:
            checks.append(
                _check(
                    "route_readiness_market_matches",
                    route_market,
                    "==",
                    expected_route_market,
                    bool(route_market and route_market == expected_route_market),
                    "route readiness market does not match scale-up market",
                )
            )
        route_ops_present = _route_readiness_ops_controls_present(route_readiness)
        route_ops_blocked_pairs = int(_number(route_readiness, "ops_launch_controls_blocked_pairs", 0.0))
        route_ops_portfolio_breach_pairs = int(
            _number(route_readiness, "ops_broker_roundtrip_portfolio_breach_pairs", 0.0)
        )
        route_ops_concentration_breach_pairs = int(
            _number(route_readiness, "ops_broker_roundtrip_portfolio_concentration_breach_pairs", 0.0)
        )
        route_ops_resume_route_breach_pairs = {
            field: int(_number(route_readiness, field, 0.0))
            for field in ROUTE_READINESS_RESUME_ROUTE_BREACH_PAIR_FIELDS
        }
        route_ops_provider_sidecar_breach_pairs = {
            field: int(_number(route_readiness, field, 0.0))
            for field in ROUTE_READINESS_PROVIDER_SIDECAR_BREACH_PAIR_FIELDS
        }
        if route_readiness_required or route_ops_present:
            checks.extend(
                [
                    _check(
                        "route_readiness_ops_launch_controls_present",
                        route_ops_present,
                        "is",
                        True,
                        route_ops_present,
                        "route readiness summary does not carry launch-grade ops broker controls",
                    ),
                    _threshold_check(
                        "route_readiness_ops_launch_controls_blocked_pairs",
                        route_ops_blocked_pairs,
                        "<=",
                        0,
                    ),
                    _threshold_check(
                        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
                        route_ops_portfolio_breach_pairs,
                        "<=",
                        0,
                    ),
                    _threshold_check(
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
                        route_ops_concentration_breach_pairs,
                        "<=",
                        0,
                    ),
                    *(
                        _threshold_check(f"route_readiness_{field}", value, "<=", 0)
                        for field, value in route_ops_resume_route_breach_pairs.items()
                    ),
                    *(
                        _threshold_check(f"route_readiness_{field}", value, "<=", 0)
                        for field, value in route_ops_provider_sidecar_breach_pairs.items()
                    ),
                ]
            )
    broker_readiness_required = _broker_readiness_required(thresholds)
    if broker_readiness_required:
        checks.append(
            _check(
                "broker_readiness_available",
                not broker_readiness.empty,
                "is",
                True,
                not broker_readiness.empty,
                "broker readiness review is required but no summary was supplied",
            )
        )
    if not broker_readiness.empty:
        broker_ready = _to_bool(broker_readiness.get("ready", False))
        checks.append(
            _check(
                "broker_readiness_ready",
                broker_ready,
                "is",
                True,
                broker_ready,
                "broker readiness review is not ready",
            )
        )
    broker_route_readiness_active = _broker_route_readiness_active(broker_readiness)
    if broker_route_readiness_active:
        broker_route_readiness_required = _to_bool(broker_readiness.get("route_readiness_required", False))
        broker_route_readiness_provided = _to_bool(broker_readiness.get("route_readiness_provided", False))
        broker_route_readiness_ready = _to_bool(broker_readiness.get("route_readiness_ready", False))
        broker_route_readiness_strategy = _strategy_key(broker_readiness.get("route_readiness_strategy", ""))
        broker_route_readiness_market = _identity_key(broker_readiness.get("route_readiness_market", ""))
        expected_broker_route_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_broker_route_market = _identity_key(thresholds.expected_market) or evidence_market
        checks.extend(
            [
                _check(
                    "broker_route_readiness_provided",
                    broker_route_readiness_provided,
                    "is",
                    True,
                    broker_route_readiness_provided or not broker_route_readiness_required,
                    "broker readiness requires route-readiness proof but did not provide it",
                ),
                _check(
                    "broker_route_readiness_ready",
                    broker_route_readiness_ready,
                    "is",
                    True,
                    broker_route_readiness_ready,
                    "broker-carried route-readiness proof is not ready",
                ),
                _check(
                    "broker_route_readiness_strategy_matches",
                    broker_route_readiness_strategy,
                    "==",
                    expected_broker_route_strategy,
                    bool(
                        broker_route_readiness_strategy
                        and expected_broker_route_strategy
                        and broker_route_readiness_strategy == expected_broker_route_strategy
                    ),
                    "broker-carried route-readiness strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_route_readiness_market_matches",
                    broker_route_readiness_market,
                    "==",
                    expected_broker_route_market,
                    bool(
                        broker_route_readiness_market
                        and expected_broker_route_market
                        and broker_route_readiness_market == expected_broker_route_market
                    ),
                    "broker-carried route-readiness market does not match scale-up market",
                ),
                _threshold_check(
                    "broker_route_readiness_gap_pairs",
                    _number(broker_readiness, "route_readiness_gap_pairs", 0.0),
                    "<=",
                    0,
                ),
                _check(
                    "broker_route_readiness_ops_launch_controls_ready",
                    _to_bool(broker_readiness.get("route_readiness_ops_launch_controls_ready", False)),
                    "is",
                    True,
                    _to_bool(broker_readiness.get("route_readiness_ops_launch_controls_ready", False)),
                    "broker-carried route-readiness proof did not preserve launch-grade ops controls",
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                    _number(broker_readiness, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
                    ">=",
                    1,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                    _number(broker_readiness, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                        0.0,
                    ),
                    ">=",
                    1,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        0.0,
                    ),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_ready_runs",
                        0.0,
                    ),
                    ">=",
                    1,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_breach_runs",
                        0.0,
                    ),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs",
                        0.0,
                    ),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs",
                        0.0,
                    ),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs",
                        0.0,
                    ),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs",
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs",
                        0.0,
                    ),
                    "<=",
                    0,
                ),
            ]
        )
    resume_gate_provided = _to_bool(broker_readiness.get("resume_gate_provided", False))
    if thresholds.require_resume_gate:
        checks.append(
            _check(
                "broker_resume_gate_provided",
                resume_gate_provided,
                "is",
                True,
                resume_gate_provided,
                "scale-up requires broker readiness with resume-gate authorization",
            )
        )
    if not broker_readiness.empty and (thresholds.require_resume_gate or resume_gate_provided):
        resume_gate_ready = _to_bool(broker_readiness.get("resume_gate_ready", False))
        resume_strategy = _strategy_key(broker_readiness.get("resume_strategy", ""))
        resume_market = _identity_key(broker_readiness.get("resume_market", ""))
        resume_proof_ready = _to_bool(broker_readiness.get("resume_proof_refresh_ready", False))
        resume_proof_strategy = _strategy_key(broker_readiness.get("resume_proof_refresh_strategy", ""))
        resume_proof_market = _identity_key(broker_readiness.get("resume_proof_refresh_market", ""))
        expected_resume_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_resume_market = _identity_key(thresholds.expected_market) or evidence_market
        checks.extend(
            [
                _check(
                    "broker_resume_gate_ready",
                    resume_gate_ready,
                    "is",
                    True,
                    resume_gate_ready,
                    "broker resume gate is not ready",
                ),
                _check(
                    "broker_resume_strategy_matches",
                    resume_strategy,
                    "==",
                    expected_resume_strategy,
                    bool(resume_strategy and expected_resume_strategy and resume_strategy == expected_resume_strategy),
                    "broker resume-gate strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_resume_market_matches",
                    resume_market,
                    "==",
                    expected_resume_market,
                    bool(resume_market and expected_resume_market and resume_market == expected_resume_market),
                    "broker resume-gate market does not match scale-up market",
                ),
                _check(
                    "broker_resume_proof_refresh_ready",
                    resume_proof_ready,
                    "is",
                    True,
                    resume_proof_ready,
                    "broker resume-gate proof freshness is not ready",
                ),
                _check(
                    "broker_resume_proof_refresh_strategy_matches",
                    resume_proof_strategy,
                    "==",
                    expected_resume_strategy,
                    bool(
                        resume_proof_strategy
                        and expected_resume_strategy
                        and resume_proof_strategy == expected_resume_strategy
                    ),
                    "broker resume-gate proof strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_resume_proof_refresh_market_matches",
                    resume_proof_market,
                    "==",
                    expected_resume_market,
                    bool(resume_proof_market and expected_resume_market and resume_proof_market == expected_resume_market),
                    "broker resume-gate proof market does not match scale-up market",
                ),
            ]
        )
        if _broker_resume_route_readiness_active(broker_readiness, "resume_broker_route_readiness"):
            checks.extend(
                _broker_resume_route_readiness_checks(
                    broker_readiness,
                    source_prefix="resume_broker_route_readiness",
                    check_prefix="broker_resume_broker_route_readiness",
                    expected_strategy=expected_resume_strategy,
                    expected_market=expected_resume_market,
                    label="broker resume-gate route proof",
                )
            )
        if _broker_resume_route_readiness_active(
            broker_readiness,
            "resume_incident_broker_route_readiness",
        ):
            checks.extend(
                _broker_resume_route_readiness_checks(
                    broker_readiness,
                    source_prefix="resume_incident_broker_route_readiness",
                    check_prefix="broker_resume_incident_broker_route_readiness",
                    expected_strategy=expected_resume_strategy,
                    expected_market=expected_resume_market,
                    label="broker resume-gate incident route proof",
                )
            )
    dispatch_roundtrip_required = _dispatch_roundtrip_required(thresholds)
    dispatch_roundtrip_provided = _to_bool(broker_readiness.get("dispatch_roundtrip_provided", False))
    route_dispatch_roundtrip_required = _route_dispatch_roundtrip_required(thresholds, broker_readiness)
    route_dispatch_roundtrip_provided = _to_bool(
        broker_readiness.get("route_dispatch_roundtrip_provided", False)
    )
    if dispatch_roundtrip_required:
        checks.append(
            _check(
                "broker_dispatch_roundtrip_provided",
                dispatch_roundtrip_provided,
                "is",
                True,
                dispatch_roundtrip_provided,
                "scale-up requires broker readiness with dry-run dispatch round-trip proof",
            )
        )
    if route_dispatch_roundtrip_required:
        checks.append(
            _check(
                "broker_route_dispatch_roundtrip_provided",
                route_dispatch_roundtrip_provided,
                "is",
                True,
                route_dispatch_roundtrip_provided,
                "scale-up requires broker readiness with dispatch route proof",
            )
        )
    if not broker_readiness.empty and (dispatch_roundtrip_required or dispatch_roundtrip_provided):
        dispatch_roundtrip_ready = _to_bool(broker_readiness.get("dispatch_roundtrip_ready", False))
        dispatch_roundtrip_target_mode = _identity_key(broker_readiness.get("dispatch_roundtrip_target_mode", ""))
        dispatch_roundtrip_strategy = _strategy_key(broker_readiness.get("dispatch_roundtrip_strategy", ""))
        dispatch_roundtrip_market = _identity_key(broker_readiness.get("dispatch_roundtrip_market", ""))
        dispatch_roundtrip_scenario = str(broker_readiness.get("dispatch_roundtrip_scenario_key", "")).strip()
        expected_dispatch_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_dispatch_market = _identity_key(thresholds.expected_market) or evidence_market
        launch_scenario = str(launch.get("scenario_key", "")).strip()
        checks.extend(
            [
                _check(
                    "broker_dispatch_roundtrip_ready",
                    dispatch_roundtrip_ready,
                    "is",
                    True,
                    dispatch_roundtrip_ready,
                    "broker dry-run dispatch round-trip proof is not ready",
                ),
                _check(
                    "broker_dispatch_roundtrip_target_mode_matches",
                    dispatch_roundtrip_target_mode,
                    "==",
                    thresholds.target_mode,
                    bool(dispatch_roundtrip_target_mode and dispatch_roundtrip_target_mode == thresholds.target_mode),
                    "broker dispatch round-trip target mode does not match scale-up target",
                ),
                _check(
                    "broker_dispatch_roundtrip_strategy_matches",
                    dispatch_roundtrip_strategy,
                    "==",
                    expected_dispatch_strategy,
                    bool(
                        dispatch_roundtrip_strategy
                        and expected_dispatch_strategy
                        and dispatch_roundtrip_strategy == expected_dispatch_strategy
                    ),
                    "broker dispatch round-trip strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_dispatch_roundtrip_market_matches",
                    dispatch_roundtrip_market,
                    "==",
                    expected_dispatch_market,
                    bool(
                        dispatch_roundtrip_market
                        and expected_dispatch_market
                        and dispatch_roundtrip_market == expected_dispatch_market
                    ),
                    "broker dispatch round-trip market does not match scale-up market",
                ),
                _check(
                    "broker_dispatch_roundtrip_scenario_matches",
                    dispatch_roundtrip_scenario,
                    "==",
                    launch_scenario,
                    bool(dispatch_roundtrip_scenario and launch_scenario and dispatch_roundtrip_scenario == launch_scenario),
                    "broker dispatch round-trip scenario does not match launch scenario",
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_missing_request_acks",
                    _number(broker_readiness, "dispatch_roundtrip_missing_request_acks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_rejected_orders",
                    _number(broker_readiness, "dispatch_roundtrip_rejected_orders", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_unmatched_acks",
                    _number(broker_readiness, "dispatch_roundtrip_unmatched_acks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_dispatch_roundtrip_failed_checks",
                    _number(broker_readiness, "dispatch_roundtrip_failed_checks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_enable_dispatch_roundtrip_failed_checks",
                    _number(broker_readiness, "route_enable_dispatch_roundtrip_failed_checks", 0.0),
                    "<=",
                    0,
                ),
            ]
        )
    if not broker_readiness.empty and (
        dispatch_roundtrip_required or dispatch_roundtrip_provided or route_dispatch_roundtrip_provided
    ):
        route_dispatch_roundtrip_ready = _to_bool(broker_readiness.get("route_dispatch_roundtrip_ready", False))
        route_dispatch_roundtrip_target_mode = _identity_key(
            broker_readiness.get("route_dispatch_roundtrip_target_mode", "")
        )
        route_dispatch_roundtrip_strategy = _strategy_key(
            broker_readiness.get("route_dispatch_roundtrip_strategy", "")
        )
        route_dispatch_roundtrip_market = _identity_key(
            broker_readiness.get("route_dispatch_roundtrip_market", "")
        )
        route_dispatch_roundtrip_scenario = str(
            broker_readiness.get("route_dispatch_roundtrip_scenario_key", "")
        ).strip()
        route_dispatch_roundtrip_batch_id = str(
            broker_readiness.get("route_dispatch_roundtrip_batch_id", "")
        ).strip()
        route_dispatch_roundtrip_requests = int(
            _number(broker_readiness, "route_dispatch_roundtrip_requests", 0.0)
        )
        route_dispatch_roundtrip_acked_orders = int(
            _number(broker_readiness, "route_dispatch_roundtrip_acked_orders", 0.0)
        )
        dispatch_roundtrip_requests = int(_number(broker_readiness, "dispatch_roundtrip_requests", 0.0))
        dispatch_roundtrip_acked_orders = int(
            _number(broker_readiness, "dispatch_roundtrip_acked_orders", 0.0)
        )
        expected_dispatch_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_dispatch_market = _identity_key(thresholds.expected_market) or evidence_market
        launch_scenario = str(launch.get("scenario_key", "")).strip()
        checks.extend(
            [
                _check(
                    "broker_route_dispatch_roundtrip_ready",
                    route_dispatch_roundtrip_ready,
                    "is",
                    True,
                    route_dispatch_roundtrip_ready,
                    "broker dispatch route proof is not ready",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_target_mode_matches",
                    route_dispatch_roundtrip_target_mode,
                    "==",
                    thresholds.target_mode,
                    bool(
                        route_dispatch_roundtrip_target_mode
                        and route_dispatch_roundtrip_target_mode == thresholds.target_mode
                    ),
                    "broker dispatch route proof target mode does not match scale-up target",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_strategy_matches",
                    route_dispatch_roundtrip_strategy,
                    "==",
                    expected_dispatch_strategy,
                    bool(
                        route_dispatch_roundtrip_strategy
                        and expected_dispatch_strategy
                        and route_dispatch_roundtrip_strategy == expected_dispatch_strategy
                    ),
                    "broker dispatch route proof strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_market_matches",
                    route_dispatch_roundtrip_market,
                    "==",
                    expected_dispatch_market,
                    bool(
                        route_dispatch_roundtrip_market
                        and expected_dispatch_market
                        and route_dispatch_roundtrip_market == expected_dispatch_market
                    ),
                    "broker dispatch route proof market does not match scale-up market",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_scenario_matches",
                    route_dispatch_roundtrip_scenario,
                    "==",
                    launch_scenario,
                    bool(
                        route_dispatch_roundtrip_scenario
                        and launch_scenario
                        and route_dispatch_roundtrip_scenario == launch_scenario
                    ),
                    "broker dispatch route proof scenario does not match launch scenario",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_batch_id_provided",
                    route_dispatch_roundtrip_batch_id,
                    "is not",
                    "",
                    bool(route_dispatch_roundtrip_batch_id),
                    "broker dispatch route proof batch id is missing",
                ),
                _check(
                    "broker_route_dispatch_roundtrip_request_count_matches",
                    f"{route_dispatch_roundtrip_requests}/{route_dispatch_roundtrip_acked_orders}",
                    "==",
                    f"{dispatch_roundtrip_requests}/{dispatch_roundtrip_acked_orders}",
                    (
                        route_dispatch_roundtrip_requests == dispatch_roundtrip_requests
                        and route_dispatch_roundtrip_acked_orders == dispatch_roundtrip_acked_orders
                    ),
                    "broker dispatch route proof request/ack counts do not match dispatch round-trip counts",
                ),
                _threshold_check(
                    "broker_route_dispatch_roundtrip_missing_request_acks",
                    _number(broker_readiness, "route_dispatch_roundtrip_missing_request_acks", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_dispatch_roundtrip_rejected_orders",
                    _number(broker_readiness, "route_dispatch_roundtrip_rejected_orders", 0.0),
                    "<=",
                    0,
                ),
                _threshold_check(
                    "broker_route_dispatch_roundtrip_unmatched_acks",
                    _number(broker_readiness, "route_dispatch_roundtrip_unmatched_acks", 0.0),
                    "<=",
                    0,
                ),
            ]
        )
    if _broker_shadow_broker_readiness_active(broker_readiness):
        expected_broker_shadow_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_broker_shadow_market = _identity_key(thresholds.expected_market) or evidence_market
        expected_broker_shadow_adapter = _identity_key(broker_readiness.get("adapter", "")) or _identity_key(
            launch.get("adapter", "")
        )
        checks.extend(
            _broker_shadow_broker_readiness_checks(
                broker_readiness,
                expected_strategy=expected_broker_shadow_strategy,
                expected_market=expected_broker_shadow_market,
                expected_adapter=expected_broker_shadow_adapter,
            )
        )
    if _broker_vendor_data_readiness_active(broker_readiness):
        checks.extend(_broker_vendor_data_readiness_checks(broker_readiness))
    if _broker_vendor_market_data_batch_active(broker_readiness):
        expected_vendor_market = _identity_key(thresholds.expected_market) or evidence_market
        expected_vendor_adapter = _identity_key(broker_readiness.get("adapter", "")) or _identity_key(
            launch.get("adapter", "")
        )
        checks.extend(
            _broker_vendor_market_data_batch_checks(
                broker_readiness,
                expected_market=expected_vendor_market,
                expected_adapter=expected_vendor_adapter,
            )
        )
    if thresholds.target_mode == "live_dryrun":
        runtime_session_provided = _to_bool(broker_readiness.get("runtime_session_provided", False))
        runtime_session_ready = _to_bool(broker_readiness.get("runtime_session_ready", False))
        runtime_guard_action = str(broker_readiness.get("runtime_guard_action", "")).strip().lower()
        runtime_guard_halted = _to_bool(broker_readiness.get("runtime_guard_halted", False))
        runtime_strategy = _strategy_key(broker_readiness.get("runtime_strategy", ""))
        runtime_market = _identity_key(broker_readiness.get("runtime_market", ""))
        expected_runtime_strategy = _strategy_key(thresholds.expected_strategy) or evidence_strategy
        expected_runtime_market = _identity_key(thresholds.expected_market) or evidence_market
        checks.extend(
            [
                _check(
                    "broker_runtime_session_provided",
                    runtime_session_provided,
                    "is",
                    True,
                    runtime_session_provided,
                    "live_dryrun scale-up requires broker readiness with runtime-session evidence",
                ),
                _check(
                    "broker_runtime_session_ready",
                    runtime_session_ready,
                    "is",
                    True,
                    runtime_session_ready,
                    "broker runtime session is not ready",
                ),
                _check(
                    "broker_runtime_guard_continue",
                    runtime_guard_action or ("halt" if runtime_guard_halted else ""),
                    "==",
                    "continue",
                    runtime_guard_action == "continue" and not runtime_guard_halted,
                    "broker runtime session guard is not continuing",
                ),
                _check(
                    "broker_runtime_strategy_matches",
                    runtime_strategy,
                    "==",
                    expected_runtime_strategy,
                    bool(runtime_strategy and expected_runtime_strategy and runtime_strategy == expected_runtime_strategy),
                    "broker runtime-session strategy does not match scale-up strategy",
                ),
                _check(
                    "broker_runtime_market_matches",
                    runtime_market,
                    "==",
                    expected_runtime_market,
                    bool(runtime_market and expected_runtime_market and runtime_market == expected_runtime_market),
                    "broker runtime-session market does not match scale-up market",
                ),
            ]
        )
    return pd.DataFrame(checks)


def _plan(rows: dict[str, pd.Series], thresholds: ScaleUpThresholds, ready: bool) -> pd.DataFrame:
    evidence = rows["evidence"]
    launch = rows["launch"]
    shadow = rows["shadow"]
    proof_refresh = rows["proof_refresh"]
    instrument_metadata = rows["instrument_metadata"]
    data_readiness = rows["data_readiness"]
    data_readiness_comparison = rows["data_readiness_comparison"]
    strategy_portfolio = rows["strategy_portfolio"]
    route_readiness = rows["route_readiness"]
    broker_readiness = rows["broker_readiness"]
    accepted_orders = int(_number(launch, "accepted_orders", fallback=0.0))
    launch_notional = _number(launch, "total_notional", fallback=0.0)
    scaled_orders = int(np.floor(accepted_orders * thresholds.max_scale_multiplier))
    scaled_notional = float(launch_notional * thresholds.max_scale_multiplier)
    if thresholds.max_orders_per_session is not None:
        scaled_orders = min(scaled_orders, int(thresholds.max_orders_per_session))
    if thresholds.max_session_notional is not None:
        scaled_notional = min(scaled_notional, float(thresholds.max_session_notional))
    pre_portfolio_scaled_notional = float(scaled_notional)
    portfolio_allocation_notional = _number(strategy_portfolio, "selected_allocation_notional", fallback=0.0)
    if portfolio_allocation_notional > 0.0:
        scaled_notional = min(scaled_notional, portfolio_allocation_notional)
    portfolio_notional_cap_applied = bool(
        portfolio_allocation_notional > 0.0 and pre_portfolio_scaled_notional > portfolio_allocation_notional
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": thresholds.target_mode,
                "strategy": _strategy_key(evidence.get("strategy", "")),
                "market": _identity_key(evidence.get("market", "")),
                "expected_strategy": _strategy_key(thresholds.expected_strategy),
                "expected_market": _identity_key(thresholds.expected_market),
                "scenario_key": str(launch.get("scenario_key", "")),
                "adapter": str(launch.get("adapter", "")),
                "source_launch_mode": str(launch.get("mode", "")),
                "launch_pipeline_provided": _to_bool(launch.get("launch_pipeline_provided", False)),
                "launch_pipeline_family": str(launch.get("launch_pipeline_family", "")),
                "launch_pipeline_summary_file": str(launch.get("launch_pipeline_summary_file", "")),
                "launch_pipeline_ready": _to_bool(launch.get("launch_pipeline_ready", False)),
                "launch_pipeline_strategy": _strategy_key(launch.get("launch_pipeline_strategy", "")),
                "launch_pipeline_market": _identity_key(launch.get("launch_pipeline_market", "")),
                "launch_pipeline_expected_strategy": _strategy_key(
                    launch.get("launch_pipeline_expected_strategy", "")
                ),
                "launch_pipeline_expected_market": _identity_key(
                    launch.get("launch_pipeline_expected_market", "")
                ),
                "launch_pipeline_failed_components": int(
                    _number(launch, "launch_pipeline_failed_components", fallback=0.0)
                ),
                "launch_pipeline_skipped_components": int(
                    _number(launch, "launch_pipeline_skipped_components", fallback=0.0)
                ),
                "surface_launch_pipeline_provided": _to_bool(
                    launch.get("surface_launch_pipeline_provided", False)
                ),
                "surface_launch_pipeline_ready": _to_bool(launch.get("surface_launch_pipeline_ready", False)),
                "surface_launch_strategy": _strategy_key(launch.get("surface_launch_strategy", "")),
                "surface_launch_market": _identity_key(launch.get("surface_launch_market", "")),
                "surface_launch_expected_strategy": _strategy_key(
                    launch.get("surface_launch_expected_strategy", "")
                ),
                "surface_launch_expected_market": _identity_key(launch.get("surface_launch_expected_market", "")),
                "surface_launch_failed_components": int(
                    _number(launch, "surface_launch_failed_components", fallback=0.0)
                ),
                "surface_launch_skipped_components": int(
                    _number(launch, "surface_launch_skipped_components", fallback=0.0)
                ),
                "max_scale_multiplier": float(thresholds.max_scale_multiplier),
                "max_orders_per_session": scaled_orders,
                "max_notional_per_session": scaled_notional,
                "pre_portfolio_max_notional_per_session": pre_portfolio_scaled_notional,
                "strategy_portfolio_required": thresholds.require_strategy_portfolio,
                "strategy_portfolio_provided": _to_bool(strategy_portfolio.get("provided", False)),
                "strategy_portfolio_ready": _to_bool(strategy_portfolio.get("ready", False)),
                "strategy_portfolio_manifest_required": _to_bool(
                    strategy_portfolio.get("manifest_required", False)
                ),
                "strategy_portfolio_manifest_provided": _to_bool(
                    strategy_portfolio.get("manifest_provided", False)
                ),
                "strategy_portfolio_manifest_current": _to_bool(
                    strategy_portfolio.get("manifest_current", False)
                ),
                "strategy_portfolio_manifest_sha256": str(
                    strategy_portfolio.get("manifest_sha256", "")
                ),
                "strategy_portfolio_manifest_error": str(
                    strategy_portfolio.get("manifest_error", "")
                ),
                "strategy_portfolio_contract_consistent": _to_bool(
                    strategy_portfolio.get("contract_consistent", False)
                ),
                "strategy_portfolio_contract_error": str(
                    strategy_portfolio.get("contract_error", "")
                ),
                "strategy_portfolio_non_authorizing": _to_bool(
                    strategy_portfolio.get("non_authorizing", False)
                ),
                "strategy_portfolio_provenance_gate_passed": _to_bool(
                    strategy_portfolio.get("provenance_gate_passed", False)
                ),
                "strategy_portfolio_dependency_count": int(
                    _number(strategy_portfolio, "dependency_count", fallback=0.0)
                ),
                "strategy_portfolio_scorecard_manifest_required": _to_bool(
                    strategy_portfolio.get("scorecard_manifest_required", False)
                ),
                "strategy_portfolio_scorecard_manifest_current": _to_bool(
                    strategy_portfolio.get("scorecard_manifest_current", False)
                ),
                "strategy_portfolio_scorecard_manifest_sha256": str(
                    strategy_portfolio.get("scorecard_manifest_sha256", "")
                ),
                "strategy_portfolio_scorecard_contract_consistent": _to_bool(
                    strategy_portfolio.get("scorecard_contract_consistent", False)
                ),
                "strategy_portfolio_scorecard_non_authorizing": _to_bool(
                    strategy_portfolio.get("scorecard_non_authorizing", False)
                ),
                "strategy_portfolio_scorecard_provenance_gate_passed": _to_bool(
                    strategy_portfolio.get("scorecard_provenance_gate_passed", False)
                ),
                "strategy_portfolio_research_family_bound": _to_bool(
                    strategy_portfolio.get("research_family_bound", False)
                ),
                "strategy_portfolio_research_family_provenance_current": _to_bool(
                    strategy_portfolio.get("research_family_provenance_current", False)
                ),
                "strategy_portfolio_research_family_id": str(
                    strategy_portfolio.get("research_family_id", "")
                ),
                "strategy_portfolio_research_family_registration_id": str(
                    strategy_portfolio.get("research_family_registration_id", "")
                ),
                "strategy_portfolio_research_family_path": str(
                    strategy_portfolio.get("research_family_path", "")
                ),
                "strategy_portfolio_research_family_manifest_sha256": str(
                    strategy_portfolio.get("research_family_manifest_sha256", "")
                ),
                "strategy_portfolio_deployment_mode": str(strategy_portfolio.get("deployment_mode", "")),
                "strategy_portfolio_allocation_mode": str(strategy_portfolio.get("allocation_mode", "")),
                "strategy_portfolio_capital_currency": str(strategy_portfolio.get("capital_currency", "")),
                "strategy_portfolio_total_capital": _number(strategy_portfolio, "total_capital", fallback=0.0),
                "strategy_portfolio_allocated_weight": _number(strategy_portfolio, "allocated_weight", fallback=0.0),
                "strategy_portfolio_allocated_notional": _number(
                    strategy_portfolio,
                    "allocated_notional",
                    fallback=0.0,
                ),
                "strategy_portfolio_min_strategy_count": int(
                    _number(strategy_portfolio, "min_strategy_count", fallback=0.0)
                ),
                "strategy_portfolio_min_market_count": int(
                    _number(strategy_portfolio, "min_market_count", fallback=0.0)
                ),
                "strategy_portfolio_max_strategy_weight": _number(
                    strategy_portfolio,
                    "max_strategy_weight",
                    fallback=0.0,
                ),
                "strategy_portfolio_max_market_weight": _number(
                    strategy_portfolio,
                    "max_market_weight",
                    fallback=0.0,
                ),
                "strategy_portfolio_allocated_strategy_count": int(
                    _number(strategy_portfolio, "allocated_strategy_count", fallback=0.0)
                ),
                "strategy_portfolio_allocated_market_count": int(
                    _number(strategy_portfolio, "allocated_market_count", fallback=0.0)
                ),
                "strategy_portfolio_top_strategy_by_weight": str(
                    strategy_portfolio.get("top_strategy_by_weight", "")
                ),
                "strategy_portfolio_top_market_by_weight": str(
                    strategy_portfolio.get("top_market_by_weight", "")
                ),
                "strategy_portfolio_max_strategy_allocation_weight": _number(
                    strategy_portfolio,
                    "max_strategy_allocation_weight",
                    fallback=0.0,
                ),
                "strategy_portfolio_max_market_allocation_weight": _number(
                    strategy_portfolio,
                    "max_market_allocation_weight",
                    fallback=0.0,
                ),
                "strategy_portfolio_selected_profile": str(strategy_portfolio.get("selected_profile", "")),
                "strategy_portfolio_selected_strategy": _strategy_key(
                    strategy_portfolio.get("selected_strategy", "")
                ),
                "strategy_portfolio_selected_market": _identity_key(
                    strategy_portfolio.get("selected_market", "")
                ),
                "strategy_portfolio_selected_eligible": _to_bool(
                    strategy_portfolio.get("selected_eligible", False)
                ),
                "strategy_portfolio_selected_source_eligible": _to_bool(
                    strategy_portfolio.get("selected_source_eligible", False)
                ),
                "strategy_portfolio_selected_allocation_weight": _number(
                    strategy_portfolio,
                    "selected_allocation_weight",
                    fallback=0.0,
                ),
                "strategy_portfolio_selected_allocation_notional": portfolio_allocation_notional,
                "strategy_portfolio_selected_source_allocation_notional": _number(
                    strategy_portfolio,
                    "selected_source_allocation_notional",
                    fallback=0.0,
                ),
                "strategy_portfolio_selected_eligibility_reason": str(
                    strategy_portfolio.get("selected_eligibility_reason", "")
                ),
                "strategy_portfolio_notional_cap_applied": portfolio_notional_cap_applied,
                "stop_loss": _jsonable(thresholds.stop_loss),
                "min_required_shadow_sessions": int(thresholds.min_shadow_sessions),
                "observed_shadow_sessions": int(_number(shadow, "session_count", fallback=0.0)),
                "observed_acceptance_rate": _number(shadow, "acceptance_rate"),
                "observed_median_fill_rate": _number(shadow, "median_order_fill_rate"),
                "observed_worst_fill_rate": _number(shadow, "worst_order_fill_rate"),
                "observed_worst_adverse_slippage": _number(shadow, "worst_adverse_slippage"),
                "shadow_proof_refresh_sessions": int(
                    _number(shadow, "runtime_proof_refresh_sessions", fallback=0.0)
                ),
                "shadow_proof_refresh_ready_sessions": int(
                    _number(shadow, "runtime_proof_refresh_ready_sessions", fallback=0.0)
                ),
                "shadow_proof_refresh_mixed_identity_sessions": int(
                    _number(shadow, "runtime_proof_refresh_mixed_identity_sessions", fallback=0.0)
                ),
                "shadow_proof_refresh_strategy": _strategy_key(shadow.get("proof_refresh_strategy", "")),
                "shadow_proof_refresh_market": _identity_key(shadow.get("proof_refresh_market", "")),
                "shadow_broker_readiness_sessions": int(
                    _number(shadow, "broker_readiness_sessions", fallback=0.0)
                ),
                "shadow_broker_readiness_ready_sessions": int(
                    _number(shadow, "broker_readiness_ready_sessions", fallback=0.0)
                ),
                "shadow_broker_vendor_data_readiness_sessions": int(
                    _number(shadow, "broker_vendor_data_readiness_sessions", fallback=0.0)
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    _number(shadow, "broker_vendor_data_readiness_provided_sessions", fallback=0.0)
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    _number(shadow, "broker_vendor_data_readiness_ready_sessions", fallback=0.0)
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    _number(shadow, "max_broker_vendor_data_readiness_failed_checks", fallback=0.0)
                ),
                "shadow_broker_adapter": _identity_key(shadow.get("broker_adapter", "")),
                "shadow_broker_adapter_count": int(_number(shadow, "broker_adapter_count", fallback=0.0)),
                "shadow_broker_route_readiness_sessions": int(
                    _number(shadow, "broker_route_readiness_sessions", fallback=0.0)
                ),
                "shadow_broker_route_readiness_ready_sessions": int(
                    _number(shadow, "broker_route_readiness_ready_sessions", fallback=0.0)
                ),
                "shadow_broker_route_readiness_strategy": _strategy_key(
                    shadow.get("broker_route_readiness_strategy", "")
                ),
                "shadow_broker_route_readiness_market": _identity_key(
                    shadow.get("broker_route_readiness_market", "")
                ),
                "shadow_broker_route_readiness_gap_pairs": int(
                    _number(shadow, "max_broker_route_readiness_gap_pairs", fallback=0.0)
                ),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    _number(shadow, "broker_dispatch_roundtrip_sessions", fallback=0.0)
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    _number(shadow, "broker_dispatch_roundtrip_ready_sessions", fallback=0.0)
                ),
                "shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
                    shadow.get("broker_dispatch_roundtrip_strategy", "")
                ),
                "shadow_broker_dispatch_roundtrip_market": _identity_key(
                    shadow.get("broker_dispatch_roundtrip_market", "")
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    _number(shadow, "broker_dispatch_roundtrip_scenario_count", fallback=0.0)
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    _number(shadow, "max_broker_dispatch_roundtrip_missing_request_acks", fallback=0.0)
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    _number(shadow, "max_broker_dispatch_roundtrip_rejected_orders", fallback=0.0)
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    _number(shadow, "max_broker_dispatch_roundtrip_unmatched_acks", fallback=0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    _number(shadow, "broker_route_dispatch_roundtrip_sessions", fallback=0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    _number(shadow, "broker_route_dispatch_roundtrip_ready_sessions", fallback=0.0)
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
                    shadow.get("broker_route_dispatch_roundtrip_strategy", "")
                ),
                "shadow_broker_route_dispatch_roundtrip_market": _identity_key(
                    shadow.get("broker_route_dispatch_roundtrip_market", "")
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    _number(shadow, "broker_route_dispatch_roundtrip_scenario_count", fallback=0.0)
                ),
                "proof_refresh_provided": not proof_refresh.empty,
                "proof_refresh_ready": _to_bool(proof_refresh.get("ready", False)) if not proof_refresh.empty else False,
                "proof_refresh_strategy": _strategy_key(proof_refresh.get("strategy", ""))
                if not proof_refresh.empty
                else "",
                "proof_refresh_market": _identity_key(proof_refresh.get("market", ""))
                if not proof_refresh.empty
                else "",
                "proof_refresh_mixed_identity": _to_bool(proof_refresh.get("mixed_identity", False))
                if not proof_refresh.empty
                else False,
                "proof_source": str(proof_refresh.get("proof_source", "")) if not proof_refresh.empty else "",
                "fresh_proof_required": _to_bool(proof_refresh.get("fresh_proof_required", False))
                if not proof_refresh.empty
                else False,
                "proof_refresh_recommendation": str(proof_refresh.get("recommendation", ""))
                if not proof_refresh.empty
                else "",
                "instrument_metadata_provided": not instrument_metadata.empty,
                "instrument_metadata_passed": _to_bool(instrument_metadata.get("passed", False))
                if not instrument_metadata.empty
                else False,
                "instrument_parse_coverage": _number(instrument_metadata, "parse_coverage", fallback=np.nan)
                if not instrument_metadata.empty
                else np.nan,
                "unparsed_instruments": int(_number(instrument_metadata, "unparsed_instruments", fallback=0.0))
                if not instrument_metadata.empty
                else 0,
                "data_readiness_provided": not data_readiness.empty,
                "data_readiness_ready": _to_bool(data_readiness.get("ready", False))
                if not data_readiness.empty
                else False,
                "data_readiness_failed_checks": int(_number(data_readiness, "failed_checks", fallback=0.0))
                if not data_readiness.empty
                else 0,
                "data_readiness_recommendation": str(data_readiness.get("recommendation", ""))
                if not data_readiness.empty
                else "",
                "data_readiness_comparison_provided": not data_readiness_comparison.empty,
                "data_readiness_comparison_accepted": _to_bool(data_readiness_comparison.get("accepted", False))
                if not data_readiness_comparison.empty
                else False,
                "data_readiness_comparison_dataset_count": int(
                    _number(data_readiness_comparison, "dataset_count", fallback=0.0)
                )
                if not data_readiness_comparison.empty
                else 0,
                "data_readiness_comparison_ready_rate": _number(
                    data_readiness_comparison,
                    "ready_rate",
                    fallback=np.nan,
                )
                if not data_readiness_comparison.empty
                else np.nan,
                "data_readiness_comparison_failed_checks": int(
                    _number(
                        data_readiness_comparison,
                        "total_failed_checks",
                        fallback=_number(data_readiness_comparison, "failed_checks", fallback=0.0),
                    )
                )
                if not data_readiness_comparison.empty
                else 0,
                "data_readiness_comparison_recommendation": str(
                    data_readiness_comparison.get("recommendation", "")
                )
                if not data_readiness_comparison.empty
                else "",
                "route_readiness_required": _route_readiness_required(thresholds),
                "route_readiness_provided": not route_readiness.empty,
                "route_readiness_ready": _to_bool(route_readiness.get("ready", False))
                if not route_readiness.empty
                else False,
                "route_readiness_strategy": _strategy_key(route_readiness.get("strategy", ""))
                if not route_readiness.empty
                else "",
                "route_readiness_market": _identity_key(route_readiness.get("market", ""))
                if not route_readiness.empty
                else "",
                "route_readiness_route_ready_pairs": int(
                    _number(route_readiness, "route_ready_pairs", fallback=0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_gap_pairs": int(_number(route_readiness, "gap_pairs", fallback=0.0))
                if not route_readiness.empty
                else 0,
                "route_readiness_recommendation": str(route_readiness.get("recommendation", ""))
                if not route_readiness.empty
                else "",
                "route_readiness_ops_launch_controls_present": _route_readiness_ops_controls_present(
                    route_readiness
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": int(
                    _number(route_readiness, "ops_launch_controls_blocked_pairs", 0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    _number(route_readiness, "ops_broker_roundtrip_portfolio_breach_pairs", 0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    _number(route_readiness, "ops_broker_roundtrip_portfolio_concentration_breach_pairs", 0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_resume_route_breach_pairs": int(
                    _number(route_readiness, "ops_broker_roundtrip_resume_route_breach_pairs", 0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs": int(
                    _number(route_readiness, "ops_broker_roundtrip_resume_route_gap_breach_pairs", 0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs": int(
                    _number(
                        route_readiness,
                        "ops_broker_roundtrip_resume_route_launch_control_breach_pairs",
                        0.0,
                    )
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs": int(
                    _number(route_readiness, "ops_broker_roundtrip_resume_route_portfolio_breach_pairs", 0.0)
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs": int(
                    _number(
                        route_readiness,
                        "ops_broker_roundtrip_resume_route_concentration_breach_pairs",
                        0.0,
                    )
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    _number(
                        route_readiness,
                        "ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs",
                        0.0,
                    )
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_provider_lineage_selected_run_count": int(
                    _number(
                        route_readiness,
                        "ops_provider_lineage_selected_run_count",
                        0.0,
                    )
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_provider_lineage_selected_pair_count": int(
                    _number(
                        route_readiness,
                        "ops_provider_lineage_selected_pair_count",
                        0.0,
                    )
                )
                if not route_readiness.empty
                else 0,
                "route_readiness_ops_provider_lineage_selected_pair_ids": str(
                    route_readiness.get("ops_provider_lineage_selected_pair_ids", "")
                )
                if not route_readiness.empty
                else "",
                "route_readiness_ops_provider_lineage_selected_run_dirs": str(
                    route_readiness.get("ops_provider_lineage_selected_run_dirs", "")
                )
                if not route_readiness.empty
                else "",
                "route_readiness_ops_provider_lineage_selection_contract_version": str(
                    route_readiness.get(
                        "ops_provider_lineage_selection_contract_version",
                        "",
                    )
                )
                if not route_readiness.empty
                else "",
                "route_readiness_ops_provider_lineage_selection_contract_sha256": str(
                    route_readiness.get(
                        "ops_provider_lineage_selection_contract_sha256",
                        "",
                    )
                )
                if not route_readiness.empty
                else "",
                "route_readiness_ops_provider_lineage_selection_artifact": str(
                    route_readiness.get("ops_provider_lineage_selection_artifact", "")
                )
                if not route_readiness.empty
                else "",
                "broker_readiness_provided": not broker_readiness.empty,
                "broker_readiness_ready": _to_bool(broker_readiness.get("ready", False))
                if not broker_readiness.empty
                else False,
                "broker_schema_status": str(broker_readiness.get("adapter_schema_status", ""))
                if not broker_readiness.empty
                else "",
                "broker_schema_reviewed": _to_bool(broker_readiness.get("schema_reviewed", False))
                if not broker_readiness.empty
                else False,
                "broker_schema_review_mode": str(broker_readiness.get("schema_review_mode", ""))
                if not broker_readiness.empty
                else "",
                "broker_readiness_recommendation": str(broker_readiness.get("recommendation", ""))
                if not broker_readiness.empty
                else "",
                "broker_route_readiness_required": _to_bool(
                    broker_readiness.get("route_readiness_required", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_readiness_provided": _to_bool(
                    broker_readiness.get("route_readiness_provided", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_readiness_ready": _to_bool(
                    broker_readiness.get("route_readiness_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_readiness_strategy": _strategy_key(
                    broker_readiness.get("route_readiness_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_readiness_market": _identity_key(
                    broker_readiness.get("route_readiness_market", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_readiness_route_ready_pairs": int(
                    _number(broker_readiness, "route_readiness_route_ready_pairs", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_gap_pairs": int(
                    _number(broker_readiness, "route_readiness_gap_pairs", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_recommendation": _text(
                    broker_readiness.get("route_readiness_recommendation", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_readiness_ops_launch_controls_ready": _to_bool(
                    broker_readiness.get("route_readiness_ops_launch_controls_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_readiness_ops_launch_control_failures": _text(
                    broker_readiness.get("route_readiness_ops_launch_control_failures", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    _number(broker_readiness, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    _number(broker_readiness, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs": int(
                    _number(broker_readiness, "route_readiness_ops_broker_roundtrip_resume_route_ready_runs", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_breach_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs": int(
                    _number(
                        broker_readiness,
                        "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs",
                        0.0,
                    )
                )
                if not broker_readiness.empty
                else 0,
                "broker_vendor_data_readiness_provided": _to_bool(
                    broker_readiness.get("broker_vendor_data_readiness_provided", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_vendor_data_readiness_ready": _to_bool(
                    broker_readiness.get("broker_vendor_data_readiness_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_vendor_data_readiness_failed_checks": int(
                    _number(broker_readiness, "broker_vendor_data_readiness_failed_checks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_runtime_session_required": thresholds.target_mode == "live_dryrun",
                "broker_runtime_session_provided": _to_bool(broker_readiness.get("runtime_session_provided", False))
                if not broker_readiness.empty
                else False,
                "broker_runtime_session_ready": _to_bool(broker_readiness.get("runtime_session_ready", False))
                if not broker_readiness.empty
                else False,
                "broker_runtime_guard_action": str(broker_readiness.get("runtime_guard_action", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_guard_halted": _to_bool(broker_readiness.get("runtime_guard_halted", False))
                if not broker_readiness.empty
                else False,
                "broker_runtime_target_mode": str(broker_readiness.get("runtime_target_mode", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_strategy": _strategy_key(broker_readiness.get("runtime_strategy", ""))
                if not broker_readiness.empty
                else "",
                "broker_runtime_market": _identity_key(broker_readiness.get("runtime_market", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_gate_required": thresholds.require_resume_gate,
                "broker_resume_gate_provided": _to_bool(broker_readiness.get("resume_gate_provided", False))
                if not broker_readiness.empty
                else False,
                "broker_resume_gate_ready": _to_bool(broker_readiness.get("resume_gate_ready", False))
                if not broker_readiness.empty
                else False,
                "broker_resume_strategy": _strategy_key(broker_readiness.get("resume_strategy", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_market": _identity_key(broker_readiness.get("resume_market", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_incident_strategy": _strategy_key(
                    broker_readiness.get("resume_incident_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_resume_incident_market": _identity_key(broker_readiness.get("resume_incident_market", ""))
                if not broker_readiness.empty
                else "",
                "broker_resume_proof_refresh_ready": _to_bool(
                    broker_readiness.get("resume_proof_refresh_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_resume_proof_refresh_strategy": _strategy_key(
                    broker_readiness.get("resume_proof_refresh_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_resume_proof_refresh_market": _identity_key(
                    broker_readiness.get("resume_proof_refresh_market", "")
                )
                if not broker_readiness.empty
                else "",
                **_broker_resume_route_readiness_plan_fields(
                    broker_readiness,
                    source_prefix="resume_broker_route_readiness",
                    output_prefix="broker_resume_broker_route_readiness",
                ),
                **_broker_resume_route_readiness_plan_fields(
                    broker_readiness,
                    source_prefix="resume_incident_broker_route_readiness",
                    output_prefix="broker_resume_incident_broker_route_readiness",
                ),
                "broker_dispatch_roundtrip_required": _dispatch_roundtrip_required(thresholds),
                "broker_dispatch_roundtrip_provided": _to_bool(
                    broker_readiness.get("dispatch_roundtrip_provided", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_dispatch_roundtrip_ready": _to_bool(
                    broker_readiness.get("dispatch_roundtrip_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_dispatch_roundtrip_target_mode": str(
                    broker_readiness.get("dispatch_roundtrip_target_mode", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_strategy": _strategy_key(
                    broker_readiness.get("dispatch_roundtrip_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_market": _identity_key(
                    broker_readiness.get("dispatch_roundtrip_market", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_scenario_key": str(
                    broker_readiness.get("dispatch_roundtrip_scenario_key", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_batch_id": str(
                    broker_readiness.get("dispatch_roundtrip_batch_id", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_dispatch_roundtrip_requests": int(
                    _number(broker_readiness, "dispatch_roundtrip_requests", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_acked_orders": int(
                    _number(broker_readiness, "dispatch_roundtrip_acked_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_missing_request_acks": int(
                    _number(broker_readiness, "dispatch_roundtrip_missing_request_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_rejected_orders": int(
                    _number(broker_readiness, "dispatch_roundtrip_rejected_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_unmatched_acks": int(
                    _number(broker_readiness, "dispatch_roundtrip_unmatched_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_dispatch_roundtrip_failed_checks": int(
                    _number(broker_readiness, "dispatch_roundtrip_failed_checks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_enable_dispatch_roundtrip_failed_checks": int(
                    _number(broker_readiness, "route_enable_dispatch_roundtrip_failed_checks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_required": _route_dispatch_roundtrip_required(
                    thresholds,
                    broker_readiness,
                ),
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    broker_readiness.get("route_dispatch_roundtrip_provided", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    broker_readiness.get("route_dispatch_roundtrip_ready", False)
                )
                if not broker_readiness.empty
                else False,
                "broker_route_dispatch_roundtrip_target_mode": str(
                    broker_readiness.get("route_dispatch_roundtrip_target_mode", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_strategy": _strategy_key(
                    broker_readiness.get("route_dispatch_roundtrip_strategy", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_market": _identity_key(
                    broker_readiness.get("route_dispatch_roundtrip_market", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_scenario_key": str(
                    broker_readiness.get("route_dispatch_roundtrip_scenario_key", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_batch_id": str(
                    broker_readiness.get("route_dispatch_roundtrip_batch_id", "")
                )
                if not broker_readiness.empty
                else "",
                "broker_route_dispatch_roundtrip_requests": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_requests", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_acked_orders": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_acked_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_missing_request_acks": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_missing_request_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_rejected_orders": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_rejected_orders", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                "broker_route_dispatch_roundtrip_unmatched_acks": int(
                    _number(broker_readiness, "route_dispatch_roundtrip_unmatched_acks", 0.0)
                )
                if not broker_readiness.empty
                else 0,
                **_broker_vendor_market_data_batch_plan_fields(broker_readiness),
                **_broker_vendor_final_lineage_plan_fields(broker_readiness),
                **_broker_vendor_readiness_final_lineage_plan_fields(
                    broker_readiness
                ),
                **_broker_vendor_readiness_complete_final_lineage_plan_fields(
                    broker_readiness
                ),
                **_broker_vendor_readiness_extended_complete_final_lineage_plan_fields(
                    broker_readiness
                ),
                **_broker_vendor_readiness_latest_extended_complete_final_lineage_42_plan_fields(
                    broker_readiness
                ),
                **_broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_plan_fields(
                    broker_readiness
                ),
                **_broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_plan_fields(
                    broker_readiness
                ),
                **_broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_plan_fields(
                    broker_readiness
                ),
                **_broker_shadow_broker_plan_fields(broker_readiness),
                "authorizes_submission": False,
            }
        ]
    )


def _summary(plan_row: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    ready = bool(plan_row["ready"])
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": str(plan_row["target_mode"]),
                "strategy": str(plan_row["strategy"]),
                "market": str(plan_row["market"]),
                "expected_strategy": str(plan_row["expected_strategy"]),
                "expected_market": str(plan_row["expected_market"]),
                "scenario_key": str(plan_row["scenario_key"]),
                "adapter": str(plan_row["adapter"]),
                "launch_pipeline_provided": _to_bool(plan_row["launch_pipeline_provided"]),
                "launch_pipeline_family": str(plan_row["launch_pipeline_family"]),
                "launch_pipeline_ready": _to_bool(plan_row["launch_pipeline_ready"]),
                "launch_pipeline_strategy": str(plan_row["launch_pipeline_strategy"]),
                "launch_pipeline_market": str(plan_row["launch_pipeline_market"]),
                "surface_launch_pipeline_ready": _to_bool(plan_row["surface_launch_pipeline_ready"]),
                "surface_launch_strategy": str(plan_row["surface_launch_strategy"]),
                "surface_launch_market": str(plan_row["surface_launch_market"]),
                "max_orders_per_session": int(plan_row["max_orders_per_session"]),
                "max_notional_per_session": float(plan_row["max_notional_per_session"]),
                "pre_portfolio_max_notional_per_session": float(
                    plan_row["pre_portfolio_max_notional_per_session"]
                ),
                "strategy_portfolio_required": _to_bool(plan_row["strategy_portfolio_required"]),
                "strategy_portfolio_provided": _to_bool(plan_row["strategy_portfolio_provided"]),
                "strategy_portfolio_ready": _to_bool(plan_row["strategy_portfolio_ready"]),
                "strategy_portfolio_manifest_required": _to_bool(
                    plan_row["strategy_portfolio_manifest_required"]
                ),
                "strategy_portfolio_manifest_provided": _to_bool(
                    plan_row["strategy_portfolio_manifest_provided"]
                ),
                "strategy_portfolio_manifest_current": _to_bool(
                    plan_row["strategy_portfolio_manifest_current"]
                ),
                "strategy_portfolio_manifest_sha256": str(
                    plan_row["strategy_portfolio_manifest_sha256"]
                ),
                "strategy_portfolio_manifest_error": str(
                    plan_row["strategy_portfolio_manifest_error"]
                ),
                "strategy_portfolio_contract_consistent": _to_bool(
                    plan_row["strategy_portfolio_contract_consistent"]
                ),
                "strategy_portfolio_contract_error": str(
                    plan_row["strategy_portfolio_contract_error"]
                ),
                "strategy_portfolio_non_authorizing": _to_bool(
                    plan_row["strategy_portfolio_non_authorizing"]
                ),
                "strategy_portfolio_provenance_gate_passed": _to_bool(
                    plan_row["strategy_portfolio_provenance_gate_passed"]
                ),
                "strategy_portfolio_dependency_count": int(
                    plan_row["strategy_portfolio_dependency_count"]
                ),
                "strategy_portfolio_scorecard_manifest_required": _to_bool(
                    plan_row["strategy_portfolio_scorecard_manifest_required"]
                ),
                "strategy_portfolio_scorecard_manifest_current": _to_bool(
                    plan_row["strategy_portfolio_scorecard_manifest_current"]
                ),
                "strategy_portfolio_scorecard_manifest_sha256": str(
                    plan_row["strategy_portfolio_scorecard_manifest_sha256"]
                ),
                "strategy_portfolio_scorecard_contract_consistent": _to_bool(
                    plan_row["strategy_portfolio_scorecard_contract_consistent"]
                ),
                "strategy_portfolio_scorecard_non_authorizing": _to_bool(
                    plan_row["strategy_portfolio_scorecard_non_authorizing"]
                ),
                "strategy_portfolio_scorecard_provenance_gate_passed": _to_bool(
                    plan_row["strategy_portfolio_scorecard_provenance_gate_passed"]
                ),
                "strategy_portfolio_research_family_bound": _to_bool(
                    plan_row["strategy_portfolio_research_family_bound"]
                ),
                "strategy_portfolio_research_family_provenance_current": _to_bool(
                    plan_row[
                        "strategy_portfolio_research_family_provenance_current"
                    ]
                ),
                "strategy_portfolio_research_family_id": str(
                    plan_row["strategy_portfolio_research_family_id"]
                ),
                "strategy_portfolio_research_family_registration_id": str(
                    plan_row[
                        "strategy_portfolio_research_family_registration_id"
                    ]
                ),
                "strategy_portfolio_research_family_path": str(
                    plan_row["strategy_portfolio_research_family_path"]
                ),
                "strategy_portfolio_research_family_manifest_sha256": str(
                    plan_row[
                        "strategy_portfolio_research_family_manifest_sha256"
                    ]
                ),
                "strategy_portfolio_deployment_mode": str(plan_row["strategy_portfolio_deployment_mode"]),
                "strategy_portfolio_allocation_mode": str(plan_row["strategy_portfolio_allocation_mode"]),
                "strategy_portfolio_capital_currency": str(plan_row["strategy_portfolio_capital_currency"]),
                "strategy_portfolio_total_capital": float(plan_row["strategy_portfolio_total_capital"]),
                "strategy_portfolio_allocated_weight": float(plan_row["strategy_portfolio_allocated_weight"]),
                "strategy_portfolio_allocated_notional": float(
                    plan_row["strategy_portfolio_allocated_notional"]
                ),
                "strategy_portfolio_min_strategy_count": int(
                    plan_row["strategy_portfolio_min_strategy_count"]
                ),
                "strategy_portfolio_min_market_count": int(plan_row["strategy_portfolio_min_market_count"]),
                "strategy_portfolio_max_strategy_weight": float(
                    plan_row["strategy_portfolio_max_strategy_weight"]
                ),
                "strategy_portfolio_max_market_weight": float(plan_row["strategy_portfolio_max_market_weight"]),
                "strategy_portfolio_allocated_strategy_count": int(
                    plan_row["strategy_portfolio_allocated_strategy_count"]
                ),
                "strategy_portfolio_allocated_market_count": int(
                    plan_row["strategy_portfolio_allocated_market_count"]
                ),
                "strategy_portfolio_top_strategy_by_weight": str(
                    plan_row["strategy_portfolio_top_strategy_by_weight"]
                ),
                "strategy_portfolio_top_market_by_weight": str(
                    plan_row["strategy_portfolio_top_market_by_weight"]
                ),
                "strategy_portfolio_max_strategy_allocation_weight": float(
                    plan_row["strategy_portfolio_max_strategy_allocation_weight"]
                ),
                "strategy_portfolio_max_market_allocation_weight": float(
                    plan_row["strategy_portfolio_max_market_allocation_weight"]
                ),
                "strategy_portfolio_selected_profile": str(plan_row["strategy_portfolio_selected_profile"]),
                "strategy_portfolio_selected_strategy": str(plan_row["strategy_portfolio_selected_strategy"]),
                "strategy_portfolio_selected_market": str(plan_row["strategy_portfolio_selected_market"]),
                "strategy_portfolio_selected_eligible": _to_bool(
                    plan_row["strategy_portfolio_selected_eligible"]
                ),
                "strategy_portfolio_selected_source_eligible": _to_bool(
                    plan_row["strategy_portfolio_selected_source_eligible"]
                ),
                "strategy_portfolio_selected_allocation_weight": float(
                    plan_row["strategy_portfolio_selected_allocation_weight"]
                ),
                "strategy_portfolio_selected_allocation_notional": float(
                    plan_row["strategy_portfolio_selected_allocation_notional"]
                ),
                "strategy_portfolio_selected_source_allocation_notional": float(
                    plan_row[
                        "strategy_portfolio_selected_source_allocation_notional"
                    ]
                ),
                "strategy_portfolio_selected_eligibility_reason": str(
                    plan_row["strategy_portfolio_selected_eligibility_reason"]
                ),
                "strategy_portfolio_notional_cap_applied": _to_bool(
                    plan_row["strategy_portfolio_notional_cap_applied"]
                ),
                "authorizes_submission": False,
                "proof_refresh_ready": _to_bool(plan_row["proof_refresh_ready"]),
                "proof_refresh_strategy": str(plan_row["proof_refresh_strategy"]),
                "proof_refresh_market": str(plan_row["proof_refresh_market"]),
                "proof_refresh_mixed_identity": _to_bool(plan_row["proof_refresh_mixed_identity"]),
                "shadow_proof_refresh_sessions": int(plan_row["shadow_proof_refresh_sessions"]),
                "shadow_proof_refresh_ready_sessions": int(plan_row["shadow_proof_refresh_ready_sessions"]),
                "shadow_proof_refresh_mixed_identity_sessions": int(
                    plan_row["shadow_proof_refresh_mixed_identity_sessions"]
                ),
                "shadow_proof_refresh_strategy": str(plan_row["shadow_proof_refresh_strategy"]),
                "shadow_proof_refresh_market": str(plan_row["shadow_proof_refresh_market"]),
                "shadow_broker_readiness_sessions": int(plan_row["shadow_broker_readiness_sessions"]),
                "shadow_broker_readiness_ready_sessions": int(
                    plan_row["shadow_broker_readiness_ready_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_sessions": int(
                    plan_row["shadow_broker_vendor_data_readiness_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": int(
                    plan_row["shadow_broker_vendor_data_readiness_provided_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": int(
                    plan_row["shadow_broker_vendor_data_readiness_ready_sessions"]
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": int(
                    plan_row["shadow_broker_vendor_data_readiness_failed_checks"]
                ),
                "shadow_broker_adapter": str(plan_row["shadow_broker_adapter"]),
                "shadow_broker_adapter_count": int(plan_row["shadow_broker_adapter_count"]),
                "shadow_broker_route_readiness_sessions": int(
                    plan_row["shadow_broker_route_readiness_sessions"]
                ),
                "shadow_broker_route_readiness_ready_sessions": int(
                    plan_row["shadow_broker_route_readiness_ready_sessions"]
                ),
                "shadow_broker_route_readiness_strategy": str(
                    plan_row["shadow_broker_route_readiness_strategy"]
                ),
                "shadow_broker_route_readiness_market": str(plan_row["shadow_broker_route_readiness_market"]),
                "shadow_broker_route_readiness_gap_pairs": int(
                    plan_row["shadow_broker_route_readiness_gap_pairs"]
                ),
                "shadow_broker_dispatch_roundtrip_sessions": int(
                    plan_row["shadow_broker_dispatch_roundtrip_sessions"]
                ),
                "shadow_broker_dispatch_roundtrip_ready_sessions": int(
                    plan_row["shadow_broker_dispatch_roundtrip_ready_sessions"]
                ),
                "shadow_broker_dispatch_roundtrip_strategy": str(
                    plan_row["shadow_broker_dispatch_roundtrip_strategy"]
                ),
                "shadow_broker_dispatch_roundtrip_market": str(
                    plan_row["shadow_broker_dispatch_roundtrip_market"]
                ),
                "shadow_broker_dispatch_roundtrip_scenario_count": int(
                    plan_row["shadow_broker_dispatch_roundtrip_scenario_count"]
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": int(
                    plan_row["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": int(
                    plan_row["shadow_broker_dispatch_roundtrip_rejected_orders"]
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": int(
                    plan_row["shadow_broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": int(
                    plan_row["shadow_broker_route_dispatch_roundtrip_sessions"]
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
                    plan_row["shadow_broker_route_dispatch_roundtrip_ready_sessions"]
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": str(
                    plan_row["shadow_broker_route_dispatch_roundtrip_strategy"]
                ),
                "shadow_broker_route_dispatch_roundtrip_market": str(
                    plan_row["shadow_broker_route_dispatch_roundtrip_market"]
                ),
                "shadow_broker_route_dispatch_roundtrip_scenario_count": int(
                    plan_row["shadow_broker_route_dispatch_roundtrip_scenario_count"]
                ),
                "proof_source": str(plan_row["proof_source"]),
                "instrument_metadata_passed": _to_bool(plan_row["instrument_metadata_passed"]),
                "instrument_parse_coverage": _jsonable(plan_row["instrument_parse_coverage"]),
                "data_readiness_ready": _to_bool(plan_row["data_readiness_ready"]),
                "data_readiness_comparison_accepted": _to_bool(
                    plan_row["data_readiness_comparison_accepted"]
                ),
                "data_readiness_comparison_dataset_count": int(
                    plan_row["data_readiness_comparison_dataset_count"]
                ),
                "data_readiness_comparison_ready_rate": _jsonable(
                    plan_row["data_readiness_comparison_ready_rate"]
                ),
                "route_readiness_required": _to_bool(plan_row["route_readiness_required"]),
                "route_readiness_provided": _to_bool(plan_row["route_readiness_provided"]),
                "route_readiness_ready": _to_bool(plan_row["route_readiness_ready"]),
                "route_readiness_strategy": str(plan_row["route_readiness_strategy"]),
                "route_readiness_market": str(plan_row["route_readiness_market"]),
                "route_readiness_route_ready_pairs": int(plan_row["route_readiness_route_ready_pairs"]),
                "route_readiness_gap_pairs": int(plan_row["route_readiness_gap_pairs"]),
                "route_readiness_ops_launch_controls_present": _to_bool(
                    plan_row["route_readiness_ops_launch_controls_present"]
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": int(
                    plan_row["route_readiness_ops_launch_controls_blocked_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    plan_row["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    plan_row["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_breach_pairs": int(
                    plan_row["route_readiness_ops_broker_roundtrip_resume_route_breach_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs": int(
                    plan_row["route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs": int(
                    plan_row[
                        "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs"
                    ]
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs": int(
                    plan_row["route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs"]
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs": int(
                    plan_row[
                        "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs"
                    ]
                ),
                "route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                    plan_row["route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"]
                ),
                "route_readiness_ops_provider_lineage_selected_run_count": int(
                    plan_row["route_readiness_ops_provider_lineage_selected_run_count"]
                ),
                "route_readiness_ops_provider_lineage_selected_pair_count": int(
                    plan_row["route_readiness_ops_provider_lineage_selected_pair_count"]
                ),
                "route_readiness_ops_provider_lineage_selected_pair_ids": str(
                    plan_row["route_readiness_ops_provider_lineage_selected_pair_ids"]
                ),
                "route_readiness_ops_provider_lineage_selected_run_dirs": str(
                    plan_row["route_readiness_ops_provider_lineage_selected_run_dirs"]
                ),
                "route_readiness_ops_provider_lineage_selection_contract_version": str(
                    plan_row[
                        "route_readiness_ops_provider_lineage_selection_contract_version"
                    ]
                ),
                "route_readiness_ops_provider_lineage_selection_contract_sha256": str(
                    plan_row[
                        "route_readiness_ops_provider_lineage_selection_contract_sha256"
                    ]
                ),
                "route_readiness_ops_provider_lineage_selection_artifact": str(
                    plan_row["route_readiness_ops_provider_lineage_selection_artifact"]
                ),
                "broker_readiness_ready": _to_bool(plan_row["broker_readiness_ready"]),
                "broker_schema_status": str(plan_row["broker_schema_status"]),
                "broker_schema_reviewed": _to_bool(plan_row["broker_schema_reviewed"]),
                "broker_schema_review_mode": str(plan_row["broker_schema_review_mode"]),
                "broker_route_readiness_required": _to_bool(plan_row["broker_route_readiness_required"]),
                "broker_route_readiness_provided": _to_bool(plan_row["broker_route_readiness_provided"]),
                "broker_route_readiness_ready": _to_bool(plan_row["broker_route_readiness_ready"]),
                "broker_route_readiness_strategy": str(plan_row["broker_route_readiness_strategy"]),
                "broker_route_readiness_market": str(plan_row["broker_route_readiness_market"]),
                "broker_route_readiness_route_ready_pairs": int(
                    plan_row["broker_route_readiness_route_ready_pairs"]
                ),
                "broker_route_readiness_gap_pairs": int(plan_row["broker_route_readiness_gap_pairs"]),
                "broker_route_readiness_recommendation": str(plan_row["broker_route_readiness_recommendation"]),
                "broker_route_readiness_ops_launch_controls_ready": _to_bool(
                    plan_row["broker_route_readiness_ops_launch_controls_ready"]
                ),
                "broker_route_readiness_ops_launch_control_failures": str(
                    plan_row["broker_route_readiness_ops_launch_control_failures"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                    ]
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
                    ]
                ),
                "broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs"
                    ]
                ),
                "broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs"]
                ),
                "broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs"
                    ]
                ),
                "broker_vendor_data_readiness_provided": _to_bool(
                    plan_row["broker_vendor_data_readiness_provided"]
                ),
                "broker_vendor_data_readiness_ready": _to_bool(
                    plan_row["broker_vendor_data_readiness_ready"]
                ),
                "broker_vendor_data_readiness_failed_checks": int(
                    plan_row["broker_vendor_data_readiness_failed_checks"]
                ),
                "broker_runtime_session_required": _to_bool(plan_row["broker_runtime_session_required"]),
                "broker_runtime_session_provided": _to_bool(plan_row["broker_runtime_session_provided"]),
                "broker_runtime_session_ready": _to_bool(plan_row["broker_runtime_session_ready"]),
                "broker_runtime_guard_action": str(plan_row["broker_runtime_guard_action"]),
                "broker_runtime_guard_halted": _to_bool(plan_row["broker_runtime_guard_halted"]),
                "broker_runtime_target_mode": str(plan_row["broker_runtime_target_mode"]),
                "broker_runtime_strategy": str(plan_row["broker_runtime_strategy"]),
                "broker_runtime_market": str(plan_row["broker_runtime_market"]),
                "broker_resume_gate_required": _to_bool(plan_row["broker_resume_gate_required"]),
                "broker_resume_gate_provided": _to_bool(plan_row["broker_resume_gate_provided"]),
                "broker_resume_gate_ready": _to_bool(plan_row["broker_resume_gate_ready"]),
                "broker_resume_strategy": str(plan_row["broker_resume_strategy"]),
                "broker_resume_market": str(plan_row["broker_resume_market"]),
                "broker_resume_proof_refresh_ready": _to_bool(
                    plan_row["broker_resume_proof_refresh_ready"]
                ),
                "broker_resume_proof_refresh_strategy": str(
                    plan_row["broker_resume_proof_refresh_strategy"]
                ),
                "broker_resume_proof_refresh_market": str(plan_row["broker_resume_proof_refresh_market"]),
                **_broker_resume_route_readiness_summary_fields(
                    plan_row,
                    prefix="broker_resume_broker_route_readiness",
                ),
                **_broker_resume_route_readiness_summary_fields(
                    plan_row,
                    prefix="broker_resume_incident_broker_route_readiness",
                ),
                "broker_dispatch_roundtrip_required": _to_bool(
                    plan_row["broker_dispatch_roundtrip_required"]
                ),
                "broker_dispatch_roundtrip_provided": _to_bool(
                    plan_row["broker_dispatch_roundtrip_provided"]
                ),
                "broker_dispatch_roundtrip_ready": _to_bool(plan_row["broker_dispatch_roundtrip_ready"]),
                "broker_dispatch_roundtrip_target_mode": str(
                    plan_row["broker_dispatch_roundtrip_target_mode"]
                ),
                "broker_dispatch_roundtrip_strategy": str(plan_row["broker_dispatch_roundtrip_strategy"]),
                "broker_dispatch_roundtrip_market": str(plan_row["broker_dispatch_roundtrip_market"]),
                "broker_dispatch_roundtrip_scenario_key": str(
                    plan_row["broker_dispatch_roundtrip_scenario_key"]
                ),
                "broker_dispatch_roundtrip_batch_id": str(plan_row["broker_dispatch_roundtrip_batch_id"]),
                "broker_dispatch_roundtrip_requests": int(plan_row["broker_dispatch_roundtrip_requests"]),
                "broker_dispatch_roundtrip_acked_orders": int(
                    plan_row["broker_dispatch_roundtrip_acked_orders"]
                ),
                "broker_dispatch_roundtrip_missing_request_acks": int(
                    plan_row["broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_dispatch_roundtrip_rejected_orders": int(
                    plan_row["broker_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_dispatch_roundtrip_unmatched_acks": int(
                    plan_row["broker_dispatch_roundtrip_unmatched_acks"]
                ),
                "broker_dispatch_roundtrip_failed_checks": int(
                    plan_row["broker_dispatch_roundtrip_failed_checks"]
                ),
                "broker_route_enable_dispatch_roundtrip_failed_checks": int(
                    plan_row["broker_route_enable_dispatch_roundtrip_failed_checks"]
                ),
                "broker_route_dispatch_roundtrip_required": _to_bool(
                    plan_row["broker_route_dispatch_roundtrip_required"]
                ),
                "broker_route_dispatch_roundtrip_provided": _to_bool(
                    plan_row["broker_route_dispatch_roundtrip_provided"]
                ),
                "broker_route_dispatch_roundtrip_ready": _to_bool(
                    plan_row["broker_route_dispatch_roundtrip_ready"]
                ),
                "broker_route_dispatch_roundtrip_target_mode": str(
                    plan_row["broker_route_dispatch_roundtrip_target_mode"]
                ),
                "broker_route_dispatch_roundtrip_strategy": str(
                    plan_row["broker_route_dispatch_roundtrip_strategy"]
                ),
                "broker_route_dispatch_roundtrip_market": str(
                    plan_row["broker_route_dispatch_roundtrip_market"]
                ),
                "broker_route_dispatch_roundtrip_scenario_key": str(
                    plan_row["broker_route_dispatch_roundtrip_scenario_key"]
                ),
                "broker_route_dispatch_roundtrip_batch_id": str(
                    plan_row["broker_route_dispatch_roundtrip_batch_id"]
                ),
                "broker_route_dispatch_roundtrip_requests": int(
                    plan_row["broker_route_dispatch_roundtrip_requests"]
                ),
                "broker_route_dispatch_roundtrip_acked_orders": int(
                    plan_row["broker_route_dispatch_roundtrip_acked_orders"]
                ),
                "broker_route_dispatch_roundtrip_missing_request_acks": int(
                    plan_row["broker_route_dispatch_roundtrip_missing_request_acks"]
                ),
                "broker_route_dispatch_roundtrip_rejected_orders": int(
                    plan_row["broker_route_dispatch_roundtrip_rejected_orders"]
                ),
                "broker_route_dispatch_roundtrip_unmatched_acks": int(
                    plan_row["broker_route_dispatch_roundtrip_unmatched_acks"]
                ),
                **_broker_vendor_market_data_batch_summary_fields(plan_row),
                **_broker_vendor_final_lineage_summary_fields(plan_row),
                **_broker_vendor_readiness_final_lineage_summary_fields(
                    plan_row
                ),
                **_broker_vendor_readiness_complete_final_lineage_summary_fields(
                    plan_row
                ),
                **_broker_vendor_readiness_extended_complete_final_lineage_summary_fields(
                    plan_row
                ),
                **_broker_vendor_readiness_latest_extended_complete_final_lineage_42_summary_fields(
                    plan_row
                ),
                **_broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_summary_fields(
                    plan_row
                ),
                **_broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_summary_fields(
                    plan_row
                ),
                **_broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_summary_fields(
                    plan_row
                ),
                **_broker_shadow_broker_summary_fields(plan_row),
                "failed_checks": failed,
                "recommendation": "scale_up_with_controls" if ready else "do_not_scale",
            }
        ]
    )


def _broker_resume_route_readiness_summary_fields(plan_row: pd.Series, *, prefix: str) -> dict[str, object]:
    return {
        f"{prefix}_required": _to_bool(plan_row[f"{prefix}_required"]),
        f"{prefix}_provided": _to_bool(plan_row[f"{prefix}_provided"]),
        f"{prefix}_ready": _to_bool(plan_row[f"{prefix}_ready"]),
        f"{prefix}_strategy": _strategy_key(plan_row[f"{prefix}_strategy"]),
        f"{prefix}_market": _identity_key(plan_row[f"{prefix}_market"]),
        f"{prefix}_route_ready_pairs": int(plan_row[f"{prefix}_route_ready_pairs"]),
        f"{prefix}_gap_pairs": int(plan_row[f"{prefix}_gap_pairs"]),
        f"{prefix}_recommendation": _text(plan_row[f"{prefix}_recommendation"]),
        f"{prefix}_ops_launch_controls_ready": _to_bool(
            plan_row[f"{prefix}_ops_launch_controls_ready"]
        ),
        f"{prefix}_ops_launch_control_failures": _text(plan_row[f"{prefix}_ops_launch_control_failures"]),
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _broker_resume_route_readiness_config(plan_row: pd.Series, *, prefix: str) -> dict[str, object]:
    return {
        "required": _to_bool(plan_row[f"{prefix}_required"]),
        "provided": _to_bool(plan_row[f"{prefix}_provided"]),
        "ready": _to_bool(plan_row[f"{prefix}_ready"]),
        "strategy": _strategy_key(plan_row[f"{prefix}_strategy"]),
        "market": _identity_key(plan_row[f"{prefix}_market"]),
        "route_ready_pairs": int(plan_row[f"{prefix}_route_ready_pairs"]),
        "gap_pairs": int(plan_row[f"{prefix}_gap_pairs"]),
        "recommendation": _text(plan_row[f"{prefix}_recommendation"]),
        "ops_launch_controls_ready": _to_bool(plan_row[f"{prefix}_ops_launch_controls_ready"]),
        "ops_launch_control_failures": _text(plan_row[f"{prefix}_ops_launch_control_failures"]),
        "ops_broker_roundtrip_portfolio_safe_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs"]
        ),
        "ops_broker_roundtrip_portfolio_breach_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs"]
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            plan_row[f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs"]
        ),
    }


def _config(plan_row: pd.Series, checks: pd.DataFrame, thresholds: ScaleUpThresholds) -> dict[str, Any]:
    failed_check_records = _failed_check_records(checks)
    return {
        "schema_version": 1,
        "ready": bool(plan_row["ready"]),
        "authorizes_submission": False,
        "failed_check_count": len(failed_check_records),
        "target_mode": str(plan_row["target_mode"]),
        "strategy": str(plan_row["strategy"]),
        "market": str(plan_row["market"]),
        "scenario_key": str(plan_row["scenario_key"]),
        "adapter": str(plan_row["adapter"]),
        "identity": {
            "strategy": str(plan_row["strategy"]),
            "market": str(plan_row["market"]),
            "expected_strategy": str(plan_row["expected_strategy"]),
            "expected_market": str(plan_row["expected_market"]),
        },
        "launch_pipeline": {
            "provided": _to_bool(plan_row["launch_pipeline_provided"]),
            "family": str(plan_row["launch_pipeline_family"]),
            "summary_file": str(plan_row["launch_pipeline_summary_file"]),
            "ready": _to_bool(plan_row["launch_pipeline_ready"]),
            "strategy": str(plan_row["launch_pipeline_strategy"]),
            "market": str(plan_row["launch_pipeline_market"]),
            "expected_strategy": str(plan_row["launch_pipeline_expected_strategy"]),
            "expected_market": str(plan_row["launch_pipeline_expected_market"]),
            "failed_components": int(plan_row["launch_pipeline_failed_components"]),
            "skipped_components": int(plan_row["launch_pipeline_skipped_components"]),
        },
        "surface_launch_pipeline": {
            "provided": _to_bool(plan_row["surface_launch_pipeline_provided"]),
            "ready": _to_bool(plan_row["surface_launch_pipeline_ready"]),
            "strategy": str(plan_row["surface_launch_strategy"]),
            "market": str(plan_row["surface_launch_market"]),
            "expected_strategy": str(plan_row["surface_launch_expected_strategy"]),
            "expected_market": str(plan_row["surface_launch_expected_market"]),
            "failed_components": int(plan_row["surface_launch_failed_components"]),
            "skipped_components": int(plan_row["surface_launch_skipped_components"]),
        },
        "limits": {
            "max_orders_per_session": int(plan_row["max_orders_per_session"]),
            "max_notional_per_session": float(plan_row["max_notional_per_session"]),
            "pre_portfolio_max_notional_per_session": float(
                plan_row["pre_portfolio_max_notional_per_session"]
            ),
            "max_scale_multiplier": float(plan_row["max_scale_multiplier"]),
            "stop_loss": _jsonable(plan_row["stop_loss"]),
        },
        "strategy_portfolio": {
            "required": _to_bool(plan_row["strategy_portfolio_required"]),
            "provided": _to_bool(plan_row["strategy_portfolio_provided"]),
            "ready": _to_bool(plan_row["strategy_portfolio_ready"]),
            "manifest_required": _to_bool(
                plan_row["strategy_portfolio_manifest_required"]
            ),
            "manifest_provided": _to_bool(
                plan_row["strategy_portfolio_manifest_provided"]
            ),
            "manifest_current": _to_bool(
                plan_row["strategy_portfolio_manifest_current"]
            ),
            "manifest_sha256": str(
                plan_row["strategy_portfolio_manifest_sha256"]
            ),
            "manifest_error": str(
                plan_row["strategy_portfolio_manifest_error"]
            ),
            "contract_consistent": _to_bool(
                plan_row["strategy_portfolio_contract_consistent"]
            ),
            "contract_error": str(
                plan_row["strategy_portfolio_contract_error"]
            ),
            "non_authorizing": _to_bool(
                plan_row["strategy_portfolio_non_authorizing"]
            ),
            "provenance_gate_passed": _to_bool(
                plan_row["strategy_portfolio_provenance_gate_passed"]
            ),
            "dependency_count": int(
                plan_row["strategy_portfolio_dependency_count"]
            ),
            "scorecard_provenance": {
                "manifest_required": _to_bool(
                    plan_row["strategy_portfolio_scorecard_manifest_required"]
                ),
                "manifest_current": _to_bool(
                    plan_row["strategy_portfolio_scorecard_manifest_current"]
                ),
                "manifest_sha256": str(
                    plan_row["strategy_portfolio_scorecard_manifest_sha256"]
                ),
                "contract_consistent": _to_bool(
                    plan_row[
                        "strategy_portfolio_scorecard_contract_consistent"
                    ]
                ),
                "non_authorizing": _to_bool(
                    plan_row["strategy_portfolio_scorecard_non_authorizing"]
                ),
                "gate_passed": _to_bool(
                    plan_row[
                        "strategy_portfolio_scorecard_provenance_gate_passed"
                    ]
                ),
            },
            "research_family": {
                "bound": _to_bool(
                    plan_row["strategy_portfolio_research_family_bound"]
                ),
                "provenance_current": _to_bool(
                    plan_row[
                        "strategy_portfolio_research_family_provenance_current"
                    ]
                ),
                "family_id": str(
                    plan_row["strategy_portfolio_research_family_id"]
                ),
                "registration_id": str(
                    plan_row[
                        "strategy_portfolio_research_family_registration_id"
                    ]
                ),
                "path": str(
                    plan_row["strategy_portfolio_research_family_path"]
                ),
                "manifest_sha256": str(
                    plan_row[
                        "strategy_portfolio_research_family_manifest_sha256"
                    ]
                ),
            },
            "deployment_mode": str(plan_row["strategy_portfolio_deployment_mode"]),
            "allocation_mode": str(plan_row["strategy_portfolio_allocation_mode"]),
            "capital_currency": str(plan_row["strategy_portfolio_capital_currency"]),
            "total_capital": float(plan_row["strategy_portfolio_total_capital"]),
            "allocated_weight": float(plan_row["strategy_portfolio_allocated_weight"]),
            "allocated_notional": float(plan_row["strategy_portfolio_allocated_notional"]),
            "min_strategy_count": int(plan_row["strategy_portfolio_min_strategy_count"]),
            "min_market_count": int(plan_row["strategy_portfolio_min_market_count"]),
            "max_strategy_weight": float(plan_row["strategy_portfolio_max_strategy_weight"]),
            "max_market_weight": float(plan_row["strategy_portfolio_max_market_weight"]),
            "allocated_strategy_count": int(plan_row["strategy_portfolio_allocated_strategy_count"]),
            "allocated_market_count": int(plan_row["strategy_portfolio_allocated_market_count"]),
            "top_strategy_by_weight": str(plan_row["strategy_portfolio_top_strategy_by_weight"]),
            "top_market_by_weight": str(plan_row["strategy_portfolio_top_market_by_weight"]),
            "max_strategy_allocation_weight": float(
                plan_row["strategy_portfolio_max_strategy_allocation_weight"]
            ),
            "max_market_allocation_weight": float(
                plan_row["strategy_portfolio_max_market_allocation_weight"]
            ),
            "selected_profile": str(plan_row["strategy_portfolio_selected_profile"]),
            "selected_strategy": str(plan_row["strategy_portfolio_selected_strategy"]),
            "selected_market": str(plan_row["strategy_portfolio_selected_market"]),
            "selected_eligible": _to_bool(plan_row["strategy_portfolio_selected_eligible"]),
            "selected_source_eligible": _to_bool(
                plan_row["strategy_portfolio_selected_source_eligible"]
            ),
            "selected_allocation_weight": float(plan_row["strategy_portfolio_selected_allocation_weight"]),
            "selected_allocation_notional": float(plan_row["strategy_portfolio_selected_allocation_notional"]),
            "selected_source_allocation_notional": float(
                plan_row[
                    "strategy_portfolio_selected_source_allocation_notional"
                ]
            ),
            "selected_eligibility_reason": str(plan_row["strategy_portfolio_selected_eligibility_reason"]),
            "notional_cap_applied": _to_bool(plan_row["strategy_portfolio_notional_cap_applied"]),
        },
        "kill_switches": {
            "max_total_failed_component_checks": thresholds.max_total_failed_component_checks,
            "max_total_unmatched_fills": thresholds.max_total_unmatched_fills,
            "max_total_mismatched_orders": thresholds.max_total_mismatched_orders,
            "max_total_overfilled_orders": thresholds.max_total_overfilled_orders,
            "max_telemetry_age_ns": _jsonable(thresholds.max_telemetry_age_ns),
            "max_lifecycle_orders": _jsonable(thresholds.max_lifecycle_orders),
            "max_replace_orders": _jsonable(thresholds.max_replace_orders),
            "max_open_order_count": _jsonable(thresholds.max_open_order_count),
            "max_open_order_qty": _jsonable(thresholds.max_open_order_qty),
            "max_open_order_notional": _jsonable(thresholds.max_open_order_notional),
            "max_open_order_age_ns": _jsonable(thresholds.max_open_order_age_ns),
            "max_gross_position_qty": _jsonable(thresholds.max_gross_position_qty),
            "max_abs_net_position_qty": _jsonable(thresholds.max_abs_net_position_qty),
            "max_gross_notional": _jsonable(thresholds.max_gross_notional),
            "max_abs_net_delta": _jsonable(thresholds.max_abs_net_delta),
            "max_abs_net_vega": _jsonable(thresholds.max_abs_net_vega),
            "max_worst_adverse_slippage": _jsonable(thresholds.max_worst_adverse_slippage),
        },
        "proof_freshness": {
            "required": bool(thresholds.require_proof_refresh),
            "provided": _to_bool(plan_row["proof_refresh_provided"]),
            "ready": _to_bool(plan_row["proof_refresh_ready"]),
            "strategy": str(plan_row["proof_refresh_strategy"]),
            "market": str(plan_row["proof_refresh_market"]),
            "mixed_identity": _to_bool(plan_row["proof_refresh_mixed_identity"]),
            "proof_source": str(plan_row["proof_source"]),
            "fresh_proof_required": _to_bool(plan_row["fresh_proof_required"]),
            "recommendation": str(plan_row["proof_refresh_recommendation"]),
        },
        "shadow_proof_freshness": {
            "sessions": int(plan_row["shadow_proof_refresh_sessions"]),
            "ready_sessions": int(plan_row["shadow_proof_refresh_ready_sessions"]),
            "mixed_identity_sessions": int(plan_row["shadow_proof_refresh_mixed_identity_sessions"]),
            "strategy": str(plan_row["shadow_proof_refresh_strategy"]),
            "market": str(plan_row["shadow_proof_refresh_market"]),
        },
        "shadow_broker_readiness": {
            "sessions": int(plan_row["shadow_broker_readiness_sessions"]),
            "ready_sessions": int(plan_row["shadow_broker_readiness_ready_sessions"]),
            "adapter": str(plan_row["shadow_broker_adapter"]),
            "adapter_count": int(plan_row["shadow_broker_adapter_count"]),
            "broker_vendor_data_readiness": {
                "sessions": int(plan_row["shadow_broker_vendor_data_readiness_sessions"]),
                "provided_sessions": int(plan_row["shadow_broker_vendor_data_readiness_provided_sessions"]),
                "ready_sessions": int(plan_row["shadow_broker_vendor_data_readiness_ready_sessions"]),
                "failed_checks": int(plan_row["shadow_broker_vendor_data_readiness_failed_checks"]),
            },
            "route_readiness": {
                "sessions": int(plan_row["shadow_broker_route_readiness_sessions"]),
                "ready_sessions": int(plan_row["shadow_broker_route_readiness_ready_sessions"]),
                "strategy": str(plan_row["shadow_broker_route_readiness_strategy"]),
                "market": str(plan_row["shadow_broker_route_readiness_market"]),
                "max_gap_pairs": int(plan_row["shadow_broker_route_readiness_gap_pairs"]),
            },
            "dispatch_roundtrip": {
                "sessions": int(plan_row["shadow_broker_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(plan_row["shadow_broker_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(plan_row["shadow_broker_dispatch_roundtrip_strategy"]),
                "market": str(plan_row["shadow_broker_dispatch_roundtrip_market"]),
                "scenario_count": int(plan_row["shadow_broker_dispatch_roundtrip_scenario_count"]),
                "max_missing_request_acks": int(
                    plan_row["shadow_broker_dispatch_roundtrip_missing_request_acks"]
                ),
                "max_rejected_orders": int(plan_row["shadow_broker_dispatch_roundtrip_rejected_orders"]),
                "max_unmatched_acks": int(plan_row["shadow_broker_dispatch_roundtrip_unmatched_acks"]),
            },
            "route_dispatch_roundtrip": {
                "sessions": int(plan_row["shadow_broker_route_dispatch_roundtrip_sessions"]),
                "ready_sessions": int(plan_row["shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
                "strategy": str(plan_row["shadow_broker_route_dispatch_roundtrip_strategy"]),
                "market": str(plan_row["shadow_broker_route_dispatch_roundtrip_market"]),
                "scenario_count": int(plan_row["shadow_broker_route_dispatch_roundtrip_scenario_count"]),
            },
        },
        "instrument_metadata": {
            "required": bool(thresholds.require_instrument_metadata),
            "provided": _to_bool(plan_row["instrument_metadata_provided"]),
            "passed": _to_bool(plan_row["instrument_metadata_passed"]),
            "parse_coverage": _jsonable(plan_row["instrument_parse_coverage"]),
            "min_parse_coverage": float(thresholds.min_instrument_parse_coverage),
            "unparsed_instruments": int(plan_row["unparsed_instruments"]),
        },
        "data_readiness": {
            "required": bool(thresholds.require_data_readiness),
            "provided": _to_bool(plan_row["data_readiness_provided"]),
            "ready": _to_bool(plan_row["data_readiness_ready"]),
            "failed_checks": int(plan_row["data_readiness_failed_checks"]),
            "recommendation": str(plan_row["data_readiness_recommendation"]),
        },
        "data_readiness_comparison": {
            "required": bool(thresholds.require_data_readiness_comparison),
            "provided": _to_bool(plan_row["data_readiness_comparison_provided"]),
            "accepted": _to_bool(plan_row["data_readiness_comparison_accepted"]),
            "dataset_count": int(plan_row["data_readiness_comparison_dataset_count"]),
            "ready_rate": _jsonable(plan_row["data_readiness_comparison_ready_rate"]),
            "failed_checks": int(plan_row["data_readiness_comparison_failed_checks"]),
            "recommendation": str(plan_row["data_readiness_comparison_recommendation"]),
        },
        "route_readiness": {
            "required": _to_bool(plan_row["route_readiness_required"]),
            "provided": _to_bool(plan_row["route_readiness_provided"]),
            "ready": _to_bool(plan_row["route_readiness_ready"]),
            "strategy": _strategy_key(plan_row["route_readiness_strategy"]),
            "market": _identity_key(plan_row["route_readiness_market"]),
            "route_ready_pairs": int(plan_row["route_readiness_route_ready_pairs"]),
            "gap_pairs": int(plan_row["route_readiness_gap_pairs"]),
            "ops_launch_controls_present": _to_bool(plan_row["route_readiness_ops_launch_controls_present"]),
            "ops_launch_controls_blocked_pairs": int(
                plan_row["route_readiness_ops_launch_controls_blocked_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs"]
            ),
            "ops_broker_roundtrip_resume_route_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_resume_route_breach_pairs"]
            ),
            "ops_broker_roundtrip_resume_route_gap_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs"]
            ),
            "ops_broker_roundtrip_resume_route_launch_control_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs"]
            ),
            "ops_broker_roundtrip_resume_route_portfolio_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs"]
            ),
            "ops_broker_roundtrip_resume_route_concentration_breach_pairs": int(
                plan_row["route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs"]
            ),
            "ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs": int(
                plan_row["route_readiness_ops_provider_broker_roundtrip_synthetic_sidecar_breach_pairs"]
            ),
            "ops_provider_lineage_selected_run_count": int(
                plan_row["route_readiness_ops_provider_lineage_selected_run_count"]
            ),
            "ops_provider_lineage_selected_pair_count": int(
                plan_row["route_readiness_ops_provider_lineage_selected_pair_count"]
            ),
            "ops_provider_lineage_selected_pair_ids": str(
                plan_row["route_readiness_ops_provider_lineage_selected_pair_ids"]
            ),
            "ops_provider_lineage_selected_run_dirs": str(
                plan_row["route_readiness_ops_provider_lineage_selected_run_dirs"]
            ),
            "ops_provider_lineage_selection_contract_version": str(
                plan_row[
                    "route_readiness_ops_provider_lineage_selection_contract_version"
                ]
            ),
            "ops_provider_lineage_selection_contract_sha256": str(
                plan_row[
                    "route_readiness_ops_provider_lineage_selection_contract_sha256"
                ]
            ),
            "ops_provider_lineage_selection_artifact": str(
                plan_row["route_readiness_ops_provider_lineage_selection_artifact"]
            ),
            "recommendation": _text(plan_row["route_readiness_recommendation"]),
        },
        "broker_readiness": {
            "required": _broker_readiness_required(thresholds),
            "provided": _to_bool(plan_row["broker_readiness_provided"]),
            "ready": _to_bool(plan_row["broker_readiness_ready"]),
            "adapter_schema_status": str(plan_row["broker_schema_status"]),
            "schema_reviewed": _to_bool(plan_row["broker_schema_reviewed"]),
            "schema_review_mode": str(plan_row["broker_schema_review_mode"]),
            "recommendation": str(plan_row["broker_readiness_recommendation"]),
            "route_readiness": {
                "required": _to_bool(plan_row["broker_route_readiness_required"]),
                "provided": _to_bool(plan_row["broker_route_readiness_provided"]),
                "ready": _to_bool(plan_row["broker_route_readiness_ready"]),
                "strategy": _strategy_key(plan_row["broker_route_readiness_strategy"]),
                "market": _identity_key(plan_row["broker_route_readiness_market"]),
                "route_ready_pairs": int(plan_row["broker_route_readiness_route_ready_pairs"]),
                "gap_pairs": int(plan_row["broker_route_readiness_gap_pairs"]),
                "recommendation": _text(plan_row["broker_route_readiness_recommendation"]),
                "ops_launch_controls_ready": _to_bool(
                    plan_row["broker_route_readiness_ops_launch_controls_ready"]
                ),
                "ops_launch_control_failures": _text(plan_row["broker_route_readiness_ops_launch_control_failures"]),
                "ops_broker_roundtrip_portfolio_safe_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]
                ),
                "ops_broker_roundtrip_portfolio_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]
                ),
                "ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                    ]
                ),
                "ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"
                    ]
                ),
                "ops_broker_roundtrip_resume_route_ready_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs"]
                ),
                "ops_broker_roundtrip_resume_route_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs"]
                ),
                "ops_broker_roundtrip_resume_route_gap_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs"]
                ),
                "ops_broker_roundtrip_resume_route_launch_control_breach_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs"
                    ]
                ),
                "ops_broker_roundtrip_resume_route_portfolio_breach_runs": int(
                    plan_row["broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs"]
                ),
                "ops_broker_roundtrip_resume_route_concentration_breach_runs": int(
                    plan_row[
                        "broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs"
                    ]
                ),
            },
            "broker_vendor_data_readiness": {
                "provided": _to_bool(plan_row["broker_vendor_data_readiness_provided"]),
                "ready": _to_bool(plan_row["broker_vendor_data_readiness_ready"]),
                "failed_checks": int(plan_row["broker_vendor_data_readiness_failed_checks"]),
            },
            "runtime_session": {
                "required": _to_bool(plan_row["broker_runtime_session_required"]),
                "provided": _to_bool(plan_row["broker_runtime_session_provided"]),
                "ready": _to_bool(plan_row["broker_runtime_session_ready"]),
                "guard_action": str(plan_row["broker_runtime_guard_action"]),
                "guard_halted": _to_bool(plan_row["broker_runtime_guard_halted"]),
                "target_mode": str(plan_row["broker_runtime_target_mode"]),
                "strategy": str(plan_row["broker_runtime_strategy"]),
                "market": str(plan_row["broker_runtime_market"]),
            },
            "resume_gate": {
                "required": _to_bool(plan_row["broker_resume_gate_required"]),
                "provided": _to_bool(plan_row["broker_resume_gate_provided"]),
                "ready": _to_bool(plan_row["broker_resume_gate_ready"]),
                "strategy": str(plan_row["broker_resume_strategy"]),
                "market": str(plan_row["broker_resume_market"]),
                "incident_strategy": str(plan_row["broker_resume_incident_strategy"]),
                "incident_market": str(plan_row["broker_resume_incident_market"]),
                "proof_refresh_ready": _to_bool(plan_row["broker_resume_proof_refresh_ready"]),
                "proof_refresh_strategy": str(plan_row["broker_resume_proof_refresh_strategy"]),
                "proof_refresh_market": str(plan_row["broker_resume_proof_refresh_market"]),
                "broker_route_readiness": _broker_resume_route_readiness_config(
                    plan_row,
                    prefix="broker_resume_broker_route_readiness",
                ),
                "incident_broker_route_readiness": _broker_resume_route_readiness_config(
                    plan_row,
                    prefix="broker_resume_incident_broker_route_readiness",
                ),
            },
            "dispatch_roundtrip": {
                "required": _to_bool(plan_row["broker_dispatch_roundtrip_required"]),
                "provided": _to_bool(plan_row["broker_dispatch_roundtrip_provided"]),
                "ready": _to_bool(plan_row["broker_dispatch_roundtrip_ready"]),
                "target_mode": str(plan_row["broker_dispatch_roundtrip_target_mode"]),
                "strategy": str(plan_row["broker_dispatch_roundtrip_strategy"]),
                "market": str(plan_row["broker_dispatch_roundtrip_market"]),
                "scenario_key": str(plan_row["broker_dispatch_roundtrip_scenario_key"]),
                "dispatch_batch_id": str(plan_row["broker_dispatch_roundtrip_batch_id"]),
                "requests": int(plan_row["broker_dispatch_roundtrip_requests"]),
                "acked_orders": int(plan_row["broker_dispatch_roundtrip_acked_orders"]),
                "missing_request_acks": int(plan_row["broker_dispatch_roundtrip_missing_request_acks"]),
                "rejected_orders": int(plan_row["broker_dispatch_roundtrip_rejected_orders"]),
                "unmatched_acks": int(plan_row["broker_dispatch_roundtrip_unmatched_acks"]),
                "failed_checks": int(plan_row["broker_dispatch_roundtrip_failed_checks"]),
                "route_enable_dispatch_roundtrip": {
                    "failed_checks": int(plan_row["broker_route_enable_dispatch_roundtrip_failed_checks"]),
                },
                "route_proof": {
                    "required": _to_bool(plan_row["broker_route_dispatch_roundtrip_required"]),
                    "provided": _to_bool(plan_row["broker_route_dispatch_roundtrip_provided"]),
                    "ready": _to_bool(plan_row["broker_route_dispatch_roundtrip_ready"]),
                    "target_mode": str(plan_row["broker_route_dispatch_roundtrip_target_mode"]),
                    "strategy": str(plan_row["broker_route_dispatch_roundtrip_strategy"]),
                    "market": str(plan_row["broker_route_dispatch_roundtrip_market"]),
                    "scenario_key": str(plan_row["broker_route_dispatch_roundtrip_scenario_key"]),
                    "dispatch_batch_id": str(plan_row["broker_route_dispatch_roundtrip_batch_id"]),
                    "requests": int(plan_row["broker_route_dispatch_roundtrip_requests"]),
                    "acked_orders": int(plan_row["broker_route_dispatch_roundtrip_acked_orders"]),
                    "missing_request_acks": int(
                        plan_row["broker_route_dispatch_roundtrip_missing_request_acks"]
                    ),
                    "rejected_orders": int(plan_row["broker_route_dispatch_roundtrip_rejected_orders"]),
                    "unmatched_acks": int(plan_row["broker_route_dispatch_roundtrip_unmatched_acks"]),
                },
                "vendor_market_data_batch": _broker_vendor_market_data_batch_config(plan_row),
                "vendor_market_data_batch_lineage_comparison": {
                    "required": _to_bool(
                        plan_row[
                            "broker_vendor_market_data_batch_lineage_match_required"
                        ]
                    ),
                    "matches": _to_bool(
                        plan_row["broker_vendor_market_data_batch_lineage_matches"]
                    ),
                    "current_application_lineage_sha256": str(
                        plan_row[
                            "vendor_market_data_batch_application_lineage_sha256"
                        ]
                    ),
                    "broker_application_lineage_sha256": str(
                        plan_row[
                            "broker_vendor_market_data_batch_application_lineage_sha256"
                        ]
                    ),
                    "carried_application_lineage_sha256": str(
                        plan_row[
                            "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
                        ]
                    ),
                },
                "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                    _broker_vendor_final_lineage_config(plan_row)
                ),
                SCALEUP_FINAL_LINEAGE_COMPARISON_KEY: (
                    _broker_vendor_scaleup_final_lineage_config(plan_row)
                ),
                SCALEUP_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
                    _broker_vendor_scaleup_complete_final_lineage_config(
                        plan_row
                    )
                ),
                SCALEUP_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY: (
                    _broker_vendor_scaleup_extended_complete_final_lineage_config(
                        plan_row
                    )
                ),
                SCALEUP_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_43_COMPARISON_KEY: (
                    _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_config(
                        plan_row
                    )
                ),
                SCALEUP_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_51_COMPARISON_KEY: (
                    _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_config(
                        plan_row
                    )
                ),
                SCALEUP_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_59_COMPARISON_KEY: (
                    _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_config(
                        plan_row
                    )
                ),
                SCALEUP_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_67_COMPARISON_KEY: (
                    _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_config(
                        plan_row
                    )
                ),
            },
            "shadow_broker_readiness": _broker_shadow_broker_config(plan_row),
        },
        "failed_checks": [str(record.get("check", "")) for record in failed_check_records],
        "primary_blocker": failed_check_records[0] if failed_check_records else {},
        "thresholds": asdict(thresholds),
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


def _broker_readiness_required(thresholds: ScaleUpThresholds) -> bool:
    return bool(
        thresholds.require_broker_readiness
        or thresholds.require_resume_gate
        or thresholds.require_dispatch_roundtrip
        or thresholds.target_mode == "live_dryrun"
    )


def _route_readiness_required(thresholds: ScaleUpThresholds) -> bool:
    return bool(thresholds.require_route_readiness or thresholds.target_mode == "live_dryrun")


def _dispatch_roundtrip_required(thresholds: ScaleUpThresholds) -> bool:
    return bool(thresholds.require_dispatch_roundtrip or thresholds.target_mode == "live_dryrun")


def _route_dispatch_roundtrip_required(thresholds: ScaleUpThresholds, broker_readiness: pd.Series) -> bool:
    return bool(
        _dispatch_roundtrip_required(thresholds)
        or _to_bool(broker_readiness.get("route_dispatch_roundtrip_required", False))
    )


def _route_readiness_ops_controls_present(route_readiness: pd.Series) -> bool:
    if route_readiness.empty:
        return False
    return any(
        field in route_readiness.index
        for field in (
            "ops_launch_controls_blocked_pairs",
            "ops_broker_roundtrip_portfolio_breach_pairs",
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs",
            *ROUTE_READINESS_RESUME_ROUTE_BREACH_PAIR_FIELDS,
            *ROUTE_READINESS_PROVIDER_SIDECAR_BREACH_PAIR_FIELDS,
        )
    )


def _broker_resume_route_readiness_plan_fields(
    broker_readiness: pd.Series,
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, object]:
    if broker_readiness.empty:
        return {
            f"{output_prefix}_required": False,
            f"{output_prefix}_provided": False,
            f"{output_prefix}_ready": False,
            f"{output_prefix}_strategy": "",
            f"{output_prefix}_market": "",
            f"{output_prefix}_route_ready_pairs": 0,
            f"{output_prefix}_gap_pairs": 0,
            f"{output_prefix}_recommendation": "",
            f"{output_prefix}_ops_launch_controls_ready": False,
            f"{output_prefix}_ops_launch_control_failures": "",
            f"{output_prefix}_ops_broker_roundtrip_portfolio_safe_runs": 0,
            f"{output_prefix}_ops_broker_roundtrip_portfolio_breach_runs": 0,
            f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": 0,
            f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
        }
    return {
        f"{output_prefix}_required": _to_bool(broker_readiness.get(f"{source_prefix}_required", False)),
        f"{output_prefix}_provided": _to_bool(broker_readiness.get(f"{source_prefix}_provided", False)),
        f"{output_prefix}_ready": _to_bool(broker_readiness.get(f"{source_prefix}_ready", False)),
        f"{output_prefix}_strategy": _strategy_key(broker_readiness.get(f"{source_prefix}_strategy", "")),
        f"{output_prefix}_market": _identity_key(broker_readiness.get(f"{source_prefix}_market", "")),
        f"{output_prefix}_route_ready_pairs": int(
            _number(broker_readiness, f"{source_prefix}_route_ready_pairs", 0.0)
        ),
        f"{output_prefix}_gap_pairs": int(_number(broker_readiness, f"{source_prefix}_gap_pairs", 0.0)),
        f"{output_prefix}_recommendation": _text(
            broker_readiness.get(f"{source_prefix}_recommendation", "")
        ),
        f"{output_prefix}_ops_launch_controls_ready": _to_bool(
            broker_readiness.get(f"{source_prefix}_ops_launch_controls_ready", False)
        ),
        f"{output_prefix}_ops_launch_control_failures": _text(
            broker_readiness.get(f"{source_prefix}_ops_launch_control_failures", "")
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(broker_readiness, f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(broker_readiness, f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(
                broker_readiness,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(
                broker_readiness,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        ),
    }


def _broker_resume_route_readiness_active(broker_readiness: pd.Series, source_prefix: str) -> bool:
    if broker_readiness.empty:
        return False
    return bool(
        _to_bool(broker_readiness.get(f"{source_prefix}_required", False))
        or _to_bool(broker_readiness.get(f"{source_prefix}_provided", False))
        or _to_bool(broker_readiness.get(f"{source_prefix}_ready", False))
        or int(_number(broker_readiness, f"{source_prefix}_route_ready_pairs", 0.0)) > 0
        or int(_number(broker_readiness, f"{source_prefix}_gap_pairs", 0.0)) > 0
        or _to_bool(broker_readiness.get(f"{source_prefix}_ops_launch_controls_ready", False))
        or bool(_text(broker_readiness.get(f"{source_prefix}_ops_launch_control_failures", "")))
        or int(_number(broker_readiness, f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0
        or int(_number(broker_readiness, f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0)) > 0
        or int(
            _number(
                broker_readiness,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            )
        )
        > 0
        or int(
            _number(
                broker_readiness,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            )
        )
        > 0
    )


def _broker_resume_route_readiness_checks(
    broker_readiness: pd.Series,
    *,
    source_prefix: str,
    check_prefix: str,
    expected_strategy: str,
    expected_market: str,
    label: str,
) -> list[dict[str, object]]:
    route_strategy = _strategy_key(broker_readiness.get(f"{source_prefix}_strategy", ""))
    route_market = _identity_key(broker_readiness.get(f"{source_prefix}_market", ""))
    return [
        _check(
            f"{check_prefix}_provided",
            _to_bool(broker_readiness.get(f"{source_prefix}_provided", False)),
            "is",
            True,
            _to_bool(broker_readiness.get(f"{source_prefix}_provided", False)),
            f"{label} is active but not marked provided",
        ),
        _check(
            f"{check_prefix}_ready",
            _to_bool(broker_readiness.get(f"{source_prefix}_ready", False)),
            "is",
            True,
            _to_bool(broker_readiness.get(f"{source_prefix}_ready", False)),
            f"{label} is not ready",
        ),
        _check(
            f"{check_prefix}_strategy_matches",
            route_strategy,
            "==",
            expected_strategy,
            bool(route_strategy and expected_strategy and route_strategy == expected_strategy),
            f"{label} strategy does not match scale-up strategy",
        ),
        _check(
            f"{check_prefix}_market_matches",
            route_market,
            "==",
            expected_market,
            bool(route_market and expected_market and route_market == expected_market),
            f"{label} market does not match scale-up market",
        ),
        _threshold_check(
            f"{check_prefix}_gap_pairs",
            _number(broker_readiness, f"{source_prefix}_gap_pairs", 0.0),
            "<=",
            0,
        ),
        _check(
            f"{check_prefix}_ops_launch_controls_ready",
            _to_bool(broker_readiness.get(f"{source_prefix}_ops_launch_controls_ready", False)),
            "is",
            True,
            _to_bool(broker_readiness.get(f"{source_prefix}_ops_launch_controls_ready", False)),
            f"{label} did not preserve launch-grade ops controls",
        ),
        _threshold_check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_safe_runs",
            _number(broker_readiness, f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs", 0.0),
            ">=",
            1,
        ),
        _threshold_check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_breach_runs",
            _number(broker_readiness, f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs", 0.0),
            "<=",
            0,
        ),
        _threshold_check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            _number(
                broker_readiness,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                0.0,
            ),
            ">=",
            1,
        ),
        _threshold_check(
            f"{check_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            _number(
                broker_readiness,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                0.0,
            ),
            "<=",
            0,
        ),
    ]


def _broker_route_readiness_active(broker_readiness: pd.Series) -> bool:
    if broker_readiness.empty:
        return False
    concentration_ok_runs = int(
        _number(
            broker_readiness,
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
            0.0,
        )
    )
    concentration_breach_runs = int(
        _number(
            broker_readiness,
            "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
            0.0,
        )
    )
    resume_route_ready_runs = int(
        _number(broker_readiness, "route_readiness_ops_broker_roundtrip_resume_route_ready_runs", 0.0)
    )
    resume_route_breach_runs = int(
        _number(broker_readiness, "route_readiness_ops_broker_roundtrip_resume_route_breach_runs", 0.0)
    )
    resume_route_gap_breach_runs = int(
        _number(
            broker_readiness,
            "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs",
            0.0,
        )
    )
    resume_route_launch_control_breach_runs = int(
        _number(
            broker_readiness,
            "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs",
            0.0,
        )
    )
    resume_route_portfolio_breach_runs = int(
        _number(
            broker_readiness,
            "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs",
            0.0,
        )
    )
    resume_route_concentration_breach_runs = int(
        _number(
            broker_readiness,
            "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs",
            0.0,
        )
    )
    return bool(
        _to_bool(broker_readiness.get("route_readiness_required", False))
        or _to_bool(broker_readiness.get("route_readiness_provided", False))
        or _to_bool(broker_readiness.get("route_readiness_ready", False))
        or _identity_key(broker_readiness.get("route_readiness_strategy", ""))
        or _identity_key(broker_readiness.get("route_readiness_market", ""))
        or int(_number(broker_readiness, "route_readiness_route_ready_pairs", 0.0)) > 0
        or int(_number(broker_readiness, "route_readiness_gap_pairs", 0.0)) > 0
        or _to_bool(broker_readiness.get("route_readiness_ops_launch_controls_ready", False))
        or bool(_text(broker_readiness.get("route_readiness_ops_launch_control_failures", "")))
        or int(_number(broker_readiness, "route_readiness_ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0
        or int(_number(broker_readiness, "route_readiness_ops_broker_roundtrip_portfolio_breach_runs", 0.0)) > 0
        or concentration_ok_runs > 0
        or concentration_breach_runs > 0
        or resume_route_ready_runs > 0
        or resume_route_breach_runs > 0
        or resume_route_gap_breach_runs > 0
        or resume_route_launch_control_breach_runs > 0
        or resume_route_portfolio_breach_runs > 0
        or resume_route_concentration_breach_runs > 0
    )


def _broker_shadow_broker_readiness_active(broker_readiness: pd.Series) -> bool:
    if broker_readiness.empty:
        return False
    session_fields = (
        "shadow_broker_readiness_sessions",
        "shadow_broker_vendor_data_readiness_sessions",
        "shadow_broker_route_readiness_sessions",
        "shadow_broker_dispatch_roundtrip_sessions",
        "shadow_broker_route_dispatch_roundtrip_sessions",
    )
    return bool(
        _to_bool(broker_readiness.get("shadow_broker_readiness_provided", False))
        or any(int(_number(broker_readiness, field, fallback=0.0)) > 0 for field in session_fields)
    )


def _broker_vendor_market_data_batch_active(broker_readiness: pd.Series) -> bool:
    if broker_readiness.empty:
        return False
    source_prefix = _broker_vendor_market_data_batch_source_prefix(broker_readiness)
    return _vendor_market_data_batch_prefix_active(broker_readiness, source_prefix)


def _broker_vendor_data_readiness_active(broker_readiness: pd.Series) -> bool:
    if broker_readiness.empty:
        return False
    return bool(
        _to_bool(broker_readiness.get("broker_vendor_data_readiness_provided", False))
        or _to_bool(broker_readiness.get("broker_vendor_data_readiness_ready", False))
        or int(_number(broker_readiness, "broker_vendor_data_readiness_failed_checks", 0.0)) > 0
    )


def _broker_vendor_market_data_batch_source_prefix(broker_readiness: pd.Series) -> str:
    generic_prefix = "dispatch_roundtrip_vendor_market_data_batch"
    if broker_readiness.empty:
        return generic_prefix
    for prefix in (
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        generic_prefix,
        "roundtrip_vendor_market_data_batch",
    ):
        if _vendor_market_data_batch_prefix_active(broker_readiness, prefix):
            return prefix
    return generic_prefix


def _vendor_market_data_batch_prefix_active(row: pd.Series, prefix: str) -> bool:
    if row.empty:
        return False
    return bool(
        _to_bool(row.get(f"{prefix}_provided", False))
        or int(_number(row, f"{prefix}_dataset_count", 0.0)) > 0
        or _identity_key(row.get(f"{prefix}_adapter", ""))
        or _identity_key(row.get(f"{prefix}_market", ""))
        or _identity_key(row.get(f"{prefix}_manifest_run_type", ""))
    )


def _broker_vendor_data_readiness_checks(broker_readiness: pd.Series) -> list[dict[str, object]]:
    return [
        _check(
            "broker_vendor_data_readiness_provided",
            _to_bool(broker_readiness.get("broker_vendor_data_readiness_provided", False)),
            "is",
            True,
            _to_bool(broker_readiness.get("broker_vendor_data_readiness_provided", False)),
            "broker-vendor readiness wrapper proof is active but not marked provided",
        ),
        _check(
            "broker_vendor_data_readiness_ready",
            _to_bool(broker_readiness.get("broker_vendor_data_readiness_ready", False)),
            "is",
            True,
            _to_bool(broker_readiness.get("broker_vendor_data_readiness_ready", False)),
            "broker-vendor readiness wrapper proof is not ready",
        ),
        _threshold_check(
            "broker_vendor_data_readiness_failed_checks",
            _number(broker_readiness, "broker_vendor_data_readiness_failed_checks", 0.0),
            "<=",
            0,
        ),
    ]


def _broker_vendor_market_data_batch_checks(
    broker_readiness: pd.Series,
    *,
    expected_market: str,
    expected_adapter: str,
) -> list[dict[str, object]]:
    source_prefix = _broker_vendor_market_data_batch_source_prefix(broker_readiness)
    vendor_adapter = _identity_key(broker_readiness.get(f"{source_prefix}_adapter", ""))
    vendor_market = _identity_key(broker_readiness.get(f"{source_prefix}_market", ""))
    manifest_run_type = _identity_key(broker_readiness.get(f"{source_prefix}_manifest_run_type", ""))
    checks = [
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_provided",
            _to_bool(broker_readiness.get(f"{source_prefix}_provided", False)),
            "is",
            True,
            _to_bool(broker_readiness.get(f"{source_prefix}_provided", False)),
            "broker-readiness vendor market-data batch proof is active but not marked provided",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_ready",
            _to_bool(broker_readiness.get(f"{source_prefix}_ready", False)),
            "is",
            True,
            _to_bool(broker_readiness.get(f"{source_prefix}_ready", False)),
            "broker-readiness vendor market-data batch proof is not ready",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
            vendor_adapter,
            "==",
            expected_adapter,
            bool(vendor_adapter and expected_adapter and vendor_adapter == expected_adapter),
            "broker-readiness vendor market-data adapter does not match scale-up adapter",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
            vendor_market,
            "==",
            expected_market,
            bool(vendor_market and expected_market and vendor_market == expected_market),
            "broker-readiness vendor market-data market does not match scale-up market",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
            manifest_run_type,
            "==",
            "vendor_market_data_batch_pipeline",
            manifest_run_type == "vendor_market_data_batch_pipeline",
            "broker-readiness vendor market-data manifest is not a vendor batch pipeline proof",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
            int(_number(broker_readiness, f"{source_prefix}_dataset_count", 0.0)),
            ">",
            0,
            int(_number(broker_readiness, f"{source_prefix}_dataset_count", 0.0)) > 0,
            "broker-readiness vendor market-data batch has no datasets",
        ),
        _threshold_check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
            _number(broker_readiness, f"{source_prefix}_failed_datasets", 0.0),
            "<=",
            0,
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
            int(_number(broker_readiness, f"{source_prefix}_unique_source_files", 0.0)),
            ">",
            0,
            int(_number(broker_readiness, f"{source_prefix}_unique_source_files", 0.0)) > 0,
            "broker-readiness vendor market-data batch is missing source-file provenance",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
            int(_number(broker_readiness, f"{source_prefix}_unique_header_fingerprints", 0.0)),
            ">",
            0,
            int(_number(broker_readiness, f"{source_prefix}_unique_header_fingerprints", 0.0)) > 0,
            "broker-readiness vendor market-data batch is missing header fingerprint provenance",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
            _number(broker_readiness, f"{source_prefix}_source_file_fingerprint_coverage", 0.0),
            ">=",
            1.0,
            _number(broker_readiness, f"{source_prefix}_source_file_fingerprint_coverage", 0.0) >= 1.0,
            "broker-readiness vendor market-data batch has incomplete source-file fingerprint coverage",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
            _number(broker_readiness, f"{source_prefix}_min_mapping_coverage", 0.0),
            ">=",
            1.0,
            _number(broker_readiness, f"{source_prefix}_min_mapping_coverage", 0.0) >= 1.0,
            "broker-readiness vendor market-data batch has incomplete field mapping coverage",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
            int(_number(broker_readiness, f"{source_prefix}_unique_mapping_drafts", 0.0)),
            ">",
            0,
            int(_number(broker_readiness, f"{source_prefix}_unique_mapping_drafts", 0.0)) > 0,
            "broker-readiness vendor market-data batch is missing mapping draft provenance",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
            str(broker_readiness.get(f"{source_prefix}_mapping_sources", "")).strip(),
            "!=",
            "",
            bool(str(broker_readiness.get(f"{source_prefix}_mapping_sources", "")).strip()),
            "broker-readiness vendor market-data batch is missing mapping source provenance",
        ),
        _check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
            _to_bool(broker_readiness.get(f"{source_prefix}_comparison_accepted", False)),
            "is",
            True,
            _to_bool(broker_readiness.get(f"{source_prefix}_comparison_accepted", False)),
            "broker-readiness vendor market-data comparison was not accepted",
        ),
        _threshold_check(
            "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
            _number(broker_readiness, f"{source_prefix}_comparison_failed_checks", 0.0),
            "<=",
            0,
        ),
    ]
    if _broker_vendor_target_application_batch_active(broker_readiness, source_prefix):
        dataset_count = int(_number(broker_readiness, f"{source_prefix}_dataset_count", 0.0))
        mapping_application_count = int(
            _number(broker_readiness, f"{source_prefix}_mapping_application_count", 0.0)
        )
        unique_mapping_applications = int(
            _number(broker_readiness, f"{source_prefix}_unique_mapping_applications", 0.0)
        )
        target_application_coverage = _number(
            broker_readiness,
            f"{source_prefix}_target_application_coverage",
            0.0,
        )
        lineage_datasets = _broker_vendor_target_application_lineage_dataset_count(
            broker_readiness,
            source_prefix,
        )
        mapping_source_mode = _identity_key(
            broker_readiness.get(f"{source_prefix}_mapping_source_mode", "")
        )
        lineage_consistency_required = _to_bool(
            broker_readiness.get(
                f"{source_prefix}_application_lineage_consistency_required",
                False,
            )
        )
        lineage_consistent = _to_bool(
            broker_readiness.get(
                f"{source_prefix}_application_lineage_consistent",
                False,
            )
        )
        lineage_match_required = _to_bool(
            broker_readiness.get(
                "broker_vendor_market_data_batch_lineage_match_required",
                False,
            )
        )
        lineage_matches = _to_bool(
            broker_readiness.get(
                "broker_vendor_market_data_batch_lineage_matches",
                False,
            )
        )
        current_lineage_sha256 = _sha256_text(
            broker_readiness.get(
                "vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        broker_lineage_sha256 = _sha256_text(
            broker_readiness.get(
                "broker_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        )
        carried_lineage_sha256 = _broker_vendor_target_application_lineage_sha256(
            broker_readiness,
            source_prefix,
        )
        checks.extend(
            [
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
                    mapping_source_mode,
                    "==",
                    TARGET_APPLICATION_BATCH_MODE,
                    mapping_source_mode == TARGET_APPLICATION_BATCH_MODE,
                    "broker-readiness vendor market-data target applications are missing strict source mode",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
                    mapping_application_count,
                    "==",
                    dataset_count,
                    dataset_count > 0 and mapping_application_count == dataset_count,
                    "broker-readiness vendor market-data target applications are not aligned one for one",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
                    unique_mapping_applications,
                    "==",
                    dataset_count,
                    dataset_count > 0 and unique_mapping_applications == dataset_count,
                    "broker-readiness vendor market-data target applications are not distinct per dataset",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
                    target_application_coverage,
                    ">=",
                    1.0,
                    target_application_coverage >= 1.0,
                    "broker-readiness vendor market-data target-application coverage is incomplete",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
                    lineage_datasets,
                    "==",
                    dataset_count,
                    dataset_count > 0 and lineage_datasets == dataset_count,
                    "broker-readiness vendor market-data datasets are missing target-application lineage",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_match_required",
                    lineage_match_required,
                    "is",
                    True,
                    lineage_match_required,
                    "target-application scale-up requires the broker-readiness current/final lineage comparison",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
                    lineage_matches,
                    "is",
                    True,
                    lineage_match_required and lineage_matches,
                    "broker-readiness current and final target-application lineages do not match",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
                    current_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and current_lineage_sha256
                        and broker_lineage_sha256
                        and current_lineage_sha256 == broker_lineage_sha256
                    ),
                    "broker-readiness current/final lineage digests are missing or disagree",
                ),
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_carried_lineage_sha256_matches",
                    carried_lineage_sha256,
                    "==",
                    broker_lineage_sha256,
                    bool(
                        lineage_match_required
                        and carried_lineage_sha256
                        and broker_lineage_sha256
                        and carried_lineage_sha256 == broker_lineage_sha256
                    ),
                    "scale-up carried target-application lineage does not match broker-readiness proof",
                ),
            ]
        )
        if lineage_consistency_required:
            checks.append(
                _check(
                    "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
                    lineage_consistent,
                    "is",
                    True,
                    lineage_consistent,
                    "broker-readiness final dispatch/send/ack target lineage was not consistent",
                )
            )
            checks.extend(
                _broker_vendor_final_lineage_checks(
                    broker_readiness,
                    source_prefix=source_prefix,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_final_lineage_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_complete_final_lineage_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_extended_complete_final_lineage_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_latest_extended_complete_final_lineage_42_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
            checks.extend(
                _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_checks(
                    broker_readiness,
                    scaleup_lineage_sha256=carried_lineage_sha256,
                )
            )
    return checks


def _broker_vendor_final_lineage_checks(
    broker_readiness: pd.Series,
    *,
    source_prefix: str,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    lineage_match_required = _to_bool(
        broker_readiness.get(f"{prefix}_lineage_match_required", False)
    )
    lineage_matches = _to_bool(
        broker_readiness.get(f"{prefix}_lineage_matches", False)
    )
    broker_lineage_sha256 = _sha256_text(
        broker_readiness.get(f"{prefix}_broker_application_lineage_sha256", "")
    )
    current_lineage_sha256 = _sha256_text(
        broker_readiness.get(f"{prefix}_current_application_lineage_sha256", "")
    )
    readiness_broker_lineage_sha256 = _sha256_text(
        broker_readiness.get(
            "broker_vendor_market_data_batch_application_lineage_sha256",
            "",
        )
    )
    declared_lineage_sha256 = _sha256_text(
        broker_readiness.get(f"{source_prefix}_application_lineage_sha256", "")
    )
    checks = [
        _check(
            f"{prefix}_final_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target scale-up requires broker readiness's final lineage comparison",
        ),
        _check(
            f"{prefix}_final_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not reconcile every final target-lineage view",
        ),
        _check(
            f"{prefix}_final_source_lineage_sha256_matches",
            current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and current_lineage_sha256
                and broker_lineage_sha256
                and current_lineage_sha256 == broker_lineage_sha256
            ),
            "broker readiness's final source lineage does not match final broker proof",
        ),
        _check(
            f"{prefix}_final_broker_lineage_sha256_matches",
            readiness_broker_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and readiness_broker_lineage_sha256
                and broker_lineage_sha256
                and readiness_broker_lineage_sha256 == broker_lineage_sha256
            ),
            "broker readiness's current/final broker digest does not match its final comparison",
        ),
        _check(
            f"{prefix}_final_application_lineage_sha256_matches",
            declared_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and declared_lineage_sha256
                and broker_lineage_sha256
                and declared_lineage_sha256 == broker_lineage_sha256
            ),
            "broker readiness's declared final batch digest does not match final comparison",
        ),
    ]
    carried_fields = (
        ("prior_scaleup", "scaleup_carried_application_lineage_sha256"),
        ("cutover", "cutover_carried_application_lineage_sha256"),
        ("route", "route_carried_application_lineage_sha256"),
        ("dispatch", "dispatch_carried_application_lineage_sha256"),
        ("send", "send_carried_application_lineage_sha256"),
        ("ack", "ack_carried_application_lineage_sha256"),
        ("roundtrip", "roundtrip_carried_application_lineage_sha256"),
        ("readiness", "readiness_carried_application_lineage_sha256"),
    )
    for stage, field in carried_fields:
        carried_sha256 = _sha256_text(
            broker_readiness.get(f"{prefix}_{field}", "")
        )
        checks.append(
            _check(
                f"{prefix}_final_{stage}_carried_lineage_sha256_matches",
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match final broker proof"
                ),
            )
        )
    scaleup_sha256 = _sha256_text(scaleup_lineage_sha256)
    checks.append(
        _check(
            f"{prefix}_scaleup_review_carried_lineage_sha256_matches",
            scaleup_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and scaleup_sha256
                and broker_lineage_sha256
                and scaleup_sha256 == broker_lineage_sha256
            ),
            "scale-up's independently recomputed target lineage does not match final broker proof",
        )
    )
    return checks


def _broker_vendor_readiness_final_lineage_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = BROKER_READINESS_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS:
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_readiness_carried_application_lineage_sha256",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_final_lineage_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = _broker_vendor_readiness_final_lineage_state(broker_readiness)
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_broker_readiness_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(
        state["broker_application_lineage_sha256"]
    )
    current_lineage_sha256 = str(
        state["current_application_lineage_sha256"]
    )
    compatibility_broker_lineage_sha256 = _sha256_text(
        broker_readiness.get(
            f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_broker_application_lineage_sha256",
            "",
        )
    )
    compatibility_readiness_lineage_sha256 = _sha256_text(
        broker_readiness.get(
            f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_readiness_carried_application_lineage_sha256",
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
            "reconciled target scale-up requires broker readiness's final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every final target-lineage view",
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
            "broker-readiness final source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's final proof",
        ),
        _check(
            f"{check_prefix}_compatibility_readiness_carried_lineage_sha256_matches",
            compatibility_readiness_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_readiness_lineage_sha256
                and broker_lineage_sha256
                and compatibility_readiness_lineage_sha256 == broker_lineage_sha256
            ),
            "scale-up compatibility readiness digest does not match broker readiness's final proof",
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
    )
    for stage, field in carried_fields:
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match final broker proof"
                ),
            )
        )
    readiness_review_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_review_lineage_sha256 = _sha256_text(scaleup_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_review_carried_lineage_sha256_matches",
                readiness_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and readiness_review_lineage_sha256
                    and broker_lineage_sha256
                    and readiness_review_lineage_sha256 == broker_lineage_sha256
                ),
                "broker readiness's carried review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_scaleup_final_review_carried_lineage_sha256_matches",
                scaleup_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_review_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_review_lineage_sha256 == broker_lineage_sha256
                ),
                "scale-up's independently recomputed target lineage does not match broker readiness's final proof",
            ),
        ]
    )
    return checks


def _broker_vendor_readiness_complete_final_lineage_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = BROKER_READINESS_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{summary_prefix}_broker_readiness_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_complete_final_lineage_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = _broker_vendor_readiness_complete_final_lineage_state(
        broker_readiness
    )
    compatibility_state = _broker_vendor_readiness_final_lineage_state(
        broker_readiness
    )
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_broker_readiness_complete_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(state["broker_application_lineage_sha256"])
    current_lineage_sha256 = str(state["current_application_lineage_sha256"])
    compatibility_broker_lineage_sha256 = str(
        compatibility_state["broker_application_lineage_sha256"]
    )
    compatibility_readiness_review_lineage_sha256 = str(
        compatibility_state["carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target scale-up requires broker readiness's complete final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every complete final target-lineage view",
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
            "broker-readiness complete-final source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's complete-final proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_readiness_review_carried_lineage_sha256_matches",
            compatibility_readiness_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_readiness_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_readiness_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "scale-up compatibility broker-readiness review does not match broker readiness's complete-final proof",
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
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match complete-final broker proof"
                ),
            )
        )
    readiness_complete_final_review_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup_lineage_sha256
    )
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
                readiness_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and readiness_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and readiness_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's carried complete-final review lineage does not match final broker proof",
            ),
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
                "scale-up's independently recomputed target lineage does not match broker readiness's complete-final proof",
            ),
        ]
    )
    return checks


def _broker_vendor_readiness_extended_complete_final_lineage_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    summary_prefix = (
        BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_SUMMARY_FIELD_PREFIX
    )

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{summary_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_extended_complete_final_lineage_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = _broker_vendor_readiness_extended_complete_final_lineage_state(
        broker_readiness
    )
    compatibility_state = _broker_vendor_readiness_complete_final_lineage_state(
        broker_readiness
    )
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "broker_readiness_extended_complete_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(state["broker_application_lineage_sha256"])
    current_lineage_sha256 = str(state["current_application_lineage_sha256"])
    compatibility_broker_lineage_sha256 = str(
        compatibility_state["broker_application_lineage_sha256"]
    )
    compatibility_readiness_complete_final_review_lineage_sha256 = str(
        compatibility_state["carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target scale-up requires broker readiness's extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every extended complete-final target-lineage view",
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
            "broker-readiness extended complete-final source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
            compatibility_readiness_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_readiness_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_readiness_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "scale-up compatibility broker-readiness complete-final review does not match broker readiness's extended proof",
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
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target "
                    "lineage does not match extended complete-final broker proof"
                ),
            )
        )
    readiness_extended_complete_final_review_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_extended_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup_lineage_sha256
    )
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
                readiness_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and readiness_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and readiness_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's carried extended complete-final review lineage does not match final broker proof",
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
                "scale-up's independently recomputed target lineage does not match broker readiness's extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_readiness_latest_extended_complete_final_lineage_42_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_FIELD_PREFIX
    summary_prefix = (
        BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_SUMMARY_FIELD_PREFIX
    )

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS:
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{summary_prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_latest_extended_complete_final_lineage_42_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = _broker_vendor_readiness_latest_extended_complete_final_lineage_42_state(
        broker_readiness
    )
    compatibility_state = (
        _broker_vendor_readiness_extended_complete_final_lineage_state(
            broker_readiness
        )
    )
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "broker_readiness_latest_extended_complete_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(state["broker_application_lineage_sha256"])
    current_lineage_sha256 = str(state["current_application_lineage_sha256"])
    compatibility_broker_lineage_sha256 = str(
        compatibility_state["broker_application_lineage_sha256"]
    )
    compatibility_readiness_extended_complete_final_review_lineage_sha256 = str(
        compatibility_state["carried_application_lineage_sha256"]
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target scale-up requires broker readiness's latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every latest extended complete-final target-lineage view",
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
            "broker-readiness latest extended complete-final source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's latest extended proof",
        ),
        _check(
            f"{check_prefix}_compatibility_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_readiness_extended_complete_final_review_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_readiness_extended_complete_final_review_lineage_sha256
                and broker_lineage_sha256
                and compatibility_readiness_extended_complete_final_review_lineage_sha256
                == broker_lineage_sha256
            ),
            "scale-up compatibility broker-readiness extended review does not match broker readiness's latest extended proof",
        ),
    ]
    for field in BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS:
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
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match latest extended complete-final broker proof"
                ),
            )
        )
    readiness_latest_extended_complete_final_review_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_latest_extended_complete_final_review_lineage_sha256 = _sha256_text(
        scaleup_lineage_sha256
    )
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                readiness_latest_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and readiness_latest_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and readiness_latest_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's carried latest extended complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                scaleup_latest_extended_complete_final_review_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_latest_extended_complete_final_review_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_latest_extended_complete_final_review_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's independently recomputed target lineage does not match broker readiness's latest extended proof",
            ),
        ]
    )
    return checks


def _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_FIELD_PREFIX
    )
    summary_prefix = (
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_SUMMARY_FIELD_PREFIX
    )

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in (
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS,
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS,
    ):
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{summary_prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = (
        _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_state(
            broker_readiness
        )
    )
    compatibility_state = (
        _broker_vendor_readiness_latest_extended_complete_final_lineage_42_state(
            broker_readiness
        )
    )
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "broker_readiness_current_latest_extended_complete_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(state["broker_application_lineage_sha256"])
    current_lineage_sha256 = str(state["current_application_lineage_sha256"])
    compatibility_broker_lineage_sha256 = str(
        compatibility_state["broker_application_lineage_sha256"]
    )
    compatibility_scaleup_latest_lineage_sha256 = _sha256_text(
        scaleup_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target scale-up requires broker readiness's current latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every current latest extended complete-final target-lineage view",
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
            "broker-readiness current latest extended complete-final source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's current latest proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_scaleup_latest_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_latest_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_latest_lineage_sha256
                == broker_lineage_sha256
            ),
            "scale-up compatibility latest review does not match broker readiness's current proof",
        ),
    ]
    for field in BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS:
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
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match current latest extended complete-final broker proof"
                ),
            )
        )
    for field in BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match current latest extended complete-final broker proof"
                ),
            )
        )
    readiness_current_latest_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_current_latest_lineage_sha256 = _sha256_text(scaleup_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                readiness_current_latest_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and readiness_current_latest_lineage_sha256
                    and broker_lineage_sha256
                    and readiness_current_latest_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's generic current latest extended complete-final review lineage does not match final broker proof",
            ),
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
                "scale-up's independently recomputed target lineage does not match broker readiness's current latest proof",
            ),
        ]
    )
    return checks


def _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_FIELD_PREFIX
    )
    summary_prefix = (
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_SUMMARY_FIELD_PREFIX
    )

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in (
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS,
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD,
    ):
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{summary_prefix}_{BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD}",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = (
        _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_state(
            broker_readiness
        )
    )
    compatibility_state = (
        _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_state(
            broker_readiness
        )
    )
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "broker_readiness_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(state["broker_application_lineage_sha256"])
    current_lineage_sha256 = str(state["current_application_lineage_sha256"])
    compatibility_broker_lineage_sha256 = str(
        compatibility_state["broker_application_lineage_sha256"]
    )
    compatibility_scaleup_current_lineage_sha256 = _sha256_text(
        scaleup_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "reconciled target scale-up requires broker readiness's reconciled current latest extended complete-final lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every reconciled current latest extended complete-final target-lineage view",
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
            "broker-readiness reconciled current latest extended complete-final source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's reconciled current proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_scaleup_current_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_current_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_current_lineage_sha256
                == broker_lineage_sha256
            ),
            "scale-up compatibility current review does not match broker readiness's reconciled current proof",
        ),
    ]
    for field in BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS:
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
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match reconciled current latest extended complete-final broker proof"
                ),
            )
        )
    for field in (
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match reconciled current latest extended complete-final broker proof"
                ),
            )
        )
    broker_readiness_reconciled_lineage_sha256 = str(
        state[
            BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD
        ]
    )
    generic_broker_readiness_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_reconciled_lineage_sha256 = _sha256_text(scaleup_lineage_sha256)
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
                "broker readiness's reconciled current latest extended complete-final review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                generic_broker_readiness_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and generic_broker_readiness_lineage_sha256
                    and broker_lineage_sha256
                    and generic_broker_readiness_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's generic reconciled current latest extended complete-final review lineage does not match final broker proof",
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
                "scale-up's independently recomputed target lineage does not match broker readiness's reconciled current proof",
            ),
        ]
    )
    return checks


def _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_state(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_FIELD_PREFIX
    )
    summary_prefix = (
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_SUMMARY_FIELD_PREFIX
    )

    def source_value(field: str, default: object = "") -> object:
        key = f"{prefix}_{field}"
        if key in broker_readiness.index:
            return broker_readiness.get(key, default)
        return broker_readiness.get(f"{summary_prefix}_{field}", default)

    state: dict[str, object] = {
        "required": _to_bool(source_value("lineage_match_required", False)),
        "matches": _to_bool(source_value("lineage_matches", False)),
    }
    for field in (
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD,
    ):
        state[field] = _sha256_text(source_value(field))
    carried_key = f"{prefix}_carried_application_lineage_sha256"
    if carried_key in broker_readiness.index:
        carried_value = broker_readiness.get(carried_key, "")
    else:
        carried_value = broker_readiness.get(
            f"{summary_prefix}_{BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD}",
            "",
        )
    state["carried_application_lineage_sha256"] = _sha256_text(carried_value)
    return state


def _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_checks(
    broker_readiness: pd.Series,
    *,
    scaleup_lineage_sha256: str,
) -> list[dict[str, object]]:
    state = (
        _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_state(
            broker_readiness
        )
    )
    compatibility_state = (
        _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_state(
            broker_readiness
        )
    )
    check_prefix = (
        f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_"
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final"
    )
    lineage_match_required = bool(state["required"])
    lineage_matches = bool(state["matches"])
    broker_lineage_sha256 = str(state["broker_application_lineage_sha256"])
    current_lineage_sha256 = str(state["current_application_lineage_sha256"])
    compatibility_broker_lineage_sha256 = str(
        compatibility_state["broker_application_lineage_sha256"]
    )
    compatibility_scaleup_reconciled_lineage_sha256 = _sha256_text(
        scaleup_lineage_sha256
    )
    checks = [
        _check(
            f"{check_prefix}_lineage_match_required",
            lineage_match_required,
            "is",
            True,
            lineage_match_required,
            "verified reconciled target scale-up requires broker readiness's verified reconciled lineage comparison",
        ),
        _check(
            f"{check_prefix}_lineage_matches",
            lineage_matches,
            "is",
            True,
            bool(lineage_match_required and lineage_matches),
            "broker readiness did not match every verified reconciled target-lineage view",
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
            "broker-readiness verified reconciled source lineage does not match final broker proof",
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
            "scale-up compatibility broker digest does not match broker readiness's verified reconciled proof",
        ),
        _check(
            f"{check_prefix}_compatibility_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            compatibility_scaleup_reconciled_lineage_sha256,
            "==",
            broker_lineage_sha256,
            bool(
                lineage_match_required
                and compatibility_scaleup_reconciled_lineage_sha256
                and broker_lineage_sha256
                and compatibility_scaleup_reconciled_lineage_sha256
                == broker_lineage_sha256
            ),
            "scale-up compatibility reconciled review does not match broker readiness's verified reconciled proof",
        ),
    ]
    for field in BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS:
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
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match verified reconciled broker proof"
                ),
            )
        )
    for field in (
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        carried_sha256 = str(state[field])
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
                    f"broker readiness's {stage.replace('_', '-')} target lineage "
                    "does not match verified reconciled broker proof"
                ),
            )
        )
    generic_broker_readiness_lineage_sha256 = str(
        state["carried_application_lineage_sha256"]
    )
    scaleup_verified_lineage_sha256 = _sha256_text(scaleup_lineage_sha256)
    checks.extend(
        [
            _check(
                f"{check_prefix}_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
                generic_broker_readiness_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and generic_broker_readiness_lineage_sha256
                    and broker_lineage_sha256
                    and generic_broker_readiness_lineage_sha256
                    == broker_lineage_sha256
                ),
                "broker readiness's generic verified reconciled review lineage does not match final broker proof",
            ),
            _check(
                f"{check_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
                scaleup_verified_lineage_sha256,
                "==",
                broker_lineage_sha256,
                bool(
                    lineage_match_required
                    and scaleup_verified_lineage_sha256
                    and broker_lineage_sha256
                    and scaleup_verified_lineage_sha256
                    == broker_lineage_sha256
                ),
                "scale-up's independently recomputed target lineage does not match broker readiness's verified reconciled proof",
            ),
        ]
    )
    return checks


def _broker_vendor_target_application_batch_active(row: pd.Series, prefix: str) -> bool:
    mapping_sources = {
        value.strip().lower()
        for value in str(row.get(f"{prefix}_mapping_sources", "")).split(";")
        if value.strip()
    }
    return bool(
        _identity_key(row.get(f"{prefix}_mapping_source_mode", ""))
        == TARGET_APPLICATION_BATCH_MODE
        or "verified_target_application" in mapping_sources
        or int(_number(row, f"{prefix}_mapping_application_count", 0.0)) > 0
        or _number(row, f"{prefix}_target_application_coverage", 0.0) > 0.0
    )


def _broker_vendor_target_application_lineage_dataset_count(
    row: pd.Series,
    prefix: str,
) -> int:
    datasets = _json_list(row.get(f"{prefix}_datasets_json", ""))
    return sum(
        isinstance(dataset, dict)
        and all(_text(dataset.get(field)) for field in TARGET_APPLICATION_DATASET_LINEAGE_FIELDS)
        for dataset in datasets
    )


def _broker_vendor_target_application_lineage_sha256(
    row: pd.Series,
    prefix: str,
) -> str:
    datasets = _json_list(row.get(f"{prefix}_datasets_json", ""))
    identities: list[dict[str, str]] = []
    for dataset in datasets:
        if not isinstance(dataset, dict):
            return ""
        identity = {
            field: _text(dataset.get(field))
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
    normalized = _text(value).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return ""
    return normalized


def _broker_shadow_broker_readiness_checks(
    broker_readiness: pd.Series,
    *,
    expected_strategy: str,
    expected_market: str,
    expected_adapter: str,
) -> list[dict[str, object]]:
    shadow_adapter = _identity_key(broker_readiness.get("shadow_broker_adapter", ""))
    shadow_sessions = int(_number(broker_readiness, "shadow_broker_readiness_sessions", fallback=0.0))
    vendor_sessions = int(
        _number(broker_readiness, "shadow_broker_vendor_data_readiness_sessions", fallback=0.0)
    )
    vendor_failed_checks = int(
        _number(broker_readiness, "shadow_broker_vendor_data_readiness_failed_checks", fallback=0.0)
    )
    vendor_active = vendor_sessions > 0 or vendor_failed_checks > 0
    return [
        _check(
            "broker_shadow_broker_readiness_provided",
            _to_bool(broker_readiness.get("shadow_broker_readiness_provided", False)),
            "is",
            True,
            _to_bool(broker_readiness.get("shadow_broker_readiness_provided", False)),
            "broker-readiness shadow broker-readiness proof is active but not marked provided",
        ),
        _check(
            "broker_shadow_broker_readiness_ready",
            int(_number(broker_readiness, "shadow_broker_readiness_ready_sessions", fallback=0.0)),
            "==",
            int(_number(broker_readiness, "shadow_broker_readiness_sessions", fallback=0.0)),
            int(_number(broker_readiness, "shadow_broker_readiness_sessions", fallback=0.0)) > 0
            and int(_number(broker_readiness, "shadow_broker_readiness_ready_sessions", fallback=0.0))
            == int(_number(broker_readiness, "shadow_broker_readiness_sessions", fallback=0.0)),
            "broker-readiness shadow broker-readiness proof is not ready",
        ),
        _check(
            "broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
            vendor_sessions,
            "==",
            shadow_sessions,
            not vendor_active or vendor_sessions == shadow_sessions,
            (
                "broker-readiness shadow broker vendor-data wrapper proof is present for only "
                "some broker-readiness sessions"
            ),
        ),
        _check(
            "broker_shadow_broker_vendor_data_readiness_provided",
            int(
                _number(
                    broker_readiness,
                    "shadow_broker_vendor_data_readiness_provided_sessions",
                    fallback=0.0,
                )
            ),
            "==",
            shadow_sessions,
            not vendor_active
            or int(
                _number(
                    broker_readiness,
                    "shadow_broker_vendor_data_readiness_provided_sessions",
                    fallback=0.0,
                )
            )
            == shadow_sessions,
            "broker-readiness shadow broker vendor-data wrapper proof is missing for some sessions",
        ),
        _check(
            "broker_shadow_broker_vendor_data_readiness_ready",
            int(
                _number(
                    broker_readiness,
                    "shadow_broker_vendor_data_readiness_ready_sessions",
                    fallback=0.0,
                )
            ),
            "==",
            shadow_sessions,
            not vendor_active
            or int(
                _number(
                    broker_readiness,
                    "shadow_broker_vendor_data_readiness_ready_sessions",
                    fallback=0.0,
                )
            )
            == shadow_sessions,
            "broker-readiness shadow broker vendor-data wrapper proof is not ready",
        ),
        _check(
            "broker_shadow_broker_vendor_data_readiness_failed_checks",
            vendor_failed_checks,
            "<=",
            0,
            not vendor_active or vendor_failed_checks <= 0,
            "broker-readiness shadow broker vendor-data wrapper proof has failed checks",
        ),
        _check(
            "broker_shadow_broker_adapter_matches",
            shadow_adapter,
            "==",
            expected_adapter,
            bool(shadow_adapter and expected_adapter and shadow_adapter == expected_adapter),
            "broker-readiness shadow broker adapter does not match broker readiness adapter",
        ),
        _check(
            "broker_shadow_broker_adapter_consistent",
            int(_number(broker_readiness, "shadow_broker_adapter_count", fallback=0.0)),
            "==",
            1,
            int(_number(broker_readiness, "shadow_broker_adapter_count", fallback=0.0)) == 1,
            "broker-readiness shadow broker adapter identity is missing or mixed",
        ),
        _check(
            "broker_shadow_broker_route_readiness_ready",
            int(_number(broker_readiness, "shadow_broker_route_readiness_ready_sessions", fallback=0.0)),
            "==",
            int(_number(broker_readiness, "shadow_broker_route_readiness_sessions", fallback=0.0)),
            int(_number(broker_readiness, "shadow_broker_route_readiness_sessions", fallback=0.0)) > 0
            and int(_number(broker_readiness, "shadow_broker_route_readiness_ready_sessions", fallback=0.0))
            == int(_number(broker_readiness, "shadow_broker_route_readiness_sessions", fallback=0.0)),
            "broker-readiness shadow broker route-readiness proof is not ready",
        ),
        _check(
            "broker_shadow_broker_route_readiness_strategy_matches",
            _strategy_key(broker_readiness.get("shadow_broker_route_readiness_strategy", "")),
            "==",
            expected_strategy,
            bool(
                _strategy_key(broker_readiness.get("shadow_broker_route_readiness_strategy", ""))
                and _strategy_key(broker_readiness.get("shadow_broker_route_readiness_strategy", ""))
                == expected_strategy
            ),
            "broker-readiness shadow broker route-readiness strategy does not match scale-up strategy",
        ),
        _check(
            "broker_shadow_broker_route_readiness_market_matches",
            _identity_key(broker_readiness.get("shadow_broker_route_readiness_market", "")),
            "==",
            expected_market,
            bool(
                _identity_key(broker_readiness.get("shadow_broker_route_readiness_market", ""))
                and _identity_key(broker_readiness.get("shadow_broker_route_readiness_market", "")) == expected_market
            ),
            "broker-readiness shadow broker route-readiness market does not match scale-up market",
        ),
        _threshold_check(
            "broker_shadow_broker_route_readiness_gap_pairs",
            _number(broker_readiness, "shadow_broker_route_readiness_gap_pairs", fallback=0.0),
            "<=",
            0,
        ),
        _check(
            "broker_shadow_broker_dispatch_roundtrip_ready",
            int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_ready_sessions", fallback=0.0)),
            "==",
            int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_sessions", fallback=0.0)),
            int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_sessions", fallback=0.0)) > 0
            and int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_ready_sessions", fallback=0.0))
            == int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_sessions", fallback=0.0)),
            "broker-readiness shadow broker dispatch round-trip proof is not ready",
        ),
        _check(
            "broker_shadow_broker_dispatch_roundtrip_strategy_matches",
            _strategy_key(broker_readiness.get("shadow_broker_dispatch_roundtrip_strategy", "")),
            "==",
            expected_strategy,
            bool(
                _strategy_key(broker_readiness.get("shadow_broker_dispatch_roundtrip_strategy", ""))
                and _strategy_key(broker_readiness.get("shadow_broker_dispatch_roundtrip_strategy", ""))
                == expected_strategy
            ),
            "broker-readiness shadow broker dispatch round-trip strategy does not match scale-up strategy",
        ),
        _check(
            "broker_shadow_broker_dispatch_roundtrip_market_matches",
            _identity_key(broker_readiness.get("shadow_broker_dispatch_roundtrip_market", "")),
            "==",
            expected_market,
            bool(
                _identity_key(broker_readiness.get("shadow_broker_dispatch_roundtrip_market", ""))
                and _identity_key(broker_readiness.get("shadow_broker_dispatch_roundtrip_market", ""))
                == expected_market
            ),
            "broker-readiness shadow broker dispatch round-trip market does not match scale-up market",
        ),
        _check(
            "broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
            int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_scenario_count", fallback=0.0)),
            "==",
            1,
            int(_number(broker_readiness, "shadow_broker_dispatch_roundtrip_scenario_count", fallback=0.0)) == 1,
            "broker-readiness shadow broker dispatch round-trip scenario is missing or mixed",
        ),
        _threshold_check(
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_missing_request_acks", fallback=0.0),
            "<=",
            0,
        ),
        _threshold_check(
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders",
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_rejected_orders", fallback=0.0),
            "<=",
            0,
        ),
        _threshold_check(
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_unmatched_acks", fallback=0.0),
            "<=",
            0,
        ),
        _check(
            "broker_shadow_broker_route_dispatch_roundtrip_ready",
            int(_number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_ready_sessions", fallback=0.0)),
            "==",
            int(_number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_sessions", fallback=0.0)),
            int(_number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_sessions", fallback=0.0)) > 0
            and int(
                _number(
                    broker_readiness,
                    "shadow_broker_route_dispatch_roundtrip_ready_sessions",
                    fallback=0.0,
                )
            )
            == int(_number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_sessions", fallback=0.0)),
            "broker-readiness shadow broker route dispatch round-trip proof is not ready",
        ),
        _check(
            "broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
            _strategy_key(broker_readiness.get("shadow_broker_route_dispatch_roundtrip_strategy", "")),
            "==",
            expected_strategy,
            bool(
                _strategy_key(broker_readiness.get("shadow_broker_route_dispatch_roundtrip_strategy", ""))
                and _strategy_key(broker_readiness.get("shadow_broker_route_dispatch_roundtrip_strategy", ""))
                == expected_strategy
            ),
            "broker-readiness shadow broker route dispatch round-trip strategy does not match scale-up strategy",
        ),
        _check(
            "broker_shadow_broker_route_dispatch_roundtrip_market_matches",
            _identity_key(broker_readiness.get("shadow_broker_route_dispatch_roundtrip_market", "")),
            "==",
            expected_market,
            bool(
                _identity_key(broker_readiness.get("shadow_broker_route_dispatch_roundtrip_market", ""))
                and _identity_key(broker_readiness.get("shadow_broker_route_dispatch_roundtrip_market", ""))
                == expected_market
            ),
            "broker-readiness shadow broker route dispatch round-trip market does not match scale-up market",
        ),
        _check(
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
            int(_number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_scenario_count", fallback=0.0)),
            "==",
            1,
            int(_number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_scenario_count", fallback=0.0))
            == 1,
            "broker-readiness shadow broker route dispatch round-trip scenario is missing or mixed",
        ),
    ]


def _broker_shadow_broker_plan_fields(broker_readiness: pd.Series) -> dict[str, object]:
    if broker_readiness.empty:
        return {
            "broker_shadow_broker_readiness_provided": False,
            "broker_shadow_broker_readiness_sessions": 0,
            "broker_shadow_broker_readiness_ready_sessions": 0,
            "broker_shadow_broker_vendor_data_readiness_sessions": 0,
            "broker_shadow_broker_vendor_data_readiness_provided_sessions": 0,
            "broker_shadow_broker_vendor_data_readiness_ready_sessions": 0,
            "broker_shadow_broker_vendor_data_readiness_failed_checks": 0,
            "broker_shadow_broker_adapter": "",
            "broker_shadow_broker_adapter_count": 0,
            "broker_shadow_broker_route_readiness_sessions": 0,
            "broker_shadow_broker_route_readiness_ready_sessions": 0,
            "broker_shadow_broker_route_readiness_strategy": "",
            "broker_shadow_broker_route_readiness_market": "",
            "broker_shadow_broker_route_readiness_gap_pairs": 0,
            "broker_shadow_broker_dispatch_roundtrip_sessions": 0,
            "broker_shadow_broker_dispatch_roundtrip_ready_sessions": 0,
            "broker_shadow_broker_dispatch_roundtrip_strategy": "",
            "broker_shadow_broker_dispatch_roundtrip_market": "",
            "broker_shadow_broker_dispatch_roundtrip_scenario_count": 0,
            "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": 0,
            "broker_shadow_broker_dispatch_roundtrip_rejected_orders": 0,
            "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": 0,
            "broker_shadow_broker_route_dispatch_roundtrip_sessions": 0,
            "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": 0,
            "broker_shadow_broker_route_dispatch_roundtrip_strategy": "",
            "broker_shadow_broker_route_dispatch_roundtrip_market": "",
            "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": 0,
        }
    return {
        "broker_shadow_broker_readiness_provided": _to_bool(
            broker_readiness.get("shadow_broker_readiness_provided", False)
        ),
        "broker_shadow_broker_readiness_sessions": int(
            _number(broker_readiness, "shadow_broker_readiness_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_readiness_ready_sessions": int(
            _number(broker_readiness, "shadow_broker_readiness_ready_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_vendor_data_readiness_sessions": int(
            _number(broker_readiness, "shadow_broker_vendor_data_readiness_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            _number(
                broker_readiness,
                "shadow_broker_vendor_data_readiness_provided_sessions",
                fallback=0.0,
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            _number(
                broker_readiness,
                "shadow_broker_vendor_data_readiness_ready_sessions",
                fallback=0.0,
            )
        ),
        "broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            _number(
                broker_readiness,
                "shadow_broker_vendor_data_readiness_failed_checks",
                fallback=0.0,
            )
        ),
        "broker_shadow_broker_adapter": _identity_key(broker_readiness.get("shadow_broker_adapter", "")),
        "broker_shadow_broker_adapter_count": int(
            _number(broker_readiness, "shadow_broker_adapter_count", fallback=0.0)
        ),
        "broker_shadow_broker_route_readiness_sessions": int(
            _number(broker_readiness, "shadow_broker_route_readiness_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            _number(broker_readiness, "shadow_broker_route_readiness_ready_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_route_readiness_strategy": _strategy_key(
            broker_readiness.get("shadow_broker_route_readiness_strategy", "")
        ),
        "broker_shadow_broker_route_readiness_market": _identity_key(
            broker_readiness.get("shadow_broker_route_readiness_market", "")
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            _number(broker_readiness, "shadow_broker_route_readiness_gap_pairs", fallback=0.0)
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_ready_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": _strategy_key(
            broker_readiness.get("shadow_broker_dispatch_roundtrip_strategy", "")
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": _identity_key(
            broker_readiness.get("shadow_broker_dispatch_roundtrip_market", "")
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_scenario_count", fallback=0.0)
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_missing_request_acks", fallback=0.0)
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_rejected_orders", fallback=0.0)
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            _number(broker_readiness, "shadow_broker_dispatch_roundtrip_unmatched_acks", fallback=0.0)
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            _number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_sessions", fallback=0.0)
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            _number(
                broker_readiness,
                "shadow_broker_route_dispatch_roundtrip_ready_sessions",
                fallback=0.0,
            )
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": _strategy_key(
            broker_readiness.get("shadow_broker_route_dispatch_roundtrip_strategy", "")
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": _identity_key(
            broker_readiness.get("shadow_broker_route_dispatch_roundtrip_market", "")
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            _number(broker_readiness, "shadow_broker_route_dispatch_roundtrip_scenario_count", fallback=0.0)
        ),
    }


def _broker_vendor_market_data_batch_plan_fields(broker_readiness: pd.Series) -> dict[str, object]:
    field_prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    source_prefix = _broker_vendor_market_data_batch_source_prefix(broker_readiness)
    if broker_readiness.empty:
        return {
            f"{field_prefix}_provided": False,
            f"{field_prefix}_ready": False,
            f"{field_prefix}_adapter": "",
            f"{field_prefix}_kind": "",
            f"{field_prefix}_manifest_run_type": "",
            f"{field_prefix}_market": "",
            f"{field_prefix}_dataset_count": 0,
            f"{field_prefix}_ready_datasets": 0,
            f"{field_prefix}_failed_datasets": 0,
            f"{field_prefix}_ready_rate": np.nan,
            f"{field_prefix}_unique_source_files": 0,
            f"{field_prefix}_unique_header_fingerprints": 0,
            f"{field_prefix}_source_file_fingerprint_coverage": 0.0,
            f"{field_prefix}_min_mapping_coverage": 0.0,
            f"{field_prefix}_unique_mapping_drafts": 0,
            f"{field_prefix}_mapping_sources": "",
            f"{field_prefix}_mapping_source_mode": "",
            f"{field_prefix}_mapping_application_count": 0,
            f"{field_prefix}_unique_mapping_applications": 0,
            f"{field_prefix}_target_application_coverage": 0.0,
            f"{field_prefix}_application_lineage_consistency_required": False,
            f"{field_prefix}_application_lineage_consistent": False,
            f"{field_prefix}_comparison_accepted": False,
            f"{field_prefix}_comparison_failed_checks": 0,
            f"{field_prefix}_datasets_json": "",
            "broker_vendor_market_data_batch_lineage_match_required": False,
            "broker_vendor_market_data_batch_lineage_matches": False,
            "vendor_market_data_batch_application_lineage_sha256": "",
            "broker_vendor_market_data_batch_application_lineage_sha256": "",
            f"{field_prefix}_application_lineage_sha256": "",
        }
    return {
        f"{field_prefix}_provided": _to_bool(broker_readiness.get(f"{source_prefix}_provided", False)),
        f"{field_prefix}_ready": _to_bool(broker_readiness.get(f"{source_prefix}_ready", False)),
        f"{field_prefix}_adapter": _identity_key(broker_readiness.get(f"{source_prefix}_adapter", "")),
        f"{field_prefix}_kind": str(broker_readiness.get(f"{source_prefix}_kind", "")).strip(),
        f"{field_prefix}_manifest_run_type": _identity_key(
            broker_readiness.get(f"{source_prefix}_manifest_run_type", "")
        ),
        f"{field_prefix}_market": _identity_key(broker_readiness.get(f"{source_prefix}_market", "")),
        f"{field_prefix}_dataset_count": int(_number(broker_readiness, f"{source_prefix}_dataset_count", 0.0)),
        f"{field_prefix}_ready_datasets": int(_number(broker_readiness, f"{source_prefix}_ready_datasets", 0.0)),
        f"{field_prefix}_failed_datasets": int(_number(broker_readiness, f"{source_prefix}_failed_datasets", 0.0)),
        f"{field_prefix}_ready_rate": _number(broker_readiness, f"{source_prefix}_ready_rate", np.nan),
        f"{field_prefix}_unique_source_files": int(
            _number(broker_readiness, f"{source_prefix}_unique_source_files", 0.0)
        ),
        f"{field_prefix}_unique_header_fingerprints": int(
            _number(broker_readiness, f"{source_prefix}_unique_header_fingerprints", 0.0)
        ),
        f"{field_prefix}_source_file_fingerprint_coverage": _number(
            broker_readiness,
            f"{source_prefix}_source_file_fingerprint_coverage",
            0.0,
        ),
        f"{field_prefix}_min_mapping_coverage": _number(
            broker_readiness,
            f"{source_prefix}_min_mapping_coverage",
            0.0,
        ),
        f"{field_prefix}_unique_mapping_drafts": int(
            _number(broker_readiness, f"{source_prefix}_unique_mapping_drafts", 0.0)
        ),
        f"{field_prefix}_mapping_sources": str(
            broker_readiness.get(f"{source_prefix}_mapping_sources", "")
        ).strip(),
        f"{field_prefix}_mapping_source_mode": _identity_key(
            broker_readiness.get(f"{source_prefix}_mapping_source_mode", "")
        ),
        f"{field_prefix}_mapping_application_count": int(
            _number(broker_readiness, f"{source_prefix}_mapping_application_count", 0.0)
        ),
        f"{field_prefix}_unique_mapping_applications": int(
            _number(broker_readiness, f"{source_prefix}_unique_mapping_applications", 0.0)
        ),
        f"{field_prefix}_target_application_coverage": _number(
            broker_readiness,
            f"{source_prefix}_target_application_coverage",
            0.0,
        ),
        f"{field_prefix}_application_lineage_consistency_required": _to_bool(
            broker_readiness.get(
                f"{source_prefix}_application_lineage_consistency_required",
                False,
            )
        ),
        f"{field_prefix}_application_lineage_consistent": _to_bool(
            broker_readiness.get(
                f"{source_prefix}_application_lineage_consistent",
                False,
            )
        ),
        f"{field_prefix}_comparison_accepted": _to_bool(
            broker_readiness.get(f"{source_prefix}_comparison_accepted", False)
        ),
        f"{field_prefix}_comparison_failed_checks": int(
            _number(broker_readiness, f"{source_prefix}_comparison_failed_checks", 0.0)
        ),
        f"{field_prefix}_datasets_json": str(broker_readiness.get(f"{source_prefix}_datasets_json", "")).strip(),
        "broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            broker_readiness.get(
                "broker_vendor_market_data_batch_lineage_match_required",
                False,
            )
        ),
        "broker_vendor_market_data_batch_lineage_matches": _to_bool(
            broker_readiness.get(
                "broker_vendor_market_data_batch_lineage_matches",
                False,
            )
        ),
        "vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            broker_readiness.get(
                "vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        ),
        "broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            broker_readiness.get(
                "broker_vendor_market_data_batch_application_lineage_sha256",
                "",
            )
        ),
        f"{field_prefix}_application_lineage_sha256": (
            _broker_vendor_target_application_lineage_sha256(
                broker_readiness,
                source_prefix,
            )
        ),
    }


def _broker_vendor_final_lineage_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            broker_readiness.get(f"{prefix}_lineage_match_required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            broker_readiness.get(f"{prefix}_lineage_matches", False)
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(
            broker_readiness.get(f"{prefix}_{field}", "")
        )
    return fields


def _broker_vendor_readiness_final_lineage_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_FINAL_LINEAGE_FIELD_PREFIX
    state = _broker_vendor_readiness_final_lineage_state(broker_readiness)
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_vendor_readiness_complete_final_lineage_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    state = _broker_vendor_readiness_complete_final_lineage_state(
        broker_readiness
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_vendor_readiness_extended_complete_final_lineage_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    state = _broker_vendor_readiness_extended_complete_final_lineage_state(
        broker_readiness
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_vendor_readiness_latest_extended_complete_final_lineage_42_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_FIELD_PREFIX
    state = _broker_vendor_readiness_latest_extended_complete_final_lineage_42_state(
        broker_readiness
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_FIELD_PREFIX
    )
    state = (
        _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_state(
            broker_readiness
        )
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in (
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS,
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_FIELD_PREFIX
    )
    state = (
        _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_state(
            broker_readiness
        )
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in (
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS,
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_plan_fields(
    broker_readiness: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_FIELD_PREFIX
    )
    state = (
        _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_state(
            broker_readiness
        )
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": bool(state["required"]),
        f"{prefix}_lineage_matches": bool(state["matches"]),
        f"{prefix}_carried_application_lineage_sha256": str(
            state["carried_application_lineage_sha256"]
        ),
    }
    for field in (
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(state[field])
    return fields


def _broker_shadow_broker_summary_fields(plan_row: pd.Series) -> dict[str, object]:
    return {
        "broker_shadow_broker_readiness_provided": _to_bool(
            plan_row["broker_shadow_broker_readiness_provided"]
        ),
        "broker_shadow_broker_readiness_sessions": int(plan_row["broker_shadow_broker_readiness_sessions"]),
        "broker_shadow_broker_readiness_ready_sessions": int(
            plan_row["broker_shadow_broker_readiness_ready_sessions"]
        ),
        "broker_shadow_broker_vendor_data_readiness_sessions": int(
            plan_row["broker_shadow_broker_vendor_data_readiness_sessions"]
        ),
        "broker_shadow_broker_vendor_data_readiness_provided_sessions": int(
            plan_row["broker_shadow_broker_vendor_data_readiness_provided_sessions"]
        ),
        "broker_shadow_broker_vendor_data_readiness_ready_sessions": int(
            plan_row["broker_shadow_broker_vendor_data_readiness_ready_sessions"]
        ),
        "broker_shadow_broker_vendor_data_readiness_failed_checks": int(
            plan_row["broker_shadow_broker_vendor_data_readiness_failed_checks"]
        ),
        "broker_shadow_broker_adapter": str(plan_row["broker_shadow_broker_adapter"]),
        "broker_shadow_broker_adapter_count": int(plan_row["broker_shadow_broker_adapter_count"]),
        "broker_shadow_broker_route_readiness_sessions": int(
            plan_row["broker_shadow_broker_route_readiness_sessions"]
        ),
        "broker_shadow_broker_route_readiness_ready_sessions": int(
            plan_row["broker_shadow_broker_route_readiness_ready_sessions"]
        ),
        "broker_shadow_broker_route_readiness_strategy": str(
            plan_row["broker_shadow_broker_route_readiness_strategy"]
        ),
        "broker_shadow_broker_route_readiness_market": str(
            plan_row["broker_shadow_broker_route_readiness_market"]
        ),
        "broker_shadow_broker_route_readiness_gap_pairs": int(
            plan_row["broker_shadow_broker_route_readiness_gap_pairs"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_sessions": int(
            plan_row["broker_shadow_broker_dispatch_roundtrip_sessions"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_ready_sessions": int(
            plan_row["broker_shadow_broker_dispatch_roundtrip_ready_sessions"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_strategy": str(
            plan_row["broker_shadow_broker_dispatch_roundtrip_strategy"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_market": str(
            plan_row["broker_shadow_broker_dispatch_roundtrip_market"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_scenario_count": int(
            plan_row["broker_shadow_broker_dispatch_roundtrip_scenario_count"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks": int(
            plan_row["broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders": int(
            plan_row["broker_shadow_broker_dispatch_roundtrip_rejected_orders"]
        ),
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks": int(
            plan_row["broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_sessions": int(
            plan_row["broker_shadow_broker_route_dispatch_roundtrip_sessions"]
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_ready_sessions": int(
            plan_row["broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_strategy": str(
            plan_row["broker_shadow_broker_route_dispatch_roundtrip_strategy"]
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_market": str(
            plan_row["broker_shadow_broker_route_dispatch_roundtrip_market"]
        ),
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_count": int(
            plan_row["broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]
        ),
    }


def _broker_vendor_market_data_batch_summary_fields(plan_row: pd.Series) -> dict[str, object]:
    field_prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{field_prefix}_provided": _to_bool(plan_row[f"{field_prefix}_provided"]),
        f"{field_prefix}_ready": _to_bool(plan_row[f"{field_prefix}_ready"]),
        f"{field_prefix}_adapter": str(plan_row[f"{field_prefix}_adapter"]),
        f"{field_prefix}_kind": str(plan_row[f"{field_prefix}_kind"]),
        f"{field_prefix}_manifest_run_type": str(plan_row[f"{field_prefix}_manifest_run_type"]),
        f"{field_prefix}_market": str(plan_row[f"{field_prefix}_market"]),
        f"{field_prefix}_dataset_count": int(plan_row[f"{field_prefix}_dataset_count"]),
        f"{field_prefix}_ready_datasets": int(plan_row[f"{field_prefix}_ready_datasets"]),
        f"{field_prefix}_failed_datasets": int(plan_row[f"{field_prefix}_failed_datasets"]),
        f"{field_prefix}_ready_rate": _jsonable(plan_row[f"{field_prefix}_ready_rate"]),
        f"{field_prefix}_unique_source_files": int(plan_row[f"{field_prefix}_unique_source_files"]),
        f"{field_prefix}_unique_header_fingerprints": int(
            plan_row[f"{field_prefix}_unique_header_fingerprints"]
        ),
        f"{field_prefix}_source_file_fingerprint_coverage": _jsonable(
            plan_row[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        f"{field_prefix}_min_mapping_coverage": _jsonable(
            plan_row[f"{field_prefix}_min_mapping_coverage"]
        ),
        f"{field_prefix}_unique_mapping_drafts": int(plan_row[f"{field_prefix}_unique_mapping_drafts"]),
        f"{field_prefix}_mapping_sources": str(plan_row[f"{field_prefix}_mapping_sources"]),
        f"{field_prefix}_mapping_source_mode": str(plan_row[f"{field_prefix}_mapping_source_mode"]),
        f"{field_prefix}_mapping_application_count": int(
            plan_row[f"{field_prefix}_mapping_application_count"]
        ),
        f"{field_prefix}_unique_mapping_applications": int(
            plan_row[f"{field_prefix}_unique_mapping_applications"]
        ),
        f"{field_prefix}_target_application_coverage": _jsonable(
            plan_row[f"{field_prefix}_target_application_coverage"]
        ),
        f"{field_prefix}_application_lineage_consistency_required": _to_bool(
            plan_row[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        f"{field_prefix}_application_lineage_consistent": _to_bool(
            plan_row[f"{field_prefix}_application_lineage_consistent"]
        ),
        "broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            plan_row["broker_vendor_market_data_batch_lineage_match_required"]
        ),
        "broker_vendor_market_data_batch_lineage_matches": _to_bool(
            plan_row["broker_vendor_market_data_batch_lineage_matches"]
        ),
        "vendor_market_data_batch_application_lineage_sha256": str(
            plan_row["vendor_market_data_batch_application_lineage_sha256"]
        ),
        "broker_vendor_market_data_batch_application_lineage_sha256": str(
            plan_row["broker_vendor_market_data_batch_application_lineage_sha256"]
        ),
        f"{field_prefix}_application_lineage_sha256": str(
            plan_row[f"{field_prefix}_application_lineage_sha256"]
        ),
        f"{field_prefix}_comparison_accepted": _to_bool(plan_row[f"{field_prefix}_comparison_accepted"]),
        f"{field_prefix}_comparison_failed_checks": int(plan_row[f"{field_prefix}_comparison_failed_checks"]),
        f"{field_prefix}_datasets_json": str(plan_row[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_final_lineage_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_final_lineage_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
    }
    for field in BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_complete_final_lineage_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        f"{prefix}_scaleup_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_extended_complete_final_lineage_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        f"{prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_latest_extended_complete_final_lineage_42_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        f"{prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        f"{prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS,
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_{BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD}": str(
            plan_row[
                f"{prefix}_{BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD}"
            ]
        ),
        f"{prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS,
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_summary_fields(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            plan_row[f"{prefix}_lineage_match_required"]
        ),
        f"{prefix}_lineage_matches": _to_bool(
            plan_row[f"{prefix}_lineage_matches"]
        ),
        f"{prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in (
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = str(plan_row[f"{prefix}_{field}"])
    return fields


def _broker_shadow_broker_config(plan_row: pd.Series) -> dict[str, object]:
    return {
        "provided": _to_bool(plan_row["broker_shadow_broker_readiness_provided"]),
        "sessions": int(plan_row["broker_shadow_broker_readiness_sessions"]),
        "ready_sessions": int(plan_row["broker_shadow_broker_readiness_ready_sessions"]),
        "adapter": str(plan_row["broker_shadow_broker_adapter"]),
        "adapter_count": int(plan_row["broker_shadow_broker_adapter_count"]),
        "broker_vendor_data_readiness": {
            "sessions": int(plan_row["broker_shadow_broker_vendor_data_readiness_sessions"]),
            "provided_sessions": int(
                plan_row["broker_shadow_broker_vendor_data_readiness_provided_sessions"]
            ),
            "ready_sessions": int(plan_row["broker_shadow_broker_vendor_data_readiness_ready_sessions"]),
            "failed_checks": int(plan_row["broker_shadow_broker_vendor_data_readiness_failed_checks"]),
        },
        "route_readiness": {
            "sessions": int(plan_row["broker_shadow_broker_route_readiness_sessions"]),
            "ready_sessions": int(plan_row["broker_shadow_broker_route_readiness_ready_sessions"]),
            "strategy": str(plan_row["broker_shadow_broker_route_readiness_strategy"]),
            "market": str(plan_row["broker_shadow_broker_route_readiness_market"]),
            "max_gap_pairs": int(plan_row["broker_shadow_broker_route_readiness_gap_pairs"]),
        },
        "dispatch_roundtrip": {
            "sessions": int(plan_row["broker_shadow_broker_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(plan_row["broker_shadow_broker_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(plan_row["broker_shadow_broker_dispatch_roundtrip_strategy"]),
            "market": str(plan_row["broker_shadow_broker_dispatch_roundtrip_market"]),
            "scenario_count": int(plan_row["broker_shadow_broker_dispatch_roundtrip_scenario_count"]),
            "max_missing_request_acks": int(
                plan_row["broker_shadow_broker_dispatch_roundtrip_missing_request_acks"]
            ),
            "max_rejected_orders": int(plan_row["broker_shadow_broker_dispatch_roundtrip_rejected_orders"]),
            "max_unmatched_acks": int(plan_row["broker_shadow_broker_dispatch_roundtrip_unmatched_acks"]),
        },
        "route_dispatch_roundtrip": {
            "sessions": int(plan_row["broker_shadow_broker_route_dispatch_roundtrip_sessions"]),
            "ready_sessions": int(plan_row["broker_shadow_broker_route_dispatch_roundtrip_ready_sessions"]),
            "strategy": str(plan_row["broker_shadow_broker_route_dispatch_roundtrip_strategy"]),
            "market": str(plan_row["broker_shadow_broker_route_dispatch_roundtrip_market"]),
            "scenario_count": int(plan_row["broker_shadow_broker_route_dispatch_roundtrip_scenario_count"]),
        },
    }


def _broker_vendor_market_data_batch_config(plan_row: pd.Series) -> dict[str, object]:
    field_prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        "provided": _to_bool(plan_row[f"{field_prefix}_provided"]),
        "ready": _to_bool(plan_row[f"{field_prefix}_ready"]),
        "adapter": str(plan_row[f"{field_prefix}_adapter"]),
        "kind": str(plan_row[f"{field_prefix}_kind"]),
        "manifest_run_type": str(plan_row[f"{field_prefix}_manifest_run_type"]),
        "market": str(plan_row[f"{field_prefix}_market"]),
        "dataset_count": int(plan_row[f"{field_prefix}_dataset_count"]),
        "ready_datasets": int(plan_row[f"{field_prefix}_ready_datasets"]),
        "failed_datasets": int(plan_row[f"{field_prefix}_failed_datasets"]),
        "ready_rate": _jsonable(plan_row[f"{field_prefix}_ready_rate"]),
        "unique_source_files": int(plan_row[f"{field_prefix}_unique_source_files"]),
        "unique_header_fingerprints": int(plan_row[f"{field_prefix}_unique_header_fingerprints"]),
        "source_file_fingerprint_coverage": _jsonable(
            plan_row[f"{field_prefix}_source_file_fingerprint_coverage"]
        ),
        "min_mapping_coverage": _jsonable(plan_row[f"{field_prefix}_min_mapping_coverage"]),
        "unique_mapping_drafts": int(plan_row[f"{field_prefix}_unique_mapping_drafts"]),
        "mapping_sources": str(plan_row[f"{field_prefix}_mapping_sources"]),
        "mapping_source_mode": str(plan_row[f"{field_prefix}_mapping_source_mode"]),
        "mapping_application_count": int(plan_row[f"{field_prefix}_mapping_application_count"]),
        "unique_mapping_applications": int(
            plan_row[f"{field_prefix}_unique_mapping_applications"]
        ),
        "target_application_coverage": _jsonable(
            plan_row[f"{field_prefix}_target_application_coverage"]
        ),
        "application_lineage_consistency_required": _to_bool(
            plan_row[f"{field_prefix}_application_lineage_consistency_required"]
        ),
        "application_lineage_consistent": _to_bool(
            plan_row[f"{field_prefix}_application_lineage_consistent"]
        ),
        "application_lineage_sha256": str(
            plan_row[f"{field_prefix}_application_lineage_sha256"]
        ),
        "comparison": {
            "accepted": _to_bool(plan_row[f"{field_prefix}_comparison_accepted"]),
            "failed_checks": int(plan_row[f"{field_prefix}_comparison_failed_checks"]),
        },
        "datasets": _json_list(plan_row[f"{field_prefix}_datasets_json"]),
    }


def _broker_vendor_final_lineage_config(plan_row: pd.Series) -> dict[str, object]:
    prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_application_lineage_sha256"]
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_final_lineage_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "broker_readiness_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        "carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_complete_final_lineage_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "broker_readiness_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        "carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_extended_complete_final_lineage_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        "carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_latest_extended_complete_final_lineage_43_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_FIELD_PREFIX
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        "carried_application_lineage_sha256": str(
            plan_row[
                f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"
            ]
        ),
    }
    for field in BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS:
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_current_latest_extended_complete_final_lineage_51_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_FIELD_PREFIX
    )
    scaleup_lineage_sha256 = str(
        plan_row[f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"]
    )
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256": str(
            plan_row[f"{prefix}_carried_application_lineage_sha256"]
        ),
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup_lineage_sha256,
        "carried_application_lineage_sha256": scaleup_lineage_sha256,
    }
    for field in (
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS,
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS,
    ):
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_reconciled_current_latest_extended_complete_final_lineage_59_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_FIELD_PREFIX
    )
    scaleup_lineage_sha256 = str(
        plan_row[f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"]
    )
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD: str(
            plan_row[
                f"{prefix}_{BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD}"
            ]
        ),
        "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup_lineage_sha256,
        "carried_application_lineage_sha256": scaleup_lineage_sha256,
    }
    for field in (
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS,
    ):
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def _broker_vendor_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_67_config(
    plan_row: pd.Series,
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_FIELD_PREFIX
    )
    scaleup_lineage_sha256 = str(
        plan_row[f"{BROKER_FINAL_LINEAGE_FIELD_PREFIX}_application_lineage_sha256"]
    )
    config: dict[str, object] = {
        "required": _to_bool(plan_row[f"{prefix}_lineage_match_required"]),
        "matches": _to_bool(plan_row[f"{prefix}_lineage_matches"]),
        "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup_lineage_sha256,
        "carried_application_lineage_sha256": scaleup_lineage_sha256,
    }
    for field in (
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD,
    ):
        config[field] = str(plan_row[f"{prefix}_{field}"])
    return config


def load_strategy_portfolio_provenance(
    summary_path: Path | None,
    summary: pd.DataFrame | None,
    allocations: pd.DataFrame | None,
) -> dict[str, Any]:
    provided = summary_path is not None
    evidence: dict[str, Any] = {
        "manifest_required": provided,
        "manifest_provided": False,
        "manifest_current": False,
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_error": "manifest_missing" if provided else "",
        "contract_consistent": not provided,
        "contract_error": "",
        "non_authorizing": True,
        "gate_passed": not provided,
        "dependency_paths": [],
        "root": "",
        "scorecard_manifest_required": False,
        "scorecard_manifest_current": False,
        "scorecard_manifest_sha256": "",
        "scorecard_contract_consistent": False,
        "scorecard_non_authorizing": False,
        "scorecard_provenance_gate_passed": False,
        "research_family_bound": False,
        "research_family_provenance_current": False,
        "research_family_id": "",
        "research_family_registration_id": "",
        "research_family_path": "",
        "research_family_manifest_sha256": "",
    }
    if not provided:
        return evidence
    candidate = Path(summary_path)
    root = candidate.parent if candidate.suffix else candidate
    root = root.resolve()
    manifest_path = root / "manifest.json"
    evidence.update(
        {
            "root": str(root),
            "manifest_path": str(manifest_path),
            "manifest_provided": manifest_path.is_file(),
        }
    )
    summary_frame = summary if summary is not None else pd.DataFrame()
    allocation_frame = allocations if allocations is not None else pd.DataFrame()
    summary_row = summary_frame.iloc[0] if not summary_frame.empty else pd.Series(dtype=object)
    config = _read_json_object(root / "strategy_portfolio_config.json")
    manifest = _read_json_object(manifest_path)
    if manifest_path.is_file():
        integrity = verify_experiment_manifest(
            manifest_path,
            expected_run_type="strategy_portfolio_allocation",
            required_artifacts=STRATEGY_PORTFOLIO_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        evidence["manifest_current"] = bool(integrity.passed)
        evidence["manifest_error"] = str(integrity.error)
        evidence["manifest_sha256"] = file_sha256(manifest_path)
        evidence["dependency_paths"] = [
            str(path) for path in manifest_dependency_paths(manifest_path)
        ]
    contract_errors = _strategy_portfolio_contract_errors(
        summary_frame,
        allocation_frame,
        config,
        manifest,
        root,
    )
    evidence["contract_consistent"] = not contract_errors
    evidence["contract_error"] = ";".join(contract_errors)
    extra_value = manifest.get("extra", {})
    extra = extra_value if isinstance(extra_value, dict) else {}
    evidence["non_authorizing"] = _strategy_portfolio_non_authorizing(
        summary_frame,
        allocation_frame,
        config,
        extra,
    )
    scorecard_value = config.get("scorecard_provenance", {})
    scorecard = scorecard_value if isinstance(scorecard_value, dict) else {}
    evidence.update(
        {
            "scorecard_manifest_required": _to_bool(
                summary_row.get(
                    "scorecard_manifest_required",
                    config.get("scorecard_manifest_required", False),
                )
            ),
            "scorecard_manifest_current": _to_bool(
                summary_row.get(
                    "scorecard_manifest_current",
                    config.get("scorecard_manifest_current", False),
                )
            ),
            "scorecard_manifest_sha256": _text(
                summary_row.get(
                    "scorecard_manifest_sha256",
                    config.get("scorecard_manifest_sha256", ""),
                )
            ),
            "scorecard_contract_consistent": _to_bool(
                summary_row.get(
                    "scorecard_contract_consistent",
                    scorecard.get("contract_consistent", False),
                )
            ),
            "scorecard_non_authorizing": _to_bool(
                summary_row.get(
                    "scorecard_non_authorizing",
                    scorecard.get("non_authorizing", False),
                )
            ),
            "scorecard_provenance_gate_passed": _to_bool(
                summary_row.get(
                    "scorecard_provenance_gate_passed",
                    scorecard.get("gate_passed", False),
                )
            ),
            "research_family_bound": _to_bool(
                summary_row.get(
                    "research_family_bound",
                    config.get("research_family_bound", False),
                )
            ),
            "research_family_provenance_current": _to_bool(
                summary_row.get(
                    "research_family_provenance_current",
                    config.get("research_family_provenance_current", False),
                )
            ),
            "research_family_id": _text(
                summary_row.get(
                    "research_family_id",
                    config.get("research_family_id", ""),
                )
            ),
            "research_family_registration_id": _text(
                summary_row.get(
                    "research_family_registration_id",
                    config.get("research_family_registration_id", ""),
                )
            ),
            "research_family_path": _text(
                summary_row.get(
                    "research_family_path",
                    config.get("research_family_path", ""),
                )
            ),
            "research_family_manifest_sha256": _text(
                summary_row.get(
                    "research_family_manifest_sha256",
                    config.get("research_family_manifest_sha256", ""),
                )
            ),
        }
    )
    family_ok = bool(
        not evidence["research_family_bound"]
        or evidence["research_family_provenance_current"]
    )
    evidence["gate_passed"] = bool(
        evidence["manifest_provided"]
        and evidence["manifest_current"]
        and evidence["contract_consistent"]
        and evidence["non_authorizing"]
        and family_ok
    )
    return evidence


def _strategy_portfolio_contract_errors(
    summary: pd.DataFrame,
    allocations: pd.DataFrame,
    config: dict[str, Any],
    manifest: dict[str, Any],
    root: Path,
) -> list[str]:
    errors: list[str] = []
    if summary.empty:
        return ["portfolio_summary_missing_or_empty"]
    if allocations.empty:
        errors.append("portfolio_allocations_missing_or_empty")
    if not config:
        errors.append("portfolio_config_missing_or_invalid")
    summary_row = summary.iloc[0]
    config_summary_value = config.get("summary", {})
    config_summary = config_summary_value if isinstance(config_summary_value, dict) else {}
    extra_value = manifest.get("extra", {})
    extra = extra_value if isinstance(extra_value, dict) else {}
    ready = _to_bool(summary_row.get("ready", False))
    if _to_bool(config.get("ready", False)) != ready:
        errors.append("portfolio_config_ready_mismatch")
    if _to_bool(config_summary.get("ready", False)) != ready:
        errors.append("portfolio_config_summary_ready_mismatch")
    if _to_bool(extra.get("ready", False)) != ready:
        errors.append("portfolio_manifest_ready_mismatch")
    checks = _read_optional_csv(root / "strategy_portfolio_checks.csv")
    if checks.empty or "passed" not in checks.columns:
        errors.append("portfolio_checks_missing_or_invalid")
    elif bool(checks["passed"].map(_to_bool).all()) != ready:
        errors.append("portfolio_checks_ready_mismatch")

    for field in (
        "deployment_mode",
        "allocation_mode",
        "capital_currency",
        "total_capital",
        "allocated_weight",
        "allocated_notional",
        "allocated_strategy_count",
        "allocated_market_count",
        "scorecard_manifest_required",
        "scorecard_manifest_current",
        "scorecard_manifest_sha256",
        "scorecard_contract_consistent",
        "scorecard_non_authorizing",
        "scorecard_provenance_gate_passed",
        "research_family_bound",
        "research_family_provenance_current",
        "research_family_id",
        "research_family_registration_id",
        "research_family_path",
        "research_family_manifest_sha256",
    ):
        if field in summary_row.index or field in config_summary:
            if _comparable(summary_row.get(field, "")) != _comparable(
                config_summary.get(field, "")
            ):
                errors.append(f"portfolio_summary_config_{field}_mismatch")
    config_allocations_value = config.get("allocations", [])
    config_allocations = config_allocations_value if isinstance(config_allocations_value, list) else []
    records = allocations.to_dict(orient="records")
    if len(config_allocations) != len(records):
        errors.append("portfolio_allocation_count_mismatch")
    else:
        for index, (row, config_row) in enumerate(
            zip(records, config_allocations, strict=True)
        ):
            if not isinstance(config_row, dict):
                errors.append(f"portfolio_config_allocation_not_object:{index}")
                continue
            for field in (
                "profile",
                "strategy",
                "market",
                "eligible",
                "allocation_weight",
                "allocation_notional",
                "scorecard_manifest_sha256",
                "research_family_enabled",
                "research_family_id",
                "research_family_registration_id",
                "research_family_manifest_sha256",
                "research_family_matched_study_label",
                "authorizes_submission",
            ):
                if field in row or field in config_row:
                    if _comparable(row.get(field, "")) != _comparable(
                        config_row.get(field, "")
                    ):
                        errors.append(f"portfolio_allocation_{field}_mismatch:{index}")
    positive = int(
        allocations.get(
            "allocation_weight",
            pd.Series(0.0, index=allocations.index),
        ).map(lambda value: _to_number(value) > 0.0).sum()
    ) if not allocations.empty else 0
    if int(_number(config, "allocation_count", fallback=-1.0)) != positive:
        errors.append("portfolio_positive_allocation_count_mismatch")
    if _to_bool(summary_row.get("research_family_bound", False)):
        errors.extend(
            _strategy_portfolio_family_contract_errors(
                summary_row,
                allocations,
                config,
                extra,
            )
        )
    if not _strategy_portfolio_non_authorizing(summary, allocations, config, extra):
        errors.append("portfolio_authorizes_submission")
    return sorted(set(errors))


def _strategy_portfolio_family_contract_errors(
    summary: pd.Series,
    allocations: pd.DataFrame,
    config: dict[str, Any],
    extra: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    family_id = str(summary.get("research_family_id", "")).strip()
    registration_id = str(summary.get("research_family_registration_id", "")).strip()
    family_sha = str(summary.get("research_family_manifest_sha256", "")).strip()
    for check, value in (
        ("summary_family_current", summary.get("research_family_provenance_current", False)),
        ("summary_scorecard_current", summary.get("scorecard_manifest_current", False)),
        ("summary_scorecard_contract", summary.get("scorecard_contract_consistent", False)),
        ("summary_scorecard_non_authorizing", summary.get("scorecard_non_authorizing", False)),
        ("summary_scorecard_gate", summary.get("scorecard_provenance_gate_passed", False)),
    ):
        if not _to_bool(value):
            errors.append(f"portfolio_{check}_not_true")
    if not family_id or not registration_id or not family_sha:
        errors.append("portfolio_family_identity_incomplete")
    for field, expected in (
        ("research_family_id", family_id),
        ("research_family_registration_id", registration_id),
        ("research_family_manifest_sha256", family_sha),
    ):
        if str(config.get(field, "")) != expected:
            errors.append(f"portfolio_config_{field}_mismatch")
        if str(extra.get(field, "")) != expected:
            errors.append(f"portfolio_manifest_{field}_mismatch")
    if not _to_bool(extra.get("research_family_bound", False)):
        errors.append("portfolio_manifest_family_not_bound")
    scorecard_value = config.get("scorecard_provenance", {})
    scorecard = scorecard_value if isinstance(scorecard_value, dict) else {}
    if not _to_bool(scorecard.get("gate_passed", False)):
        errors.append("portfolio_scorecard_provenance_gate_not_passed")
    errors.extend(
        _strategy_portfolio_nested_lineage_errors(
            scorecard,
            family_id=family_id,
            registration_id=registration_id,
            family_manifest_sha256=family_sha,
        )
    )
    family_rows = allocations.loc[
        allocations.get(
            "research_family_enabled",
            pd.Series(False, index=allocations.index),
        ).map(_to_bool)
    ] if not allocations.empty else allocations
    for index, row in family_rows.iterrows():
        if str(row.get("research_family_id", "")) != family_id:
            errors.append(f"portfolio_family_row_id_mismatch:{index}")
        if str(row.get("research_family_registration_id", "")) != registration_id:
            errors.append(f"portfolio_family_row_registration_mismatch:{index}")
        if str(row.get("research_family_manifest_sha256", "")) != family_sha:
            errors.append(f"portfolio_family_row_manifest_mismatch:{index}")
        if not _to_bool(row.get("research_family_gate_passed", False)):
            errors.append(f"portfolio_family_row_gate_not_passed:{index}")
    return errors


def _strategy_portfolio_nested_lineage_errors(
    scorecard: dict[str, Any],
    *,
    family_id: str,
    registration_id: str,
    family_manifest_sha256: str,
) -> list[str]:
    errors: list[str] = []
    raw_scorecard_manifest = str(scorecard.get("manifest_path", "")).strip()
    scorecard_manifest = Path(raw_scorecard_manifest) if raw_scorecard_manifest else Path()
    if not raw_scorecard_manifest or not scorecard_manifest.is_file():
        errors.append("portfolio_nested_scorecard_manifest_missing")
    else:
        scorecard_integrity = verify_experiment_manifest(
            scorecard_manifest,
            expected_run_type="strategy_scorecard",
            required_artifacts=STRATEGY_SCORECARD_REQUIRED_ARTIFACTS,
            require_input_fingerprints=True,
        )
        if not scorecard_integrity.passed:
            errors.append(
                "portfolio_nested_scorecard_manifest_not_current:"
                f"{scorecard_integrity.error}"
            )
        if file_sha256(scorecard_manifest) != str(
            scorecard.get("manifest_sha256", "")
        ):
            errors.append("portfolio_nested_scorecard_manifest_sha256_mismatch")
        scorecard_summary = _read_optional_csv(
            scorecard_manifest.parent / "strategy_scorecard_summary.csv"
        )
        scorecard_config = _read_json_object(
            scorecard_manifest.parent / "strategy_scorecard_next_actions.json"
        )
        scorecard_row = (
            scorecard_summary.iloc[0]
            if not scorecard_summary.empty
            else pd.Series(dtype=object)
        )
        for source, row in (
            ("summary", scorecard_row),
            ("config", scorecard_config),
        ):
            if str(row.get("research_family_id", "")) != family_id:
                errors.append(
                    f"portfolio_nested_scorecard_family_id_mismatch:{source}"
                )
            if str(row.get("research_family_registration_id", "")) != registration_id:
                errors.append(
                    "portfolio_nested_scorecard_registration_id_mismatch:"
                    f"{source}"
                )
            if str(row.get("research_family_manifest_sha256", "")) != family_manifest_sha256:
                errors.append(
                    "portfolio_nested_scorecard_family_manifest_mismatch:"
                    f"{source}"
                )
            if _to_bool(row.get("authorizes_submission", False)):
                errors.append(
                    f"portfolio_nested_scorecard_authorizes_submission:{source}"
                )
        if int(
            _number(
                scorecard_row,
                "research_family_gate_passed_profiles",
                fallback=0.0,
            )
        ) < 1:
            errors.append("portfolio_nested_scorecard_family_gate_not_passed")

    raw_family_path = str(scorecard.get("research_family_path", "")).strip()
    family_root = Path(raw_family_path) if raw_family_path else Path()
    family_manifest = family_root / "manifest.json"
    if not raw_family_path or not family_manifest.is_file():
        errors.append("portfolio_nested_research_family_manifest_missing")
        return errors
    family_integrity = verify_experiment_manifest(
        family_manifest,
        expected_run_type="research_family_audit",
        required_artifacts=RESEARCH_FAMILY_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    if not family_integrity.passed:
        errors.append(
            "portfolio_nested_research_family_manifest_not_current:"
            f"{family_integrity.error}"
        )
    if file_sha256(family_manifest) != family_manifest_sha256:
        errors.append("portfolio_nested_research_family_manifest_sha256_mismatch")
    family_summary = _read_optional_csv(
        family_root / "research_family_summary.csv"
    )
    family_config = _read_json_object(
        family_root / "research_family_config.json"
    )
    family_manifest_payload = _read_json_object(family_manifest)
    family_extra_value = family_manifest_payload.get("extra", {})
    family_extra = family_extra_value if isinstance(family_extra_value, dict) else {}
    family_config_summary_value = family_config.get("summary", {})
    family_config_summary = (
        family_config_summary_value
        if isinstance(family_config_summary_value, dict)
        else {}
    )
    family_parameters_value = family_config.get("parameters", {})
    family_parameters = (
        family_parameters_value
        if isinstance(family_parameters_value, dict)
        else {}
    )
    family_row = (
        family_summary.iloc[0]
        if not family_summary.empty
        else pd.Series(dtype=object)
    )
    for source, row in (
        ("summary", family_row),
        ("config_summary", family_config_summary),
        ("manifest", family_extra),
    ):
        if str(row.get("family_id", "")) != family_id:
            errors.append(f"portfolio_nested_family_id_mismatch:{source}")
        if str(row.get("registration_id", "")) != registration_id:
            errors.append(
                f"portfolio_nested_family_registration_id_mismatch:{source}"
            )
        if _to_bool(row.get("authorizes_submission", False)):
            errors.append(
                f"portfolio_nested_family_authorizes_submission:{source}"
            )
    if str(family_parameters.get("family_id", "")) != family_id:
        errors.append("portfolio_nested_family_id_mismatch:config_parameters")
    for check, value in (
        ("passed", family_row.get("passed", False)),
        (
            "prospective_registration_passed",
            family_row.get("prospective_registration_passed", False),
        ),
        ("registration_closed", family_row.get("registration_closed", False)),
        (
            "family_wise_error_control_claimed",
            family_row.get("family_wise_error_control_claimed", False),
        ),
    ):
        if not _to_bool(value):
            errors.append(f"portfolio_nested_family_{check}_not_true")
    for source, row in (
        ("config_summary", family_config_summary),
        ("manifest", family_extra),
    ):
        for check in (
            "registration_closed",
            "family_wise_error_control_claimed",
        ):
            if not _to_bool(row.get(check, False)):
                errors.append(
                    f"portfolio_nested_family_{check}_not_true:{source}"
                )
    if not _to_bool(family_config.get("passed", False)):
        errors.append("portfolio_nested_family_passed_not_true:config")
    if not _to_bool(family_extra.get("passed", False)):
        errors.append("portfolio_nested_family_passed_not_true:manifest")
    if not _to_bool(
        family_extra.get("prospective_registration_passed", False)
    ):
        errors.append(
            "portfolio_nested_family_prospective_registration_not_true:manifest"
        )
    return errors


def _strategy_portfolio_non_authorizing(
    summary: pd.DataFrame,
    allocations: pd.DataFrame,
    config: dict[str, Any],
    extra: dict[str, Any],
) -> bool:
    summary_authorizes = bool(
        summary.get(
            "authorizes_submission",
            pd.Series(False, index=summary.index),
        ).map(_to_bool).any()
    ) if not summary.empty else False
    allocation_authorizes = bool(
        allocations.get(
            "authorizes_submission",
            pd.Series(False, index=allocations.index),
        ).map(_to_bool).any()
    ) if not allocations.empty else False
    return bool(
        not summary_authorizes
        and not allocation_authorizes
        and not _to_bool(config.get("authorizes_submission", False))
        and not _to_bool(extra.get("authorizes_submission", False))
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_optional_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame()


def _comparable(value: Any) -> Any:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.number)) and not pd.isna(value):
        return float(value)
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return "" if value is None else str(value)


def _to_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if np.isnan(number) else number


def _strategy_portfolio_state(
    summary: pd.DataFrame,
    allocations: pd.DataFrame,
    evidence: pd.Series,
    thresholds: ScaleUpThresholds,
    *,
    provenance: dict[str, Any] | None = None,
) -> pd.Series:
    expected_strategy = _strategy_key(thresholds.expected_strategy) or _strategy_key(evidence.get("strategy", ""))
    expected_market = _identity_key(thresholds.expected_market) or _identity_key(evidence.get("market", ""))
    summary_row = summary.iloc[0] if summary is not None and not summary.empty else pd.Series(dtype=object)
    selected = _select_strategy_portfolio_allocation(allocations, expected_strategy, expected_market)
    proof = provenance or {
        "manifest_required": False,
        "manifest_provided": False,
        "manifest_current": False,
        "manifest_path": "",
        "manifest_sha256": "",
        "manifest_error": "",
        "contract_consistent": True,
        "contract_error": "",
        "non_authorizing": True,
        "gate_passed": True,
        "dependency_paths": [],
        "scorecard_manifest_required": False,
        "scorecard_manifest_current": False,
        "scorecard_manifest_sha256": "",
        "scorecard_contract_consistent": True,
        "scorecard_non_authorizing": True,
        "scorecard_provenance_gate_passed": True,
        "research_family_bound": False,
        "research_family_provenance_current": True,
        "research_family_id": "",
        "research_family_registration_id": "",
        "research_family_path": "",
        "research_family_manifest_sha256": "",
    }
    provenance_gate = bool(
        not _to_bool(proof.get("manifest_required", False))
        or _to_bool(proof.get("gate_passed", False))
    )
    selected_source_eligible = _to_bool(selected.get("eligible", False)) if not selected.empty else False
    selected_source_notional = (
        _number(selected, "allocation_notional", fallback=0.0)
        if not selected.empty
        else 0.0
    )
    selected_eligible = bool(selected_source_eligible and provenance_gate)
    selected_notional = selected_source_notional if provenance_gate else 0.0
    selected_reason = str(selected.get("eligibility_reason", "")) if not selected.empty else ""
    if not provenance_gate and not selected.empty:
        selected_reason = "strategy_portfolio_provenance_not_current"
    return pd.Series(
        {
            "provided": summary is not None and not summary.empty,
            "ready": _to_bool(summary_row.get("ready", False)) if not summary_row.empty else False,
            "manifest_required": _to_bool(proof.get("manifest_required", False)),
            "manifest_provided": _to_bool(proof.get("manifest_provided", False)),
            "manifest_current": _to_bool(proof.get("manifest_current", False)),
            "manifest_path": str(proof.get("manifest_path", "")),
            "manifest_sha256": str(proof.get("manifest_sha256", "")),
            "manifest_error": str(proof.get("manifest_error", "")),
            "contract_consistent": _to_bool(proof.get("contract_consistent", False)),
            "contract_error": str(proof.get("contract_error", "")),
            "non_authorizing": _to_bool(proof.get("non_authorizing", False)),
            "provenance_gate_passed": provenance_gate,
            "dependency_count": len(proof.get("dependency_paths", [])),
            "scorecard_manifest_required": _to_bool(
                proof.get("scorecard_manifest_required", False)
            ),
            "scorecard_manifest_current": _to_bool(
                proof.get("scorecard_manifest_current", False)
            ),
            "scorecard_manifest_sha256": str(
                proof.get("scorecard_manifest_sha256", "")
            ),
            "scorecard_contract_consistent": _to_bool(
                proof.get("scorecard_contract_consistent", False)
            ),
            "scorecard_non_authorizing": _to_bool(
                proof.get("scorecard_non_authorizing", False)
            ),
            "scorecard_provenance_gate_passed": _to_bool(
                proof.get("scorecard_provenance_gate_passed", False)
            ),
            "research_family_bound": _to_bool(
                proof.get("research_family_bound", False)
            ),
            "research_family_provenance_current": _to_bool(
                proof.get("research_family_provenance_current", False)
            ),
            "research_family_id": str(proof.get("research_family_id", "")),
            "research_family_registration_id": str(
                proof.get("research_family_registration_id", "")
            ),
            "research_family_path": str(
                proof.get("research_family_path", "")
            ),
            "research_family_manifest_sha256": str(
                proof.get("research_family_manifest_sha256", "")
            ),
            "deployment_mode": str(summary_row.get("deployment_mode", "")) if not summary_row.empty else "",
            "allocation_mode": str(summary_row.get("allocation_mode", "")) if not summary_row.empty else "",
            "capital_currency": str(summary_row.get("capital_currency", "")) if not summary_row.empty else "",
            "total_capital": _number(summary_row, "total_capital", fallback=0.0) if not summary_row.empty else 0.0,
            "allocated_weight": _number(summary_row, "allocated_weight", fallback=0.0)
            if not summary_row.empty
            else 0.0,
            "allocated_notional": _number(summary_row, "allocated_notional", fallback=0.0)
            if not summary_row.empty
            else 0.0,
            "min_strategy_count": int(_number(summary_row, "min_strategy_count", fallback=0.0))
            if not summary_row.empty
            else 0,
            "min_market_count": int(_number(summary_row, "min_market_count", fallback=0.0))
            if not summary_row.empty
            else 0,
            "max_strategy_weight": _number(summary_row, "max_strategy_weight", fallback=0.0)
            if not summary_row.empty
            else 0.0,
            "max_market_weight": _number(summary_row, "max_market_weight", fallback=0.0)
            if not summary_row.empty
            else 0.0,
            "allocated_strategy_count": int(
                _number(summary_row, "allocated_strategy_count", fallback=0.0)
            )
            if not summary_row.empty
            else 0,
            "allocated_market_count": int(_number(summary_row, "allocated_market_count", fallback=0.0))
            if not summary_row.empty
            else 0,
            "top_strategy_by_weight": str(summary_row.get("top_strategy_by_weight", ""))
            if not summary_row.empty
            else "",
            "top_market_by_weight": str(summary_row.get("top_market_by_weight", ""))
            if not summary_row.empty
            else "",
            "max_strategy_allocation_weight": _number(
                summary_row,
                "max_strategy_allocation_weight",
                fallback=0.0,
            )
            if not summary_row.empty
            else 0.0,
            "max_market_allocation_weight": _number(
                summary_row,
                "max_market_allocation_weight",
                fallback=0.0,
            )
            if not summary_row.empty
            else 0.0,
            "selected_allocation_provided": not selected.empty,
            "selected_profile": str(selected.get("profile", "")) if not selected.empty else "",
            "selected_strategy": _strategy_key(selected.get("strategy", "")) if not selected.empty else "",
            "selected_market": _identity_key(selected.get("market", "")) if not selected.empty else "",
            "selected_source_eligible": selected_source_eligible,
            "selected_eligible": selected_eligible,
            "selected_allocation_weight": _number(selected, "allocation_weight", fallback=0.0)
            if not selected.empty
            else 0.0,
            "selected_source_allocation_notional": selected_source_notional,
            "selected_allocation_notional": selected_notional,
            "selected_eligibility_reason": selected_reason,
        }
    )


def _select_strategy_portfolio_allocation(
    allocations: pd.DataFrame,
    expected_strategy: str,
    expected_market: str,
) -> pd.Series:
    if allocations is None or allocations.empty or not expected_strategy:
        return pd.Series(dtype=object)
    rows: list[dict[str, object]] = []
    for _, row in allocations.iterrows():
        strategy = _strategy_key(row.get("strategy", ""))
        market = _identity_key(row.get("market", ""))
        if strategy != expected_strategy:
            continue
        if expected_market and market != expected_market:
            continue
        rows.append(row.to_dict())
    if not rows:
        return pd.Series(dtype=object)
    frame = pd.DataFrame(rows)
    frame["_eligible_sort"] = frame["eligible"].map(_to_bool) if "eligible" in frame.columns else False
    frame["_allocation_weight_sort"] = frame.apply(
        lambda row: _number(row, "allocation_weight", fallback=0.0),
        axis=1,
    )
    frame["_allocation_notional_sort"] = frame.apply(
        lambda row: _number(row, "allocation_notional", fallback=0.0),
        axis=1,
    )
    ordered = frame.sort_values(
        ["_eligible_sort", "_allocation_weight_sort", "_allocation_notional_sort"],
        ascending=[False, False, False],
    )
    return ordered.drop(columns=["_eligible_sort", "_allocation_weight_sort", "_allocation_notional_sort"]).iloc[0]


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


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _identity_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _read_summary(path: str | Path, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> pd.DataFrame:
    file_path = _summary_path(path, filename, fallback_dirs=fallback_dirs)
    if not file_path.exists():
        raise FileNotFoundError(f"required scale-up input missing: {file_path}")
    frame = pd.read_csv(file_path)
    if frame.empty:
        raise ValueError(f"required scale-up input is empty: {file_path}")
    return frame


def _read_optional_summary(path: str | Path, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> pd.DataFrame:
    file_path = _summary_path(path, filename, fallback_dirs=fallback_dirs)
    if not file_path.exists():
        return pd.DataFrame()
    return _read_summary(file_path, filename)


def _optional_summary_input(
    path: str | Path | None,
    filename: str,
    *,
    fallback_dirs: tuple[str, ...] = (),
) -> Path | None:
    if path is None:
        return None
    file_path = _summary_path(path, filename, fallback_dirs=fallback_dirs)
    return file_path if file_path.exists() else Path(path)


def _optional_sidecar_input(path: str | Path | None, filename: str) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    file_path = candidate / filename if candidate.is_dir() else candidate.with_name(filename)
    return file_path if file_path.exists() else None


def _optional_vendor_market_data_batch_config(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path)
    base = candidate.parent if candidate.is_file() else candidate
    for folder in (base, base.parent):
        file_path = folder / "vendor_market_data_batch_config.json"
        if file_path.exists():
            return file_path
    return None


def _apply_vendor_market_data_batch_config(config: dict[str, Any], batch_config: dict[str, Any]) -> None:
    comparison = config.setdefault("data_readiness_comparison", {})
    comparison["vendor_market_data_batch"] = _vendor_market_data_batch_summary(batch_config)


def _with_broker_vendor_market_data_batch_config(
    broker_readiness: pd.DataFrame | None,
    broker_readiness_config: dict[str, Any],
) -> pd.DataFrame | None:
    if broker_readiness is None or broker_readiness.empty:
        return broker_readiness
    broker_config = _broker_readiness_config_root(broker_readiness_config)
    row = broker_readiness.iloc[0]
    batch_config = None
    if not any(
        _vendor_market_data_batch_prefix_active(row, prefix)
        for prefix in (
            "broker_dispatch_roundtrip_vendor_market_data_batch",
            "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        )
    ):
        batch_config = _broker_vendor_market_data_batch_config_from_readiness_config(
            broker_config
        )
    vendor_readiness_config = _broker_vendor_data_readiness_config_from_readiness_config(
        broker_config
    )
    lineage_comparison_config = (
        _broker_vendor_market_data_batch_lineage_comparison_from_readiness_config(
            broker_config
        )
    )
    final_lineage_comparison_config = (
        _broker_vendor_final_lineage_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_final_lineage_comparison_config = (
        _broker_vendor_readiness_final_lineage_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_complete_final_lineage_comparison_config = (
        _broker_vendor_readiness_complete_final_lineage_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_extended_complete_final_lineage_comparison_config = (
        _broker_vendor_readiness_extended_complete_final_lineage_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_latest_extended_complete_final_lineage_42_comparison_config = (
        _broker_vendor_readiness_latest_extended_complete_final_lineage_42_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_current_latest_extended_complete_final_lineage_50_comparison_config = (
        _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_reconciled_current_latest_extended_complete_final_lineage_58_comparison_config = (
        _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_comparison_from_readiness_config(
            broker_config
        )
    )
    readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_comparison_config = (
        _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_comparison_from_readiness_config(
            broker_config
        )
    )
    resume_route_configs = _broker_resume_route_readiness_configs_from_readiness_config(
        broker_config
    )
    if (
        batch_config is None
        and vendor_readiness_config is None
        and lineage_comparison_config is None
        and final_lineage_comparison_config is None
        and readiness_final_lineage_comparison_config is None
        and readiness_complete_final_lineage_comparison_config is None
        and readiness_extended_complete_final_lineage_comparison_config is None
        and readiness_latest_extended_complete_final_lineage_42_comparison_config
        is None
        and readiness_current_latest_extended_complete_final_lineage_50_comparison_config
        is None
        and readiness_reconciled_current_latest_extended_complete_final_lineage_58_comparison_config
        is None
        and readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_comparison_config
        is None
        and not resume_route_configs
    ):
        return broker_readiness

    out = broker_readiness.copy()
    index = out.index[0]
    if batch_config is not None:
        for column, value in _broker_vendor_market_data_batch_flat_fields(batch_config).items():
            out.loc[index, column] = value
    if vendor_readiness_config is not None:
        for column, value in _broker_vendor_data_readiness_flat_fields(vendor_readiness_config).items():
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if lineage_comparison_config is not None:
        for column, value in _broker_vendor_market_data_batch_lineage_flat_fields(
            lineage_comparison_config
        ).items():
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if final_lineage_comparison_config is not None:
        for column, value in _broker_vendor_final_lineage_flat_fields(
            final_lineage_comparison_config
        ).items():
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if readiness_final_lineage_comparison_config is not None:
        for column, value in _broker_vendor_readiness_final_lineage_flat_fields(
            readiness_final_lineage_comparison_config
        ).items():
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if readiness_complete_final_lineage_comparison_config is not None:
        for column, value in (
            _broker_vendor_readiness_complete_final_lineage_flat_fields(
                readiness_complete_final_lineage_comparison_config
            ).items()
        ):
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if readiness_extended_complete_final_lineage_comparison_config is not None:
        for column, value in (
            _broker_vendor_readiness_extended_complete_final_lineage_flat_fields(
                readiness_extended_complete_final_lineage_comparison_config
            ).items()
        ):
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if (
        readiness_latest_extended_complete_final_lineage_42_comparison_config
        is not None
    ):
        for column, value in (
            _broker_vendor_readiness_latest_extended_complete_final_lineage_42_flat_fields(
                readiness_latest_extended_complete_final_lineage_42_comparison_config
            ).items()
        ):
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if (
        readiness_current_latest_extended_complete_final_lineage_50_comparison_config
        is not None
    ):
        for column, value in (
            _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_flat_fields(
                readiness_current_latest_extended_complete_final_lineage_50_comparison_config
            ).items()
        ):
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if (
        readiness_reconciled_current_latest_extended_complete_final_lineage_58_comparison_config
        is not None
    ):
        for column, value in (
            _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_flat_fields(
                readiness_reconciled_current_latest_extended_complete_final_lineage_58_comparison_config
            ).items()
        ):
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    if (
        readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_comparison_config
        is not None
    ):
        for column, value in (
            _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_flat_fields(
                readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_comparison_config
            ).items()
        ):
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    for source_prefix, config in resume_route_configs.items():
        for column, value in _broker_resume_route_readiness_flat_fields(config, source_prefix).items():
            if column in out.columns:
                out[column] = out[column].astype("object")
            out.loc[index, column] = value
    return out


def _broker_readiness_config_root(config: dict[str, Any]) -> dict[str, Any]:
    nested = config.get("broker_readiness")
    if isinstance(nested, dict) and nested:
        return nested
    return config


def _broker_vendor_market_data_batch_lineage_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get("vendor_market_data_batch_lineage_comparison")
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_final_lineage_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_final_lineage_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(BROKER_READINESS_FINAL_LINEAGE_COMPARISON_KEY)
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_complete_final_lineage_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        BROKER_READINESS_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_extended_complete_final_lineage_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_COMPARISON_KEY
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_latest_extended_complete_final_lineage_42_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_COMPARISON_KEY
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_COMPARISON_KEY
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_COMPARISON_KEY
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_comparison_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    comparison = dispatch.get(
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_COMPARISON_KEY
    )
    if not isinstance(comparison, dict) or not comparison:
        return None
    return comparison


def _broker_vendor_market_data_batch_lineage_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    return {
        "broker_vendor_market_data_batch_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        "broker_vendor_market_data_batch_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        "vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            comparison.get("current_application_lineage_sha256", "")
        ),
        "broker_vendor_market_data_batch_application_lineage_sha256": _sha256_text(
            comparison.get("broker_application_lineage_sha256", "")
        ),
    }


def _broker_vendor_final_lineage_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = BROKER_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
    }
    for field in BROKER_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_final_lineage_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = BROKER_READINESS_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in BROKER_READINESS_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_complete_final_lineage_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = BROKER_READINESS_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in BROKER_READINESS_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_extended_complete_final_lineage_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in BROKER_READINESS_EXTENDED_COMPLETE_FINAL_LINEAGE_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_latest_extended_complete_final_lineage_42_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_FIELD_PREFIX
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in BROKER_READINESS_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_42_DIGEST_FIELDS:
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_current_latest_extended_complete_final_lineage_50_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in (
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_DIGEST_FIELDS,
        *BROKER_READINESS_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_50_STAGE_FIELDS,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_reconciled_current_latest_extended_complete_final_lineage_58_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in (
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_DIGEST_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_STAGE_FIELDS,
        *BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_CURRENT_STAGE_FIELDS,
        BROKER_READINESS_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_58_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_66_flat_fields(
    comparison: dict[str, Any],
) -> dict[str, object]:
    prefix = (
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_FIELD_PREFIX
    )
    fields: dict[str, object] = {
        f"{prefix}_lineage_match_required": _to_bool(
            comparison.get("required", False)
        ),
        f"{prefix}_lineage_matches": _to_bool(
            comparison.get("matches", False)
        ),
        f"{prefix}_carried_application_lineage_sha256": _sha256_text(
            comparison.get("carried_application_lineage_sha256", "")
        ),
    }
    for field in (
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_DIGEST_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_CURRENT_STAGE_FIELDS,
        *BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_REVIEW_FIELDS,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ACK_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_ROUNDTRIP_REVIEW_FIELD,
        BROKER_READINESS_VERIFIED_RECONCILED_CURRENT_LATEST_EXTENDED_COMPLETE_FINAL_LINEAGE_66_BROKER_READINESS_REVIEW_FIELD,
    ):
        fields[f"{prefix}_{field}"] = _sha256_text(comparison.get(field, ""))
    return fields


def _broker_vendor_data_readiness_config_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    candidates: list[object] = []
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if isinstance(dispatch, dict):
        candidates.append(dispatch.get("broker_vendor_data_readiness"))
    candidates.append(broker_readiness_config.get("broker_vendor_data_readiness"))
    for candidate in candidates:
        if _broker_vendor_data_readiness_config_active(candidate):
            return candidate
    return None


def _broker_vendor_data_readiness_config_active(candidate: object) -> bool:
    if not isinstance(candidate, dict) or not candidate:
        return False
    return bool(
        _to_bool(candidate.get("provided", True))
        or _to_bool(candidate.get("ready", False))
        or _broker_vendor_data_failed_check_count(candidate) > 0
    )


def _broker_vendor_data_readiness_flat_fields(config: dict[str, Any]) -> dict[str, object]:
    return {
        "broker_vendor_data_readiness_provided": _to_bool(config.get("provided", True)),
        "broker_vendor_data_readiness_ready": _to_bool(config.get("ready", False)),
        "broker_vendor_data_readiness_failed_checks": _broker_vendor_data_failed_check_count(config),
    }


def _broker_resume_route_readiness_configs_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    resume_gate = broker_readiness_config.get("resume_gate", {}) or {}
    if not isinstance(resume_gate, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, source_prefix in (
        ("broker_route_readiness", "resume_broker_route_readiness"),
        ("incident_broker_route_readiness", "resume_incident_broker_route_readiness"),
    ):
        candidate = resume_gate.get(key)
        if _broker_resume_route_readiness_config_active(candidate):
            out[source_prefix] = candidate
    return out


def _broker_resume_route_readiness_config_active(candidate: object) -> bool:
    if not isinstance(candidate, dict) or not candidate:
        return False
    return bool(
        _to_bool(candidate.get("required", False))
        or _to_bool(candidate.get("provided", False))
        or _to_bool(candidate.get("ready", False))
        or _identity_key(candidate.get("strategy", ""))
        or _identity_key(candidate.get("market", ""))
        or int(_number_from(candidate, "route_ready_pairs", 0.0)) > 0
        or int(_number_from(candidate, "gap_pairs", 0.0)) > 0
        or _identity_key(candidate.get("recommendation", ""))
        or _to_bool(candidate.get("ops_launch_controls_ready", False))
        or bool(_text(candidate.get("ops_launch_control_failures", "")))
        or int(_number_from(candidate, "ops_broker_roundtrip_portfolio_safe_runs", 0.0)) > 0
        or int(_number_from(candidate, "ops_broker_roundtrip_portfolio_breach_runs", 0.0)) > 0
        or int(_number_from(candidate, "ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)) > 0
        or int(_number_from(candidate, "ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0))
        > 0
    )


def _broker_resume_route_readiness_flat_fields(
    config: dict[str, Any],
    source_prefix: str,
) -> dict[str, object]:
    return {
        f"{source_prefix}_required": _to_bool(config.get("required", False)),
        f"{source_prefix}_provided": _to_bool(config.get("provided", True)),
        f"{source_prefix}_ready": _to_bool(config.get("ready", False)),
        f"{source_prefix}_strategy": _strategy_key(config.get("strategy", "")),
        f"{source_prefix}_market": _identity_key(config.get("market", "")),
        f"{source_prefix}_route_ready_pairs": int(_number_from(config, "route_ready_pairs", 0.0)),
        f"{source_prefix}_gap_pairs": int(_number_from(config, "gap_pairs", 0.0)),
        f"{source_prefix}_recommendation": _text(config.get("recommendation", "")),
        f"{source_prefix}_ops_launch_controls_ready": _to_bool(
            config.get("ops_launch_controls_ready", False)
        ),
        f"{source_prefix}_ops_launch_control_failures": _text(config.get("ops_launch_control_failures", "")),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number_from(config, "ops_broker_roundtrip_portfolio_safe_runs", 0.0)
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number_from(config, "ops_broker_roundtrip_portfolio_breach_runs", 0.0)
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number_from(config, "ops_broker_roundtrip_portfolio_concentration_ok_runs", 0.0)
        ),
        f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number_from(config, "ops_broker_roundtrip_portfolio_concentration_breach_runs", 0.0)
        ),
    }


def _broker_vendor_data_failed_check_count(config: dict[str, Any]) -> int:
    failed_checks = config.get("failed_checks")
    if isinstance(failed_checks, list):
        return len(failed_checks)
    if failed_checks not in (None, ""):
        return int(_number_from(config, "failed_checks", 0.0))
    return int(_number_from(config, "failed_check_count", 0.0))


def _broker_vendor_market_data_batch_config_from_readiness_config(
    broker_readiness_config: dict[str, Any],
) -> dict[str, Any] | None:
    dispatch = broker_readiness_config.get("dispatch_roundtrip", {}) or {}
    if not isinstance(dispatch, dict):
        return None
    for key in (
        "broker_dispatch_roundtrip_vendor_market_data_batch",
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
        "vendor_market_data_batch",
        "roundtrip_vendor_market_data_batch",
    ):
        candidate = dispatch.get(key)
        if _vendor_market_data_batch_config_active(candidate):
            return candidate
    return None


def _vendor_market_data_batch_config_active(candidate: object) -> bool:
    if not isinstance(candidate, dict) or not candidate:
        return False
    datasets = candidate.get("datasets") or []
    return bool(
        _to_bool(candidate.get("provided", False))
        or int(_number_from(candidate, "dataset_count", 0.0)) > 0
        or str(candidate.get("adapter", "")).strip()
        or str(candidate.get("market", "")).strip()
        or str(candidate.get("manifest_run_type", "")).strip()
        or datasets
    )


def _broker_vendor_market_data_batch_flat_fields(batch_config: dict[str, Any]) -> dict[str, object]:
    summary = _vendor_market_data_batch_summary(batch_config)
    comparison = summary["comparison"]
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    return {
        f"{prefix}_provided": _to_bool(batch_config.get("provided", True)),
        f"{prefix}_ready": _to_bool(summary["ready"]),
        f"{prefix}_adapter": _identity_key(summary["adapter"]),
        f"{prefix}_kind": str(summary["kind"]),
        f"{prefix}_manifest_run_type": _identity_key(summary["manifest_run_type"]),
        f"{prefix}_market": _identity_key(summary["market"]),
        f"{prefix}_dataset_count": int(summary["dataset_count"]),
        f"{prefix}_ready_datasets": int(summary["ready_datasets"]),
        f"{prefix}_failed_datasets": int(summary["failed_datasets"]),
        f"{prefix}_ready_rate": summary["ready_rate"],
        f"{prefix}_unique_source_files": int(summary["unique_source_files"]),
        f"{prefix}_unique_header_fingerprints": int(summary["unique_header_fingerprints"]),
        f"{prefix}_source_file_fingerprint_coverage": summary["source_file_fingerprint_coverage"],
        f"{prefix}_min_mapping_coverage": summary["min_mapping_coverage"],
        f"{prefix}_unique_mapping_drafts": int(summary["unique_mapping_drafts"]),
        f"{prefix}_mapping_sources": str(summary["mapping_sources"]),
        f"{prefix}_mapping_source_mode": _identity_key(summary["mapping_source_mode"]),
        f"{prefix}_mapping_application_count": int(summary["mapping_application_count"]),
        f"{prefix}_unique_mapping_applications": int(summary["unique_mapping_applications"]),
        f"{prefix}_target_application_coverage": summary["target_application_coverage"],
        f"{prefix}_application_lineage_consistency_required": _to_bool(
            summary["application_lineage_consistency_required"]
        ),
        f"{prefix}_application_lineage_consistent": _to_bool(
            summary["application_lineage_consistent"]
        ),
        f"{prefix}_application_lineage_sha256": _sha256_text(
            summary["application_lineage_sha256"]
        ),
        f"{prefix}_comparison_accepted": _to_bool(comparison.get("accepted", False)),
        f"{prefix}_comparison_failed_checks": int(_number_from(comparison, "failed_checks", 0.0)),
        f"{prefix}_datasets_json": json.dumps(summary["datasets"], sort_keys=True),
    }


def _vendor_market_data_batch_summary(batch_config: dict[str, Any]) -> dict[str, Any]:
    comparison = batch_config.get("comparison", {}) or {}
    datasets = batch_config.get("datasets") or []
    return {
        "provided": True,
        "ready": _to_bool(batch_config.get("ready", False)),
        "adapter": str(batch_config.get("adapter", "")),
        "kind": str(batch_config.get("kind", "")),
        "manifest_run_type": str(batch_config.get("manifest_run_type", "")),
        "market": str(batch_config.get("market", "")),
        "dataset_count": int(_number_from(batch_config, "dataset_count", 0.0)),
        "ready_datasets": int(_number_from(batch_config, "ready_datasets", 0.0)),
        "failed_datasets": int(_number_from(batch_config, "failed_datasets", 0.0)),
        "ready_rate": _jsonable(_number_from(batch_config, "ready_rate", np.nan)),
        "unique_source_files": int(_number_from(batch_config, "unique_source_files", 0.0)),
        "unique_header_fingerprints": int(_number_from(batch_config, "unique_header_fingerprints", 0.0)),
        "source_file_fingerprint_coverage": _jsonable(
            _number_from(batch_config, "source_file_fingerprint_coverage", 0.0)
        ),
        "min_mapping_coverage": _jsonable(_number_from(batch_config, "min_mapping_coverage", 0.0)),
        "unique_mapping_drafts": int(_number_from(batch_config, "unique_mapping_drafts", 0.0)),
        "mapping_sources": str(batch_config.get("mapping_sources", "")),
        "mapping_source_mode": str(batch_config.get("mapping_source_mode", "")),
        "mapping_application_count": int(
            _number_from(batch_config, "mapping_application_count", 0.0)
        ),
        "unique_mapping_applications": int(
            _number_from(batch_config, "unique_mapping_applications", 0.0)
        ),
        "target_application_coverage": _jsonable(
            _number_from(batch_config, "target_application_coverage", 0.0)
        ),
        "application_lineage_consistency_required": _to_bool(
            batch_config.get("application_lineage_consistency_required", False)
        ),
        "application_lineage_consistent": _to_bool(
            batch_config.get("application_lineage_consistent", False)
        ),
        "application_lineage_sha256": _sha256_text(
            batch_config.get("application_lineage_sha256", "")
        ),
        "comparison": {
            "accepted": _to_bool(comparison.get("accepted", False)),
            "ready_rate": _jsonable(_number_from(comparison, "ready_rate", np.nan)),
            "failed_checks": int(_number_from(comparison, "failed_checks", 0.0)),
        },
        "datasets": [
            {
                "dataset": str(item.get("dataset", "")),
                "ready": _to_bool(item.get("ready", False)),
                "source_file_sha256": str(item.get("source_file_sha256", "")),
                "source_header_sha256": str(item.get("source_header_sha256", "")),
                "mapping_draft_sha256": str(item.get("mapping_draft_sha256", "")),
                "mapping_source": str(item.get("mapping_source", "")),
                "mapping_application_path": str(item.get("mapping_application_path", "")),
                "mapping_application_id": str(item.get("mapping_application_id", "")),
                "mapping_application_sha256": str(item.get("mapping_application_sha256", "")),
                "mapping_scope_review_id": str(item.get("mapping_scope_review_id", "")),
                "mapping_scope_review_sha256": str(item.get("mapping_scope_review_sha256", "")),
                "target_intake_receipt_id": str(item.get("target_intake_receipt_id", "")),
                "applied_mapping_sha256": str(item.get("applied_mapping_sha256", "")),
            }
            for item in datasets
        ],
    }


def _launch_pipeline_summary_path(path: str | Path) -> Path | None:
    candidate = Path(path)
    if candidate.is_file():
        return candidate if candidate.name in {filename for _, filename in LAUNCH_PIPELINE_SUMMARIES} else None

    found: list[Path] = []
    for _, filename in LAUNCH_PIPELINE_SUMMARIES:
        file_path = _summary_path(path, filename)
        if file_path.exists():
            found.append(file_path)
    if len(found) > 1:
        files = ", ".join(file.name for file in found)
        raise ValueError(f"multiple launch pipeline summaries found: {files}")
    return found[0] if found else None


def _read_launch_pipeline_summary(path: str | Path) -> tuple[str, str, pd.DataFrame] | None:
    candidate = Path(path)
    if candidate.is_file():
        for family, filename in LAUNCH_PIPELINE_SUMMARIES:
            if candidate.name == filename:
                return family, filename, _read_summary(candidate, filename)
        return None

    found: list[tuple[str, str, pd.DataFrame]] = []
    for family, filename in LAUNCH_PIPELINE_SUMMARIES:
        file_path = _summary_path(path, filename)
        if file_path.exists():
            found.append((family, filename, _read_summary(file_path, filename)))
    if len(found) > 1:
        files = ", ".join(filename for _, filename, _ in found)
        raise ValueError(f"multiple launch pipeline summaries found: {files}")
    return found[0] if found else None


def _with_launch_pipeline_identity(
    launch: pd.DataFrame,
    launch_pipeline: tuple[str, str, pd.DataFrame] | None,
) -> pd.DataFrame:
    out = launch.copy()
    out["launch_pipeline_provided"] = False
    out["launch_pipeline_family"] = ""
    out["launch_pipeline_summary_file"] = ""
    out["launch_pipeline_ready"] = False
    out["launch_pipeline_strategy"] = ""
    out["launch_pipeline_market"] = ""
    out["launch_pipeline_expected_strategy"] = ""
    out["launch_pipeline_expected_market"] = ""
    out["launch_pipeline_failed_components"] = 0
    out["launch_pipeline_skipped_components"] = 0
    if launch_pipeline is None:
        out["surface_launch_pipeline_provided"] = False
        out["surface_launch_pipeline_ready"] = False
        out["surface_launch_strategy"] = ""
        out["surface_launch_market"] = ""
        out["surface_launch_expected_strategy"] = ""
        out["surface_launch_expected_market"] = ""
        out["surface_launch_failed_components"] = 0
        out["surface_launch_skipped_components"] = 0
        return out
    family, filename, summary = launch_pipeline
    row = summary.iloc[0]
    out["launch_pipeline_provided"] = True
    out["launch_pipeline_family"] = family
    out["launch_pipeline_summary_file"] = filename
    out["launch_pipeline_ready"] = _to_bool(row.get("ready", False))
    out["launch_pipeline_strategy"] = _strategy_key(row.get("strategy", ""))
    out["launch_pipeline_market"] = _identity_key(row.get("market", ""))
    out["launch_pipeline_expected_strategy"] = _strategy_key(row.get("expected_strategy", ""))
    out["launch_pipeline_expected_market"] = _identity_key(row.get("expected_market", ""))
    out["launch_pipeline_failed_components"] = int(_number(row, "failed_components", fallback=0.0))
    out["launch_pipeline_skipped_components"] = int(_number(row, "skipped_components", fallback=0.0))
    out["surface_launch_pipeline_provided"] = family == "surface_mm"
    out["surface_launch_pipeline_ready"] = _to_bool(row.get("ready", False)) if family == "surface_mm" else False
    out["surface_launch_strategy"] = _strategy_key(row.get("strategy", "")) if family == "surface_mm" else ""
    out["surface_launch_market"] = _identity_key(row.get("market", "")) if family == "surface_mm" else ""
    out["surface_launch_expected_strategy"] = (
        _strategy_key(row.get("expected_strategy", "")) if family == "surface_mm" else ""
    )
    out["surface_launch_expected_market"] = (
        _identity_key(row.get("expected_market", "")) if family == "surface_mm" else ""
    )
    out["surface_launch_failed_components"] = (
        int(_number(row, "failed_components", fallback=0.0)) if family == "surface_mm" else 0
    )
    out["surface_launch_skipped_components"] = (
        int(_number(row, "skipped_components", fallback=0.0)) if family == "surface_mm" else 0
    )
    return out


def _broker_readiness_from_launch_pipeline_summary(
    launch_pipeline: tuple[str, str, pd.DataFrame] | None,
) -> pd.DataFrame | None:
    if launch_pipeline is None:
        return None
    _, _, summary = launch_pipeline
    if summary.empty:
        return None
    row = summary.iloc[0]
    if not _launch_pipeline_broker_readiness_active(row):
        return None
    route_ready = _to_bool(row.get("broker_readiness_route_readiness_ready", False))
    route_broker_ready = _to_bool(row.get("broker_readiness_route_broker_route_readiness_ready", False))
    launch_controls_ready = _to_bool(
        row.get(
            "broker_readiness_route_broker_route_readiness_ops_launch_controls_ready",
            row.get("broker_readiness_route_readiness_ops_launch_controls_present", False),
        )
    )
    return pd.DataFrame(
        [
            {
                "ready": _to_bool(row.get("broker_readiness_ready", route_ready or route_broker_ready)),
                "adapter_schema_status": "",
                "schema_reviewed": False,
                "schema_review_mode": "",
                "recommendation": "launch_pipeline_broker_route_proof",
                "route_readiness_required": route_ready or route_broker_ready,
                "route_readiness_provided": route_ready or route_broker_ready,
                "route_readiness_ready": route_ready,
                "route_readiness_strategy": _strategy_key(
                    row.get(
                        "broker_readiness_route_readiness_strategy",
                        row.get("broker_readiness_route_broker_route_readiness_strategy", ""),
                    )
                ),
                "route_readiness_market": _identity_key(
                    row.get(
                        "broker_readiness_route_readiness_market",
                        row.get("broker_readiness_route_broker_route_readiness_market", ""),
                    )
                ),
                "route_readiness_route_ready_pairs": 0,
                "route_readiness_gap_pairs": int(
                    _number(row, "broker_readiness_route_readiness_gap_pairs", fallback=0.0)
                ),
                "route_readiness_recommendation": "",
                "route_readiness_ops_launch_controls_present": _to_bool(
                    row.get("broker_readiness_route_readiness_ops_launch_controls_present", False)
                ),
                "route_readiness_ops_launch_controls_blocked_pairs": int(
                    _number(
                        row,
                        "broker_readiness_route_readiness_ops_launch_controls_blocked_pairs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": int(
                    _number(
                        row,
                        "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_"
                            "concentration_breach_pairs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_breach_pairs": int(
                    _number(
                        row,
                        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_breach_pairs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs": int(
                    _number(
                        row,
                        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_"
                            "launch_control_breach_pairs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs": int(
                    _number(
                        row,
                        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_"
                            "concentration_breach_pairs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_launch_controls_ready": launch_controls_ready,
                "route_readiness_ops_launch_control_failures": "",
                "route_readiness_ops_broker_roundtrip_portfolio_safe_runs": int(
                    _number(
                        row,
                        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_runs": int(
                    _number(
                        row,
                        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                            "concentration_ok_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                            "concentration_breach_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_ready_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_"
                            "resume_route_ready_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_breach_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_"
                            "resume_route_breach_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_"
                            "resume_route_gap_breach_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_"
                            "resume_route_launch_control_breach_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_"
                            "resume_route_portfolio_breach_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs": int(
                    _number(
                        row,
                        (
                            "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_"
                            "resume_route_concentration_breach_runs"
                        ),
                        fallback=0.0,
                    )
                ),
                "broker_vendor_data_readiness_provided": False,
                "broker_vendor_data_readiness_ready": False,
                "broker_vendor_data_readiness_failed_checks": 0,
                **_launch_pipeline_resume_route_readiness_fields(
                    row,
                    source_prefix="broker_readiness_resume_broker_route_readiness",
                    output_prefix="resume_broker_route_readiness",
                ),
                **_launch_pipeline_resume_route_readiness_fields(
                    row,
                    source_prefix="broker_readiness_resume_incident_broker_route_readiness",
                    output_prefix="resume_incident_broker_route_readiness",
                ),
            }
        ]
    )


def _launch_pipeline_resume_route_readiness_fields(
    row: pd.Series,
    *,
    source_prefix: str,
    output_prefix: str,
) -> dict[str, object]:
    return {
        f"{output_prefix}_required": _to_bool(row.get(f"{source_prefix}_required", False)),
        f"{output_prefix}_provided": _to_bool(row.get(f"{source_prefix}_provided", False)),
        f"{output_prefix}_ready": _to_bool(row.get(f"{source_prefix}_ready", False)),
        f"{output_prefix}_strategy": _strategy_key(row.get(f"{source_prefix}_strategy", "")),
        f"{output_prefix}_market": _identity_key(row.get(f"{source_prefix}_market", "")),
        f"{output_prefix}_route_ready_pairs": int(
            _number(row, f"{source_prefix}_route_ready_pairs", fallback=0.0)
        ),
        f"{output_prefix}_gap_pairs": int(_number(row, f"{source_prefix}_gap_pairs", fallback=0.0)),
        f"{output_prefix}_recommendation": _text(row.get(f"{source_prefix}_recommendation", "")),
        f"{output_prefix}_ops_launch_controls_ready": _to_bool(
            row.get(f"{source_prefix}_ops_launch_controls_ready", False)
        ),
        f"{output_prefix}_ops_launch_control_failures": _text(
            row.get(f"{source_prefix}_ops_launch_control_failures", "")
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_safe_runs": int(
            _number(row, f"{source_prefix}_ops_broker_roundtrip_portfolio_safe_runs", fallback=0.0)
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_breach_runs": int(
            _number(row, f"{source_prefix}_ops_broker_roundtrip_portfolio_breach_runs", fallback=0.0)
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": int(
            _number(
                row,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs",
                fallback=0.0,
            )
        ),
        f"{output_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": int(
            _number(
                row,
                f"{source_prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs",
                fallback=0.0,
            )
        ),
    }


def _launch_pipeline_broker_readiness_active(row: pd.Series) -> bool:
    return bool(
        _to_bool(row.get("broker_readiness_provided", False))
        or _to_bool(row.get("broker_readiness_ready", False))
        or _to_bool(row.get("broker_readiness_route_readiness_ready", False))
        or _to_bool(row.get("broker_readiness_route_broker_route_readiness_ready", False))
        or _to_bool(row.get("broker_readiness_route_readiness_ops_launch_controls_present", False))
        or _to_bool(
            row.get("broker_readiness_route_broker_route_readiness_ops_launch_controls_ready", False)
        )
        or _to_bool(row.get("broker_readiness_resume_broker_route_readiness_ready", False))
        or _to_bool(row.get("broker_readiness_resume_incident_broker_route_readiness_ready", False))
        or _to_bool(
            row.get("broker_readiness_resume_broker_route_readiness_ops_launch_controls_ready", False)
        )
        or _to_bool(
            row.get("broker_readiness_resume_incident_broker_route_readiness_ops_launch_controls_ready", False)
        )
        or int(
            _number(
                row,
                "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                fallback=0.0,
            )
        )
        > 0
        or any(
            int(_number(row, f"broker_readiness_route_readiness_{field}", fallback=0.0)) > 0
            for field in ROUTE_READINESS_RESUME_ROUTE_BREACH_PAIR_FIELDS
        )
        or any(
            int(
                _number(
                    row,
                    f"broker_readiness_route_broker_route_readiness_{field}",
                    fallback=0.0,
                )
            )
            > 0
            for field in BROKER_ROUTE_READINESS_RESUME_ROUTE_RUN_FIELDS
        )
        or int(
            _number(
                row,
                "broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
                fallback=0.0,
            )
        )
        > 0
        or int(
            _number(
                row,
                (
                    "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_"
                    "safe_runs"
                ),
                fallback=0.0,
            )
        )
        > 0
    )


def _summary_path(path: str | Path, filename: str, *, fallback_dirs: tuple[str, ...] = ()) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        direct = candidate / filename
        if direct.exists():
            return direct
        for folder in fallback_dirs:
            nested = candidate / folder / filename
            if nested.exists():
                return nested
        return direct
    return candidate


def _auto_broker_readiness_dir(launch_dir: str | Path) -> Path | None:
    candidate = Path(launch_dir)
    if not candidate.is_dir():
        return None
    for folder in ("06_broker_readiness", "05_broker_readiness"):
        broker_dir = candidate / folder
        if (broker_dir / "broker_readiness_summary.csv").exists():
            return broker_dir
    return None


def _validate_thresholds(thresholds: ScaleUpThresholds) -> None:
    if thresholds.target_mode not in {"paper", "shadow", "live_dryrun"}:
        raise ValueError("target_mode must be paper, shadow, or live_dryrun")
    if thresholds.max_scale_multiplier <= 0:
        raise ValueError("max_scale_multiplier must be positive")
    if thresholds.min_shadow_sessions <= 0:
        raise ValueError("min_shadow_sessions must be positive")
    for name in ("min_shadow_acceptance_rate", "min_median_order_fill_rate"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if thresholds.min_worst_order_fill_rate is not None and not 0 <= thresholds.min_worst_order_fill_rate <= 1:
        raise ValueError("min_worst_order_fill_rate must be between 0 and 1")
    if not 0 <= thresholds.min_instrument_parse_coverage <= 1:
        raise ValueError("min_instrument_parse_coverage must be between 0 and 1")
    for name in (
        "max_total_failed_component_checks",
        "max_total_unmatched_fills",
        "max_total_mismatched_orders",
        "max_total_overfilled_orders",
        "max_lifecycle_orders",
        "max_replace_orders",
    ):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    for name in (
        "max_telemetry_age_ns",
        "max_open_order_count",
        "max_open_order_qty",
        "max_open_order_notional",
        "max_open_order_age_ns",
        "max_gross_position_qty",
        "max_abs_net_position_qty",
        "max_orders_per_session",
        "max_session_notional",
        "max_gross_notional",
        "max_abs_net_delta",
        "max_abs_net_vega",
        "stop_loss",
    ):
        value = getattr(thresholds, name)
        if value is not None and value <= 0:
            raise ValueError(f"{name} must be positive")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


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


def _number(row: pd.Series, column: str, fallback: float = np.nan) -> float:
    value = row.get(column, fallback)
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _number_from(mapping: dict[str, Any], key: str, fallback: float = np.nan) -> float:
    value = mapping.get(key, fallback)
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return float(fallback)
    return float(parsed)


def _to_bool(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _jsonable(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
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
