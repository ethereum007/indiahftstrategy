import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from hft_cli import main
from reports.data_readiness_comparison import write_data_readiness_comparison
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.operational_lineage import (
    BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
    BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
    BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
    BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
    BROKER_READINESS_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELD_MAP,
    BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP,
    BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP,
    BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP,
)
from reports.proof import ProofThresholds, write_proof_report
from reports.proof_refresh import (
    ProofRefreshThresholds,
    write_proof_refresh_report,
)
from reports.scaleup import ScaleUpThresholds, evaluate_scaleup_plan, write_scaleup_plan
from reports.scaleup_runtime_provenance import (
    load_scaleup_runtime_provenance,
    scaleup_runtime_fields,
    scaleup_runtime_manifest_extra,
)
from tests.data_readiness_helpers import (
    reseal_experiment_manifest,
    write_manifest_bound_data_readiness,
)


def path_tail(value):
    return str(value).replace("\\", "/")


def leadlag_lineage(*, ready=True):
    if not ready:
        return {
            "leadlag_edge_lineage_ready": False,
            "leadlag_lineage_bound_stages": 0,
            "leadlag_lineage_required_stages": 0,
            "leadlag_lineage_selected_stage_count": 0,
            "leadlag_lineage_selected_run_dirs": "",
            "leadlag_measurement_manifest_sha256": "",
            "leadlag_edge_candidate_manifest_sha256": "",
            "leadlag_edge_latency_budget_ns": 0.0,
            "leadlag_total_replay_latency_ns": 0.0,
            "leadlag_edge_latency_headroom_ns": 0.0,
            "leadlag_edge_lineage_contract_version": "",
            "leadlag_edge_lineage_contract_sha256": "",
        }
    return {
        "leadlag_edge_lineage_ready": True,
        "leadlag_lineage_bound_stages": 5,
        "leadlag_lineage_required_stages": 5,
        "leadlag_lineage_selected_stage_count": 5,
        "leadlag_lineage_selected_run_dirs": ";".join(
            [
                "runs/leadlag_edge_audit",
                "runs/leadlag_replay_walkforward",
                "runs/promotion_report",
                "runs/leadlag_order_plan",
                "runs/leadlag_launch_pipeline",
            ]
        ),
        "leadlag_measurement_manifest_sha256": "a" * 64,
        "leadlag_edge_candidate_manifest_sha256": "b" * 64,
        "leadlag_edge_latency_budget_ns": 100_000.0,
        "leadlag_total_replay_latency_ns": 50_000.0,
        "leadlag_edge_latency_headroom_ns": 50_000.0,
        "leadlag_edge_lineage_contract_version": "leadlag_edge_lineage/v1",
        "leadlag_edge_lineage_contract_sha256": "c" * 64,
    }


LEADLAG_LINEAGE_FIELDS = tuple(leadlag_lineage(ready=False))


def target_application_lineage_sha256(datasets):
    identity_fields = (
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
    identities = [
        {field: str(dataset.get(field, "")) for field in identity_fields}
        for dataset in datasets
    ]
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


def target_application_lineage_comparison(vendor, **overrides):
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    comparison = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": lineage_sha256,
        "broker_application_lineage_sha256": lineage_sha256,
        "scaleup_carried_application_lineage_sha256": lineage_sha256,
        "cutover_carried_application_lineage_sha256": lineage_sha256,
        "route_carried_application_lineage_sha256": lineage_sha256,
        "dispatch_carried_application_lineage_sha256": lineage_sha256,
        "send_carried_application_lineage_sha256": lineage_sha256,
        "ack_carried_application_lineage_sha256": lineage_sha256,
        "roundtrip_carried_application_lineage_sha256": lineage_sha256,
        "readiness_carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def broker_readiness_final_target_application_lineage_comparison(
    vendor,
    **overrides,
):
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    comparison = target_application_lineage_comparison(vendor)
    comparison.update(
        {
            "scaleup_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_review_carried_application_lineage_sha256": lineage_sha256,
            "route_enable_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_plan_review_carried_application_lineage_sha256": lineage_sha256,
            "send_packet_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_reconciliation_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_complete_final_target_application_lineage_comparison(
    vendor,
    **overrides,
):
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    comparison = broker_readiness_final_target_application_lineage_comparison(
        vendor
    )
    comparison.update(
        {
            "broker_readiness_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_34_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_complete_final_target_application_lineage_comparison(
        vendor
    )
    for field in tuple(comparison):
        if field.endswith("_sha256"):
            comparison[field] = lineage_sha256
    comparison.update(
        {
            "scaleup_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_42_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_34_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_50_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_34_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "route_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_58_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_50_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_view_59_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_58_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_66_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_58_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.pop(
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
        None,
    )
    comparison.update(
        {
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_74_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_66_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_view_67_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = broker_readiness_view_66_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_view_75_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    scaleup_lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    scaleup_lineage_sha256 = scaleup_lineage_sha256 or lineage_sha256
    comparison = broker_readiness_view_74_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": scaleup_lineage_sha256,
            "carried_application_lineage_sha256": scaleup_lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def evidence_summary(ready=True, strategy="lead_lag_taker", market="india_nse_index_derivatives"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": strategy,
                "market": market,
                "failed_checks": 0 if ready else 1,
                "recommendation": "eligible_for_shadow_scaleup_review" if ready else "evidence_incomplete",
            }
        ]
    )


def shadow_summary(
    accepted=True,
    proof_refresh_sessions=0,
    proof_refresh_ready_sessions=None,
    proof_refresh_strategy="",
    proof_refresh_market="",
    proof_refresh_mixed_identity_sessions=0,
    broker_readiness_sessions=0,
    broker_readiness_ready_sessions=None,
    broker_vendor_data_readiness_sessions=0,
    broker_vendor_data_readiness_provided_sessions=None,
    broker_vendor_data_readiness_ready_sessions=None,
    max_broker_vendor_data_readiness_failed_checks=0,
    broker_adapter="",
    broker_adapter_count=0,
    missing_broker_adapter_sessions=0,
    broker_route_readiness_sessions=0,
    broker_route_readiness_required_sessions=None,
    broker_route_readiness_provided_sessions=None,
    broker_route_readiness_ready_sessions=None,
    broker_route_readiness_strategy="",
    broker_route_readiness_market="",
    max_broker_route_readiness_gap_pairs=0,
    broker_dispatch_roundtrip_sessions=0,
    broker_dispatch_roundtrip_ready_sessions=None,
    broker_dispatch_roundtrip_strategy="",
    broker_dispatch_roundtrip_market="",
    broker_dispatch_roundtrip_scenario_count=0,
    missing_broker_dispatch_roundtrip_scenario_sessions=0,
    max_broker_dispatch_roundtrip_missing_request_acks=0,
    max_broker_dispatch_roundtrip_rejected_orders=0,
    max_broker_dispatch_roundtrip_unmatched_acks=0,
    broker_route_dispatch_roundtrip_sessions=0,
    broker_route_dispatch_roundtrip_ready_sessions=None,
    broker_route_dispatch_roundtrip_strategy="",
    broker_route_dispatch_roundtrip_market="",
    broker_route_dispatch_roundtrip_scenario_count=0,
    missing_broker_route_dispatch_roundtrip_scenario_sessions=0,
):
    if proof_refresh_ready_sessions is None:
        proof_refresh_ready_sessions = proof_refresh_sessions
    if broker_readiness_ready_sessions is None:
        broker_readiness_ready_sessions = broker_readiness_sessions
    if broker_vendor_data_readiness_provided_sessions is None:
        broker_vendor_data_readiness_provided_sessions = broker_vendor_data_readiness_sessions
    if broker_vendor_data_readiness_ready_sessions is None:
        broker_vendor_data_readiness_ready_sessions = broker_vendor_data_readiness_sessions
    if broker_route_readiness_required_sessions is None:
        broker_route_readiness_required_sessions = broker_route_readiness_sessions
    if broker_route_readiness_provided_sessions is None:
        broker_route_readiness_provided_sessions = broker_route_readiness_sessions
    if broker_route_readiness_ready_sessions is None:
        broker_route_readiness_ready_sessions = broker_route_readiness_sessions
    if broker_dispatch_roundtrip_ready_sessions is None:
        broker_dispatch_roundtrip_ready_sessions = broker_dispatch_roundtrip_sessions
    if broker_route_dispatch_roundtrip_ready_sessions is None:
        broker_route_dispatch_roundtrip_ready_sessions = broker_route_dispatch_roundtrip_sessions
    return pd.DataFrame(
        [
            {
                "accepted": accepted,
                "session_count": 2,
                "accepted_sessions": 2 if accepted else 1,
                "acceptance_rate": 1.0 if accepted else 0.5,
                "scenario_count": 1,
                "scenario_key": "trigger_ticks=2",
                "median_order_fill_rate": 0.95,
                "worst_order_fill_rate": 0.9,
                "total_failed_component_checks": 0 if accepted else 1,
                "total_unmatched_fills": 0,
                "total_mismatched_orders": 0,
                "total_overfilled_orders": 0,
                "worst_adverse_slippage": 0.04,
                "runtime_proof_refresh_sessions": proof_refresh_sessions,
                "runtime_proof_refresh_ready_sessions": proof_refresh_ready_sessions,
                "runtime_proof_refresh_mixed_identity_sessions": proof_refresh_mixed_identity_sessions,
                "proof_refresh_strategy": proof_refresh_strategy,
                "proof_refresh_market": proof_refresh_market,
                "broker_readiness_sessions": broker_readiness_sessions,
                "broker_readiness_ready_sessions": broker_readiness_ready_sessions,
                "broker_vendor_data_readiness_sessions": broker_vendor_data_readiness_sessions,
                "broker_vendor_data_readiness_provided_sessions": (
                    broker_vendor_data_readiness_provided_sessions
                ),
                "broker_vendor_data_readiness_ready_sessions": broker_vendor_data_readiness_ready_sessions,
                "max_broker_vendor_data_readiness_failed_checks": (
                    max_broker_vendor_data_readiness_failed_checks
                ),
                "broker_adapter": broker_adapter,
                "broker_adapter_count": broker_adapter_count,
                "missing_broker_adapter_sessions": missing_broker_adapter_sessions,
                "broker_route_readiness_sessions": broker_route_readiness_sessions,
                "broker_route_readiness_required_sessions": broker_route_readiness_required_sessions,
                "broker_route_readiness_provided_sessions": broker_route_readiness_provided_sessions,
                "broker_route_readiness_ready_sessions": broker_route_readiness_ready_sessions,
                "broker_route_readiness_strategy": broker_route_readiness_strategy,
                "broker_route_readiness_market": broker_route_readiness_market,
                "max_broker_route_readiness_gap_pairs": max_broker_route_readiness_gap_pairs,
                "broker_dispatch_roundtrip_sessions": broker_dispatch_roundtrip_sessions,
                "broker_dispatch_roundtrip_ready_sessions": broker_dispatch_roundtrip_ready_sessions,
                "broker_dispatch_roundtrip_strategy": broker_dispatch_roundtrip_strategy,
                "broker_dispatch_roundtrip_market": broker_dispatch_roundtrip_market,
                "broker_dispatch_roundtrip_scenario_count": broker_dispatch_roundtrip_scenario_count,
                "missing_broker_dispatch_roundtrip_scenario_sessions": (
                    missing_broker_dispatch_roundtrip_scenario_sessions
                ),
                "max_broker_dispatch_roundtrip_missing_request_acks": (
                    max_broker_dispatch_roundtrip_missing_request_acks
                ),
                "max_broker_dispatch_roundtrip_rejected_orders": max_broker_dispatch_roundtrip_rejected_orders,
                "max_broker_dispatch_roundtrip_unmatched_acks": max_broker_dispatch_roundtrip_unmatched_acks,
                "broker_route_dispatch_roundtrip_sessions": broker_route_dispatch_roundtrip_sessions,
                "broker_route_dispatch_roundtrip_ready_sessions": (
                    broker_route_dispatch_roundtrip_ready_sessions
                ),
                "broker_route_dispatch_roundtrip_strategy": broker_route_dispatch_roundtrip_strategy,
                "broker_route_dispatch_roundtrip_market": broker_route_dispatch_roundtrip_market,
                "broker_route_dispatch_roundtrip_scenario_count": broker_route_dispatch_roundtrip_scenario_count,
                "missing_broker_route_dispatch_roundtrip_scenario_sessions": (
                    missing_broker_route_dispatch_roundtrip_scenario_sessions
                ),
            }
        ]
    )


def launch_summary(ready=True, adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "mode": "shadow",
                "adapter": adapter,
                "scenario_key": "trigger_ticks=2",
                "accepted_orders": 2,
                "rejected_orders": 0,
                "acceptance_rate": 1.0,
                "total_notional": 1500.0,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def exposure_summary(passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "orders": 2,
                "gross_notional": 1500.0,
                "net_delta": 50.0,
                "net_vega": 200.0,
            }
        ]
    )


def proof_refresh_summary(
    ready=True,
    proof_source="latest",
    strategy="leadlag",
    market="india_nse_index_derivatives",
    mixed_identity=False,
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "drift_passed": proof_source == "baseline",
                "fresh_proof_required": proof_source != "baseline",
                "proof_source": proof_source if ready else "none",
                "strategy": strategy,
                "market": market,
                "mixed_identity": mixed_identity,
                "failed_checks": 0 if ready else 1,
                "recommendation": "use_latest_calibrated_proof" if ready else "rerun_calibrated_proof_before_promotion",
            }
        ]
    )


def instrument_metadata_summary(passed=True, parse_coverage=1.0, unparsed_instruments=0):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "instruments": 2,
                "parsed_instruments": 2 - unparsed_instruments,
                "unparsed_instruments": unparsed_instruments,
                "parse_coverage": parse_coverage,
                "min_parse_coverage": 1.0,
                "symbol_formats": "nse_compact_option:1|occ_option:1",
            }
        ]
    )


def broker_readiness_summary(
    ready=True,
    adapter="arrow_money",
    runtime_session_provided=False,
    runtime_session_ready=False,
    runtime_guard_action="",
    runtime_guard_halted=False,
    runtime_target_mode="shadow",
    runtime_strategy="lead_lag_taker",
    runtime_market="india_nse_index_derivatives",
    resume_gate_provided=False,
    resume_gate_ready=False,
    resume_strategy="lead_lag_taker",
    resume_market="india_nse_index_derivatives",
    resume_incident_strategy="lead_lag_taker",
    resume_incident_market="india_nse_index_derivatives",
    resume_proof_refresh_ready=False,
    resume_proof_refresh_strategy="lead_lag_taker",
    resume_proof_refresh_market="india_nse_index_derivatives",
    resume_broker_route_readiness_required=False,
    resume_broker_route_readiness_provided=False,
    resume_broker_route_readiness_ready=False,
    resume_broker_route_readiness_strategy="lead_lag_taker",
    resume_broker_route_readiness_market="india_nse_index_derivatives",
    resume_broker_route_readiness_route_ready_pairs=0,
    resume_broker_route_readiness_gap_pairs=0,
    resume_broker_route_readiness_recommendation="",
    resume_broker_route_readiness_ops_launch_controls_ready=False,
    resume_broker_route_readiness_ops_launch_control_failures="",
    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    resume_incident_broker_route_readiness_required=False,
    resume_incident_broker_route_readiness_provided=False,
    resume_incident_broker_route_readiness_ready=False,
    resume_incident_broker_route_readiness_strategy="lead_lag_taker",
    resume_incident_broker_route_readiness_market="india_nse_index_derivatives",
    resume_incident_broker_route_readiness_route_ready_pairs=0,
    resume_incident_broker_route_readiness_gap_pairs=0,
    resume_incident_broker_route_readiness_recommendation="",
    resume_incident_broker_route_readiness_ops_launch_controls_ready=False,
    resume_incident_broker_route_readiness_ops_launch_control_failures="",
    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    dispatch_roundtrip_provided=False,
    dispatch_roundtrip_ready=False,
    dispatch_roundtrip_target_mode="live_dryrun",
    dispatch_roundtrip_strategy="lead_lag_taker",
    dispatch_roundtrip_market="india_nse_index_derivatives",
    dispatch_roundtrip_scenario_key="trigger_ticks=2",
    dispatch_roundtrip_batch_id="BDP-1",
    dispatch_roundtrip_requests=2,
    dispatch_roundtrip_acked_orders=2,
    dispatch_roundtrip_missing_request_acks=0,
    dispatch_roundtrip_rejected_orders=0,
    dispatch_roundtrip_unmatched_acks=0,
    dispatch_roundtrip_failed_checks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_dispatch_roundtrip_required=None,
    route_dispatch_roundtrip_provided=None,
    route_dispatch_roundtrip_ready=None,
    route_dispatch_roundtrip_target_mode=None,
    route_dispatch_roundtrip_strategy=None,
    route_dispatch_roundtrip_market=None,
    route_dispatch_roundtrip_scenario_key=None,
    route_dispatch_roundtrip_batch_id="BDP-0",
    route_dispatch_roundtrip_requests=None,
    route_dispatch_roundtrip_acked_orders=None,
    route_dispatch_roundtrip_missing_request_acks=None,
    route_dispatch_roundtrip_rejected_orders=None,
    route_dispatch_roundtrip_unmatched_acks=None,
    route_readiness_required=False,
    route_readiness_provided=False,
    route_readiness_ready=False,
    route_readiness_strategy="",
    route_readiness_market="",
    route_readiness_route_ready_pairs=0,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation="",
    route_readiness_ops_launch_controls_ready=False,
    route_readiness_ops_launch_control_failures="",
    route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
    route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    route_readiness_ops_broker_roundtrip_resume_route_ready_runs=0,
    route_readiness_ops_broker_roundtrip_resume_route_breach_runs=0,
    route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs=0,
    route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs=0,
    route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs=0,
    route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs=0,
    shadow_broker_readiness_provided=False,
    shadow_broker_readiness_sessions=0,
    shadow_broker_readiness_ready_sessions=None,
    shadow_broker_vendor_data_readiness_sessions=0,
    shadow_broker_vendor_data_readiness_provided_sessions=None,
    shadow_broker_vendor_data_readiness_ready_sessions=None,
    shadow_broker_vendor_data_readiness_failed_checks=0,
    shadow_broker_adapter="",
    shadow_broker_adapter_count=0,
    shadow_broker_route_readiness_sessions=0,
    shadow_broker_route_readiness_ready_sessions=None,
    shadow_broker_route_readiness_strategy="",
    shadow_broker_route_readiness_market="",
    shadow_broker_route_readiness_gap_pairs=0,
    shadow_broker_dispatch_roundtrip_sessions=0,
    shadow_broker_dispatch_roundtrip_ready_sessions=None,
    shadow_broker_dispatch_roundtrip_strategy="",
    shadow_broker_dispatch_roundtrip_market="",
    shadow_broker_dispatch_roundtrip_scenario_count=0,
    shadow_broker_dispatch_roundtrip_missing_request_acks=0,
    shadow_broker_dispatch_roundtrip_rejected_orders=0,
    shadow_broker_dispatch_roundtrip_unmatched_acks=0,
    shadow_broker_route_dispatch_roundtrip_sessions=0,
    shadow_broker_route_dispatch_roundtrip_ready_sessions=None,
    shadow_broker_route_dispatch_roundtrip_strategy="",
    shadow_broker_route_dispatch_roundtrip_market="",
    shadow_broker_route_dispatch_roundtrip_scenario_count=0,
    dispatch_roundtrip_vendor_market_data_batch_provided=False,
    dispatch_roundtrip_vendor_market_data_batch_ready=False,
    dispatch_roundtrip_vendor_market_data_batch_adapter="",
    dispatch_roundtrip_vendor_market_data_batch_kind="",
    dispatch_roundtrip_vendor_market_data_batch_manifest_run_type="",
    dispatch_roundtrip_vendor_market_data_batch_market="",
    dispatch_roundtrip_vendor_market_data_batch_dataset_count=0,
    dispatch_roundtrip_vendor_market_data_batch_ready_datasets=0,
    dispatch_roundtrip_vendor_market_data_batch_failed_datasets=0,
    dispatch_roundtrip_vendor_market_data_batch_ready_rate=0.0,
    dispatch_roundtrip_vendor_market_data_batch_unique_source_files=0,
    dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints=0,
    dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage=0.0,
    dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage=0.0,
    dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts=0,
    dispatch_roundtrip_vendor_market_data_batch_mapping_sources="",
    dispatch_roundtrip_vendor_market_data_batch_comparison_accepted=False,
    dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks=0,
    dispatch_roundtrip_vendor_market_data_batch_datasets_json="[]",
    schema_reviewed=None,
    schema_review_mode=None,
):
    if schema_reviewed is None:
        schema_reviewed = adapter == "normalized"
    if schema_review_mode is None:
        schema_review_mode = "native_schema" if adapter == "normalized" else "placeholder_unreviewed"
    if route_dispatch_roundtrip_required is None:
        route_dispatch_roundtrip_required = dispatch_roundtrip_provided
    if route_dispatch_roundtrip_provided is None:
        route_dispatch_roundtrip_provided = dispatch_roundtrip_provided
    if route_dispatch_roundtrip_ready is None:
        route_dispatch_roundtrip_ready = dispatch_roundtrip_ready
    if route_dispatch_roundtrip_target_mode is None:
        route_dispatch_roundtrip_target_mode = dispatch_roundtrip_target_mode
    if route_dispatch_roundtrip_strategy is None:
        route_dispatch_roundtrip_strategy = dispatch_roundtrip_strategy
    if route_dispatch_roundtrip_market is None:
        route_dispatch_roundtrip_market = dispatch_roundtrip_market
    if route_dispatch_roundtrip_scenario_key is None:
        route_dispatch_roundtrip_scenario_key = dispatch_roundtrip_scenario_key
    if route_dispatch_roundtrip_requests is None:
        route_dispatch_roundtrip_requests = dispatch_roundtrip_requests
    if route_dispatch_roundtrip_acked_orders is None:
        route_dispatch_roundtrip_acked_orders = dispatch_roundtrip_acked_orders
    if route_dispatch_roundtrip_missing_request_acks is None:
        route_dispatch_roundtrip_missing_request_acks = dispatch_roundtrip_missing_request_acks
    if route_dispatch_roundtrip_rejected_orders is None:
        route_dispatch_roundtrip_rejected_orders = dispatch_roundtrip_rejected_orders
    if route_dispatch_roundtrip_unmatched_acks is None:
        route_dispatch_roundtrip_unmatched_acks = dispatch_roundtrip_unmatched_acks
    if shadow_broker_readiness_ready_sessions is None:
        shadow_broker_readiness_ready_sessions = shadow_broker_readiness_sessions
    if shadow_broker_vendor_data_readiness_provided_sessions is None:
        shadow_broker_vendor_data_readiness_provided_sessions = shadow_broker_vendor_data_readiness_sessions
    if shadow_broker_vendor_data_readiness_ready_sessions is None:
        shadow_broker_vendor_data_readiness_ready_sessions = shadow_broker_vendor_data_readiness_sessions
    if shadow_broker_route_readiness_ready_sessions is None:
        shadow_broker_route_readiness_ready_sessions = shadow_broker_route_readiness_sessions
    if shadow_broker_dispatch_roundtrip_ready_sessions is None:
        shadow_broker_dispatch_roundtrip_ready_sessions = shadow_broker_dispatch_roundtrip_sessions
    if shadow_broker_route_dispatch_roundtrip_ready_sessions is None:
        shadow_broker_route_dispatch_roundtrip_ready_sessions = shadow_broker_route_dispatch_roundtrip_sessions
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema"
                if adapter != "normalized"
                else "native_normalized",
                "schema_reviewed": schema_reviewed,
                "schema_review_mode": schema_review_mode,
                "required_components": 3,
                "provided_components": 3,
                "failed_checks": 0 if ready else 1,
                "runtime_session_provided": runtime_session_provided,
                "runtime_session_ready": runtime_session_ready,
                "runtime_guard_action": runtime_guard_action,
                "runtime_guard_halted": runtime_guard_halted,
                "runtime_target_mode": runtime_target_mode,
                "runtime_strategy": runtime_strategy,
                "runtime_market": runtime_market,
                "resume_gate_provided": resume_gate_provided,
                "resume_gate_ready": resume_gate_ready,
                "resume_strategy": resume_strategy,
                "resume_market": resume_market,
                "resume_incident_strategy": resume_incident_strategy,
                "resume_incident_market": resume_incident_market,
                "resume_proof_refresh_ready": resume_proof_refresh_ready,
                "resume_proof_refresh_strategy": resume_proof_refresh_strategy,
                "resume_proof_refresh_market": resume_proof_refresh_market,
                "resume_broker_route_readiness_required": resume_broker_route_readiness_required,
                "resume_broker_route_readiness_provided": resume_broker_route_readiness_provided,
                "resume_broker_route_readiness_ready": resume_broker_route_readiness_ready,
                "resume_broker_route_readiness_strategy": resume_broker_route_readiness_strategy,
                "resume_broker_route_readiness_market": resume_broker_route_readiness_market,
                "resume_broker_route_readiness_route_ready_pairs": (
                    resume_broker_route_readiness_route_ready_pairs
                ),
                "resume_broker_route_readiness_gap_pairs": resume_broker_route_readiness_gap_pairs,
                "resume_broker_route_readiness_recommendation": resume_broker_route_readiness_recommendation,
                "resume_broker_route_readiness_ops_launch_controls_ready": (
                    resume_broker_route_readiness_ops_launch_controls_ready
                ),
                "resume_broker_route_readiness_ops_launch_control_failures": (
                    resume_broker_route_readiness_ops_launch_control_failures
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "resume_incident_broker_route_readiness_required": (
                    resume_incident_broker_route_readiness_required
                ),
                "resume_incident_broker_route_readiness_provided": (
                    resume_incident_broker_route_readiness_provided
                ),
                "resume_incident_broker_route_readiness_ready": resume_incident_broker_route_readiness_ready,
                "resume_incident_broker_route_readiness_strategy": (
                    resume_incident_broker_route_readiness_strategy
                ),
                "resume_incident_broker_route_readiness_market": (
                    resume_incident_broker_route_readiness_market
                ),
                "resume_incident_broker_route_readiness_route_ready_pairs": (
                    resume_incident_broker_route_readiness_route_ready_pairs
                ),
                "resume_incident_broker_route_readiness_gap_pairs": (
                    resume_incident_broker_route_readiness_gap_pairs
                ),
                "resume_incident_broker_route_readiness_recommendation": (
                    resume_incident_broker_route_readiness_recommendation
                ),
                "resume_incident_broker_route_readiness_ops_launch_controls_ready": (
                    resume_incident_broker_route_readiness_ops_launch_controls_ready
                ),
                "resume_incident_broker_route_readiness_ops_launch_control_failures": (
                    resume_incident_broker_route_readiness_ops_launch_control_failures
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "dispatch_roundtrip_provided": dispatch_roundtrip_provided,
                "dispatch_roundtrip_ready": dispatch_roundtrip_ready,
                "dispatch_roundtrip_target_mode": dispatch_roundtrip_target_mode,
                "dispatch_roundtrip_strategy": dispatch_roundtrip_strategy,
                "dispatch_roundtrip_market": dispatch_roundtrip_market,
                "dispatch_roundtrip_scenario_key": dispatch_roundtrip_scenario_key,
                "dispatch_roundtrip_batch_id": dispatch_roundtrip_batch_id,
                "dispatch_roundtrip_requests": dispatch_roundtrip_requests,
                "dispatch_roundtrip_acked_orders": dispatch_roundtrip_acked_orders,
                "dispatch_roundtrip_missing_request_acks": dispatch_roundtrip_missing_request_acks,
                "dispatch_roundtrip_rejected_orders": dispatch_roundtrip_rejected_orders,
                "dispatch_roundtrip_unmatched_acks": dispatch_roundtrip_unmatched_acks,
                "dispatch_roundtrip_failed_checks": dispatch_roundtrip_failed_checks,
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "route_dispatch_roundtrip_required": route_dispatch_roundtrip_required,
                "route_dispatch_roundtrip_provided": route_dispatch_roundtrip_provided,
                "route_dispatch_roundtrip_ready": route_dispatch_roundtrip_ready,
                "route_dispatch_roundtrip_target_mode": route_dispatch_roundtrip_target_mode,
                "route_dispatch_roundtrip_strategy": route_dispatch_roundtrip_strategy,
                "route_dispatch_roundtrip_market": route_dispatch_roundtrip_market,
                "route_dispatch_roundtrip_scenario_key": route_dispatch_roundtrip_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_dispatch_roundtrip_batch_id,
                "route_dispatch_roundtrip_requests": route_dispatch_roundtrip_requests,
                "route_dispatch_roundtrip_acked_orders": route_dispatch_roundtrip_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_dispatch_roundtrip_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_dispatch_roundtrip_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_dispatch_roundtrip_unmatched_acks,
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
                "route_readiness_ops_launch_controls_ready": route_readiness_ops_launch_controls_ready,
                "route_readiness_ops_launch_control_failures": route_readiness_ops_launch_control_failures,
                "route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_ready_runs": (
                    route_readiness_ops_broker_roundtrip_resume_route_ready_runs
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_breach_runs": (
                    route_readiness_ops_broker_roundtrip_resume_route_breach_runs
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs": (
                    route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs": (
                    route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs": (
                    route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs
                ),
                "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs": (
                    route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs
                ),
                "shadow_broker_readiness_provided": shadow_broker_readiness_provided,
                "shadow_broker_readiness_sessions": shadow_broker_readiness_sessions,
                "shadow_broker_readiness_ready_sessions": shadow_broker_readiness_ready_sessions,
                "shadow_broker_vendor_data_readiness_sessions": (
                    shadow_broker_vendor_data_readiness_sessions
                ),
                "shadow_broker_vendor_data_readiness_provided_sessions": (
                    shadow_broker_vendor_data_readiness_provided_sessions
                ),
                "shadow_broker_vendor_data_readiness_ready_sessions": (
                    shadow_broker_vendor_data_readiness_ready_sessions
                ),
                "shadow_broker_vendor_data_readiness_failed_checks": (
                    shadow_broker_vendor_data_readiness_failed_checks
                ),
                "shadow_broker_adapter": shadow_broker_adapter,
                "shadow_broker_adapter_count": shadow_broker_adapter_count,
                "shadow_broker_route_readiness_sessions": shadow_broker_route_readiness_sessions,
                "shadow_broker_route_readiness_ready_sessions": shadow_broker_route_readiness_ready_sessions,
                "shadow_broker_route_readiness_strategy": shadow_broker_route_readiness_strategy,
                "shadow_broker_route_readiness_market": shadow_broker_route_readiness_market,
                "shadow_broker_route_readiness_gap_pairs": shadow_broker_route_readiness_gap_pairs,
                "shadow_broker_dispatch_roundtrip_sessions": shadow_broker_dispatch_roundtrip_sessions,
                "shadow_broker_dispatch_roundtrip_ready_sessions": (
                    shadow_broker_dispatch_roundtrip_ready_sessions
                ),
                "shadow_broker_dispatch_roundtrip_strategy": shadow_broker_dispatch_roundtrip_strategy,
                "shadow_broker_dispatch_roundtrip_market": shadow_broker_dispatch_roundtrip_market,
                "shadow_broker_dispatch_roundtrip_scenario_count": (
                    shadow_broker_dispatch_roundtrip_scenario_count
                ),
                "shadow_broker_dispatch_roundtrip_missing_request_acks": (
                    shadow_broker_dispatch_roundtrip_missing_request_acks
                ),
                "shadow_broker_dispatch_roundtrip_rejected_orders": (
                    shadow_broker_dispatch_roundtrip_rejected_orders
                ),
                "shadow_broker_dispatch_roundtrip_unmatched_acks": (
                    shadow_broker_dispatch_roundtrip_unmatched_acks
                ),
                "shadow_broker_route_dispatch_roundtrip_sessions": (
                    shadow_broker_route_dispatch_roundtrip_sessions
                ),
                "shadow_broker_route_dispatch_roundtrip_ready_sessions": (
                    shadow_broker_route_dispatch_roundtrip_ready_sessions
                ),
                "shadow_broker_route_dispatch_roundtrip_strategy": (
                    shadow_broker_route_dispatch_roundtrip_strategy
                ),
                "shadow_broker_route_dispatch_roundtrip_market": shadow_broker_route_dispatch_roundtrip_market,
                "shadow_broker_route_dispatch_roundtrip_scenario_count": (
                    shadow_broker_route_dispatch_roundtrip_scenario_count
                ),
                "dispatch_roundtrip_vendor_market_data_batch_provided": (
                    dispatch_roundtrip_vendor_market_data_batch_provided
                ),
                "dispatch_roundtrip_vendor_market_data_batch_ready": (
                    dispatch_roundtrip_vendor_market_data_batch_ready
                ),
                "dispatch_roundtrip_vendor_market_data_batch_adapter": (
                    dispatch_roundtrip_vendor_market_data_batch_adapter
                ),
                "dispatch_roundtrip_vendor_market_data_batch_kind": (
                    dispatch_roundtrip_vendor_market_data_batch_kind
                ),
                "dispatch_roundtrip_vendor_market_data_batch_manifest_run_type": (
                    dispatch_roundtrip_vendor_market_data_batch_manifest_run_type
                ),
                "dispatch_roundtrip_vendor_market_data_batch_market": (
                    dispatch_roundtrip_vendor_market_data_batch_market
                ),
                "dispatch_roundtrip_vendor_market_data_batch_dataset_count": (
                    dispatch_roundtrip_vendor_market_data_batch_dataset_count
                ),
                "dispatch_roundtrip_vendor_market_data_batch_ready_datasets": (
                    dispatch_roundtrip_vendor_market_data_batch_ready_datasets
                ),
                "dispatch_roundtrip_vendor_market_data_batch_failed_datasets": (
                    dispatch_roundtrip_vendor_market_data_batch_failed_datasets
                ),
                "dispatch_roundtrip_vendor_market_data_batch_ready_rate": (
                    dispatch_roundtrip_vendor_market_data_batch_ready_rate
                ),
                "dispatch_roundtrip_vendor_market_data_batch_unique_source_files": (
                    dispatch_roundtrip_vendor_market_data_batch_unique_source_files
                ),
                "dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints": (
                    dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints
                ),
                "dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage": (
                    dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage
                ),
                "dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage": (
                    dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage
                ),
                "dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts": (
                    dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts
                ),
                "dispatch_roundtrip_vendor_market_data_batch_mapping_sources": (
                    dispatch_roundtrip_vendor_market_data_batch_mapping_sources
                ),
                "dispatch_roundtrip_vendor_market_data_batch_comparison_accepted": (
                    dispatch_roundtrip_vendor_market_data_batch_comparison_accepted
                ),
                "dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks": (
                    dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks
                ),
                "dispatch_roundtrip_vendor_market_data_batch_datasets_json": (
                    dispatch_roundtrip_vendor_market_data_batch_datasets_json
                ),
                "recommendation": "broker_integration_ready"
                if ready and bool(schema_reviewed)
                else (
                    "dry_run_only_until_vendor_schema_review"
                    if ready and adapter != "normalized"
                    else "fix_broker_readiness_gaps"
                ),
            }
        ]
    )


def data_readiness_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "components": 6,
                "required_components": 3,
                "provided_components": 6,
                "ready_components": 6 if ready else 5,
                "failed_checks": 0 if ready else 1,
                "recommendation": "feed_strategy_research" if ready else "fix_data_readiness_gaps",
            }
        ]
    )


def with_broker_dispatch_roundtrip_vendor_batch(
    summary,
    *,
    prefix="broker_dispatch_roundtrip_vendor_market_data_batch",
    **overrides,
):
    values = {
        "provided": True,
        "ready": True,
        "adapter": "arrow_money",
        "kind": "ticks",
        "manifest_run_type": "vendor_market_data_batch_pipeline",
        "market": "india_nse_index_derivatives",
        "dataset_count": 2,
        "ready_datasets": 2,
        "failed_datasets": 0,
        "ready_rate": 1.0,
        "unique_source_files": 2,
        "unique_header_fingerprints": 1,
        "source_file_fingerprint_coverage": 1.0,
        "min_mapping_coverage": 1.0,
        "unique_mapping_drafts": 1,
        "mapping_sources": "vendor_intake_draft",
        "mapping_source_mode": "",
        "mapping_application_count": 0,
        "unique_mapping_applications": 0,
        "target_application_coverage": 0.0,
        "comparison_accepted": True,
        "comparison_failed_checks": 0,
        "datasets_json": json.dumps(
            [
                {
                    "dataset": "nifty_day1",
                    "ready": True,
                    "source_file_sha256": "a" * 64,
                    "source_header_sha256": "b" * 64,
                    "mapping_draft_sha256": "c" * 64,
                    "mapping_source": "vendor_intake_draft",
                }
            ],
            sort_keys=True,
        ),
    }
    values.update(overrides)
    result = summary.copy()
    for suffix, value in values.items():
        result.loc[0, f"{prefix}_{suffix}"] = value
    return result


def broker_vendor_market_data_batch_config(**overrides):
    values = {
        "provided": True,
        "ready": True,
        "adapter": "arrow_money",
        "kind": "ticks",
        "manifest_run_type": "vendor_market_data_batch_pipeline",
        "market": "india_nse_index_derivatives",
        "dataset_count": 2,
        "ready_datasets": 2,
        "failed_datasets": 0,
        "ready_rate": 1.0,
        "unique_source_files": 2,
        "unique_header_fingerprints": 1,
        "source_file_fingerprint_coverage": 1.0,
        "min_mapping_coverage": 1.0,
        "unique_mapping_drafts": 1,
        "mapping_sources": "vendor_intake_draft",
        "mapping_source_mode": "",
        "mapping_application_count": 0,
        "unique_mapping_applications": 0,
        "target_application_coverage": 0.0,
        "comparison": {"accepted": True, "failed_checks": 0},
        "datasets": [
            {
                "dataset": "nifty_day1",
                "ready": True,
                "source_file_sha256": "a" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "vendor_intake_draft",
            },
            {
                "dataset": "nifty_day2",
                "ready": True,
                "source_file_sha256": "d" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "vendor_intake_draft",
            },
        ],
    }
    values.update(overrides)
    return values


def target_application_vendor_market_data_batch_config(**overrides):
    values = broker_vendor_market_data_batch_config(
        mapping_sources="verified_target_application",
        mapping_source_mode="per_dataset_verified_target_application",
        mapping_application_count=2,
        unique_mapping_applications=2,
        target_application_coverage=1.0,
        application_lineage_consistency_required=True,
        application_lineage_consistent=True,
        datasets=[
            {
                "dataset": "nifty_day1",
                "ready": True,
                "source_file_sha256": "a" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "verified_target_application",
                "mapping_application_path": "applications/nifty_day1/application.json",
                "mapping_application_id": "mapping-app-day1",
                "mapping_application_sha256": "1" * 64,
                "mapping_scope_review_id": "scope-review-1",
                "mapping_scope_review_sha256": "2" * 64,
                "target_intake_receipt_id": "target-intake-day1",
                "applied_mapping_sha256": "3" * 64,
            },
            {
                "dataset": "nifty_day2",
                "ready": True,
                "source_file_sha256": "d" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "verified_target_application",
                "mapping_application_path": "applications/nifty_day2/application.json",
                "mapping_application_id": "mapping-app-day2",
                "mapping_application_sha256": "4" * 64,
                "mapping_scope_review_id": "scope-review-1",
                "mapping_scope_review_sha256": "2" * 64,
                "target_intake_receipt_id": "target-intake-day2",
                "applied_mapping_sha256": "3" * 64,
            },
        ],
    )
    values.update(overrides)
    values.setdefault(
        "application_lineage_sha256",
        target_application_lineage_sha256(values["datasets"]),
    )
    return values


def with_target_application_vendor_batch(
    summary,
    *,
    include_final_lineage=True,
    include_readiness_final_lineage=None,
    include_readiness_complete_final_lineage=None,
    include_readiness_extended_complete_final_lineage=None,
    include_readiness_latest_extended_complete_final_lineage=None,
    include_readiness_current_latest_extended_complete_final_lineage=None,
    include_readiness_reconciled_current_latest_extended_complete_final_lineage=None,
    include_readiness_verified_reconciled_current_latest_extended_complete_final_lineage=None,
    include_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage=None,
    **overrides,
):
    config = target_application_vendor_market_data_batch_config()
    values = {
        key: value
        for key, value in config.items()
        if key not in {"comparison", "datasets"}
    }
    values.update(
        {
            "comparison_accepted": config["comparison"]["accepted"],
            "comparison_failed_checks": config["comparison"]["failed_checks"],
            "datasets_json": json.dumps(config["datasets"], sort_keys=True),
        }
    )
    values.update(overrides)
    result = with_broker_dispatch_roundtrip_vendor_batch(summary, **values)
    lineage_sha256 = target_application_lineage_sha256(config["datasets"])
    result.loc[0, "broker_vendor_market_data_batch_lineage_match_required"] = True
    result.loc[0, "broker_vendor_market_data_batch_lineage_matches"] = True
    result.loc[0, "vendor_market_data_batch_application_lineage_sha256"] = (
        lineage_sha256
    )
    result.loc[0, "broker_vendor_market_data_batch_application_lineage_sha256"] = (
        lineage_sha256
    )
    if include_final_lineage:
        comparison = target_application_lineage_comparison(config)
        prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison["required"]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        for field, value in comparison.items():
            if field not in {"required", "matches"}:
                result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_final_lineage is None:
        include_readiness_final_lineage = include_final_lineage
    if include_readiness_final_lineage:
        comparison = broker_readiness_final_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        for field, value in comparison.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_complete_final_lineage is None:
        include_readiness_complete_final_lineage = (
            include_readiness_final_lineage
        )
    if include_readiness_complete_final_lineage:
        comparison = (
            broker_readiness_complete_final_target_application_lineage_comparison(
                config
            )
        )
        prefix = (
            "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        result.loc[
            0,
            f"{prefix}_broker_readiness_complete_final_review_carried_application_lineage_sha256",
        ] = comparison["carried_application_lineage_sha256"]
        for field, value in comparison.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_extended_complete_final_lineage is None:
        include_readiness_extended_complete_final_lineage = (
            include_readiness_complete_final_lineage
        )
    if include_readiness_extended_complete_final_lineage:
        comparison = broker_readiness_view_34_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        result.loc[
            0,
            f"{prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        ] = comparison["carried_application_lineage_sha256"]
        for field, value in comparison.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_latest_extended_complete_final_lineage is None:
        include_readiness_latest_extended_complete_final_lineage = (
            include_readiness_extended_complete_final_lineage
        )
    if include_readiness_latest_extended_complete_final_lineage:
        comparison = broker_readiness_view_42_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        result.loc[
            0,
            f"{prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ] = comparison["carried_application_lineage_sha256"]
        for field, value in comparison.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_current_latest_extended_complete_final_lineage is None:
        include_readiness_current_latest_extended_complete_final_lineage = (
            include_readiness_latest_extended_complete_final_lineage
        )
    if include_readiness_current_latest_extended_complete_final_lineage:
        comparison = broker_readiness_view_50_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        for field, value in comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "broker_readiness_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_reconciled_current_latest_extended_complete_final_lineage is None:
        include_readiness_reconciled_current_latest_extended_complete_final_lineage = (
            include_readiness_current_latest_extended_complete_final_lineage
        )
    if include_readiness_reconciled_current_latest_extended_complete_final_lineage:
        comparison = broker_readiness_view_58_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        for field, value in comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "broker_readiness_reconciled_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_verified_reconciled_current_latest_extended_complete_final_lineage is None:
        include_readiness_verified_reconciled_current_latest_extended_complete_final_lineage = (
            include_readiness_reconciled_current_latest_extended_complete_final_lineage
        )
    if include_readiness_verified_reconciled_current_latest_extended_complete_final_lineage:
        comparison = broker_readiness_view_66_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        for field, value in comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[0, f"{prefix}_{field}"] = value
    if include_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage is None:
        include_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage = (
            include_readiness_verified_reconciled_current_latest_extended_complete_final_lineage
        )
    if include_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage:
        comparison = broker_readiness_view_74_target_application_lineage_comparison(
            config
        )
        prefix = (
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[0, f"{prefix}_lineage_match_required"] = comparison[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
        for field, value in comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[0, f"{prefix}_{field}"] = value
    return result


def data_readiness_comparison_summary(accepted=True):
    return pd.DataFrame(
        [
            {
                "provided": True,
                "manifest_required": True,
                "manifest_provided": True,
                "manifest_current": True,
                "verified": accepted,
                "read_error": "",
                "reason": (
                    "accepted"
                    if accepted
                    else "data_readiness_comparison_not_accepted"
                ),
                "summary_path": "runs/comparison/data_readiness_comparison_summary.csv",
                "manifest_path": "runs/comparison/manifest.json",
                "manifest_sha256": "a" * 64,
                "manifest_error": "",
                "manifest_run_type": "data_readiness_comparison",
                "manifest_run_type_matches": True,
                "manifest_artifact_count": 6,
                "manifest_artifact_match_count": 6,
                "manifest_input_fingerprint_count": 2,
                "manifest_input_fingerprint_match_count": 2,
                "accepted": accepted,
                "dataset_count": 2,
                "ready_datasets": 2 if accepted else 1,
                "failed_datasets": 0 if accepted else 1,
                "ready_rate": 1.0 if accepted else 0.5,
                "total_failed_checks": 0 if accepted else 1,
                "failed_checks": 0 if accepted else 1,
                "recommendation": "feed_walkforward_research" if accepted else "collect_or_fix_data",
            }
        ]
    )


def write_data_readiness_comparison_bundle(root, *, accepted=True):
    source_root = root.parent / f"{root.name}_readiness_sources"
    readiness_dirs = []
    for index, source_hash in enumerate(("a" * 64, "d" * 64), start=1):
        readiness = source_root / f"day{index}"
        ready = accepted or index == 1
        write_manifest_bound_data_readiness(
            readiness,
            {
                "ready": ready,
                "components": 1,
                "required_components": 1,
                "provided_components": 1,
                "ready_components": 1 if ready else 0,
                "failed_checks": 0 if ready else 1,
                "vendor_intake_source_file_sha256": source_hash,
                "vendor_intake_source_header_sha256": "b" * 64,
                "vendor_intake_mapping_draft_sha256": "c" * 64,
                "vendor_intake_mapping_coverage": 1.0,
                "recommendation": (
                    "feed_strategy_research"
                    if ready
                    else "fix_data_readiness_gaps"
                ),
            },
            source_text=f"source_hash\n{source_hash}\n",
        )
        readiness_dirs.append(readiness)
    write_data_readiness_comparison(
        readiness_dirs,
        output_dir=root,
        labels=["day1", "day2"],
    )
    return root


def strategy_portfolio_summary(ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "deployment_mode": "paper_shadow",
                "allocation_mode": "readiness_weighted",
                "capital_currency": "INR",
                "total_capital": 1_000_000.0,
                "reserve_weight": 0.10,
                "allocated_weight": 0.90 if ready else 0.0,
                "allocated_notional": 900_000.0 if ready else 0.0,
                "min_strategy_count": 2 if ready else 0,
                "min_market_count": 1 if ready else 0,
                "max_strategy_weight": 0.60 if ready else 0.0,
                "max_market_weight": 0.90 if ready else 0.0,
                "allocated_strategy_count": 2 if ready else 0,
                "allocated_market_count": 1 if ready else 0,
                "top_strategy_by_weight": "lead_lag_taker" if ready else "",
                "top_market_by_weight": "india_nse_index_derivatives" if ready else "",
                "max_strategy_allocation_weight": 0.45 if ready else 0.0,
                "max_market_allocation_weight": 0.90 if ready else 0.0,
                "top_profile": "leadlag" if ready else "",
                "top_strategy": "lead_lag_taker" if ready else "",
                "top_market": "india_nse_index_derivatives" if ready else "",
                "failed_check_count": 0 if ready else 1,
                "failed_check_names": "" if ready else "eligible_profile_count",
                "first_failed_reason": "" if ready else "at least one strategy profile must pass readiness filters",
                "recommendation": "paper_shadow_allocation_ready" if ready else "complete_strategy_scorecard_evidence",
                **leadlag_lineage(ready=ready),
            }
        ]
    )


def strategy_portfolio_allocations(
    *,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    profile="leadlag",
    eligible=True,
    allocation_weight=0.0012,
    allocation_notional=1200.0,
):
    return pd.DataFrame(
        [
            {
                "rank": 1,
                "profile": profile,
                "strategy": strategy,
                "market": market,
                "ready": eligible,
                "readiness_score": 1.0 if eligible else 0.5,
                "passed_required_run_types": 6 if eligible else 3,
                "required_run_type_count": 6,
                "eligible": eligible,
                "eligibility_reason": "eligible_for_paper_shadow_allocation"
                if eligible
                else "profile_not_ready",
                "allocation_score": 1.0 if eligible else 0.0,
                "allocation_weight": allocation_weight,
                "allocation_notional": allocation_notional,
                "reserve_weight": 0.10,
                "max_profile_weight": 0.40,
                "capital_currency": "INR",
                "deployment_mode": "paper_shadow",
                "allocation_mode": "readiness_weighted",
                "next_required_run_type": "",
                "next_gate": "plan-scaleup",
                "next_gate_help_command": "python -m hft_cli plan-scaleup --help",
                "recommendation": "ready_for_shadow_scaleup_review",
                **leadlag_lineage(
                    ready=str(profile).strip().lower() == "leadlag"
                ),
            }
        ]
    )


def route_readiness_summary(
    ready=True,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    ops_launch_controls_blocked_pairs=0,
    ops_broker_roundtrip_portfolio_breach_pairs=0,
    ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    ops_broker_roundtrip_resume_route_breach_pairs=0,
    ops_broker_roundtrip_resume_route_gap_breach_pairs=0,
    ops_broker_roundtrip_resume_route_launch_control_breach_pairs=0,
    ops_broker_roundtrip_resume_route_portfolio_breach_pairs=0,
    ops_broker_roundtrip_resume_route_concentration_breach_pairs=0,
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": strategy,
                "market": market,
                "strategy_count": 1,
                "market_count": 1,
                "pair_count": 1,
                "route_ready_pairs": 1 if ready else 0,
                "gap_pairs": 0 if ready else 1,
                "strategy_evidence_ready_pairs": 1,
                "ops_evidence_ready_pairs": 1 if ready else 0,
                "portability_blocked_pairs": 0,
                "ops_file_provenance_blocked_pairs": 0 if ready else 1,
                "ops_launch_controls_blocked_pairs": ops_launch_controls_blocked_pairs,
                "ops_broker_roundtrip_portfolio_breach_pairs": (
                    ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
                "ops_broker_roundtrip_resume_route_breach_pairs": (
                    ops_broker_roundtrip_resume_route_breach_pairs
                ),
                "ops_broker_roundtrip_resume_route_gap_breach_pairs": (
                    ops_broker_roundtrip_resume_route_gap_breach_pairs
                ),
                "ops_broker_roundtrip_resume_route_launch_control_breach_pairs": (
                    ops_broker_roundtrip_resume_route_launch_control_breach_pairs
                ),
                "ops_broker_roundtrip_resume_route_portfolio_breach_pairs": (
                    ops_broker_roundtrip_resume_route_portfolio_breach_pairs
                ),
                "ops_broker_roundtrip_resume_route_concentration_breach_pairs": (
                    ops_broker_roundtrip_resume_route_concentration_breach_pairs
                ),
                "require_ops_file_inputs": True,
                "recommendation": "eligible_for_live_dryrun_route_review"
                if ready
                else "complete_route_readiness_gaps",
            }
        ]
    )


def write_inputs(
    root,
    *,
    evidence_ready=True,
    shadow_accepted=True,
    launch_ready=True,
    exposure_passed=True,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
):
    evidence = root / "evidence"
    shadow = root / "shadow"
    launch = root / "launch"
    exposure = root / "exposure"
    for path in (evidence, shadow, launch, exposure):
        path.mkdir(parents=True, exist_ok=True)
    evidence_summary(evidence_ready, strategy=strategy, market=market).to_csv(
        evidence / "strategy_evidence_summary.csv",
        index=False,
    )
    shadow_summary(shadow_accepted).to_csv(shadow / "shadow_session_comparison_summary.csv", index=False)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    exposure_summary(exposure_passed).to_csv(exposure / "order_exposure_summary.csv", index=False)
    return evidence, shadow, launch, exposure


def write_proof_refresh_bundle(root):
    root.mkdir(parents=True, exist_ok=True)
    drift = root.parent / f"_{root.name}_drift"
    replay = root.parent / f"_{root.name}_replay"
    baseline = root.parent / f"_{root.name}_baseline_proof"
    source = root.parent / f"_{root.name}_source.csv"
    drift.mkdir(parents=True, exist_ok=True)
    replay.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "passed": True,
                "failed_checks": 0,
                "recommendation": "reuse_existing_proof_assumptions",
            }
        ]
    ).to_csv(drift / "fill_model_drift_summary.csv", index=False)
    source.write_text("ts,bid,ask\n1,100,101\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "net_pnl": 10.0,
                "total_costs": 0.0,
                "fills": 10,
                "orders_sent": 10,
                "order_to_trade_ratio": 1.0,
                "otr_breached": False,
                "turnover": 1000.0,
                "maker_share": 1.0,
            }
        ]
    ).to_csv(replay / "summary.csv", index=False)
    write_experiment_manifest(
        replay,
        run_type="scaleup_proof_refresh_unit_replay",
        inputs={"source": source},
    )
    write_proof_report(
        [replay],
        output_dir=baseline,
        thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
    )
    report = write_proof_refresh_report(
        drift_path=drift,
        baseline_proof_path=baseline,
        output_dir=root,
        thresholds=ProofRefreshThresholds(
            expected_strategy="lead_lag_taker",
            expected_market="india_nse_index_derivatives",
        ),
    )
    assert report.ready
    return root, source


def write_broker_readiness_bundle(
    root,
    summary,
    *,
    config_overrides=None,
):
    root.mkdir(parents=True, exist_ok=True)
    row = summary.iloc[0]
    summary.to_csv(root / "broker_readiness_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "component": "resume_gate",
                "required": True,
                "provided": True,
                "ready": bool(row["ready"]),
            }
        ]
    ).to_csv(root / "broker_readiness_items.csv", index=False)
    pd.DataFrame(
        [
            {
                "check": "resume_gate_ready",
                "passed": bool(row["ready"]),
                "value": bool(row["ready"]),
                "operator": "is",
                "threshold": True,
                "reason": "",
            }
        ]
    ).to_csv(root / "broker_readiness_checks.csv", index=False)
    pd.DataFrame(
        [
            {
                "priority": 1,
                "queue_status": "ready" if bool(row["ready"]) else "blocked",
                "check": "resume_gate_ready",
                "next_gate": "review-broker-readiness",
            }
        ]
    ).to_csv(root / "broker_readiness_action_queue.csv", index=False)
    config = {
        "ready": bool(row["ready"]),
        "adapter": str(row["adapter"]),
        "component_counts": {
            "failed_checks": int(row["failed_checks"]),
        },
    }
    if config_overrides:
        config.update(config_overrides)
    (root / "broker_readiness_config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "broker_readiness_runbook.md").write_text(
        "# Broker readiness\n\nReview-only evidence bundle.\n",
        encoding="utf-8",
    )
    source = root.parent / "broker_readiness_source.csv"
    pd.DataFrame([{"source": "fixture", "ready": bool(row["ready"])}]).to_csv(
        source,
        index=False,
    )
    write_experiment_manifest(
        root,
        run_type="broker_readiness",
        inputs={"broker_readiness_source": source},
        extra={"ready": bool(row["ready"])},
    )
    return root


def write_verified_broker_readiness_bundle(
    root,
    output_dir,
    *,
    contract_identity=False,
    route_contract_identity=False,
    route_enable_route_contract_identity=False,
    route_enable_route_enable_route_contract_identity=False,
    route_enable_route_enable_route_enable_route_contract_identity=False,
):
    from adapters.broker_readiness import (
        BrokerReadinessThresholds,
        write_broker_readiness_report,
    )
    from tests.test_broker_readiness import write_broker_readiness_input_dirs

    schema, export, upload, roundtrip = write_broker_readiness_input_dirs(
        root,
        "arrow_money",
        verified_roundtrip=True,
        contract_identity=contract_identity,
        route_contract_identity=route_contract_identity,
        route_enable_route_contract_identity=(
            route_enable_route_contract_identity
        ),
        route_enable_route_enable_route_contract_identity=(
            route_enable_route_enable_route_contract_identity
        ),
        route_enable_route_enable_route_enable_route_contract_identity=(
            route_enable_route_enable_route_enable_route_contract_identity
        ),
    )
    report = write_broker_readiness_report(
        output_dir=output_dir,
        schema_audit_dir=schema,
        order_export_dir=export,
        upload_pack_dir=upload,
        dispatch_roundtrip_dir=roundtrip,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )
    assert report.ready
    return output_dir


@pytest.fixture(scope="module")
def verified_route_identity_broker_readiness_bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("scaleup_route_identity")
    return write_verified_broker_readiness_bundle(
        root / "sources",
        root / "broker_readiness",
        route_contract_identity=True,
    )


@pytest.fixture(scope="module")
def verified_route_enable_identity_broker_readiness_bundle(
    tmp_path_factory,
):
    root = tmp_path_factory.mktemp("su_broker_route")
    return write_verified_broker_readiness_bundle(
        root / "s",
        root / "b",
        route_enable_route_contract_identity=True,
    )


@pytest.fixture(scope="module")
def verified_route_enable_route_enable_identity_broker_readiness_bundle(
    tmp_path_factory,
):
    root = tmp_path_factory.mktemp("su_bri")
    return write_verified_broker_readiness_bundle(
        root / "s",
        root / "b",
        route_enable_route_enable_route_contract_identity=True,
    )


@pytest.fixture(scope="module")
def verified_route_enable_route_enable_route_enable_identity_broker_readiness_bundle(
    tmp_path_factory,
):
    if os.name == "nt":
        short_root = Path(Path.cwd().anchor) / ".hft_test_tmp"
        short_root.mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="subr_", dir=short_root))
    else:
        root = tmp_path_factory.mktemp(
            "scaleup_terminal_broker_readiness_identity"
        )
    try:
        yield write_verified_broker_readiness_bundle(
            root / "s",
            root / "b",
            route_enable_route_enable_route_enable_route_contract_identity=True,
        )
    finally:
        if os.name == "nt":
            shutil.rmtree(root, ignore_errors=True)
            try:
                short_root.rmdir()
            except OSError:
                pass


def forge_broker_readiness_route_identity(root, forged_sha256):
    fields = (
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
        (
            "broker_dispatch_roundtrip_current_ack_"
            "route_contract_identity_sha256"
        ),
    )
    original_sha256 = ""
    for filename in (
        "broker_readiness_summary.csv",
        "broker_readiness_items.csv",
    ):
        path = root / filename
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        original_sha256 = original_sha256 or str(frame.loc[0, fields[0]])
        for field in fields:
            frame[field] = forged_sha256
        frame.to_csv(path, index=False)

    config_path = root / "broker_readiness_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lineage = config["dispatch_roundtrip"]["lineage"]
    for field in fields:
        lineage[field.removeprefix("broker_dispatch_roundtrip_")] = (
            forged_sha256
        )
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runbook_path = root / "broker_readiness_runbook.md"
    runbook_path.write_text(
        runbook_path.read_text(encoding="utf-8").replace(
            original_sha256,
            forged_sha256,
        ),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in fields:
        manifest["extra"][field] = forged_sha256
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(root)
    return original_sha256


def forge_broker_readiness_route_enable_identity(
    root,
    forged_sha256,
):
    fields = (
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD,
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_contract_identity_sha256"
        ),
    )
    original_sha256 = ""
    for filename in (
        "broker_readiness_summary.csv",
        "broker_readiness_items.csv",
    ):
        path = root / filename
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        original_sha256 = original_sha256 or str(
            frame.loc[0, fields[0]]
        )
        for field in fields:
            frame[field] = forged_sha256
        frame.to_csv(path, index=False)

    config_path = root / "broker_readiness_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lineage = config["dispatch_roundtrip"]["lineage"]
    for field in fields:
        lineage[field.removeprefix("broker_dispatch_roundtrip_")] = (
            forged_sha256
        )
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runbook_path = root / "broker_readiness_runbook.md"
    runbook_path.write_text(
        runbook_path.read_text(encoding="utf-8").replace(
            original_sha256,
            forged_sha256,
        ),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in fields:
        manifest["extra"][field] = forged_sha256
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(root)
    return original_sha256


def forge_broker_readiness_route_enable_route_enable_identity(
    root,
    forged_sha256,
):
    fields = (
        (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
        ),
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_enable_route_contract_identity_sha256"
        ),
    )
    original_sha256 = ""
    for filename in (
        "broker_readiness_summary.csv",
        "broker_readiness_items.csv",
    ):
        path = root / filename
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        original_sha256 = original_sha256 or str(
            frame.loc[0, fields[0]]
        )
        for field in fields:
            frame[field] = forged_sha256
        frame.to_csv(path, index=False)

    config_path = root / "broker_readiness_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lineage = config["dispatch_roundtrip"]["lineage"]
    for field in fields:
        lineage[field.removeprefix("broker_dispatch_roundtrip_")] = (
            forged_sha256
        )
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runbook_path = root / "broker_readiness_runbook.md"
    runbook_path.write_text(
        runbook_path.read_text(encoding="utf-8").replace(
            original_sha256,
            forged_sha256,
        ),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in fields:
        manifest["extra"][field] = forged_sha256
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(root)
    return original_sha256


def forge_broker_readiness_route_enable_route_enable_route_enable_identity(
    root,
    forged_sha256,
):
    fields = (
        (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
        ),
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_enable_route_enable_route_contract_identity_sha256"
        ),
    )
    original_sha256 = ""
    for filename in (
        "broker_readiness_summary.csv",
        "broker_readiness_items.csv",
    ):
        path = root / filename
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        original_sha256 = original_sha256 or str(
            frame.loc[0, fields[0]]
        )
        for field in fields:
            frame[field] = forged_sha256
        frame.to_csv(path, index=False)

    config_path = root / "broker_readiness_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    lineage = config["dispatch_roundtrip"]["lineage"]
    for field in fields:
        lineage[field.removeprefix("broker_dispatch_roundtrip_")] = (
            forged_sha256
        )
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    runbook_path = root / "broker_readiness_runbook.md"
    runbook_path.write_text(
        runbook_path.read_text(encoding="utf-8").replace(
            original_sha256,
            forged_sha256,
        ),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in fields:
        manifest["extra"][field] = forged_sha256
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(root)
    return original_sha256


def write_strategy_portfolio(root, *, ready=True, allocation_notional=1200.0):
    portfolio = root / "strategy_portfolio"
    portfolio.mkdir(parents=True, exist_ok=True)
    summary = strategy_portfolio_summary(ready)
    allocations = strategy_portfolio_allocations(
        allocation_notional=allocation_notional
    )
    summary.to_csv(portfolio / "strategy_portfolio_summary.csv", index=False)
    allocations.to_csv(
        portfolio / "strategy_portfolio_allocations.csv",
        index=False,
    )
    checks = pd.DataFrame(
        [
            {
                "check": "portfolio_ready",
                "passed": ready,
                "value": ready,
                "operator": "is",
                "threshold": True,
                "reason": "" if ready else "portfolio is blocked",
            }
        ]
    )
    checks.to_csv(portfolio / "strategy_portfolio_checks.csv", index=False)
    pd.DataFrame(
        [
            {
                "priority": 1,
                "queue_status": "ready" if ready else "blocked",
                "profile": "leadlag",
            }
        ]
    ).to_csv(portfolio / "strategy_portfolio_action_queue.csv", index=False)
    summary_record = json.loads(summary.to_json(orient="records"))[0]
    allocation_records = json.loads(allocations.to_json(orient="records"))
    (portfolio / "strategy_portfolio_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": ready,
                "summary": summary_record,
                "allocation_count": int(
                    (allocations["allocation_weight"] > 0.0).sum()
                ),
                **leadlag_lineage(ready=ready),
                "allocations": allocation_records,
                "authorizes_submission": False,
            }
        ),
        encoding="utf-8",
    )
    (portfolio / "strategy_portfolio_runbook.md").write_text(
        "# Strategy Portfolio\n",
        encoding="utf-8",
    )
    source = portfolio / "strategy_scorecard_source.csv"
    pd.DataFrame(
        [
            {
                "profile": "leadlag",
                "ready": ready,
                **leadlag_lineage(ready=ready),
            }
        ]
    ).to_csv(
        source,
        index=False,
    )
    write_experiment_manifest(
        portfolio,
        run_type="strategy_portfolio_allocation",
        inputs={"strategy_scorecard": source},
        extra={
            "ready": ready,
            "research_family_bound": False,
            **leadlag_lineage(ready=ready),
            "authorizes_submission": False,
        },
    )
    return portfolio


def write_lineage_scorecard(root, lineage):
    root.mkdir(parents=True, exist_ok=True)
    ranked = {
        "profile": "leadlag",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "ready": True,
        **lineage,
        "authorizes_submission": False,
    }
    pd.DataFrame([ranked]).to_csv(
        root / "strategy_scorecard.csv",
        index=False,
    )
    pd.DataFrame([{"profile": "leadlag", "gap": ""}]).to_csv(
        root / "strategy_scorecard_gaps.csv",
        index=False,
    )
    pd.DataFrame([{**lineage, "authorizes_submission": False}]).to_csv(
        root / "strategy_scorecard_summary.csv",
        index=False,
    )
    pd.DataFrame([{"profile": "leadlag", "queue_status": "ready"}]).to_csv(
        root / "strategy_scorecard_action_queue.csv",
        index=False,
    )
    (root / "strategy_scorecard_next_actions.json").write_text(
        json.dumps(
            {
                "ready": True,
                **lineage,
                "next_actions": [ranked],
                "authorizes_submission": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "strategy_scorecard_runbook.md").write_text(
        "# Strategy Scorecard\n",
        encoding="utf-8",
    )
    source = root / "catalog.csv"
    pd.DataFrame([{"run_type": "strategy_evidence"}]).to_csv(
        source,
        index=False,
    )
    write_experiment_manifest(
        root,
        run_type="strategy_scorecard",
        inputs={"catalog": source},
        extra={
            "ready": True,
            **lineage,
            "authorizes_submission": False,
        },
    )
    return root


def bind_portfolio_to_scorecard(portfolio, scorecard):
    manifest_path = scorecard / "manifest.json"
    manifest_sha = file_sha256(manifest_path)
    proof = {
        "scorecard_manifest_required": True,
        "scorecard_manifest_current": True,
        "scorecard_manifest_sha256": manifest_sha,
        "scorecard_contract_consistent": True,
        "scorecard_non_authorizing": True,
        "scorecard_provenance_gate_passed": True,
    }
    summary_path = portfolio / "strategy_portfolio_summary.csv"
    summary = pd.read_csv(summary_path)
    for field, value in proof.items():
        summary[field] = value
    summary.to_csv(summary_path, index=False)
    allocations_path = portfolio / "strategy_portfolio_allocations.csv"
    allocations = pd.read_csv(allocations_path)
    allocations["scorecard_manifest_sha256"] = manifest_sha
    allocations.to_csv(allocations_path, index=False)
    config_path = portfolio / "strategy_portfolio_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update(proof)
    config["summary"].update(proof)
    for row in config["allocations"]:
        row["scorecard_manifest_sha256"] = manifest_sha
    config["scorecard_provenance"] = {
        "manifest_required": True,
        "manifest_provided": True,
        "manifest_current": True,
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": manifest_sha,
        "contract_consistent": True,
        "non_authorizing": True,
        "gate_passed": True,
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    inputs = {
        "strategy_scorecard": scorecard / "strategy_scorecard.csv",
        "strategy_scorecard_manifest": manifest_path,
    }
    for artifact in (
        "strategy_scorecard_gaps.csv",
        "strategy_scorecard_summary.csv",
        "strategy_scorecard_action_queue.csv",
        "strategy_scorecard_next_actions.json",
        "strategy_scorecard_runbook.md",
    ):
        inputs[f"strategy_scorecard_artifact:{artifact}"] = scorecard / artifact
    write_experiment_manifest(
        portfolio,
        run_type="strategy_portfolio_allocation",
        inputs=inputs,
        extra={
            "ready": True,
            "research_family_bound": False,
            **leadlag_lineage(),
            "authorizes_submission": False,
        },
    )


def write_settlement_pipeline(root, *, launch_ready=True, broker_ready=True):
    pipeline = root / "settlement_pipeline"
    launch = pipeline / "03_launch"
    broker = pipeline / "06_broker_readiness"
    launch.mkdir(parents=True, exist_ok=True)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    write_broker_readiness_bundle(
        broker,
        broker_readiness_summary(broker_ready),
    )
    return pipeline


def write_surface_launch_pipeline(
    root,
    *,
    launch_ready=True,
    broker_ready=True,
    strategy="surface_mm",
    market="india_nse_index_derivatives",
):
    pipeline = root / "surface_launch_pipeline"
    launch = pipeline / "02_launch"
    broker = pipeline / "05_broker_readiness"
    launch.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": launch_ready and broker_ready,
                "adapter": "arrow_money",
                "mode": "shadow",
                "strategy": strategy,
                "market": market,
                "expected_strategy": strategy,
                "expected_market": market,
                "surface_pipeline_ready": True,
                "surface_candidate_ready": True,
                "require_surface_pipeline_ready": True,
                "components": 7,
                "ready_components": 7 if launch_ready and broker_ready else 6,
                "failed_components": 0 if launch_ready and broker_ready else 1,
                "skipped_components": 0,
                "recommendation": "paper_or_shadow_handoff" if launch_ready and broker_ready else "keep_in_research",
            }
        ]
    ).to_csv(pipeline / "surface_mm_launch_pipeline_summary.csv", index=False)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    write_broker_readiness_bundle(
        broker,
        broker_readiness_summary(broker_ready),
    )
    return pipeline


def write_strategy_launch_pipeline(
    root,
    *,
    family="leadlag",
    summary_file="leadlag_launch_pipeline_summary.csv",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    launch_ready=True,
    broker_ready=True,
    include_broker_dir=True,
    launch_root_broker_route_proof=False,
):
    pipeline = root / f"{family}_launch_pipeline"
    launch = pipeline / "03_launch"
    broker = pipeline / "06_broker_readiness"
    launch.mkdir(parents=True, exist_ok=True)
    if include_broker_dir:
        broker.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": launch_ready and broker_ready,
                "strategy": strategy,
                "market": market,
                "adapter": "arrow_money",
                "mode": "shadow",
                "components": 6,
                "ready_components": 6 if launch_ready and broker_ready else 5,
                "failed_components": 0 if launch_ready and broker_ready else 1,
                "skipped_components": 0,
                "recommendation": "paper_or_shadow_handoff" if launch_ready and broker_ready else "keep_in_research",
                **(
                    launch_root_broker_route_fields(strategy=strategy, market=market, ready=broker_ready)
                    if launch_root_broker_route_proof
                    else {}
                ),
            }
        ]
    ).to_csv(pipeline / summary_file, index=False)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    if include_broker_dir:
        write_broker_readiness_bundle(
            broker,
            broker_readiness_summary(broker_ready),
            config_overrides={
                "dispatch_roundtrip": {"ready": broker_ready},
            },
        )
    return pipeline


def launch_root_broker_route_fields(*, strategy, market, ready=True):
    return {
        "broker_readiness_provided": True,
        "broker_readiness_ready": ready,
        "broker_readiness_route_readiness_ready": ready,
        "broker_readiness_route_readiness_strategy": strategy,
        "broker_readiness_route_readiness_market": market,
        "broker_readiness_route_readiness_gap_pairs": 0,
        "broker_readiness_route_readiness_ops_launch_controls_present": ready,
        "broker_readiness_route_readiness_ops_launch_controls_blocked_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_breach_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs": 0,
        "broker_readiness_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs": 0,
        "broker_readiness_route_broker_route_readiness_provided": True,
        "broker_readiness_route_broker_route_readiness_ready": ready,
        "broker_readiness_route_broker_route_readiness_strategy": strategy,
        "broker_readiness_route_broker_route_readiness_market": market,
        "broker_readiness_route_broker_route_readiness_gap_pairs": 0,
        "broker_readiness_route_broker_route_readiness_ops_launch_controls_ready": ready,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": 1,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": 0,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs": 1,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs": 0,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs": 0,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs": 0,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs": 0,
        "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs": 0,
    }


def test_scaleup_plan_accepts_clean_shadow_scaleup():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        order_exposure_summary=exposure_summary(True),
        thresholds=ScaleUpThresholds(
            target_mode="shadow",
            max_scale_multiplier=1.5,
            min_shadow_sessions=2,
            min_worst_order_fill_rate=0.9,
            max_worst_adverse_slippage=0.05,
            max_orders_per_session=3,
            max_session_notional=2000.0,
            max_gross_notional=2000.0,
            max_abs_net_delta=100.0,
            max_abs_net_vega=250.0,
            max_telemetry_age_ns=5_000_000_000,
            max_open_order_count=2,
            max_open_order_qty=75.0,
            max_open_order_notional=1_000.0,
            max_open_order_age_ns=5_000_000_000.0,
            max_gross_position_qty=150.0,
            max_abs_net_position_qty=75.0,
            max_lifecycle_orders=6,
            max_replace_orders=2,
            stop_loss=500.0,
            allowed_adapters=("arrow_money",),
        ),
    )

    assert report.ready
    plan = report.plan.iloc[0]
    assert plan["max_orders_per_session"] == 3
    assert plan["max_notional_per_session"] == 2000.0
    assert report.summary.iloc[0]["recommendation"] == "scale_up_with_controls"
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.config["identity"]["strategy"] == "lead_lag_taker"
    assert report.config["identity"]["market"] == "india_nse_index_derivatives"
    assert report.config["kill_switches"]["max_worst_adverse_slippage"] == 0.05
    assert report.config["kill_switches"]["max_telemetry_age_ns"] == 5_000_000_000
    assert report.config["kill_switches"]["max_lifecycle_orders"] == 6
    assert report.config["kill_switches"]["max_replace_orders"] == 2
    assert report.config["kill_switches"]["max_open_order_count"] == 2
    assert report.config["kill_switches"]["max_open_order_notional"] == 1000.0
    assert report.config["kill_switches"]["max_open_order_age_ns"] == 5_000_000_000.0
    assert report.config["kill_switches"]["max_gross_position_qty"] == 150.0
    assert report.config["kill_switches"]["max_gross_notional"] == 2000.0
    assert report.config["kill_switches"]["max_abs_net_delta"] == 100.0
    assert report.config["kill_switches"]["max_abs_net_vega"] == 250.0


def test_scaleup_plan_can_require_expected_strategy_and_market():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True, strategy="leadlag", market="india_nse_index_derivatives"),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        thresholds=ScaleUpThresholds(
            expected_strategy="lead_lag_taker",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert report.ready
    assert report.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["expected_strategy"] == "lead_lag_taker"
    assert report.config["identity"]["expected_market"] == "india_nse_index_derivatives"


def test_scaleup_plan_caps_notional_with_strategy_portfolio_allocation():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        strategy_portfolio_summary=strategy_portfolio_summary(True),
        strategy_portfolio_allocations=strategy_portfolio_allocations(allocation_notional=1200.0),
        thresholds=ScaleUpThresholds(max_scale_multiplier=2.0, require_strategy_portfolio=True),
    )

    assert report.ready
    plan = report.plan.iloc[0]
    assert plan["pre_portfolio_max_notional_per_session"] == 3000.0
    assert plan["max_notional_per_session"] == 1200.0
    assert plan["strategy_portfolio_notional_cap_applied"]
    assert report.summary.iloc[0]["strategy_portfolio_ready"]
    assert report.summary.iloc[0]["strategy_portfolio_selected_profile"] == "leadlag"
    assert report.summary.iloc[0]["strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert report.summary.iloc[0]["strategy_portfolio_allocated_strategy_count"] == 2
    assert report.summary.iloc[0]["strategy_portfolio_allocated_market_count"] == 1
    assert report.summary.iloc[0]["strategy_portfolio_top_strategy_by_weight"] == "lead_lag_taker"
    assert report.summary.iloc[0]["strategy_portfolio_max_strategy_allocation_weight"] == 0.45
    assert report.summary.iloc[0]["strategy_portfolio_max_market_allocation_weight"] == 0.90
    assert report.summary.iloc[0]["strategy_portfolio_leadlag_edge_lineage_ready"]
    assert (
        report.summary.iloc[0][
            "strategy_portfolio_leadlag_edge_lineage_contract_sha256"
        ]
        == "c" * 64
    )
    assert report.config["strategy_portfolio"]["required"]
    assert report.config["strategy_portfolio"]["selected_strategy"] == "lead_lag_taker"
    assert report.config["strategy_portfolio"]["selected_market"] == "india_nse_index_derivatives"
    assert report.config["strategy_portfolio"]["selected_allocation_notional"] == 1200.0
    assert report.config["strategy_portfolio"]["min_strategy_count"] == 2
    assert report.config["strategy_portfolio"]["min_market_count"] == 1
    assert report.config["strategy_portfolio"]["max_strategy_weight"] == 0.60
    assert report.config["strategy_portfolio"]["max_market_weight"] == 0.90
    assert report.config["strategy_portfolio"]["allocated_strategy_count"] == 2
    assert report.config["strategy_portfolio"]["allocated_market_count"] == 1
    assert report.config["strategy_portfolio"]["top_strategy_by_weight"] == "lead_lag_taker"
    assert report.config["strategy_portfolio"]["top_market_by_weight"] == "india_nse_index_derivatives"
    assert report.config["strategy_portfolio"]["max_strategy_allocation_weight"] == 0.45
    assert report.config["strategy_portfolio"]["max_market_allocation_weight"] == 0.90
    assert report.config["strategy_portfolio"]["leadlag_edge_lineage_required"]
    assert report.config["strategy_portfolio"]["leadlag_edge_lineage_ready"]
    assert (
        report.config["strategy_portfolio"][
            "leadlag_edge_lineage_contract_version"
        ]
        == "leadlag_edge_lineage/v1"
    )
    assert report.config["strategy_portfolio"]["notional_cap_applied"]
    assert report.config["limits"]["pre_portfolio_max_notional_per_session"] == 3000.0
    assert report.config["limits"]["max_notional_per_session"] == 1200.0


def test_scaleup_plan_blocks_legacy_leadlag_portfolio_without_edge_lineage():
    allocations = strategy_portfolio_allocations().drop(
        columns=list(LEADLAG_LINEAGE_FIELDS)
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        strategy_portfolio_summary=strategy_portfolio_summary(True),
        strategy_portfolio_allocations=allocations,
        thresholds=ScaleUpThresholds(
            max_scale_multiplier=2.0,
            require_strategy_portfolio=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert "strategy_portfolio_leadlag_edge_lineage_ready" in failed
    assert not report.plan.loc[0, "strategy_portfolio_selected_eligible"]
    assert (
        report.plan.loc[0, "strategy_portfolio_selected_eligibility_reason"]
        == "strategy_portfolio_leadlag_edge_lineage_not_ready"
    )
    assert report.plan.loc[0, "strategy_portfolio_selected_allocation_notional"] == 0.0
    assert not report.plan.loc[0, "strategy_portfolio_notional_cap_applied"]


def test_scaleup_plan_blocks_required_missing_strategy_portfolio():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "strategy_portfolio_available" in failed
    assert report.config["strategy_portfolio"]["required"]
    assert not report.config["strategy_portfolio"]["provided"]
    assert report.config["primary_blocker"]["check"] == "strategy_portfolio_available"


def test_scaleup_plan_blocks_strategy_portfolio_without_matching_allocation():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        strategy_portfolio_summary=strategy_portfolio_summary(True),
        strategy_portfolio_allocations=strategy_portfolio_allocations(
            strategy="parity_box",
            profile="parity",
            allocation_notional=1200.0,
        ),
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "strategy_portfolio_allocation_available" in failed
    assert "strategy_portfolio_allocation_positive" in failed
    assert not report.summary.iloc[0]["strategy_portfolio_selected_eligible"]
    assert report.config["strategy_portfolio"]["selected_allocation_notional"] == 0.0


def test_scaleup_plan_blocks_wrong_evidence_identity():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True, strategy="imbalance", market="us_equities_regular"),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        thresholds=ScaleUpThresholds(
            expected_strategy="leadlag",
            expected_market="india_nse_index_derivatives",
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"evidence_strategy_matches", "evidence_market_matches"} <= failed
    assert report.config["identity"]["strategy"] == "imbalance"
    assert report.config["identity"]["expected_strategy"] == "lead_lag_taker"


def test_scaleup_plan_accepts_required_ready_proof_refresh():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        proof_refresh_summary=proof_refresh_summary(True, proof_source="latest"),
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["proof_refresh_ready"]
    assert report.summary.iloc[0]["proof_source"] == "latest"
    assert report.config["proof_freshness"]["required"]
    assert report.config["proof_freshness"]["ready"]
    assert report.config["proof_freshness"]["strategy"] == "lead_lag_taker"
    assert report.config["proof_freshness"]["market"] == "india_nse_index_derivatives"
    assert report.config["proof_freshness"]["proof_source"] == "latest"


def test_scaleup_plan_blocks_mismatched_proof_refresh_identity():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True, strategy="leadlag", market="india_nse_index_derivatives"),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        proof_refresh_summary=proof_refresh_summary(
            True,
            proof_source="latest",
            strategy="surface_mm",
            market="us_options_regular",
            mixed_identity=True,
        ),
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "proof_refresh_identity_consistent",
        "proof_refresh_strategy_matches",
        "proof_refresh_market_matches",
    } <= failed
    assert report.summary.iloc[0]["proof_refresh_strategy"] == "surface_mm"
    assert report.summary.iloc[0]["proof_refresh_market"] == "us_options_regular"
    assert report.config["proof_freshness"]["mixed_identity"]


def test_scaleup_plan_carries_shadow_proof_refresh_identity():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(
            True,
            proof_refresh_sessions=2,
            proof_refresh_strategy="leadlag",
            proof_refresh_market="india_nse_index_derivatives",
        ),
        launch_summary=launch_summary(True),
        proof_refresh_summary=proof_refresh_summary(True, proof_source="latest"),
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["shadow_proof_refresh_sessions"] == 2
    assert report.summary.iloc[0]["shadow_proof_refresh_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["shadow_proof_refresh_market"] == "india_nse_index_derivatives"
    assert report.config["shadow_proof_freshness"]["sessions"] == 2
    assert report.config["shadow_proof_freshness"]["strategy"] == "lead_lag_taker"


def test_scaleup_plan_blocks_bad_shadow_proof_refresh_identity():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True, strategy="leadlag", market="india_nse_index_derivatives"),
        shadow_comparison_summary=shadow_summary(
            True,
            proof_refresh_sessions=2,
            proof_refresh_ready_sessions=1,
            proof_refresh_strategy="surface_mm",
            proof_refresh_market="us_options_regular",
            proof_refresh_mixed_identity_sessions=1,
        ),
        launch_summary=launch_summary(True),
        proof_refresh_summary=proof_refresh_summary(True, proof_source="latest"),
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_proof_refresh_ready",
        "shadow_proof_refresh_identity_consistent",
        "shadow_proof_refresh_strategy_matches",
        "shadow_proof_refresh_market_matches",
    } <= failed
    assert report.summary.iloc[0]["shadow_proof_refresh_strategy"] == "surface_mm"
    assert report.config["shadow_proof_freshness"]["mixed_identity_sessions"] == 1


def test_scaleup_plan_carries_shadow_broker_readiness_proof():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(
            True,
            broker_readiness_sessions=2,
            broker_vendor_data_readiness_sessions=2,
            broker_adapter="arrow_money",
            broker_adapter_count=1,
            broker_route_readiness_sessions=2,
            broker_route_readiness_strategy="lead_lag_taker",
            broker_route_readiness_market="india_nse_index_derivatives",
            broker_dispatch_roundtrip_sessions=2,
            broker_dispatch_roundtrip_strategy="lead_lag_taker",
            broker_dispatch_roundtrip_market="india_nse_index_derivatives",
            broker_dispatch_roundtrip_scenario_count=1,
            broker_route_dispatch_roundtrip_sessions=2,
            broker_route_dispatch_roundtrip_strategy="lead_lag_taker",
            broker_route_dispatch_roundtrip_market="india_nse_index_derivatives",
            broker_route_dispatch_roundtrip_scenario_count=1,
        ),
        launch_summary=launch_summary(True),
    )

    assert report.ready
    assert report.summary.iloc[0]["shadow_broker_readiness_sessions"] == 2
    assert report.summary.iloc[0]["shadow_broker_vendor_data_readiness_ready_sessions"] == 2
    assert report.summary.iloc[0]["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["shadow_broker_readiness"]["sessions"] == 2
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert report.config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_scaleup_plan_blocks_bad_shadow_broker_readiness_proof():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(
            True,
            broker_readiness_sessions=1,
            broker_readiness_ready_sessions=0,
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=0,
            max_broker_vendor_data_readiness_failed_checks=1,
            broker_adapter="",
            broker_adapter_count=2,
            missing_broker_adapter_sessions=1,
            broker_route_readiness_sessions=2,
            broker_route_readiness_ready_sessions=1,
            broker_route_readiness_strategy="surface_mm",
            broker_route_readiness_market="us_options_regular",
            max_broker_route_readiness_gap_pairs=2,
            broker_dispatch_roundtrip_sessions=2,
            broker_dispatch_roundtrip_ready_sessions=1,
            broker_dispatch_roundtrip_strategy="surface_mm",
            broker_dispatch_roundtrip_market="us_options_regular",
            broker_dispatch_roundtrip_scenario_count=2,
            max_broker_dispatch_roundtrip_missing_request_acks=1,
            max_broker_dispatch_roundtrip_rejected_orders=1,
            max_broker_dispatch_roundtrip_unmatched_acks=1,
            broker_route_dispatch_roundtrip_sessions=2,
            broker_route_dispatch_roundtrip_ready_sessions=1,
            broker_route_dispatch_roundtrip_strategy="surface_mm",
            broker_route_dispatch_roundtrip_market="us_options_regular",
            broker_route_dispatch_roundtrip_scenario_count=2,
        ),
        launch_summary=launch_summary(True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_broker_readiness_present_for_accepted_sessions",
        "shadow_broker_readiness_ready",
        "shadow_broker_vendor_data_readiness_ready",
        "shadow_broker_vendor_data_readiness_failed_checks",
        "shadow_broker_adapter_consistent",
        "shadow_broker_route_readiness_ready",
        "shadow_broker_route_readiness_strategy_matches",
        "shadow_broker_route_readiness_market_matches",
        "shadow_broker_route_readiness_gap_pairs",
        "shadow_broker_dispatch_roundtrip_ready",
        "shadow_broker_dispatch_roundtrip_strategy_matches",
        "shadow_broker_dispatch_roundtrip_market_matches",
        "shadow_broker_dispatch_roundtrip_scenario_consistent",
        "shadow_broker_dispatch_roundtrip_missing_request_acks",
        "shadow_broker_dispatch_roundtrip_rejected_orders",
        "shadow_broker_dispatch_roundtrip_unmatched_acks",
        "shadow_broker_route_dispatch_roundtrip_ready",
        "shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "shadow_broker_route_dispatch_roundtrip_market_matches",
        "shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.summary.iloc[0]["shadow_broker_route_readiness_strategy"] == "surface_mm"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_scaleup_plan_blocks_partial_shadow_broker_vendor_data_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(
            True,
            broker_readiness_sessions=2,
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
            broker_adapter="arrow_money",
            broker_adapter_count=1,
        ),
        launch_summary=launch_summary(True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "shadow_broker_vendor_data_readiness_provided",
        "shadow_broker_vendor_data_readiness_ready",
    } <= failed
    assert report.summary.iloc[0]["shadow_broker_vendor_data_readiness_sessions"] == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["provided_sessions"] == 1


def test_scaleup_plan_accepts_required_instrument_metadata():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        instrument_metadata_summary=instrument_metadata_summary(True, parse_coverage=1.0),
        thresholds=ScaleUpThresholds(require_instrument_metadata=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["instrument_metadata_passed"]
    assert report.summary.iloc[0]["instrument_parse_coverage"] == 1.0
    assert report.config["instrument_metadata"]["required"]
    assert report.config["instrument_metadata"]["passed"]


def test_scaleup_plan_accepts_required_broker_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            runtime_session_provided=True,
            runtime_session_ready=True,
            runtime_guard_action="continue",
            runtime_guard_halted=False,
            schema_reviewed=True,
            schema_review_mode="reviewed_vendor_mapping",
        ),
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["broker_readiness_ready"]
    assert report.summary.iloc[0]["broker_schema_reviewed"]
    assert report.summary.iloc[0]["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["broker_readiness"]["required"]
    assert report.config["broker_readiness"]["ready"]
    assert report.config["broker_readiness"]["schema_reviewed"]
    assert report.config["broker_readiness"]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.summary.iloc[0]["broker_runtime_session_ready"]
    assert report.summary.iloc[0]["broker_runtime_guard_action"] == "continue"
    assert report.summary.iloc[0]["broker_runtime_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["broker_runtime_market"] == "india_nse_index_derivatives"
    assert report.config["broker_readiness"]["runtime_session"]["provided"]
    assert report.config["broker_readiness"]["runtime_session"]["ready"]
    assert report.config["broker_readiness"]["runtime_session"]["strategy"] == "lead_lag_taker"
    assert report.config["broker_readiness"]["runtime_session"]["market"] == "india_nse_index_derivatives"


def test_scaleup_plan_accepts_required_broker_resume_gate():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            resume_gate_provided=True,
            resume_gate_ready=True,
            resume_proof_refresh_ready=True,
        ),
        thresholds=ScaleUpThresholds(require_resume_gate=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["broker_resume_gate_required"]
    assert report.summary.iloc[0]["broker_resume_gate_provided"]
    assert report.summary.iloc[0]["broker_resume_gate_ready"]
    assert report.summary.iloc[0]["broker_resume_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["broker_resume_proof_refresh_market"] == "india_nse_index_derivatives"
    assert report.config["broker_readiness"]["required"]
    assert report.config["broker_readiness"]["resume_gate"]["required"]
    assert report.config["broker_readiness"]["resume_gate"]["ready"]
    assert report.config["broker_readiness"]["resume_gate"]["proof_refresh_strategy"] == "lead_lag_taker"


def test_scaleup_plan_carries_broker_resume_route_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            resume_gate_provided=True,
            resume_gate_ready=True,
            resume_proof_refresh_ready=True,
            resume_broker_route_readiness_required=True,
            resume_broker_route_readiness_provided=True,
            resume_broker_route_readiness_ready=True,
            resume_broker_route_readiness_route_ready_pairs=1,
            resume_broker_route_readiness_recommendation="route_ready",
            resume_broker_route_readiness_ops_launch_controls_ready=True,
            resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
            resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
            resume_incident_broker_route_readiness_required=True,
            resume_incident_broker_route_readiness_provided=True,
            resume_incident_broker_route_readiness_ready=True,
            resume_incident_broker_route_readiness_route_ready_pairs=1,
            resume_incident_broker_route_readiness_recommendation="route_ready",
            resume_incident_broker_route_readiness_ops_launch_controls_ready=True,
            resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
            resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
        ),
        thresholds=ScaleUpThresholds(require_resume_gate=True),
    )

    summary = report.summary.iloc[0]
    resume_gate = report.config["broker_readiness"]["resume_gate"]
    assert report.ready
    assert summary["broker_resume_broker_route_readiness_required"]
    assert summary["broker_resume_broker_route_readiness_ready"]
    assert summary["broker_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["broker_resume_incident_broker_route_readiness_ready"]
    assert summary["broker_resume_incident_broker_route_readiness_market"] == "india_nse_index_derivatives"
    assert resume_gate["broker_route_readiness"]["ready"]
    assert resume_gate["broker_route_readiness"]["ops_broker_roundtrip_portfolio_safe_runs"] == 1
    assert resume_gate["incident_broker_route_readiness"]["ready"]
    assert resume_gate["incident_broker_route_readiness"]["route_ready_pairs"] == 1


def test_scaleup_plan_accepts_required_broker_dispatch_roundtrip():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_required"]
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_provided"]
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_ready"]
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_market"] == "india_nse_index_derivatives"
    assert report.summary.iloc[0]["broker_route_dispatch_roundtrip_provided"]
    assert report.summary.iloc[0]["broker_route_dispatch_roundtrip_ready"]
    assert report.summary.iloc[0]["broker_route_dispatch_roundtrip_strategy"] == "lead_lag_taker"
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["required"]
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["ready"]
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-1"
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_failed_checks"] == 0
    assert report.summary.iloc[0]["broker_route_enable_dispatch_roundtrip_failed_checks"] == 0
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["failed_checks"] == 0
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_enable_dispatch_roundtrip"][
        "failed_checks"
    ] == 0
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]["provided"]
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]["requests"] == 2


def test_scaleup_plan_carries_broker_readiness_vendor_market_data_batch():
    datasets_json = json.dumps(
        [
            {
                "dataset": "nifty_day1",
                "ready": True,
                "source_file_sha256": "a" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "vendor_intake_draft",
            }
        ],
        sort_keys=True,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            dispatch_roundtrip_vendor_market_data_batch_provided=True,
            dispatch_roundtrip_vendor_market_data_batch_ready=True,
            dispatch_roundtrip_vendor_market_data_batch_adapter="arrow_money",
            dispatch_roundtrip_vendor_market_data_batch_kind="ticks",
            dispatch_roundtrip_vendor_market_data_batch_manifest_run_type="vendor_market_data_batch_pipeline",
            dispatch_roundtrip_vendor_market_data_batch_market="india_nse_index_derivatives",
            dispatch_roundtrip_vendor_market_data_batch_dataset_count=2,
            dispatch_roundtrip_vendor_market_data_batch_ready_datasets=2,
            dispatch_roundtrip_vendor_market_data_batch_ready_rate=1.0,
            dispatch_roundtrip_vendor_market_data_batch_unique_source_files=2,
            dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints=1,
            dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage=1.0,
            dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage=1.0,
            dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts=1,
            dispatch_roundtrip_vendor_market_data_batch_mapping_sources="vendor_intake_draft",
            dispatch_roundtrip_vendor_market_data_batch_comparison_accepted=True,
            dispatch_roundtrip_vendor_market_data_batch_datasets_json=datasets_json,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_scaleup_plan_carries_target_application_vendor_market_data_batch():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert bool(summary[f"{prefix}_application_lineage_consistency_required"])
    assert bool(summary[f"{prefix}_application_lineage_consistent"])
    assert bool(summary["broker_vendor_market_data_batch_lineage_match_required"])
    assert bool(summary["broker_vendor_market_data_batch_lineage_matches"])
    assert summary["vendor_market_data_batch_application_lineage_sha256"] == (
        summary["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    assert summary[f"{prefix}_application_lineage_sha256"] == (
        summary["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    assert bool(summary[f"{prefix}_lineage_match_required"])
    assert bool(summary[f"{prefix}_lineage_matches"])
    expected_lineage_sha256 = summary[f"{prefix}_application_lineage_sha256"]
    for field in (
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
    ):
        assert summary[f"{prefix}_{field}"] == expected_lineage_sha256
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert vendor["mapping_source_mode"] == "per_dataset_verified_target_application"
    assert vendor["mapping_application_count"] == 2
    assert vendor["unique_mapping_applications"] == 2
    assert vendor["target_application_coverage"] == 1.0
    assert vendor["application_lineage_consistency_required"]
    assert vendor["application_lineage_consistent"]
    assert len(vendor["application_lineage_sha256"]) == 64
    assert vendor["datasets"][0]["mapping_application_id"] == "mapping-app-day1"
    assert vendor["datasets"][1]["target_intake_receipt_id"] == "target-intake-day2"
    lineage = report.config["broker_readiness"]["dispatch_roundtrip"][
        "vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["required"]
    assert lineage["matches"]
    assert lineage["current_application_lineage_sha256"] == (
        lineage["broker_application_lineage_sha256"]
    )
    assert lineage["carried_application_lineage_sha256"] == (
        lineage["broker_application_lineage_sha256"]
    )
    final_lineage = report.config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    for field in (
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
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == expected_lineage_sha256
    readiness_final_prefix = (
        "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    for field in (
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
    ):
        assert summary[f"{readiness_final_prefix}_{field}"] == (
            expected_lineage_sha256
        )
    scaleup_final_lineage = report.config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_final_lineage["required"]
    assert scaleup_final_lineage["matches"]
    for field in (
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
        "carried_application_lineage_sha256",
    ):
        assert scaleup_final_lineage[field] == expected_lineage_sha256
    readiness_complete_final_prefix = (
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    complete_final_digest_fields = (
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
        "dispatch_final_review_carried_application_lineage_sha256",
        "send_final_review_carried_application_lineage_sha256",
        "ack_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_complete_final_review_carried_application_lineage_sha256",
    )
    for field in (
        *complete_final_digest_fields,
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
        "scaleup_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{readiness_complete_final_prefix}_{field}"] == (
            expected_lineage_sha256
        )
    scaleup_complete_final_lineage = report.config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_complete_final_lineage["required"]
    assert scaleup_complete_final_lineage["matches"]
    for field in (
        *complete_final_digest_fields,
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert scaleup_complete_final_lineage[field] == expected_lineage_sha256
    readiness_extended_complete_final_prefix = (
        "broker_readiness_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    extended_complete_final_digest_fields = (
        *complete_final_digest_fields,
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
        "send_complete_final_review_carried_application_lineage_sha256",
        "ack_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
    )
    for field in (
        *extended_complete_final_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{readiness_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    scaleup_extended_complete_final_lineage = report.config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_extended_complete_final_lineage["required"]
    assert scaleup_extended_complete_final_lineage["matches"]
    for field in (
        *extended_complete_final_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert (
            scaleup_extended_complete_final_lineage[field]
            == expected_lineage_sha256
        )
    readiness_latest_extended_complete_final_prefix = (
        "broker_readiness_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    latest_extended_complete_final_digest_fields = (
        *extended_complete_final_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
        "send_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    for field in (
        *latest_extended_complete_final_digest_fields,
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{readiness_latest_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    scaleup_latest_extended_complete_final_lineage = report.config[
        "broker_readiness"
    ]["dispatch_roundtrip"][
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_latest_extended_complete_final_lineage["required"]
    assert scaleup_latest_extended_complete_final_lineage["matches"]
    for field in (
        *latest_extended_complete_final_digest_fields,
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert (
            scaleup_latest_extended_complete_final_lineage[field]
            == expected_lineage_sha256
        )
    readiness_current_latest_extended_complete_final_prefix = (
        "broker_readiness_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    current_latest_extended_complete_final_digest_fields = (
        *extended_complete_final_digest_fields,
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
        "send_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    current_latest_extended_complete_final_stage_fields = (
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
    assert bool(
        summary[
            f"{readiness_current_latest_extended_complete_final_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[
            f"{readiness_current_latest_extended_complete_final_prefix}_lineage_matches"
        ]
    )
    for field in (
        *current_latest_extended_complete_final_digest_fields,
        *current_latest_extended_complete_final_stage_fields,
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{readiness_current_latest_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    scaleup_current_latest_extended_complete_final_lineage = report.config[
        "broker_readiness"
    ]["dispatch_roundtrip"][
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_current_latest_extended_complete_final_lineage["required"]
    assert scaleup_current_latest_extended_complete_final_lineage["matches"]
    for field in (
        *current_latest_extended_complete_final_digest_fields,
        *current_latest_extended_complete_final_stage_fields,
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert (
            scaleup_current_latest_extended_complete_final_lineage[field]
            == expected_lineage_sha256
        )
    readiness_reconciled_current_latest_extended_complete_final_prefix = (
        "broker_readiness_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    reconciled_current_latest_extended_complete_final_stage_fields = (
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    assert bool(
        summary[
            f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[
            f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches"
        ]
    )
    for field in (
        *current_latest_extended_complete_final_digest_fields,
        *current_latest_extended_complete_final_stage_fields,
        *reconciled_current_latest_extended_complete_final_stage_fields,
        "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    scaleup_reconciled_current_latest_extended_complete_final_lineage = report.config[
        "broker_readiness"
    ]["dispatch_roundtrip"][
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_view_59_fields = {
        "required",
        "matches",
        *current_latest_extended_complete_final_digest_fields,
        *current_latest_extended_complete_final_stage_fields,
        *reconciled_current_latest_extended_complete_final_stage_fields,
        "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }
    assert set(scaleup_reconciled_current_latest_extended_complete_final_lineage) == (
        expected_view_59_fields
    )
    assert len(expected_view_59_fields) == 58
    assert scaleup_reconciled_current_latest_extended_complete_final_lineage[
        "required"
    ]
    assert scaleup_reconciled_current_latest_extended_complete_final_lineage[
        "matches"
    ]
    for field in expected_view_59_fields - {"required", "matches"}:
        assert (
            scaleup_reconciled_current_latest_extended_complete_final_lineage[field]
            == expected_lineage_sha256
        )
    readiness_verified_reconciled_current_latest_extended_complete_final_prefix = (
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    source_view_66 = broker_readiness_view_66_target_application_lineage_comparison(
        target_application_vendor_market_data_batch_config()
    )
    assert len(source_view_66) == 65
    assert bool(
        summary[
            f"{readiness_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[
            f"{readiness_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches"
        ]
    )
    for field, value in source_view_66.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[
            f"{readiness_verified_reconciled_current_latest_extended_complete_final_prefix}_{field}"
        ] == value
    assert summary[
        f"{readiness_verified_reconciled_current_latest_extended_complete_final_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    scaleup_verified_reconciled_current_latest_extended_complete_final_lineage = (
        report.config["broker_readiness"]["dispatch_roundtrip"][
            "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
        ]
    )
    expected_view_67 = scaleup_view_67_target_application_lineage_comparison(
        target_application_vendor_market_data_batch_config()
    )
    assert len(scaleup_verified_reconciled_current_latest_extended_complete_final_lineage) == 66
    assert scaleup_verified_reconciled_current_latest_extended_complete_final_lineage == (
        expected_view_67
    )
    readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix = (
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    source_view_74 = broker_readiness_view_74_target_application_lineage_comparison(
        target_application_vendor_market_data_batch_config()
    )
    assert len(source_view_74) == 73
    assert bool(
        summary[
            f"{readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[
            f"{readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches"
        ]
    )
    for field, value in source_view_74.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[
            f"{readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_{field}"
        ] == value
    assert summary[
        f"{readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage = (
        report.config["broker_readiness"]["dispatch_roundtrip"][
            "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
        ]
    )
    expected_view_75 = scaleup_view_75_target_application_lineage_comparison(
        target_application_vendor_market_data_batch_config()
    )
    assert len(scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage) == 74
    assert scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage == (
        expected_view_75
    )
    expected_target_checks = {
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_broker_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_application_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_prior_scaleup_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_cutover_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_route_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_dispatch_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_send_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_ack_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_roundtrip_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_review_carried_lineage_sha256_matches",
    }
    readiness_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final"
    )
    expected_target_checks.update(
        {
            f"{readiness_check_prefix}_lineage_match_required",
            f"{readiness_check_prefix}_lineage_matches",
            f"{readiness_check_prefix}_source_lineage_sha256_matches",
            f"{readiness_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{readiness_check_prefix}_compatibility_readiness_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_prior_scaleup_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_prior_cutover_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_route_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_dispatch_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_send_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_ack_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_roundtrip_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_readiness_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_scaleup_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_cutover_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_route_enable_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_dispatch_plan_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_send_packet_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_ack_reconciliation_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_roundtrip_final_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_broker_readiness_review_carried_lineage_sha256_matches",
            f"{readiness_check_prefix}_scaleup_final_review_carried_lineage_sha256_matches",
        }
    )
    complete_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final"
    )
    expected_target_checks.update(
        {
            f"{complete_check_prefix}_lineage_match_required",
            f"{complete_check_prefix}_lineage_matches",
            f"{complete_check_prefix}_source_lineage_sha256_matches",
            f"{complete_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{complete_check_prefix}_compatibility_broker_readiness_review_carried_lineage_sha256_matches",
            f"{complete_check_prefix}_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
            f"{complete_check_prefix}_scaleup_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for stage in (
        "prior_scaleup",
        "prior_cutover",
        "route",
        "dispatch",
        "send",
        "ack",
        "roundtrip",
        "readiness",
        "scaleup_review",
        "cutover_review",
        "route_enable_review",
        "dispatch_plan_review",
        "send_packet_review",
        "ack_reconciliation_review",
        "roundtrip_final_review",
        "broker_readiness_review",
        "scaleup_final_review",
        "cutover_final_review",
        "route_final_review",
        "dispatch_final_review",
        "send_final_review",
        "ack_complete_final_review",
        "roundtrip_complete_final_review",
    ):
        expected_target_checks.add(
            f"{complete_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_extended_complete_final"
    )
    expected_target_checks.update(
        {
            f"{extended_check_prefix}_lineage_match_required",
            f"{extended_check_prefix}_lineage_matches",
            f"{extended_check_prefix}_source_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
            f"{extended_check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{extended_check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for stage in (
        "prior_scaleup",
        "prior_cutover",
        "route",
        "dispatch",
        "send",
        "ack",
        "roundtrip",
        "readiness",
        "scaleup_review",
        "cutover_review",
        "route_enable_review",
        "dispatch_plan_review",
        "send_packet_review",
        "ack_reconciliation_review",
        "roundtrip_final_review",
        "broker_readiness_review",
        "scaleup_final_review",
        "cutover_final_review",
        "route_final_review",
        "dispatch_final_review",
        "send_final_review",
        "ack_complete_final_review",
        "roundtrip_complete_final_review",
        "scaleup_complete_final_review",
        "cutover_complete_final_review",
        "route_complete_final_review",
        "dispatch_complete_final_review",
        "send_complete_final_review",
        "ack_extended_complete_final_review",
        "roundtrip_extended_complete_final_review",
    ):
        expected_target_checks.add(
            f"{extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    latest_extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_latest_extended_complete_final"
    )
    expected_target_checks.update(
        {
            f"{latest_extended_check_prefix}_lineage_match_required",
            f"{latest_extended_check_prefix}_lineage_matches",
            f"{latest_extended_check_prefix}_source_lineage_sha256_matches",
            f"{latest_extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{latest_extended_check_prefix}_compatibility_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{latest_extended_check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{latest_extended_check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for stage in (
        "prior_scaleup",
        "prior_cutover",
        "route",
        "dispatch",
        "send",
        "ack",
        "roundtrip",
        "readiness",
        "scaleup_review",
        "cutover_review",
        "route_enable_review",
        "dispatch_plan_review",
        "send_packet_review",
        "ack_reconciliation_review",
        "roundtrip_final_review",
        "broker_readiness_review",
        "scaleup_final_review",
        "cutover_final_review",
        "route_final_review",
        "dispatch_final_review",
        "send_final_review",
        "ack_complete_final_review",
        "roundtrip_complete_final_review",
        "scaleup_complete_final_review",
        "cutover_complete_final_review",
        "route_complete_final_review",
        "dispatch_complete_final_review",
        "send_complete_final_review",
        "ack_extended_complete_final_review",
        "roundtrip_extended_complete_final_review",
        "broker_readiness_extended_complete_final_review",
        "scaleup_extended_complete_final_review",
        "cutover_extended_complete_final_review",
        "route_extended_complete_final_review",
        "dispatch_extended_complete_final_review",
        "send_extended_complete_final_review",
        "ack_latest_extended_complete_final_review",
        "roundtrip_latest_extended_complete_final_review",
    ):
        expected_target_checks.add(
            f"{latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    current_latest_extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_current_latest_extended_complete_final"
    )
    expected_target_checks.update(
        {
            f"{current_latest_extended_check_prefix}_lineage_match_required",
            f"{current_latest_extended_check_prefix}_lineage_matches",
            f"{current_latest_extended_check_prefix}_source_lineage_sha256_matches",
            f"{current_latest_extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{current_latest_extended_check_prefix}_compatibility_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_extended_check_prefix}_broker_readiness_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{current_latest_extended_check_prefix}_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for field in current_latest_extended_complete_final_digest_fields:
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
        expected_target_checks.add(
            f"{current_latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    for field in current_latest_extended_complete_final_stage_fields:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        expected_target_checks.add(
            f"{current_latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    reconciled_current_latest_extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_reconciled_current_latest_extended_complete_final"
    )
    expected_target_checks.update(
        {
            f"{reconciled_current_latest_extended_check_prefix}_lineage_match_required",
            f"{reconciled_current_latest_extended_check_prefix}_lineage_matches",
            f"{reconciled_current_latest_extended_check_prefix}_source_lineage_sha256_matches",
            f"{reconciled_current_latest_extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{reconciled_current_latest_extended_check_prefix}_compatibility_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{reconciled_current_latest_extended_check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{reconciled_current_latest_extended_check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{reconciled_current_latest_extended_check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for field in current_latest_extended_complete_final_digest_fields:
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
        expected_target_checks.add(
            f"{reconciled_current_latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    for field in (
        *current_latest_extended_complete_final_stage_fields,
        *reconciled_current_latest_extended_complete_final_stage_fields,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        expected_target_checks.add(
            f"{reconciled_current_latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    verified_reconciled_current_latest_extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_target_checks.update(
        {
            f"{verified_reconciled_current_latest_extended_check_prefix}_lineage_match_required",
            f"{verified_reconciled_current_latest_extended_check_prefix}_lineage_matches",
            f"{verified_reconciled_current_latest_extended_check_prefix}_source_lineage_sha256_matches",
            f"{verified_reconciled_current_latest_extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{verified_reconciled_current_latest_extended_check_prefix}_compatibility_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{verified_reconciled_current_latest_extended_check_prefix}_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{verified_reconciled_current_latest_extended_check_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for field in set(source_view_66) - {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_target_checks.add(
            f"{verified_reconciled_current_latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    confirmed_verified_reconciled_current_latest_extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_target_checks.update(
        {
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_lineage_match_required",
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_lineage_matches",
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_source_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_compatibility_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    for field in set(source_view_74) - {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_target_checks.add(
            f"{confirmed_verified_reconciled_current_latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_target_checks <= passed
    source_mode = report.checks.loc[
        report.checks["check"]
        == "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode"
    ]
    assert len(source_mode) == 1
    assert source_mode["passed"].astype(bool).all()


def test_scaleup_plan_blocks_broker_readiness_view_34_drift_while_preserving_view_27():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    comparison = broker_readiness_view_34_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    prefix = (
        "roundtrip_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_lineage_match_required"] = comparison[
        "required"
    ]
    broker_readiness.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
    for field, value in comparison.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "broker_readiness_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_complete_final_lineage = report.config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        scaleup_complete_final_lineage["broker_application_lineage_sha256"]
        == lineage_sha256
    )
    assert (
        scaleup_complete_final_lineage[
            "broker_readiness_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        scaleup_complete_final_lineage["carried_application_lineage_sha256"]
        == lineage_sha256
    )
    assert scaleup_complete_final_lineage["broker_application_lineage_sha256"] != (
        "f" * 64
    )
    scaleup_extended_complete_final_lineage = report.config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        scaleup_extended_complete_final_lineage[
            "broker_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        scaleup_extended_complete_final_lineage[
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        scaleup_extended_complete_final_lineage[
            "carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )


def test_scaleup_plan_blocks_broker_readiness_view_42_drift_while_preserving_view_35():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    comparison = broker_readiness_view_42_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    prefix = (
        "roundtrip_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_lineage_match_required"] = comparison[
        "required"
    ]
    broker_readiness.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
    for field, value in comparison.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "broker_readiness_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_view_35 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_35["required"]
    assert scaleup_view_35["matches"]
    assert scaleup_view_35["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        scaleup_view_35[
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert scaleup_view_35["carried_application_lineage_sha256"] == lineage_sha256
    assert scaleup_view_35["broker_application_lineage_sha256"] != "f" * 64
    scaleup_view_43 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_43["broker_application_lineage_sha256"] == "f" * 64
    assert (
        scaleup_view_43[
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        scaleup_view_43[
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert scaleup_view_43["carried_application_lineage_sha256"] == lineage_sha256


def test_scaleup_plan_blocks_broker_readiness_view_50_drift_while_preserving_view_43():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    comparison = broker_readiness_view_50_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    prefix = (
        "roundtrip_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_lineage_match_required"] = comparison[
        "required"
    ]
    broker_readiness.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
    for field, value in comparison.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "broker_readiness_current_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_view_43 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_43["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        scaleup_view_43[
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert scaleup_view_43["carried_application_lineage_sha256"] == lineage_sha256
    assert scaleup_view_43["broker_application_lineage_sha256"] != "f" * 64
    scaleup_view_51 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_51["broker_application_lineage_sha256"] == "f" * 64
    assert (
        scaleup_view_51[
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        scaleup_view_51[
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert scaleup_view_51["carried_application_lineage_sha256"] == lineage_sha256


def test_scaleup_plan_blocks_broker_readiness_view_58_drift_while_preserving_view_51():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    comparison = broker_readiness_view_58_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    prefix = (
        "roundtrip_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_lineage_match_required"] = comparison[
        "required"
    ]
    broker_readiness.loc[0, f"{prefix}_lineage_matches"] = comparison["matches"]
    for field, value in comparison.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "broker_readiness_reconciled_current_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        broker_readiness.loc[0, f"{prefix}_{field}"] = value
    direct_prefix = (
        "broker_readiness_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[
        0,
        f"{direct_prefix}_carried_application_lineage_sha256",
    ] = "e" * 64

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_view_51 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_51["required"]
    assert scaleup_view_51["matches"]
    assert scaleup_view_51["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        scaleup_view_51[
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        scaleup_view_51[
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert scaleup_view_51["carried_application_lineage_sha256"] == lineage_sha256
    assert scaleup_view_51["broker_application_lineage_sha256"] != "f" * 64
    scaleup_view_59 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_59["required"]
    assert scaleup_view_59["matches"]
    assert scaleup_view_59["broker_application_lineage_sha256"] == "f" * 64
    assert (
        scaleup_view_59[
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        scaleup_view_59[
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert scaleup_view_59["carried_application_lineage_sha256"] == lineage_sha256


def test_scaleup_plan_blocks_broker_readiness_view_74_drift_while_preserving_view_67():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    drifted_view_74 = (
        broker_readiness_view_74_target_application_lineage_comparison(
            vendor,
            lineage_sha256=drifted_lineage_sha256,
        )
    )
    assert len(drifted_view_74) == 73
    prefix = (
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_lineage_match_required"] = drifted_view_74[
        "required"
    ]
    broker_readiness.loc[0, f"{prefix}_lineage_matches"] = drifted_view_74[
        "matches"
    ]
    for field, value in drifted_view_74.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_view_67 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_67 == scaleup_view_67_target_application_lineage_comparison(
        vendor
    )
    assert scaleup_view_67["broker_application_lineage_sha256"] == lineage_sha256
    assert scaleup_view_67["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    scaleup_view_75 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_75 == scaleup_view_75_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
        scaleup_lineage_sha256=lineage_sha256,
    )


def test_scaleup_plan_requires_broker_readiness_view_74_lineage():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    scaleup_view_67 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_67["required"]
    assert scaleup_view_67["matches"]
    scaleup_view_75 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not scaleup_view_75["required"]
    assert not scaleup_view_75["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_view_74_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    source_prefix = (
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    direct_prefix = (
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    if field == "required":
        broker_readiness.loc[0, f"{source_prefix}_lineage_match_required"] = value
    elif field == "matches":
        broker_readiness.loc[0, f"{source_prefix}_lineage_matches"] = value
    elif field == "carried_application_lineage_sha256":
        broker_readiness.loc[0, f"{direct_prefix}_{field}"] = value
    else:
        broker_readiness.loc[0, f"{source_prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_blocks_broker_readiness_view_66_drift_while_preserving_view_59():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    drifted_view_66 = broker_readiness_view_66_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_66) == 65
    prefix = (
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_lineage_match_required"] = (
        drifted_view_66["required"]
    )
    broker_readiness.loc[0, f"{prefix}_lineage_matches"] = drifted_view_66[
        "matches"
    ]
    for field, value in drifted_view_66.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_view_59 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_59 == scaleup_view_59_target_application_lineage_comparison(
        vendor
    )
    assert scaleup_view_59["broker_application_lineage_sha256"] == lineage_sha256
    assert scaleup_view_59["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    scaleup_view_67 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_67["broker_application_lineage_sha256"] == (
        drifted_lineage_sha256
    )
    assert (
        scaleup_view_67[
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == drifted_lineage_sha256
    )
    assert (
        scaleup_view_67[
            "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert scaleup_view_67["carried_application_lineage_sha256"] == lineage_sha256


def test_scaleup_plan_requires_broker_readiness_view_66_lineage():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_verified_reconciled_current_latest_extended_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    scaleup_view_59 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_59["required"]
    assert scaleup_view_59["matches"]
    scaleup_view_67 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not scaleup_view_67["required"]
    assert not scaleup_view_67["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_verified_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_verified_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_view_66_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    source_prefix = (
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    direct_prefix = (
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    if field == "required":
        broker_readiness.loc[0, f"{source_prefix}_lineage_match_required"] = value
    elif field == "matches":
        broker_readiness.loc[0, f"{source_prefix}_lineage_matches"] = value
    elif field == "carried_application_lineage_sha256":
        broker_readiness.loc[0, f"{direct_prefix}_{field}"] = value
    else:
        broker_readiness.loc[0, f"{source_prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_requires_broker_readiness_view_34_lineage_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_extended_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


def test_scaleup_plan_requires_broker_readiness_view_42_lineage_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_latest_extended_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


def test_scaleup_plan_requires_broker_readiness_view_50_lineage_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_current_latest_extended_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    scaleup_view_43 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_43["required"]
    assert scaleup_view_43["matches"]
    scaleup_view_51 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not scaleup_view_51["required"]
    assert not scaleup_view_51["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_extended_complete_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_extended_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_extended_complete_final_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_view_34_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = (
        "roundtrip_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    if field == "carried_application_lineage_sha256":
        field = (
            "broker_readiness_extended_complete_final_review_"
            "carried_application_lineage_sha256"
        )
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_latest_extended_complete_final_roundtrip_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_latest_extended_complete_final_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_view_42_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = (
        "roundtrip_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_current_latest_extended_complete_final_roundtrip_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_current_latest_extended_complete_final_broker_readiness_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_view_50_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = (
        "roundtrip_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    if field == "carried_application_lineage_sha256":
        field = (
            "broker_readiness_current_latest_extended_complete_final_review_"
            "carried_application_lineage_sha256"
        )
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_requires_broker_readiness_view_58_lineage_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_reconciled_current_latest_extended_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "broker_readiness_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    scaleup_view_51 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_view_51["required"]
    assert scaleup_view_51["matches"]
    scaleup_view_59 = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not scaleup_view_59["required"]
    assert not scaleup_view_59["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_reconciled_current_latest_extended_complete_final_roundtrip_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_reconciled_current_latest_extended_complete_final_broker_readiness_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_view_58_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = (
        "roundtrip_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    if field == "carried_application_lineage_sha256":
        prefix = (
            "broker_readiness_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_blocks_broker_readiness_complete_final_lineage_drift():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    lineage_sha256 = target_application_lineage_sha256(
        target_application_vendor_market_data_batch_config()["datasets"]
    )
    complete_final_sha256 = "f" * 64
    complete_prefix = (
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    broker_readiness.loc[0, f"{complete_prefix}_lineage_match_required"] = True
    broker_readiness.loc[0, f"{complete_prefix}_lineage_matches"] = True
    for field in (
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
        "dispatch_final_review_carried_application_lineage_sha256",
        "send_final_review_carried_application_lineage_sha256",
        "ack_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_complete_final_review_carried_application_lineage_sha256",
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
    ):
        broker_readiness.loc[0, f"{complete_prefix}_{field}"] = (
            complete_final_sha256
        )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_review_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    scaleup_final_lineage = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_final_lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert scaleup_final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    scaleup_complete_final_lineage = report.config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_complete_final_lineage["broker_application_lineage_sha256"] == (
        complete_final_sha256
    )
    assert scaleup_complete_final_lineage["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_scaleup_plan_requires_broker_readiness_complete_final_lineage_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_complete_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final_source_lineage_sha256_matches",
        ),
        (
            "route_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final_route_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_complete_final_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_complete_final_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = (
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    if field == "carried_application_lineage_sha256":
        field = (
            "broker_readiness_complete_final_review_carried_application_lineage_sha256"
        )
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_blocks_broker_readiness_final_lineage_drift():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    final_prefix = "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    broker_readiness.loc[0, f"{final_prefix}_lineage_match_required"] = True
    broker_readiness.loc[0, f"{final_prefix}_lineage_matches"] = True
    for field in (
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
    ):
        broker_readiness.loc[0, f"{final_prefix}_{field}"] = "f" * 64

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_readiness_carried_lineage_sha256_matches",
        f"{check_prefix}_scaleup_final_review_carried_lineage_sha256_matches",
    } <= failed
    compatibility_sha256 = target_application_lineage_sha256(
        target_application_vendor_market_data_batch_config()["datasets"]
    )
    lineage = report.config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["current_application_lineage_sha256"] == compatibility_sha256
    assert lineage["broker_application_lineage_sha256"] == compatibility_sha256
    assert lineage["readiness_carried_application_lineage_sha256"] == (
        compatibility_sha256
    )
    scaleup_final = report.config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_final["broker_application_lineage_sha256"] == "f" * 64
    assert scaleup_final["carried_application_lineage_sha256"] == (
        compatibility_sha256
    )


def test_scaleup_plan_requires_broker_readiness_final_lineage_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_readiness_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final_roundtrip_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_broker_readiness_final_broker_readiness_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_broker_readiness_final_lineage(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    if field == "carried_application_lineage_sha256":
        prefix = (
            "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
    else:
        prefix = (
            "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_blocks_carried_target_application_lineage_drift():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    datasets = json.loads(broker_readiness.loc[0, f"{prefix}_datasets_json"])
    datasets[1]["mapping_application_id"] = "mapping-app-replaced"
    broker_readiness.loc[0, f"{prefix}_datasets_json"] = json.dumps(
        datasets,
        sort_keys=True,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "carried_lineage_sha256_matches"
    ) in failed
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_review_carried_lineage_sha256_matches"
    ) in failed
    summary = report.summary.iloc[0]
    assert bool(summary["broker_vendor_market_data_batch_lineage_matches"])
    assert summary[f"{prefix}_application_lineage_sha256"] != (
        summary["broker_vendor_market_data_batch_application_lineage_sha256"]
    )


def test_scaleup_plan_blocks_failed_final_target_lineage_decisions():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        application_lineage_consistent=False,
    )
    broker_readiness.loc[0, "broker_vendor_market_data_batch_lineage_matches"] = (
        False
    )
    broker_readiness.loc[
        0,
        "vendor_market_data_batch_application_lineage_sha256",
    ] = "f" * 64

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
    } <= failed


def test_scaleup_plan_requires_final_lineage_comparison_for_reconciled_target():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_final_lineage=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
    } <= failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "lineage_match_required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "lineage_matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        ),
        (
            "readiness_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        ),
        (
            "application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_application_lineage_sha256_matches",
        ),
    ],
)
def test_scaleup_plan_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(broker_readiness)
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    broker_readiness.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_scaleup_plan_keeps_generic_target_application_batch_compatible():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        include_final_lineage=False,
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    checks = set(report.checks["check"])
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required"
        not in checks
    )


def test_scaleup_plan_blocks_incomplete_target_application_vendor_market_data_batch():
    datasets = target_application_vendor_market_data_batch_config()["datasets"]
    datasets[1]["mapping_application_sha256"] = ""
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_target_application_vendor_batch(
        broker_readiness,
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
        datasets_json=json.dumps(datasets, sort_keys=True),
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
    } <= failed


def test_scaleup_plan_blocks_bad_broker_readiness_vendor_market_data_batch():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            dispatch_roundtrip_vendor_market_data_batch_provided=True,
            dispatch_roundtrip_vendor_market_data_batch_ready=False,
            dispatch_roundtrip_vendor_market_data_batch_adapter="irage",
            dispatch_roundtrip_vendor_market_data_batch_market="us_options_regular",
            dispatch_roundtrip_vendor_market_data_batch_failed_datasets=1,
            dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
        "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed


def test_scaleup_plan_blocks_wrong_manifest_broker_readiness_vendor_market_data_batch():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            dispatch_roundtrip_vendor_market_data_batch_provided=True,
            dispatch_roundtrip_vendor_market_data_batch_ready=True,
            dispatch_roundtrip_vendor_market_data_batch_adapter="arrow_money",
            dispatch_roundtrip_vendor_market_data_batch_kind="ticks",
            dispatch_roundtrip_vendor_market_data_batch_manifest_run_type="not_vendor_batch",
            dispatch_roundtrip_vendor_market_data_batch_market="india_nse_index_derivatives",
            dispatch_roundtrip_vendor_market_data_batch_dataset_count=2,
            dispatch_roundtrip_vendor_market_data_batch_ready_datasets=2,
            dispatch_roundtrip_vendor_market_data_batch_ready_rate=1.0,
            dispatch_roundtrip_vendor_market_data_batch_unique_source_files=2,
            dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints=1,
            dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage=1.0,
            dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage=1.0,
            dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts=1,
            dispatch_roundtrip_vendor_market_data_batch_mapping_sources="vendor_intake_draft",
            dispatch_roundtrip_vendor_market_data_batch_comparison_accepted=True,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"


def test_scaleup_plan_prefers_broker_readiness_broker_vendor_market_data_batch():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
        dispatch_roundtrip_vendor_market_data_batch_provided=True,
        dispatch_roundtrip_vendor_market_data_batch_ready=False,
        dispatch_roundtrip_vendor_market_data_batch_adapter="irage",
        dispatch_roundtrip_vendor_market_data_batch_market="us_options_regular",
        dispatch_roundtrip_vendor_market_data_batch_failed_datasets=1,
        dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks=1,
    )
    broker_readiness = with_broker_dispatch_roundtrip_vendor_batch(broker_readiness)

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]


def test_scaleup_plan_carries_roundtrip_broker_vendor_market_data_batch():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_broker_dispatch_roundtrip_vendor_batch(
        broker_readiness,
        prefix="roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch",
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["unique_mapping_drafts"] == 1


def test_scaleup_plan_blocks_wrong_manifest_roundtrip_vendor_market_data_batch():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_broker_dispatch_roundtrip_vendor_batch(
        broker_readiness,
        prefix="roundtrip_vendor_market_data_batch",
        manifest_run_type="not_vendor_batch",
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_scaleup_plan_blocks_bad_broker_readiness_broker_vendor_market_data_batch():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
        dispatch_roundtrip_vendor_market_data_batch_provided=True,
        dispatch_roundtrip_vendor_market_data_batch_ready=True,
        dispatch_roundtrip_vendor_market_data_batch_adapter="arrow_money",
        dispatch_roundtrip_vendor_market_data_batch_kind="ticks",
        dispatch_roundtrip_vendor_market_data_batch_market="india_nse_index_derivatives",
        dispatch_roundtrip_vendor_market_data_batch_dataset_count=2,
        dispatch_roundtrip_vendor_market_data_batch_ready_datasets=2,
        dispatch_roundtrip_vendor_market_data_batch_ready_rate=1.0,
        dispatch_roundtrip_vendor_market_data_batch_unique_source_files=2,
        dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints=1,
        dispatch_roundtrip_vendor_market_data_batch_mapping_sources="vendor_intake_draft",
        dispatch_roundtrip_vendor_market_data_batch_comparison_accepted=True,
    )
    broker_readiness = with_broker_dispatch_roundtrip_vendor_batch(
        broker_readiness,
        ready=False,
        adapter="irage",
        market="us_options_regular",
        dataset_count=0,
        ready_datasets=0,
        failed_datasets=1,
        unique_source_files=0,
        unique_header_fingerprints=0,
        source_file_fingerprint_coverage=0.0,
        min_mapping_coverage=0.0,
        unique_mapping_drafts=0,
        mapping_sources="",
        comparison_accepted=False,
        comparison_failed_checks=1,
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed


def test_scaleup_plan_blocks_wrong_manifest_broker_readiness_broker_vendor_market_data_batch():
    broker_readiness = broker_readiness_summary(
        True,
        dispatch_roundtrip_provided=True,
        dispatch_roundtrip_ready=True,
        dispatch_roundtrip_target_mode="shadow",
    )
    broker_readiness = with_broker_dispatch_roundtrip_vendor_batch(
        broker_readiness,
        manifest_run_type="not_vendor_batch",
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness,
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"


def test_scaleup_plan_carries_broker_readiness_shadow_broker_proof():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            shadow_broker_readiness_provided=True,
            shadow_broker_readiness_sessions=2,
            shadow_broker_readiness_ready_sessions=2,
            shadow_broker_vendor_data_readiness_sessions=2,
            shadow_broker_vendor_data_readiness_provided_sessions=2,
            shadow_broker_vendor_data_readiness_ready_sessions=2,
            shadow_broker_vendor_data_readiness_failed_checks=0,
            shadow_broker_adapter="arrow_money",
            shadow_broker_adapter_count=1,
            shadow_broker_route_readiness_sessions=2,
            shadow_broker_route_readiness_ready_sessions=2,
            shadow_broker_route_readiness_strategy="lead_lag_taker",
            shadow_broker_route_readiness_market="india_nse_index_derivatives",
            shadow_broker_route_readiness_gap_pairs=0,
            shadow_broker_dispatch_roundtrip_sessions=2,
            shadow_broker_dispatch_roundtrip_ready_sessions=2,
            shadow_broker_dispatch_roundtrip_strategy="lead_lag_taker",
            shadow_broker_dispatch_roundtrip_market="india_nse_index_derivatives",
            shadow_broker_dispatch_roundtrip_scenario_count=1,
            shadow_broker_route_dispatch_roundtrip_sessions=2,
            shadow_broker_route_dispatch_roundtrip_ready_sessions=2,
            shadow_broker_route_dispatch_roundtrip_strategy="lead_lag_taker",
            shadow_broker_route_dispatch_roundtrip_market="india_nse_index_derivatives",
            shadow_broker_route_dispatch_roundtrip_scenario_count=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["broker_shadow_broker_readiness_provided"]
    assert int(summary["broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["broker_shadow_broker_dispatch_roundtrip_scenario_count"]) == 1
    assert int(summary["broker_shadow_broker_route_dispatch_roundtrip_sessions"]) == 2
    shadow_proof = report.config["broker_readiness"]["shadow_broker_readiness"]
    assert shadow_proof["provided"]
    assert shadow_proof["adapter"] == "arrow_money"
    assert shadow_proof["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert shadow_proof["route_readiness"]["market"] == "india_nse_index_derivatives"
    assert shadow_proof["dispatch_roundtrip"]["sessions"] == 2
    assert shadow_proof["route_dispatch_roundtrip"]["scenario_count"] == 1


def test_scaleup_plan_blocks_dirty_broker_readiness_shadow_broker_proof():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            shadow_broker_readiness_provided=True,
            shadow_broker_readiness_sessions=2,
            shadow_broker_readiness_ready_sessions=1,
            shadow_broker_vendor_data_readiness_sessions=2,
            shadow_broker_vendor_data_readiness_provided_sessions=2,
            shadow_broker_vendor_data_readiness_ready_sessions=1,
            shadow_broker_vendor_data_readiness_failed_checks=1,
            shadow_broker_adapter="irage",
            shadow_broker_adapter_count=2,
            shadow_broker_route_readiness_sessions=2,
            shadow_broker_route_readiness_ready_sessions=1,
            shadow_broker_route_readiness_strategy="surface_mm",
            shadow_broker_route_readiness_market="us_options_regular",
            shadow_broker_route_readiness_gap_pairs=2,
            shadow_broker_dispatch_roundtrip_sessions=2,
            shadow_broker_dispatch_roundtrip_ready_sessions=1,
            shadow_broker_dispatch_roundtrip_strategy="surface_mm",
            shadow_broker_dispatch_roundtrip_market="us_options_regular",
            shadow_broker_dispatch_roundtrip_scenario_count=2,
            shadow_broker_dispatch_roundtrip_missing_request_acks=1,
            shadow_broker_dispatch_roundtrip_rejected_orders=1,
            shadow_broker_dispatch_roundtrip_unmatched_acks=1,
            shadow_broker_route_dispatch_roundtrip_sessions=2,
            shadow_broker_route_dispatch_roundtrip_ready_sessions=1,
            shadow_broker_route_dispatch_roundtrip_strategy="surface_mm",
            shadow_broker_route_dispatch_roundtrip_market="us_options_regular",
            shadow_broker_route_dispatch_roundtrip_scenario_count=2,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_shadow_broker_readiness_ready",
        "broker_shadow_broker_vendor_data_readiness_ready",
        "broker_shadow_broker_vendor_data_readiness_failed_checks",
        "broker_shadow_broker_adapter_matches",
        "broker_shadow_broker_adapter_consistent",
        "broker_shadow_broker_route_readiness_ready",
        "broker_shadow_broker_route_readiness_strategy_matches",
        "broker_shadow_broker_route_readiness_market_matches",
        "broker_shadow_broker_route_readiness_gap_pairs",
        "broker_shadow_broker_dispatch_roundtrip_ready",
        "broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "broker_shadow_broker_dispatch_roundtrip_market_matches",
        "broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "broker_shadow_broker_route_dispatch_roundtrip_ready",
        "broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    summary = report.summary.iloc[0]
    assert summary["broker_shadow_broker_adapter"] == "irage"
    assert int(summary["broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 1
    assert int(summary["broker_shadow_broker_route_readiness_gap_pairs"]) == 2
    shadow_proof = report.config["broker_readiness"]["shadow_broker_readiness"]
    assert shadow_proof["adapter"] == "irage"
    assert shadow_proof["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert shadow_proof["dispatch_roundtrip"]["max_rejected_orders"] == 1


def test_scaleup_plan_blocks_partial_broker_readiness_shadow_broker_vendor_data_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            shadow_broker_readiness_provided=True,
            shadow_broker_readiness_sessions=2,
            shadow_broker_readiness_ready_sessions=2,
            shadow_broker_vendor_data_readiness_sessions=1,
            shadow_broker_vendor_data_readiness_provided_sessions=1,
            shadow_broker_vendor_data_readiness_ready_sessions=1,
            shadow_broker_adapter="arrow_money",
            shadow_broker_adapter_count=1,
            shadow_broker_route_readiness_sessions=2,
            shadow_broker_route_readiness_ready_sessions=2,
            shadow_broker_route_readiness_strategy="lead_lag_taker",
            shadow_broker_route_readiness_market="india_nse_index_derivatives",
            shadow_broker_dispatch_roundtrip_sessions=2,
            shadow_broker_dispatch_roundtrip_ready_sessions=2,
            shadow_broker_dispatch_roundtrip_strategy="lead_lag_taker",
            shadow_broker_dispatch_roundtrip_market="india_nse_index_derivatives",
            shadow_broker_dispatch_roundtrip_scenario_count=1,
            shadow_broker_route_dispatch_roundtrip_sessions=2,
            shadow_broker_route_dispatch_roundtrip_ready_sessions=2,
            shadow_broker_route_dispatch_roundtrip_strategy="lead_lag_taker",
            shadow_broker_route_dispatch_roundtrip_market="india_nse_index_derivatives",
            shadow_broker_route_dispatch_roundtrip_scenario_count=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "broker_shadow_broker_vendor_data_readiness_provided",
        "broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    shadow_proof = report.config["broker_readiness"]["shadow_broker_readiness"]
    assert shadow_proof["broker_vendor_data_readiness"]["provided_sessions"] == 1


def test_scaleup_plan_blocks_missing_broker_dispatch_route_proof():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            route_dispatch_roundtrip_provided=False,
            route_dispatch_roundtrip_ready=False,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_route_dispatch_roundtrip_provided",
        "broker_route_dispatch_roundtrip_ready",
    } <= failed
    assert not report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]["provided"]


def test_scaleup_plan_blocks_bad_broker_dispatch_route_proof_quality():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            route_dispatch_roundtrip_ready=False,
            route_dispatch_roundtrip_target_mode="paper",
            route_dispatch_roundtrip_strategy="imbalance",
            route_dispatch_roundtrip_market="us_equities_regular",
            route_dispatch_roundtrip_scenario_key="wrong-scenario",
            route_dispatch_roundtrip_batch_id="",
            route_dispatch_roundtrip_requests=1,
            route_dispatch_roundtrip_acked_orders=1,
            route_dispatch_roundtrip_missing_request_acks=1,
            route_dispatch_roundtrip_rejected_orders=1,
            route_dispatch_roundtrip_unmatched_acks=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_route_dispatch_roundtrip_ready",
        "broker_route_dispatch_roundtrip_target_mode_matches",
        "broker_route_dispatch_roundtrip_strategy_matches",
        "broker_route_dispatch_roundtrip_market_matches",
        "broker_route_dispatch_roundtrip_scenario_matches",
        "broker_route_dispatch_roundtrip_batch_id_provided",
        "broker_route_dispatch_roundtrip_request_count_matches",
        "broker_route_dispatch_roundtrip_missing_request_acks",
        "broker_route_dispatch_roundtrip_rejected_orders",
        "broker_route_dispatch_roundtrip_unmatched_acks",
    } <= failed
    route_proof = report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]
    assert route_proof["strategy"] == "imbalance"
    assert route_proof["missing_request_acks"] == 1


def test_scaleup_plan_blocks_stale_broker_route_readiness_ops_controls():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            route_readiness_required=True,
            route_readiness_provided=True,
            route_readiness_ready=True,
            route_readiness_strategy="lead_lag_taker",
            route_readiness_market="india_nse_index_derivatives",
            route_readiness_route_ready_pairs=1,
            route_readiness_ops_launch_controls_ready=False,
            route_readiness_ops_launch_control_failures=(
                "broker_roundtrip_portfolio_concentration_ok_runs;"
                "broker_roundtrip_portfolio_concentration_breach_runs"
            ),
            route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
            route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
            route_readiness_ops_broker_roundtrip_resume_route_ready_runs=1,
            route_readiness_ops_broker_roundtrip_resume_route_breach_runs=1,
            route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs=1,
            route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs=1,
            route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs=1,
            route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs=1,
        ),
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_route_readiness_ops_launch_controls_ready",
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
        "broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs",
        "broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs",
        "broker_route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_runs",
        "broker_route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_runs",
        "broker_route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["broker_route_readiness_ops_launch_controls_ready"])
    assert int(summary["broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) == 1
    assert int(summary["broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs"]) == 1
    assert int(summary["broker_route_readiness_ops_broker_roundtrip_resume_route_gap_breach_runs"]) == 1
    route_proof = report.config["broker_readiness"]["route_readiness"]
    assert not route_proof["ops_launch_controls_ready"]
    assert "broker_roundtrip_portfolio_concentration_breach_runs" in route_proof[
        "ops_launch_control_failures"
    ]
    assert route_proof["ops_broker_roundtrip_resume_route_ready_runs"] == 1
    assert route_proof["ops_broker_roundtrip_resume_route_breach_runs"] == 1


def test_scaleup_plan_blocks_bad_broker_dispatch_roundtrip_quality():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=False,
            dispatch_roundtrip_target_mode="shadow",
            dispatch_roundtrip_strategy="imbalance",
            dispatch_roundtrip_market="us_equities_regular",
            dispatch_roundtrip_scenario_key="wrong-scenario",
            dispatch_roundtrip_missing_request_acks=1,
            dispatch_roundtrip_rejected_orders=1,
            dispatch_roundtrip_unmatched_acks=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_ready",
        "broker_dispatch_roundtrip_strategy_matches",
        "broker_dispatch_roundtrip_market_matches",
        "broker_dispatch_roundtrip_scenario_matches",
        "broker_dispatch_roundtrip_missing_request_acks",
        "broker_dispatch_roundtrip_rejected_orders",
        "broker_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["missing_request_acks"] == 1


def test_scaleup_plan_blocks_broker_dispatch_roundtrip_failed_checks():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            dispatch_roundtrip_failed_checks=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "broker_dispatch_roundtrip_failed_checks" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert report.summary.iloc[0]["broker_dispatch_roundtrip_failed_checks"] == 1
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["failed_checks"] == 1


def test_scaleup_plan_blocks_broker_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
            dispatch_roundtrip_target_mode="shadow",
            route_enable_dispatch_roundtrip_failed_checks=1,
        ),
        thresholds=ScaleUpThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "broker_route_enable_dispatch_roundtrip_failed_checks" in failed
    assert report.summary.iloc[0]["broker_route_enable_dispatch_roundtrip_failed_checks"] == 1
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_enable_dispatch_roundtrip"][
        "failed_checks"
    ] == 1


def test_scaleup_plan_blocks_bad_broker_resume_proof_identity():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            resume_gate_provided=True,
            resume_gate_ready=True,
            resume_proof_refresh_ready=True,
            resume_proof_refresh_strategy="surface_mm",
            resume_proof_refresh_market="us_options_regular",
        ),
        thresholds=ScaleUpThresholds(require_resume_gate=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"broker_resume_proof_refresh_strategy_matches", "broker_resume_proof_refresh_market_matches"} <= failed
    assert report.summary.iloc[0]["broker_resume_proof_refresh_strategy"] == "surface_mm"
    assert report.config["broker_readiness"]["resume_gate"]["proof_refresh_market"] == "us_options_regular"


def test_scaleup_plan_blocks_bad_broker_resume_route_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            resume_gate_provided=True,
            resume_gate_ready=True,
            resume_proof_refresh_ready=True,
            resume_broker_route_readiness_required=True,
            resume_broker_route_readiness_provided=True,
            resume_broker_route_readiness_ready=False,
            resume_broker_route_readiness_strategy="surface_mm",
            resume_broker_route_readiness_market="us_options_regular",
            resume_broker_route_readiness_gap_pairs=2,
            resume_broker_route_readiness_ops_launch_controls_ready=False,
            resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        thresholds=ScaleUpThresholds(require_resume_gate=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_resume_broker_route_readiness_ready",
        "broker_resume_broker_route_readiness_strategy_matches",
        "broker_resume_broker_route_readiness_market_matches",
        "broker_resume_broker_route_readiness_gap_pairs",
        "broker_resume_broker_route_readiness_ops_launch_controls_ready",
        "broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    assert report.summary.iloc[0]["broker_resume_broker_route_readiness_market"] == "us_options_regular"
    assert report.config["broker_readiness"]["resume_gate"]["broker_route_readiness"]["gap_pairs"] == 2


def test_scaleup_plan_live_dryrun_requires_broker_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        thresholds=ScaleUpThresholds(target_mode="live_dryrun"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_available",
        "broker_readiness_available",
        "broker_runtime_session_provided",
        "broker_dispatch_roundtrip_provided",
    } <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]
    assert report.config["broker_readiness"]["required"]
    assert report.config["broker_readiness"]["runtime_session"]["required"]
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["required"]


def test_scaleup_plan_live_dryrun_blocks_halted_broker_runtime_session():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        route_readiness_summary=route_readiness_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            False,
            runtime_session_provided=True,
            runtime_session_ready=False,
            runtime_guard_action="halt",
            runtime_guard_halted=True,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
        ),
        thresholds=ScaleUpThresholds(target_mode="live_dryrun"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"broker_readiness_ready", "broker_runtime_session_ready", "broker_runtime_guard_continue"} <= failed


def test_scaleup_plan_live_dryrun_accepts_broker_runtime_guard_continue():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        route_readiness_summary=route_readiness_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            runtime_session_provided=True,
            runtime_session_ready=True,
            runtime_guard_action="continue",
            runtime_guard_halted=False,
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
        ),
        thresholds=ScaleUpThresholds(target_mode="live_dryrun"),
    )

    assert report.ready
    assert report.summary.iloc[0]["target_mode"] == "live_dryrun"
    assert report.summary.iloc[0]["broker_runtime_session_required"]
    assert report.config["broker_readiness"]["required"]
    assert report.config["broker_readiness"]["runtime_session"]["required"]
    assert report.config["broker_readiness"]["runtime_session"]["guard_action"] == "continue"
    assert report.config["broker_readiness"]["runtime_session"]["target_mode"] == "shadow"
    assert report.config["broker_readiness"]["runtime_session"]["strategy"] == "lead_lag_taker"
    assert report.config["broker_readiness"]["runtime_session"]["market"] == "india_nse_index_derivatives"
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["required"]
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["ready"]
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["acked_orders"] == 2
    assert report.config["route_readiness"]["required"]
    assert report.config["route_readiness"]["ready"]
    assert report.config["route_readiness"]["strategy"] == "lead_lag_taker"


def test_scaleup_plan_live_dryrun_blocks_broker_runtime_identity_mismatch():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        route_readiness_summary=route_readiness_summary(True),
        broker_readiness_summary=broker_readiness_summary(
            True,
            runtime_session_provided=True,
            runtime_session_ready=True,
            runtime_guard_action="continue",
            runtime_guard_halted=False,
            runtime_strategy="imbalance",
            runtime_market="us_equities_regular",
            dispatch_roundtrip_provided=True,
            dispatch_roundtrip_ready=True,
        ),
        thresholds=ScaleUpThresholds(target_mode="live_dryrun"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"broker_runtime_strategy_matches", "broker_runtime_market_matches"} <= failed
    assert report.summary.iloc[0]["broker_runtime_strategy"] == "imbalance"
    assert report.summary.iloc[0]["broker_runtime_market"] == "us_equities_regular"
    assert report.config["broker_readiness"]["runtime_session"]["strategy"] == "imbalance"


def test_scaleup_plan_can_require_route_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        thresholds=ScaleUpThresholds(require_route_readiness=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_readiness_available" in failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_scaleup_plan_blocks_route_readiness_identity_mismatch():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        route_readiness_summary=route_readiness_summary(
            True,
            strategy="surface_mm",
            market="us_options_regular",
        ),
        thresholds=ScaleUpThresholds(require_route_readiness=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_strategy_matches", "route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "us_options_regular"


def test_scaleup_plan_blocks_stale_route_readiness_ops_controls():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        route_readiness_summary=route_readiness_summary(
            True,
            ops_launch_controls_blocked_pairs=1,
            ops_broker_roundtrip_portfolio_breach_pairs=1,
            ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
            ops_broker_roundtrip_resume_route_breach_pairs=1,
            ops_broker_roundtrip_resume_route_gap_breach_pairs=1,
            ops_broker_roundtrip_resume_route_launch_control_breach_pairs=1,
            ops_broker_roundtrip_resume_route_portfolio_breach_pairs=1,
            ops_broker_roundtrip_resume_route_concentration_breach_pairs=1,
        ),
        thresholds=ScaleUpThresholds(require_route_readiness=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_ops_launch_controls_blocked_pairs",
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
        "route_readiness_ops_broker_roundtrip_resume_route_breach_pairs",
        "route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs",
        "route_readiness_ops_broker_roundtrip_resume_route_launch_control_breach_pairs",
        "route_readiness_ops_broker_roundtrip_resume_route_portfolio_breach_pairs",
        "route_readiness_ops_broker_roundtrip_resume_route_concentration_breach_pairs",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["route_readiness_ops_launch_controls_blocked_pairs"]) == 1
    assert int(summary["route_readiness_ops_broker_roundtrip_resume_route_gap_breach_pairs"]) == 1
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_concentration_breach_pairs"] == 1
    assert report.config["route_readiness"]["ops_broker_roundtrip_resume_route_concentration_breach_pairs"] == 1


def test_scaleup_plan_accepts_required_data_readiness():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        data_readiness_summary=data_readiness_summary(True),
        thresholds=ScaleUpThresholds(require_data_readiness=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["data_readiness_ready"]
    assert report.config["data_readiness"]["required"]
    assert report.config["data_readiness"]["ready"]


def test_scaleup_plan_accepts_required_data_readiness_comparison():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        data_readiness_comparison_summary=data_readiness_comparison_summary(True),
        thresholds=ScaleUpThresholds(require_data_readiness_comparison=True),
    )

    assert report.ready
    assert report.summary.iloc[0]["data_readiness_comparison_accepted"]
    assert report.summary.iloc[0]["data_readiness_comparison_verified"]
    assert report.summary.iloc[0]["data_readiness_comparison_manifest_current"]
    assert report.summary.iloc[0]["data_readiness_comparison_dataset_count"] == 2
    assert report.config["data_readiness_comparison"]["required"]
    assert report.config["data_readiness_comparison"]["accepted"]
    assert report.config["data_readiness_comparison"]["verified"]
    assert report.config["data_readiness_comparison"]["manifest_current"]
    assert report.config["data_readiness_comparison"]["manifest_artifact_count"] == 6
    assert report.config["data_readiness_comparison"]["manifest_artifact_match_count"] == 6
    assert report.config["data_readiness_comparison"]["ready_rate"] == 1.0


def test_scaleup_plan_rejects_required_loose_data_readiness_comparison():
    comparison = data_readiness_comparison_summary(True).drop(
        columns=[
            "manifest_required",
            "manifest_provided",
            "manifest_current",
            "verified",
            "manifest_error",
            "manifest_run_type",
            "manifest_run_type_matches",
            "manifest_artifact_count",
            "manifest_artifact_match_count",
            "manifest_input_fingerprint_count",
            "manifest_input_fingerprint_match_count",
        ]
    )

    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        data_readiness_comparison_summary=comparison,
        thresholds=ScaleUpThresholds(require_data_readiness_comparison=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert {
        "data_readiness_comparison_manifest_provided",
        "data_readiness_comparison_manifest_current",
        "data_readiness_comparison_verified",
    } <= failed
    assert report.config["data_readiness_comparison"]["accepted"]
    assert not report.config["data_readiness_comparison"]["verified"]


def test_write_scaleup_plan_carries_vendor_market_data_batch_config(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    vendor_batch = tmp_path / "vendor_batch"
    comparison = vendor_batch / "comparison"
    write_data_readiness_comparison_bundle(comparison)
    (vendor_batch / "vendor_market_data_batch_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "adapter": "arrow_money",
                "kind": "ticks",
                "market": "india_nse_index_derivatives",
                "dataset_count": 2,
                "ready_datasets": 2,
                "failed_datasets": 0,
                "ready_rate": 1.0,
                "unique_source_files": 2,
                "unique_header_fingerprints": 1,
                "source_file_fingerprint_coverage": 1.0,
                "min_mapping_coverage": 1.0,
                "unique_mapping_drafts": 1,
                "mapping_sources": "vendor_intake_draft",
                "comparison": {
                    "accepted": True,
                    "ready_rate": 1.0,
                    "failed_checks": 0,
                },
                "datasets": [
                    {
                        "dataset": "day1",
                        "ready": True,
                        "source_file_sha256": "a" * 64,
                        "source_header_sha256": "b" * 64,
                        "mapping_draft_sha256": "c" * 64,
                        "mapping_source": "vendor_intake_draft",
                    },
                    {
                        "dataset": "day2",
                        "ready": True,
                        "source_file_sha256": "d" * 64,
                        "source_header_sha256": "b" * 64,
                        "mapping_draft_sha256": "c" * 64,
                        "mapping_source": "vendor_intake_draft",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        data_readiness_comparison_dir=comparison,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_data_readiness_comparison=True),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    comparison_lineage = config["data_readiness_comparison"]
    vendor = comparison_lineage["vendor_market_data_batch"]
    assert report.ready
    assert comparison_lineage["verified"]
    assert comparison_lineage["manifest_current"]
    assert comparison_lineage["semantically_verified"]
    assert comparison_lineage["verification_inputs_current"]
    assert comparison_lineage["verification_artifacts_consistent"]
    assert comparison_lineage["verification_non_authorizing"]
    assert comparison_lineage["verification_error"] == ""
    assert comparison_lineage["manifest_run_type_matches"]
    assert comparison_lineage["manifest_artifact_count"] == 6
    assert comparison_lineage["manifest_artifact_match_count"] == 6
    assert comparison_lineage["manifest_sha256"] == file_sha256(
        comparison / "manifest.json"
    )
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["dataset_count"] == 2
    assert vendor["unique_source_files"] == 2
    assert vendor["unique_header_fingerprints"] == 1
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["mapping_sources"] == "vendor_intake_draft"
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64
    assert path_tail(manifest["inputs"]["vendor_market_data_batch_config"]["path"]).endswith(
        "/vendor_batch/vendor_market_data_batch_config.json"
    )
    assert path_tail(
        manifest["inputs"]["data_readiness_comparison_manifest"]["path"]
    ).endswith("/vendor_batch/comparison/manifest.json")
    assert manifest["extra"]["data_readiness_comparison_verified"]
    assert manifest["extra"]["data_readiness_comparison_manifest_current"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed


def test_write_scaleup_plan_blocks_tampered_data_readiness_comparison(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    comparison = write_data_readiness_comparison_bundle(
        tmp_path / "comparison"
    )
    summary_path = comparison / "data_readiness_comparison_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "recommendation"] = "tampered_after_manifest"
    summary.to_csv(summary_path, index=False)
    reseal_experiment_manifest(comparison)
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        data_readiness_comparison_dir=comparison,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_data_readiness_comparison=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    lineage = report.config["data_readiness_comparison"]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert not report.ready
    assert {
        "data_readiness_comparison_verified",
    } <= failed
    assert lineage["accepted"]
    assert lineage["manifest_current"]
    assert not lineage["verified"]
    assert not lineage["semantically_verified"]
    assert not lineage["verification_artifacts_consistent"]
    assert lineage["manifest_error"] == ""
    assert lineage["verification_error"] == (
        "artifacts do not reconstruct from inputs"
    )
    assert lineage["reason"] == (
        "data_readiness_comparison_"
        "artifacts_do_not_reconstruct_from_inputs"
    )
    assert path_tail(
        manifest["inputs"]["data_readiness_comparison_manifest"]["path"]
    ).endswith("/comparison/manifest.json")
    assert not manifest["extra"]["data_readiness_comparison_verified"]


def test_write_scaleup_plan_blocks_loose_broker_readiness_bundle(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = launch / "06_broker_readiness"
    broker.mkdir(parents=True)
    readiness = broker_readiness_summary(True)
    readiness.to_csv(broker / "broker_readiness_summary.csv", index=False)
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "adapter": "arrow_money",
                "component_counts": {"failed_checks": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    lineage = report.config["broker_readiness"]["lineage"]
    assert not report.ready
    assert {
        "broker_readiness_lineage_manifest_current",
        "broker_readiness_lineage_contract_consistent",
        "broker_readiness_lineage_gate_passed",
    } <= failed
    assert lineage["lineage_required"]
    assert not lineage["manifest_current"]
    assert not lineage["lineage_gate_passed"]


def test_write_scaleup_plan_seals_broker_readiness_lineage(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = write_broker_readiness_bundle(
        launch / "06_broker_readiness",
        broker_readiness_summary(True),
    )
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    lineage = report.config["broker_readiness"]["lineage"]
    assert report.ready
    assert lineage["lineage_required"]
    assert lineage["lineage_provided"]
    assert lineage["manifest_current"]
    assert lineage["lineage_contract_consistent"]
    assert lineage["lineage_gate_passed"]
    assert lineage["lineage_dependency_count"] == 1
    assert len(manifest["inputs"]["broker_readiness_artifacts"]) == 6
    assert len(manifest["inputs"]["broker_readiness_dependencies"]) == 1
    assert manifest["extra"]["broker_readiness_lineage_gate_passed"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    source = broker.parent / "broker_readiness_source.csv"
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_write_scaleup_plan_retains_verified_broker_readiness_route_identity(
    tmp_path,
    verified_route_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = verified_route_identity_broker_readiness_bundle
    readiness_summary = pd.read_csv(
        broker / "broker_readiness_summary.csv",
        dtype=str,
        keep_default_na=False,
    ).iloc[0]
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in BROKER_READINESS_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
    }
    active_field = route_fields[
        "broker_dispatch_roundtrip_ack_route_contract_identity_active"
    ]
    carried_field = route_fields[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_"
            "route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_"
            "route_contract_identity_matches_current"
        )
    ]
    expected_sha256 = readiness_summary[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    summary = report.summary.iloc[0]
    plan = report.plan.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    checks = report.checks.set_index("check")

    assert not report.ready
    assert bool(summary[active_field])
    assert summary[carried_field] == expected_sha256
    assert summary[current_field] == expected_sha256
    assert bool(summary[verdict_field])
    assert plan[carried_field] == expected_sha256
    assert plan[current_field] == expected_sha256
    assert bool(plan[verdict_field])
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert checks.loc[
        checks.index.str.startswith(
            "broker_readiness_roundtrip_route_contract_identity_"
        ),
        "passed",
    ].astype(bool).all()
    assert checks.loc[
        checks.index.str.startswith("broker_readiness_lineage_"),
        "passed",
    ].astype(bool).all()
    assert manifest["extra"][carried_field] == expected_sha256
    assert manifest["extra"][current_field] == expected_sha256
    assert manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed


def test_write_scaleup_plan_blocks_remanifested_broker_readiness_route_forgery(
    tmp_path,
    verified_route_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = tmp_path / "forged_broker_readiness"
    shutil.copytree(
        verified_route_identity_broker_readiness_bundle,
        broker,
    )
    forged_sha256 = "d" * 64
    current_sha256 = forge_broker_readiness_route_identity(
        broker,
        forged_sha256,
    )
    assert verify_experiment_manifest(
        broker / "manifest.json",
        expected_run_type="broker_readiness",
        require_input_fingerprints=True,
    ).passed
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in BROKER_READINESS_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
    }
    carried_field = route_fields[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_"
            "route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_"
            "route_contract_identity_matches_current"
        )
    ]
    summary = report.summary.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )

    assert not report.ready
    assert bool(summary["broker_readiness_manifest_current"])
    assert not bool(
        summary["broker_readiness_lineage_contract_consistent"]
    )
    assert summary[carried_field] == forged_sha256
    assert summary[current_field] == current_sha256
    assert not bool(summary[verdict_field])
    assert {
        "broker_readiness_lineage_contract_consistent",
        "broker_readiness_lineage_roundtrip_matches_current",
        "broker_readiness_lineage_gate_passed",
        (
            "broker_readiness_roundtrip_route_contract_identity_"
            "sha256_matches_current"
        ),
        (
            "broker_readiness_roundtrip_route_contract_identity_"
            "matches_current"
        ),
    } <= failed
    assert "broker_readiness_lineage_manifest_current" not in failed
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == forged_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == current_sha256
    )
    assert not lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert manifest["extra"][carried_field] == forged_sha256
    assert manifest["extra"][current_field] == current_sha256
    assert not manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed


def test_write_scaleup_plan_retains_verified_broker_readiness_broker_route_identity(
    tmp_path,
    verified_route_enable_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = verified_route_enable_identity_broker_readiness_bundle
    readiness_summary = pd.read_csv(
        broker / "broker_readiness_summary.csv",
        dtype=str,
        keep_default_na=False,
    ).iloc[0]
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in (
            BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
        )
    }
    active_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_"
            "route_contract_identity_active"
        )
    ]
    carried_field = route_fields[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    expected_sha256 = readiness_summary[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    summary = report.summary.iloc[0]
    plan = report.plan.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    checks = report.checks.set_index("check")

    assert not bool(
        summary[
            "broker_readiness_roundtrip_ack_route_contract_identity_active"
        ]
    )
    assert bool(summary[active_field])
    assert summary[carried_field] == expected_sha256
    assert summary[current_field] == expected_sha256
    assert bool(summary[verdict_field])
    assert plan[carried_field] == expected_sha256
    assert plan[current_field] == expected_sha256
    assert bool(plan[verdict_field])
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert checks.loc[
        checks.index.str.startswith(
            "broker_readiness_roundtrip_broker_route_contract_identity_"
        ),
        "passed",
    ].astype(bool).all()
    assert checks.loc[
        checks.index.str.startswith("broker_readiness_lineage_"),
        "passed",
    ].astype(bool).all()
    assert manifest["extra"][carried_field] == expected_sha256
    assert manifest["extra"][current_field] == expected_sha256
    assert manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    provenance = load_scaleup_runtime_provenance(
        out_dir / "scaleup_config.json"
    )
    assert provenance["contract_consistent"], provenance["contract_error"]
    assert provenance["broker_readiness_matches_current"]
    assert provenance[
        "broker_readiness_route_enable_route_contract_identity_active"
    ]
    assert provenance[
        "broker_readiness_route_enable_route_contract_identity_sha256"
    ] == expected_sha256
    assert provenance[
        "broker_readiness_current_route_enable_route_contract_identity_sha256"
    ] == expected_sha256
    assert provenance[
        (
            "broker_readiness_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    assert provenance["provenance_gate_passed"] == report.ready


def test_write_scaleup_plan_blocks_remanifested_broker_readiness_broker_route_forgery(
    tmp_path,
    verified_route_enable_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = tmp_path / "forged_broker_readiness"
    shutil.copytree(
        verified_route_enable_identity_broker_readiness_bundle,
        broker,
    )
    forged_sha256 = "f" * 64
    current_sha256 = forge_broker_readiness_route_enable_identity(
        broker,
        forged_sha256,
    )
    assert verify_experiment_manifest(
        broker / "manifest.json",
        expected_run_type="broker_readiness",
        require_input_fingerprints=True,
    ).passed
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in (
            BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
        )
    }
    carried_field = route_fields[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    summary = report.summary.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )

    assert not report.ready
    assert bool(summary["broker_readiness_manifest_current"])
    assert not bool(
        summary["broker_readiness_lineage_contract_consistent"]
    )
    assert summary[carried_field] == forged_sha256
    assert summary[current_field] == current_sha256
    assert not bool(summary[verdict_field])
    assert {
        "broker_readiness_lineage_contract_consistent",
        "broker_readiness_lineage_roundtrip_matches_current",
        "broker_readiness_lineage_gate_passed",
        (
            "broker_readiness_roundtrip_broker_route_contract_identity_"
            "sha256_matches_current"
        ),
        (
            "broker_readiness_roundtrip_broker_route_contract_identity_"
            "matches_current"
        ),
    } <= failed
    assert "broker_readiness_lineage_manifest_current" not in failed
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == forged_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == current_sha256
    )
    assert not lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert manifest["extra"][carried_field] == forged_sha256
    assert manifest["extra"][current_field] == current_sha256
    assert not manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    provenance = load_scaleup_runtime_provenance(
        out_dir / "scaleup_config.json"
    )
    assert provenance["manifest_current"]
    assert not provenance["contract_consistent"]
    assert provenance[
        "broker_readiness_route_enable_route_contract_identity_active"
    ]
    assert provenance[
        "broker_readiness_route_enable_route_contract_identity_sha256"
    ] == forged_sha256
    assert provenance[
        "broker_readiness_current_route_enable_route_contract_identity_sha256"
    ] == current_sha256
    assert not provenance[
        (
            "broker_readiness_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    assert not provenance["provenance_gate_passed"]


def test_write_scaleup_plan_retains_verified_broker_readiness_route_enable_route_identity(
    tmp_path,
    verified_route_enable_route_enable_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = (
        verified_route_enable_route_enable_identity_broker_readiness_bundle
    )
    readiness_summary = pd.read_csv(
        broker / "broker_readiness_summary.csv",
        dtype=str,
        keep_default_na=False,
    ).iloc[0]
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in (
            BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
        )
    }
    active_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_route_enable_"
            "route_contract_identity_active"
        )
    ]
    carried_field = route_fields[
        (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
        )
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_enable_route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    expected_sha256 = readiness_summary[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    summary = report.summary.iloc[0]
    plan = report.plan.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    checks = report.checks.set_index("check")

    assert not bool(
        summary.get(
            (
                "broker_readiness_roundtrip_ack_route_enable_"
                "route_contract_identity_active"
            ),
            False,
        )
    )
    assert bool(summary[active_field])
    assert summary[carried_field] == expected_sha256
    assert summary[current_field] == expected_sha256
    assert bool(summary[verdict_field])
    assert plan[carried_field] == expected_sha256
    assert plan[current_field] == expected_sha256
    assert bool(plan[verdict_field])
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert checks.loc[
        checks.index.str.startswith(
            "broker_readiness_roundtrip_route_enable_route_enable_"
            "route_contract_identity_"
        ),
        "passed",
    ].astype(bool).all()
    assert checks.loc[
        checks.index.str.startswith("broker_readiness_lineage_"),
        "passed",
    ].astype(bool).all()
    assert manifest["extra"][carried_field] == expected_sha256
    assert manifest["extra"][current_field] == expected_sha256
    assert manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    provenance = load_scaleup_runtime_provenance(
        out_dir / "scaleup_config.json"
    )
    assert provenance["contract_consistent"], provenance["contract_error"]
    assert provenance["broker_readiness_matches_current"]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity_active"
        )
    ]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == expected_sha256
    assert provenance[
        (
            "broker_readiness_current_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == expected_sha256
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    assert provenance["provenance_gate_passed"] == report.ready


def test_write_scaleup_plan_blocks_remanifested_broker_readiness_route_enable_route_forgery(
    tmp_path,
    verified_route_enable_route_enable_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = tmp_path / "forged_broker_readiness"
    shutil.copytree(
        verified_route_enable_route_enable_identity_broker_readiness_bundle,
        broker,
    )
    forged_sha256 = "e" * 64
    current_sha256 = (
        forge_broker_readiness_route_enable_route_enable_identity(
            broker,
            forged_sha256,
        )
    )
    assert verify_experiment_manifest(
        broker / "manifest.json",
        expected_run_type="broker_readiness",
        require_input_fingerprints=True,
    ).passed
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in (
            BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
        )
    }
    carried_field = route_fields[
        (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
        )
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_enable_route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    summary = report.summary.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )

    assert not report.ready
    assert bool(summary["broker_readiness_manifest_current"])
    assert not bool(
        summary["broker_readiness_lineage_contract_consistent"]
    )
    assert summary[carried_field] == forged_sha256
    assert summary[current_field] == current_sha256
    assert not bool(summary[verdict_field])
    assert {
        "broker_readiness_lineage_contract_consistent",
        "broker_readiness_lineage_roundtrip_matches_current",
        "broker_readiness_lineage_gate_passed",
        (
            "broker_readiness_roundtrip_route_enable_route_enable_"
            "route_contract_identity_sha256_matches_current"
        ),
        (
            "broker_readiness_roundtrip_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        ),
    } <= failed
    assert "broker_readiness_lineage_manifest_current" not in failed
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == forged_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == current_sha256
    )
    assert not lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert manifest["extra"][carried_field] == forged_sha256
    assert manifest["extra"][current_field] == current_sha256
    assert not manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    provenance = load_scaleup_runtime_provenance(
        out_dir / "scaleup_config.json"
    )
    assert provenance["manifest_current"]
    assert not provenance["contract_consistent"]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity_active"
        )
    ]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == forged_sha256
    assert provenance[
        (
            "broker_readiness_current_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == current_sha256
    assert not provenance[
        (
            "broker_readiness_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    assert not provenance["provenance_gate_passed"]


def test_write_scaleup_plan_revalidates_terminal_broker_readiness_route_identity(
    tmp_path,
    verified_route_enable_route_enable_route_enable_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = (
        verified_route_enable_route_enable_route_enable_identity_broker_readiness_bundle
    )
    readiness_summary = pd.read_csv(
        broker / "broker_readiness_summary.csv",
        dtype=str,
        keep_default_na=False,
    ).iloc[0]
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in (
            BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
        )
    }
    active_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_route_enable_"
            "route_enable_route_contract_identity_active"
        )
    ]
    carried_field = route_fields[
        (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
        )
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_enable_route_enable_route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_route_enable_"
            "route_enable_route_contract_identity_matches_current"
        )
    ]
    expected_sha256 = readiness_summary[
        BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
    ]
    summary = report.summary.iloc[0]
    plan = report.plan.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    checks = report.checks.set_index("check")

    assert not bool(
        summary.get(
            (
                "broker_readiness_roundtrip_ack_route_enable_"
                "route_enable_route_contract_identity_active"
            ),
            False,
        )
    )
    assert bool(summary[active_field])
    assert summary[carried_field] == expected_sha256
    assert summary[current_field] == expected_sha256
    assert bool(summary[verdict_field])
    assert plan[carried_field] == expected_sha256
    assert plan[current_field] == expected_sha256
    assert bool(plan[verdict_field])
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == expected_sha256
    )
    assert lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert checks.loc[
        checks.index.str.startswith(
            "broker_readiness_roundtrip_route_enable_route_enable_"
            "route_enable_route_contract_identity_"
        ),
        "passed",
    ].astype(bool).all()
    assert checks.loc[
        checks.index.str.startswith("broker_readiness_lineage_"),
        "passed",
    ].astype(bool).all()
    assert manifest["extra"][carried_field] == expected_sha256
    assert manifest["extra"][current_field] == expected_sha256
    assert manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    provenance = load_scaleup_runtime_provenance(
        out_dir / "scaleup_config.json"
    )
    assert provenance["contract_consistent"], provenance["contract_error"]
    assert provenance["broker_readiness_matches_current"]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_active"
        )
    ]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == expected_sha256
    assert provenance[
        (
            "broker_readiness_current_route_enable_route_enable_"
            "route_enable_route_contract_identity_sha256"
        )
    ] == expected_sha256
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    assert provenance["provenance_gate_passed"] == report.ready
    runtime_fields = scaleup_runtime_fields(provenance)
    assert runtime_fields[
        (
            "scaleup_broker_readiness_route_enable_route_enable_"
            "route_enable_route_contract_identity_sha256"
        )
    ] == expected_sha256
    runtime_manifest_extra = scaleup_runtime_manifest_extra(provenance)
    assert runtime_manifest_extra[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == expected_sha256
    assert runtime_manifest_extra[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]


def test_write_scaleup_plan_blocks_remanifested_terminal_broker_readiness_route_forgery(
    tmp_path,
    verified_route_enable_route_enable_route_enable_identity_broker_readiness_bundle,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = tmp_path / "forged_broker_readiness"
    shutil.copytree(
        verified_route_enable_route_enable_route_enable_identity_broker_readiness_bundle,
        broker,
    )
    forged_sha256 = "d" * 64
    current_sha256 = (
        forge_broker_readiness_route_enable_route_enable_route_enable_identity(
            broker,
            forged_sha256,
        )
    )
    assert verify_experiment_manifest(
        broker / "manifest.json",
        expected_run_type="broker_readiness",
        require_input_fingerprints=True,
    ).passed
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        broker_readiness_dir=broker,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_broker_readiness=True),
    )

    route_fields = {
        source_field: target_field
        for (
            target_field,
            source_field,
        ) in (
            BROKER_READINESS_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_FIELD_MAP
        )
    }
    carried_field = route_fields[
        (
            BROKER_DISPATCH_ROUNDTRIP_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_ENABLE_ROUTE_CONTRACT_IDENTITY_SHA256_FIELD
        )
    ]
    current_field = route_fields[
        (
            "broker_dispatch_roundtrip_current_ack_route_enable_"
            "route_enable_route_enable_route_contract_identity_sha256"
        )
    ]
    verdict_field = route_fields[
        (
            "broker_dispatch_roundtrip_ack_route_enable_route_enable_"
            "route_enable_route_contract_identity_matches_current"
        )
    ]
    summary = report.summary.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )

    assert not report.ready
    assert bool(summary["broker_readiness_manifest_current"])
    assert not bool(
        summary["broker_readiness_lineage_contract_consistent"]
    )
    assert summary[carried_field] == forged_sha256
    assert summary[current_field] == current_sha256
    assert not bool(summary[verdict_field])
    assert {
        "broker_readiness_lineage_contract_consistent",
        "broker_readiness_lineage_roundtrip_matches_current",
        "broker_readiness_lineage_gate_passed",
        (
            "broker_readiness_roundtrip_route_enable_route_enable_"
            "route_enable_route_contract_identity_sha256_matches_current"
        ),
        (
            "broker_readiness_roundtrip_route_enable_route_enable_"
            "route_enable_route_contract_identity_matches_current"
        ),
    } <= failed
    assert "broker_readiness_lineage_manifest_current" not in failed
    assert (
        lineage[carried_field.removeprefix("broker_readiness_")]
        == forged_sha256
    )
    assert (
        lineage[current_field.removeprefix("broker_readiness_")]
        == current_sha256
    )
    assert not lineage[
        verdict_field.removeprefix("broker_readiness_")
    ]
    assert manifest["extra"][carried_field] == forged_sha256
    assert manifest["extra"][current_field] == current_sha256
    assert not manifest["extra"][verdict_field]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    provenance = load_scaleup_runtime_provenance(
        out_dir / "scaleup_config.json"
    )
    assert provenance["manifest_current"]
    assert not provenance["contract_consistent"]
    assert not provenance["broker_readiness_matches_current"]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_active"
        )
    ]
    assert provenance[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_sha256"
        )
    ] == forged_sha256
    assert provenance[
        (
            "broker_readiness_current_route_enable_route_enable_"
            "route_enable_route_contract_identity_sha256"
        )
    ] == current_sha256
    assert not provenance[
        (
            "broker_readiness_route_enable_route_enable_route_enable_"
            "route_contract_identity_matches_current"
        )
    ]
    assert not provenance["provenance_gate_passed"]


def test_write_scaleup_plan_promotes_verified_broker_contract_identity(
    tmp_path,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = write_verified_broker_readiness_bundle(
        tmp_path / "broker_readiness_sources",
        launch / "06_broker_readiness",
        contract_identity=True,
    )
    readiness_summary = pd.read_csv(
        broker / "broker_readiness_summary.csv"
    ).iloc[0]
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(
            require_broker_readiness=True,
        ),
    )

    identity_sha256 = readiness_summary[
        "broker_dispatch_roundtrip_contract_identity_sha256"
    ]
    identity_field = (
        "broker_readiness_roundtrip_contract_identity_sha256"
    )
    summary = report.summary.iloc[0]
    plan = report.plan.iloc[0]
    lineage = report.config["broker_readiness"]["lineage"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    checks = report.checks.set_index("check")

    assert bool(
        summary[
            "broker_readiness_roundtrip_contract_identity_lineage_verified"
        ]
    )
    assert summary[identity_field] == identity_sha256
    assert plan[identity_field] == identity_sha256
    assert (
        lineage["roundtrip_contract_identity_sha256"]
        == identity_sha256
    )
    assert lineage[
        "roundtrip_contract_identity_lineage_verified"
    ]
    assert manifest["extra"][identity_field] == identity_sha256
    assert manifest["extra"][
        "broker_readiness_roundtrip_contract_identity_lineage_verified"
    ]
    assert bool(
        checks.loc[
            "broker_readiness_roundtrip_contract_identity_lineage_verified",
            "passed",
        ]
    )
    assert checks.loc[
        checks.index.str.startswith(
            "broker_readiness_roundtrip_contract_identity_"
        ),
        "passed",
    ].astype(bool).all()
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed


def test_write_scaleup_plan_hydrates_resume_route_readiness_from_broker_config(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    broker = launch / "06_broker_readiness"
    readiness_summary = broker_readiness_summary(
        True,
        resume_gate_provided=True,
        resume_gate_ready=True,
        resume_proof_refresh_ready=True,
    )
    route_proof = {
        "provided": True,
        "ready": True,
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "route_ready_pairs": 1,
        "gap_pairs": 0,
        "recommendation": "route_ready",
        "ops_launch_controls_ready": True,
        "ops_broker_roundtrip_portfolio_safe_runs": 1,
        "ops_broker_roundtrip_portfolio_breach_runs": 0,
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
    }
    write_broker_readiness_bundle(
        broker,
        readiness_summary,
        config_overrides={
            "broker_readiness": {
                "ready": True,
                "resume_gate": {
                    "broker_route_readiness": route_proof,
                    "incident_broker_route_readiness": route_proof,
                },
            }
        },
    )
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_resume_gate=True),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    summary = report.summary.iloc[0]
    resume_gate = config["broker_readiness"]["resume_gate"]
    assert report.ready
    assert summary["broker_resume_broker_route_readiness_ready"]
    assert summary["broker_resume_incident_broker_route_readiness_route_ready_pairs"] == 1
    assert resume_gate["broker_route_readiness"]["ready"]
    assert resume_gate["incident_broker_route_readiness"]["ops_launch_controls_ready"]


def test_write_scaleup_plan_carries_strategy_portfolio_inputs(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(max_scale_multiplier=2.0, require_strategy_portfolio=True),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert config["strategy_portfolio"]["required"]
    assert config["strategy_portfolio"]["provided"]
    assert config["strategy_portfolio"]["manifest_required"]
    assert config["strategy_portfolio"]["manifest_provided"]
    assert config["strategy_portfolio"]["manifest_current"]
    assert config["strategy_portfolio"]["contract_consistent"]
    assert config["strategy_portfolio"]["non_authorizing"]
    assert config["strategy_portfolio"]["provenance_gate_passed"]
    assert config["strategy_portfolio"]["dependency_count"] == 1
    assert config["strategy_portfolio"]["selected_profile"] == "leadlag"
    assert config["strategy_portfolio"]["selected_allocation_notional"] == 1200.0
    assert config["strategy_portfolio"]["leadlag_edge_lineage_required"]
    assert config["strategy_portfolio"]["leadlag_edge_lineage_ready"]
    assert config["strategy_portfolio"]["leadlag_lineage_bound_stages"] == 5
    assert (
        config["strategy_portfolio"]["leadlag_edge_lineage_contract_sha256"]
        == "c" * 64
    )
    assert config["strategy_portfolio"]["notional_cap_applied"]
    assert config["limits"]["max_notional_per_session"] == 1200.0
    assert path_tail(manifest["inputs"]["strategy_portfolio"]["path"]).endswith(
        "/strategy_portfolio/strategy_portfolio_summary.csv"
    )
    assert path_tail(manifest["inputs"]["strategy_portfolio_allocations"]["path"]).endswith(
        "/strategy_portfolio/strategy_portfolio_allocations.csv"
    )
    assert path_tail(
        manifest["inputs"]["strategy_portfolio_manifest"]["path"]
    ).endswith("/strategy_portfolio/manifest.json")
    assert len(manifest["inputs"]["strategy_portfolio_dependencies"]) == 1
    assert manifest["extra"]["strategy_portfolio_leadlag_edge_lineage_ready"]
    assert (
        manifest["extra"][
            "strategy_portfolio_leadlag_edge_lineage_contract_sha256"
        ]
        == "c" * 64
    )
    assert not config["authorizes_submission"]
    assert not manifest["extra"]["authorizes_submission"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed
    source = portfolio / "strategy_scorecard_source.csv"
    source.write_text(
        source.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_write_scaleup_blocks_portfolio_without_manifest(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    (portfolio / "manifest.json").unlink()

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(max_scale_multiplier=2.0),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert "strategy_portfolio_manifest_provided" in failed
    assert "strategy_portfolio_provenance_gate_passed" in failed
    assert report.plan.loc[0, "strategy_portfolio_selected_source_allocation_notional"] == 1200.0
    assert report.plan.loc[0, "strategy_portfolio_selected_allocation_notional"] == 0.0
    assert not bool(report.plan.loc[0, "strategy_portfolio_notional_cap_applied"])


def test_write_scaleup_blocks_drifted_portfolio_allocation(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    allocations_path = portfolio / "strategy_portfolio_allocations.csv"
    allocations = pd.read_csv(allocations_path)
    allocations.loc[0, "allocation_notional"] = 5000.0
    allocations.to_csv(allocations_path, index=False)

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert "strategy_portfolio_manifest_current" in failed
    assert report.config["strategy_portfolio"]["manifest_error"] == "artifact_drift"
    assert report.config["strategy_portfolio"]["selected_source_allocation_notional"] == 5000.0
    assert report.config["strategy_portfolio"]["selected_allocation_notional"] == 0.0


def test_write_scaleup_blocks_current_but_detached_portfolio_config(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    config_path = portfolio / "strategy_portfolio_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["allocations"][0]["allocation_notional"] = 9999.0
    config_path.write_text(json.dumps(config), encoding="utf-8")
    write_experiment_manifest(
        portfolio,
        run_type="strategy_portfolio_allocation",
        inputs={
            "strategy_scorecard": portfolio / "strategy_scorecard_source.csv"
        },
        extra={
            "ready": True,
            "research_family_bound": False,
            **leadlag_lineage(),
            "authorizes_submission": False,
        },
    )

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert bool(report.config["strategy_portfolio"]["manifest_current"])
    assert not bool(report.config["strategy_portfolio"]["contract_consistent"])
    assert "strategy_portfolio_contract_consistent" in failed
    assert "portfolio_allocation_allocation_notional_mismatch:0" in report.config[
        "strategy_portfolio"
    ]["contract_error"]


def test_write_scaleup_blocks_freshly_manifested_malformed_leadlag_lineage(
    tmp_path,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    malformed_sha = "not-a-sha256"
    summary_path = portfolio / "strategy_portfolio_summary.csv"
    summary = pd.read_csv(summary_path)
    summary["leadlag_edge_lineage_contract_sha256"] = malformed_sha
    summary.to_csv(summary_path, index=False)
    allocations_path = portfolio / "strategy_portfolio_allocations.csv"
    allocations = pd.read_csv(allocations_path)
    allocations["leadlag_edge_lineage_contract_sha256"] = malformed_sha
    allocations.to_csv(allocations_path, index=False)
    config_path = portfolio / "strategy_portfolio_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["leadlag_edge_lineage_contract_sha256"] = malformed_sha
    config["summary"]["leadlag_edge_lineage_contract_sha256"] = malformed_sha
    for row in config["allocations"]:
        row["leadlag_edge_lineage_contract_sha256"] = malformed_sha
    config_path.write_text(json.dumps(config), encoding="utf-8")
    malformed_lineage = leadlag_lineage()
    malformed_lineage["leadlag_edge_lineage_contract_sha256"] = malformed_sha
    write_experiment_manifest(
        portfolio,
        run_type="strategy_portfolio_allocation",
        inputs={
            "strategy_scorecard": portfolio / "strategy_scorecard_source.csv"
        },
        extra={
            "ready": True,
            "research_family_bound": False,
            **malformed_lineage,
            "authorizes_submission": False,
        },
    )

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    portfolio_config = report.config["strategy_portfolio"]
    assert not report.ready
    assert portfolio_config["manifest_current"]
    assert not portfolio_config["contract_consistent"]
    assert "strategy_portfolio_contract_consistent" in failed
    assert "portfolio_leadlag_edge_lineage_not_ready:summary" in portfolio_config[
        "contract_error"
    ]
    assert portfolio_config["selected_source_allocation_notional"] == 1200.0
    assert portfolio_config["selected_allocation_notional"] == 0.0


def test_write_scaleup_rejects_refreshed_nested_scorecard_lineage_drift(
    tmp_path,
):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    scorecard = write_lineage_scorecard(
        tmp_path / "strategy_scorecard",
        leadlag_lineage(),
    )
    bind_portfolio_to_scorecard(portfolio, scorecard)

    accepted = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "accepted_scaleup",
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    assert accepted.ready

    drifted_lineage = leadlag_lineage()
    drifted_lineage["leadlag_edge_lineage_contract_sha256"] = "d" * 64
    write_lineage_scorecard(scorecard, drifted_lineage)
    bind_portfolio_to_scorecard(portfolio, scorecard)
    rejected = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "rejected_scaleup",
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    failed = set(rejected.checks.loc[~rejected.checks["passed"], "check"])
    portfolio_config = rejected.config["strategy_portfolio"]
    assert not rejected.ready
    assert portfolio_config["manifest_current"]
    assert not portfolio_config["contract_consistent"]
    assert "strategy_portfolio_contract_consistent" in failed
    assert (
        "portfolio_leadlag_edge_lineage_contract_sha256_mismatch:"
        "nested_scorecard_ranked"
        in portfolio_config["contract_error"]
    )
    assert portfolio_config["selected_source_allocation_notional"] == 1200.0
    assert portfolio_config["selected_allocation_notional"] == 0.0


def test_write_scaleup_rejects_authorizing_portfolio_bundle(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    summary_path = portfolio / "strategy_portfolio_summary.csv"
    summary = pd.read_csv(summary_path)
    summary["authorizes_submission"] = True
    summary.to_csv(summary_path, index=False)
    allocations_path = portfolio / "strategy_portfolio_allocations.csv"
    allocations = pd.read_csv(allocations_path)
    allocations["authorizes_submission"] = True
    allocations.to_csv(allocations_path, index=False)
    config_path = portfolio / "strategy_portfolio_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["authorizes_submission"] = True
    config["summary"]["authorizes_submission"] = True
    for row in config["allocations"]:
        row["authorizes_submission"] = True
    config_path.write_text(json.dumps(config), encoding="utf-8")
    write_experiment_manifest(
        portfolio,
        run_type="strategy_portfolio_allocation",
        inputs={
            "strategy_scorecard": portfolio / "strategy_scorecard_source.csv"
        },
        extra={
            "ready": True,
            "research_family_bound": False,
            **leadlag_lineage(),
            "authorizes_submission": True,
        },
    )

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        strategy_portfolio_dir=portfolio,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.ready
    assert report.config["strategy_portfolio"]["manifest_current"]
    assert not report.config["strategy_portfolio"]["non_authorizing"]
    assert "strategy_portfolio_non_authorizing" in failed
    assert report.config["strategy_portfolio"]["selected_allocation_notional"] == 0.0
    assert not report.config["authorizes_submission"]


def test_write_scaleup_refuses_to_overwrite_portfolio_bundle(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_scaleup_plan(
            evidence_dir=evidence,
            shadow_comparison_dir=shadow,
            launch_dir=launch,
            strategy_portfolio_dir=portfolio,
            output_dir=portfolio,
            thresholds=ScaleUpThresholds(require_strategy_portfolio=True),
        )


def test_scaleup_plan_fails_on_instrument_metadata_gap():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(True),
        shadow_comparison_summary=shadow_summary(True),
        launch_summary=launch_summary(True),
        instrument_metadata_summary=instrument_metadata_summary(False, parse_coverage=0.5, unparsed_instruments=1),
        thresholds=ScaleUpThresholds(min_instrument_parse_coverage=1.0),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"instrument_metadata_passed", "instrument_parse_coverage"}.issubset(failed)
    assert report.config["instrument_metadata"]["unparsed_instruments"] == 1


def test_scaleup_plan_fails_on_incomplete_evidence_and_adapter_gap():
    report = evaluate_scaleup_plan(
        evidence_summary=evidence_summary(False),
        shadow_comparison_summary=shadow_summary(False),
        launch_summary=launch_summary(True, adapter="irage"),
        thresholds=ScaleUpThresholds(
            min_shadow_sessions=2,
            min_shadow_acceptance_rate=1.0,
            allowed_adapters=("arrow_money",),
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "evidence_ready" in failed
    assert "shadow_comparison_accepted" in failed
    assert "acceptance_rate" in failed
    assert "adapter_allowed" in failed


def test_write_scaleup_plan_outputs_artifacts(tmp_path):
    evidence, shadow, launch, exposure = write_inputs(tmp_path)
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    instrument_metadata_summary(True).to_csv(metadata / "instrument_metadata_summary.csv", index=False)
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        order_exposure_dir=exposure,
        instrument_metadata_dir=metadata,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(allowed_adapters=("arrow_money",), stop_loss=500.0),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert config["limits"]["stop_loss"] == 500.0
    assert config["instrument_metadata"]["provided"]
    assert (out_dir / "scaleup_plan.csv").exists()
    assert (out_dir / "scaleup_checks.csv").exists()
    assert (out_dir / "scaleup_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {
        "evidence",
        "shadow_comparison",
        "launch",
        "order_exposure",
        "instrument_metadata",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["evidence"]["path"]).endswith("/evidence/strategy_evidence_summary.csv")
    assert path_tail(manifest["inputs"]["shadow_comparison"]["path"]).endswith(
        "/shadow/shadow_session_comparison_summary.csv"
    )
    assert path_tail(manifest["inputs"]["launch"]["path"]).endswith("/launch/launch_summary.csv")
    assert path_tail(manifest["inputs"]["order_exposure"]["path"]).endswith(
        "/exposure/order_exposure_summary.csv"
    )
    assert path_tail(manifest["inputs"]["instrument_metadata"]["path"]).endswith(
        "/metadata/instrument_metadata_summary.csv"
    )


def test_write_scaleup_plan_verifies_proof_refresh_bundle(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    proof_refresh, proof_source = write_proof_refresh_bundle(
        tmp_path / "proof_refresh"
    )
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        proof_refresh_dir=proof_refresh,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    summary = report.summary.iloc[0]
    proof = report.config["proof_freshness"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert report.ready
    assert bool(summary["proof_refresh_requested"])
    assert bool(summary["proof_refresh_provided"])
    assert bool(summary["proof_refresh_reported_ready"])
    assert bool(summary["proof_refresh_ready"])
    assert bool(summary["proof_refresh_verified"])
    assert bool(summary["proof_refresh_manifest_current"])
    assert bool(summary["proof_refresh_semantically_verified"])
    assert summary["proof_refresh_reason"] == "ready"
    assert proof["requested"]
    assert proof["provided"]
    assert proof["reported_ready"]
    assert proof["ready"]
    assert proof["verified"]
    assert proof["manifest"]["required"]
    assert proof["manifest"]["current"]
    assert proof["manifest"]["sha256"] == file_sha256(
        proof_refresh / "manifest.json"
    )
    assert proof["semantic_verification"] == {
        "required": True,
        "verified": True,
        "inputs_current": True,
        "artifacts_consistent": True,
        "non_authorizing": True,
        "error": "",
    }
    assert {
        "proof_refresh",
        "proof_refresh_manifest",
        "proof_refresh_dependencies",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["proof_refresh"]["path"]).endswith(
        "/proof_refresh"
    )
    assert manifest["extra"]["proof_refresh_verified"]
    assert manifest["extra"]["proof_refresh_manifest_current"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    proof_source.write_text(
        "ts,bid,ask\n1,100,101\n2,101,102\n",
        encoding="utf-8",
    )
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_write_scaleup_plan_blocks_resealed_tampered_proof_refresh(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    proof_refresh, _ = write_proof_refresh_bundle(
        tmp_path / "proof_refresh"
    )
    refresh_summary_path = proof_refresh / "proof_refresh_summary.csv"
    refresh_summary = pd.read_csv(refresh_summary_path)
    refresh_summary.loc[0, "proof_source"] = "latest"
    refresh_summary.to_csv(refresh_summary_path, index=False)
    reseal_experiment_manifest(proof_refresh)
    assert verify_experiment_manifest(
        proof_refresh / "manifest.json",
        expected_run_type="proof_refresh_gate",
        require_input_fingerprints=True,
    ).passed
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        proof_refresh_dir=proof_refresh,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    summary = report.summary.iloc[0]
    proof = report.config["proof_freshness"]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    expected_error = "artifacts do not reconstruct from inputs"
    expected_reason = (
        "proof_refresh_verification_"
        "artifacts_do_not_reconstruct_from_inputs"
    )
    assert not report.ready
    assert {
        "proof_refresh_semantically_verified",
        "proof_refresh_ready",
    } <= failed
    assert "proof_refresh_manifest_current" not in failed
    assert bool(summary["proof_refresh_reported_ready"])
    assert not bool(summary["proof_refresh_ready"])
    assert not bool(summary["proof_refresh_verified"])
    assert bool(summary["proof_refresh_manifest_current"])
    assert not bool(summary["proof_refresh_semantically_verified"])
    assert summary["proof_refresh_verification_error"] == expected_error
    assert summary["proof_refresh_reason"] == expected_reason
    assert proof["reported_ready"]
    assert not proof["ready"]
    assert not proof["verified"]
    assert proof["manifest"]["current"]
    assert not proof["semantic_verification"]["verified"]
    assert not proof["semantic_verification"]["artifacts_consistent"]
    assert proof["semantic_verification"]["error"] == expected_error
    assert proof["reason"] == expected_reason
    assert not manifest["extra"]["proof_refresh_verified"]
    assert manifest["extra"]["proof_refresh_manifest_current"]


def test_write_scaleup_plan_blocks_unbound_proof_refresh_csv(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    proof_refresh, _ = write_proof_refresh_bundle(
        tmp_path / "proof_refresh"
    )
    unbound_summary = proof_refresh / "operator_summary.csv"
    summary = pd.read_csv(proof_refresh / "proof_refresh_summary.csv")
    summary.loc[0, "proof_source"] = "latest"
    summary.to_csv(unbound_summary, index=False)
    assert verify_experiment_manifest(
        proof_refresh / "manifest.json",
        expected_run_type="proof_refresh_gate",
        require_input_fingerprints=True,
    ).passed

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        proof_refresh_dir=unbound_summary,
        output_dir=tmp_path / "scaleup",
        thresholds=ScaleUpThresholds(require_proof_refresh=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    proof = report.config["proof_freshness"]
    assert not report.ready
    assert {
        "proof_refresh_available",
        "proof_refresh_ready",
    } <= failed
    assert "proof_refresh_semantically_verified" not in failed
    assert proof["manifest"]["current"]
    assert proof["semantic_verification"]["verified"]
    assert not proof["verified"]
    assert proof["read_error"] == "summary_path_invalid"
    assert proof["reason"] == "proof_refresh_summary_path_invalid"


def test_write_scaleup_plan_fingerprints_route_readiness_input(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    route = tmp_path / "route_readiness"
    route.mkdir()
    route_readiness_summary(True).to_csv(route / "route_readiness_summary.csv", index=False)
    out_dir = tmp_path / "scaleup"

    report = write_scaleup_plan(
        evidence_dir=evidence,
        shadow_comparison_dir=shadow,
        launch_dir=launch,
        route_readiness_dir=route,
        output_dir=out_dir,
        thresholds=ScaleUpThresholds(require_route_readiness=True),
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert config["route_readiness"]["required"]
    assert config["route_readiness"]["ready"]
    assert path_tail(manifest["inputs"]["route_readiness"]["path"]).endswith(
        "/route_readiness/route_readiness_summary.csv"
    )


def test_cli_scaleup_plan_can_fail_on_breach(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path, evidence_ready=False)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--allowed-adapter",
            "arrow_money",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_checks"]) == 1


def test_cli_scaleup_plan_can_require_expected_identity(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path, strategy="imbalance", market="us_equities_regular")
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--expected-strategy",
            "leadlag",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {"evidence_strategy_matches", "evidence_market_matches"} <= failed


def test_cli_scaleup_plan_can_require_strategy_portfolio(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    portfolio = write_strategy_portfolio(tmp_path, allocation_notional=1200.0)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--strategy-portfolio",
            str(portfolio),
            "--require-strategy-portfolio",
            "--max-scale-multiplier",
            "2.0",
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert summary.loc[0, "max_notional_per_session"] == 1200.0
    assert bool(summary.loc[0, "strategy_portfolio_notional_cap_applied"])
    assert config["strategy_portfolio"]["required"]
    assert config["strategy_portfolio"]["selected_allocation_notional"] == 1200.0


def test_cli_scaleup_plan_can_require_proof_refresh(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-proof-refresh",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "proof_refresh_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_instrument_metadata(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-instrument-metadata",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "instrument_metadata_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_broker_readiness(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "broker_readiness_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_route_readiness(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_readiness_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_resume_gate(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-resume-gate",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {"broker_readiness_available", "broker_resume_gate_provided"} <= failed


def test_cli_scaleup_plan_can_require_dispatch_roundtrip(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {"broker_readiness_available", "broker_dispatch_roundtrip_provided"} <= failed


def test_cli_scaleup_plan_live_dryrun_auto_requires_broker_runtime_evidence(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--target-mode",
            "live_dryrun",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        "route_readiness_available",
        "broker_readiness_available",
        "broker_runtime_session_provided",
        "broker_dispatch_roundtrip_provided",
    } <= failed


def test_cli_scaleup_plan_reads_settlement_launch_pipeline_outputs(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path)
    pipeline = write_settlement_pipeline(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert config["broker_readiness"]["provided"]
    assert config["broker_readiness"]["ready"]


def test_cli_scaleup_plan_reads_surface_launch_pipeline_outputs(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path, strategy="surface_mm")
    pipeline = write_surface_launch_pipeline(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "surface_launch_pipeline_ready"])
    assert summary.loc[0, "surface_launch_strategy"] == "surface_mm"
    assert config["broker_readiness"]["provided"]
    assert config["broker_readiness"]["ready"]
    assert config["surface_launch_pipeline"]["provided"]
    assert config["surface_launch_pipeline"]["market"] == "india_nse_index_derivatives"


def test_cli_scaleup_plan_reads_strategy_launch_pipeline_roots(tmp_path):
    cases = [
        ("leadlag", "leadlag_launch_pipeline_summary.csv", "lead_lag_taker"),
        ("imbalance", "imbalance_launch_pipeline_summary.csv", "imbalance"),
        ("parity", "parity_launch_pipeline_summary.csv", "parity"),
    ]
    for family, summary_file, strategy in cases:
        case_dir = tmp_path / family
        evidence, shadow, _, _ = write_inputs(case_dir, strategy=strategy)
        pipeline = write_strategy_launch_pipeline(
            case_dir,
            family=family,
            summary_file=summary_file,
            strategy=strategy,
        )
        out_dir = case_dir / "scaleup"

        code = main(
            [
                "plan-scaleup",
                "--evidence",
                str(evidence),
                "--shadow-comparison",
                str(shadow),
                "--launch",
                str(pipeline),
                "--out",
                str(out_dir),
                "--require-broker-readiness",
                "--fail-on-breach",
            ]
        )

        summary = pd.read_csv(out_dir / "scaleup_summary.csv")
        config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert code == 0
        assert bool(summary.loc[0, "ready"])
        assert bool(summary.loc[0, "launch_pipeline_ready"])
        assert summary.loc[0, "launch_pipeline_family"] == family
        assert summary.loc[0, "launch_pipeline_strategy"] == strategy
        assert config["launch_pipeline"]["provided"]
        assert config["launch_pipeline"]["family"] == family
        assert config["broker_readiness"]["provided"]
        assert config["broker_readiness"]["ready"]
        assert path_tail(manifest["inputs"]["launch"]["path"]).endswith(
            f"/{family}_launch_pipeline/03_launch/launch_summary.csv"
        )
        assert path_tail(manifest["inputs"]["launch_pipeline"]["path"]).endswith(
            f"/{family}_launch_pipeline/{summary_file}"
        )
        assert path_tail(manifest["inputs"]["broker_readiness"]["path"]).endswith(
            f"/{family}_launch_pipeline/06_broker_readiness/broker_readiness_summary.csv"
        )
        assert path_tail(manifest["inputs"]["broker_readiness_config"]["path"]).endswith(
            f"/{family}_launch_pipeline/06_broker_readiness/broker_readiness_config.json"
        )


def test_cli_scaleup_plan_hydrates_launch_root_broker_route_ops_without_broker_dir(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path)
    pipeline = write_strategy_launch_pipeline(
        tmp_path,
        include_broker_dir=False,
        launch_root_broker_route_proof=True,
    )
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_readiness_ready"])
    assert bool(summary.loc[0, "broker_route_readiness_ready"])
    assert bool(summary.loc[0, "broker_route_readiness_ops_launch_controls_ready"])
    assert int(summary.loc[0, "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(summary.loc[0, "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) == 1
    assert int(summary.loc[0, "broker_route_readiness_ops_broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(summary.loc[0, "broker_route_readiness_ops_broker_roundtrip_resume_route_breach_runs"]) == 0
    assert "broker_readiness_available" not in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert config["broker_readiness"]["provided"]
    assert config["broker_readiness"]["route_readiness"]["ops_broker_roundtrip_portfolio_safe_runs"] == 1
    assert config["broker_readiness"]["route_readiness"]["ops_broker_roundtrip_resume_route_ready_runs"] == 1
    assert config["route_readiness"]["ops_broker_roundtrip_resume_route_breach_pairs"] == 0
    assert "broker_readiness" not in manifest["inputs"]
    assert path_tail(manifest["inputs"]["launch_pipeline"]["path"]).endswith(
        "/leadlag_launch_pipeline/leadlag_launch_pipeline_summary.csv"
    )


def test_cli_scaleup_plan_hydrates_launch_pipeline_broker_vendor_data_config(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path)
    pipeline = write_strategy_launch_pipeline(tmp_path)
    broker = pipeline / "06_broker_readiness"
    write_verified_broker_readiness_bundle(
        tmp_path / "verified_broker_sources",
        broker,
    )
    verified_config = json.loads(
        (broker / "broker_readiness_config.json").read_text(encoding="utf-8")
    )
    target_batch = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(target_batch["datasets"])
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                **verified_config,
                "ready": True,
                "adapter": "arrow_money",
                "dispatch_roundtrip": {
                    **verified_config["dispatch_roundtrip"],
                    "provided": True,
                    "ready": True,
                    "strategy": "lead_lag_taker",
                    "market": "india_nse_index_derivatives",
                    "broker_dispatch_roundtrip_vendor_market_data_batch": (
                        target_batch
                    ),
                    "vendor_market_data_batch_lineage_comparison": {
                        "required": True,
                        "matches": True,
                        "current_application_lineage_sha256": lineage_sha256,
                        "broker_application_lineage_sha256": lineage_sha256,
                    },
                    "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        target_application_lineage_comparison(target_batch)
                    ),
                    "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        broker_readiness_final_target_application_lineage_comparison(
                            target_batch
                        )
                    ),
                    "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        broker_readiness_complete_final_target_application_lineage_comparison(
                            target_batch
                        )
                    ),
                    "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        broker_readiness_view_34_target_application_lineage_comparison(
                            target_batch
                        )
                    ),
                    "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        broker_readiness_view_42_target_application_lineage_comparison(
                            target_batch
                        )
                    ),
                    "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        broker_readiness_view_50_target_application_lineage_comparison(
                            target_batch
                        )
                    ),
                        "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                            broker_readiness_view_58_target_application_lineage_comparison(
                                target_batch
                            )
                        ),
                        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                            broker_readiness_view_66_target_application_lineage_comparison(
                                target_batch
                            )
                        ),
                        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                            broker_readiness_view_74_target_application_lineage_comparison(
                                target_batch
                            )
                        ),
                    },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    from tests.test_broker_dispatch_send import _refresh_manifest

    _refresh_manifest(broker / "manifest.json")
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    vendor = config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_readiness_lineage_gate_passed"])
    assert bool(summary.loc[0, "broker_readiness_roundtrip_lineage_gate_passed"])
    assert bool(summary.loc[0, "broker_readiness_roundtrip_matches_current"])
    assert {
        "broker_dispatch_roundtrip_target_mode_matches",
        "broker_route_dispatch_roundtrip_target_mode_matches",
    } <= failed
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode"] == (
        "per_dataset_verified_target_application"
    )
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count"]) == 2
    assert int(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications"]) == 2
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage"] == 1.0
    assert bool(
        summary.loc[
            0,
            "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistency_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        ]
    )
    assert bool(summary.loc[0, "broker_vendor_market_data_batch_lineage_match_required"])
    assert bool(summary.loc[0, "broker_vendor_market_data_batch_lineage_matches"])
    assert bool(
        summary.loc[
            0,
            "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ]
    )
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["mapping_source_mode"] == "per_dataset_verified_target_application"
    assert vendor["mapping_application_count"] == 2
    assert vendor["unique_mapping_applications"] == 2
    assert vendor["target_application_coverage"] == 1.0
    assert vendor["application_lineage_consistency_required"]
    assert vendor["application_lineage_consistent"]
    assert vendor["application_lineage_sha256"] == lineage_sha256
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64
    assert vendor["datasets"][1]["mapping_application_id"] == "mapping-app-day2"
    lineage = config["broker_readiness"]["dispatch_roundtrip"][
        "vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["required"]
    assert lineage["matches"]
    assert lineage["current_application_lineage_sha256"] == lineage_sha256
    assert lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert lineage["carried_application_lineage_sha256"] == lineage_sha256
    final_lineage = config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["readiness_carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    readiness_final_prefix = (
        "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(summary.loc[0, f"{readiness_final_prefix}_lineage_match_required"])
    assert bool(summary.loc[0, f"{readiness_final_prefix}_lineage_matches"])
    assert summary.loc[
        0,
        f"{readiness_final_prefix}_broker_readiness_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_final = config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_final["required"]
    assert scaleup_final["matches"]
    assert scaleup_final[
        "roundtrip_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_final[
        "broker_readiness_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_final["carried_application_lineage_sha256"] == lineage_sha256
    readiness_complete_final_prefix = (
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_complete_final_prefix}_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[0, f"{readiness_complete_final_prefix}_lineage_matches"]
    )
    assert summary.loc[
        0,
        f"{readiness_complete_final_prefix}_broker_readiness_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    assert summary.loc[
        0,
        f"{readiness_complete_final_prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_complete_final = config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_complete_final["required"]
    assert scaleup_complete_final["matches"]
    assert scaleup_complete_final[
        "roundtrip_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_complete_final[
        "broker_readiness_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    readiness_extended_complete_final_prefix = (
        "broker_readiness_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_extended_complete_final_prefix}_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_extended_complete_final_prefix}_lineage_matches",
        ]
    )
    assert summary.loc[
        0,
        f"{readiness_extended_complete_final_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    assert summary.loc[
        0,
        f"{readiness_extended_complete_final_prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_extended_complete_final = config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_extended_complete_final["required"]
    assert scaleup_extended_complete_final["matches"]
    assert scaleup_extended_complete_final[
        "roundtrip_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_extended_complete_final[
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_extended_complete_final[
        "carried_application_lineage_sha256"
    ] == lineage_sha256
    readiness_latest_extended_complete_final_prefix = (
        "broker_readiness_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_latest_extended_complete_final_prefix}_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_latest_extended_complete_final_prefix}_lineage_matches",
        ]
    )
    assert summary.loc[
        0,
        f"{readiness_latest_extended_complete_final_prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    assert summary.loc[
        0,
        f"{readiness_latest_extended_complete_final_prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_latest_extended_complete_final = config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_latest_extended_complete_final["required"]
    assert scaleup_latest_extended_complete_final["matches"]
    assert scaleup_latest_extended_complete_final[
        "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_latest_extended_complete_final[
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_latest_extended_complete_final[
        "carried_application_lineage_sha256"
    ] == lineage_sha256
    readiness_current_latest_extended_complete_final_prefix = (
        "broker_readiness_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_current_latest_extended_complete_final_prefix}_lineage_matches",
        ]
    )
    assert summary.loc[
        0,
        f"{readiness_current_latest_extended_complete_final_prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    assert summary.loc[
        0,
        f"{readiness_current_latest_extended_complete_final_prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_current_latest_extended_complete_final = config["broker_readiness"][
        "dispatch_roundtrip"
    ][
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert scaleup_current_latest_extended_complete_final["required"]
    assert scaleup_current_latest_extended_complete_final["matches"]
    assert scaleup_current_latest_extended_complete_final[
        "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_current_latest_extended_complete_final[
        "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_current_latest_extended_complete_final[
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert scaleup_current_latest_extended_complete_final[
        "carried_application_lineage_sha256"
    ] == lineage_sha256
    readiness_reconciled_current_latest_extended_complete_final_prefix = (
        "broker_readiness_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
        ]
    )
    assert summary.loc[
        0,
        f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    assert summary.loc[
        0,
        f"{readiness_reconciled_current_latest_extended_complete_final_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_reconciled_current_latest_extended_complete_final = config[
        "broker_readiness"
    ]["dispatch_roundtrip"][
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_scaleup_view_59 = scaleup_view_59_target_application_lineage_comparison(
        target_batch
    )
    assert scaleup_reconciled_current_latest_extended_complete_final == (
        expected_scaleup_view_59
    )
    assert len(scaleup_reconciled_current_latest_extended_complete_final) == 58
    confirmed_prefix = (
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(summary.loc[0, f"{confirmed_prefix}_lineage_match_required"])
    assert bool(summary.loc[0, f"{confirmed_prefix}_lineage_matches"])
    assert summary.loc[
        0,
        f"{confirmed_prefix}_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    assert summary.loc[
        0,
        f"{confirmed_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] == lineage_sha256
    scaleup_view_75 = config["broker_readiness"]["dispatch_roundtrip"][
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert len(scaleup_view_75) == 74
    assert scaleup_view_75 == scaleup_view_75_target_application_lineage_comparison(
        target_batch
    )
    assert path_tail(manifest["inputs"]["broker_readiness_config"]["path"]).endswith(
        "/leadlag_launch_pipeline/06_broker_readiness/broker_readiness_config.json"
    )


def test_cli_scaleup_plan_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path)
    pipeline = write_strategy_launch_pipeline(tmp_path)
    broker = pipeline / "06_broker_readiness"
    write_verified_broker_readiness_bundle(
        tmp_path / "verified_broker_sources",
        broker,
    )
    verified_config = json.loads(
        (broker / "broker_readiness_config.json").read_text(encoding="utf-8")
    )
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                **verified_config,
                "ready": True,
                "adapter": "arrow_money",
                "dispatch_roundtrip": {
                    **verified_config["dispatch_roundtrip"],
                    "provided": True,
                    "ready": True,
                    "strategy": "lead_lag_taker",
                    "market": "india_nse_index_derivatives",
                    "broker_vendor_data_readiness": {
                        "provided": True,
                        "ready": False,
                        "failed_checks": 1,
                    },
                    "broker_dispatch_roundtrip_vendor_market_data_batch": (
                        broker_vendor_market_data_batch_config()
                    ),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    from tests.test_broker_dispatch_send import _refresh_manifest

    _refresh_manifest(broker / "manifest.json")
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    vendor_readiness = config["broker_readiness"]["broker_vendor_data_readiness"]
    vendor_batch = config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "broker_vendor_data_readiness_failed_checks"]) == 1
    assert {
        "broker_vendor_data_readiness_ready",
        "broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert vendor_readiness == {
        "provided": True,
        "ready": False,
        "failed_checks": 1,
    }
    assert vendor_batch["ready"]
    assert vendor_batch["dataset_count"] == 2


def test_cli_scaleup_plan_direct_launch_summary_file_ignores_pipeline_detector(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch / "launch_summary.csv"),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert not bool(summary.loc[0, "launch_pipeline_provided"])
    assert not config["launch_pipeline"]["provided"]


def test_cli_scaleup_plan_blocks_strategy_launch_pipeline_market_mismatch(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path, strategy="parity", market="india_nse_index_derivatives")
    pipeline = write_strategy_launch_pipeline(
        tmp_path,
        family="parity",
        summary_file="parity_launch_pipeline_summary.csv",
        strategy="parity",
        market="us_options_regular",
    )
    out_dir = tmp_path / "scaleup_parity_mismatch"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--expected-strategy",
            "parity",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "launch_pipeline_market"] == "us_options_regular"
    assert "launch_pipeline_market_matches" in failed


def test_cli_scaleup_plan_blocks_surface_launch_pipeline_market_mismatch(tmp_path):
    evidence, shadow, _, _ = write_inputs(tmp_path, strategy="surface_mm", market="india_nse_index_derivatives")
    pipeline = write_surface_launch_pipeline(tmp_path, strategy="surface_mm", market="us_options_regular")
    out_dir = tmp_path / "scaleup_surface_mismatch"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(pipeline),
            "--out",
            str(out_dir),
            "--require-broker-readiness",
            "--expected-strategy",
            "surface_mm",
            "--expected-market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "surface_launch_market"] == "us_options_regular"
    assert "surface_launch_market_matches" in failed


def test_cli_scaleup_plan_can_require_data_readiness(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-data-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "data_readiness_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_can_require_data_readiness_comparison(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--require-data-readiness-comparison",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "scaleup_summary.csv")
    checks = pd.read_csv(out_dir / "scaleup_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "data_readiness_comparison_available" in set(checks.loc[~checks["passed"].astype(bool), "check"])


def test_cli_scaleup_plan_writes_runtime_freshness_kill_switch(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    out_dir = tmp_path / "scaleup"

    code = main(
        [
            "plan-scaleup",
            "--evidence",
            str(evidence),
            "--shadow-comparison",
            str(shadow),
            "--launch",
            str(launch),
            "--out",
            str(out_dir),
            "--max-telemetry-age-ns",
            "5000000000",
            "--max-lifecycle-orders",
            "6",
            "--max-replace-orders",
            "2",
            "--max-open-order-count",
            "2",
            "--max-open-order-qty",
            "75",
            "--max-open-order-notional",
            "1000",
            "--max-open-order-age-ns",
            "5000000000",
            "--max-gross-position-qty",
            "150",
            "--max-abs-net-position-qty",
            "75",
            "--max-gross-notional",
            "2000",
            "--max-abs-net-delta",
            "100",
            "--max-abs-net-vega",
            "250",
        ]
    )

    config = json.loads((out_dir / "scaleup_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert config["kill_switches"]["max_telemetry_age_ns"] == 5_000_000_000
    assert config["kill_switches"]["max_lifecycle_orders"] == 6
    assert config["kill_switches"]["max_replace_orders"] == 2
    assert config["kill_switches"]["max_open_order_count"] == 2
    assert config["kill_switches"]["max_open_order_qty"] == 75.0
    assert config["kill_switches"]["max_open_order_notional"] == 1000.0
    assert config["kill_switches"]["max_open_order_age_ns"] == 5_000_000_000.0
    assert config["kill_switches"]["max_gross_position_qty"] == 150.0
    assert config["kill_switches"]["max_abs_net_position_qty"] == 75.0
    assert config["kill_switches"]["max_gross_notional"] == 2000.0
    assert config["kill_switches"]["max_abs_net_delta"] == 100.0
    assert config["kill_switches"]["max_abs_net_vega"] == 250.0
