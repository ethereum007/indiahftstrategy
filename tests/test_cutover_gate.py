import hashlib
import json
import shutil

import pandas as pd
import pytest

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.cutover import CutoverGateThresholds, evaluate_cutover_gate, write_cutover_gate_report
from reports.manifest import file_sha256, verify_experiment_manifest, write_experiment_manifest
from reports.operational_lineage import (
    broker_readiness_lineage_fields,
    broker_readiness_lineage_manifest_inputs,
    load_broker_readiness_lineage,
    load_cutover_lineage,
)
from reports.runtime_guard import RUNTIME_LINEAGE_COLUMNS, SCALEUP_PROVENANCE_COLUMNS
from reports.runtime_session import write_runtime_session_monitor


def leadlag_lineage(prefix=""):
    fields = {
        "leadlag_edge_lineage_required": True,
        "leadlag_edge_lineage_ready": True,
        "leadlag_lineage_bound_stages": 5,
        "leadlag_lineage_required_stages": 5,
        "leadlag_lineage_selected_stage_count": 5,
        "leadlag_lineage_selected_run_dirs": ";".join(
            [
                "edge-audit",
                "replay-walkforward",
                "promotion",
                "order-plan",
                "launch-pipeline",
            ]
        ),
        "leadlag_measurement_manifest_sha256": "a" * 64,
        "leadlag_edge_candidate_manifest_sha256": "b" * 64,
        "leadlag_edge_lineage_contract_version": "leadlag_edge_lineage/v1",
        "leadlag_edge_lineage_contract_sha256": "c" * 64,
        "leadlag_edge_latency_budget_ns": 5_000.0,
        "leadlag_total_replay_latency_ns": 3_000.0,
        "leadlag_edge_latency_headroom_ns": 2_000.0,
    }
    return {f"{prefix}{field}": value for field, value in fields.items()}


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


def target_application_lineage_comparison(vendor):
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    return {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": lineage_sha256,
        "broker_application_lineage_sha256": lineage_sha256,
        "carried_application_lineage_sha256": lineage_sha256,
    }


def final_target_application_lineage_comparison(vendor, **overrides):
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def scaleup_final_target_application_lineage_comparison(vendor, **overrides):
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    comparison = final_target_application_lineage_comparison(vendor)
    comparison.update(
        {
            "scaleup_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_review_carried_application_lineage_sha256": lineage_sha256,
            "route_enable_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_plan_review_carried_application_lineage_sha256": lineage_sha256,
            "send_packet_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_reconciliation_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_complete_final_target_application_lineage_comparison(
    vendor,
    **overrides,
):
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    comparison = scaleup_final_target_application_lineage_comparison(vendor)
    comparison.update(
        {
            "scaleup_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_view_35_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = scaleup_complete_final_target_application_lineage_comparison(
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
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_view_43_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = scaleup_view_35_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def scaleup_view_51_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = scaleup_view_35_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.pop(
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
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
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
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
    comparison = scaleup_view_51_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.pop(
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
        None,
    )
    comparison.update(
        {
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
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
    comparison = scaleup_view_59_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
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
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = scaleup_view_67_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def cutover_view_60_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = scaleup_view_59_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def cutover_view_68_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = scaleup_view_67_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def cutover_view_76_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    cutover_lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    cutover_lineage_sha256 = cutover_lineage_sha256 or lineage_sha256
    comparison = scaleup_view_75_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": cutover_lineage_sha256,
            "carried_application_lineage_sha256": cutover_lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def add_scaleup_final_target_application_lineage(config, vendor, **overrides):
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_final_target_application_lineage_comparison(
        vendor,
        **overrides,
    )
    dispatch[
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_complete_final_target_application_lineage_comparison(vendor)
    dispatch[
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_35_target_application_lineage_comparison(vendor)
    dispatch[
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_43_target_application_lineage_comparison(vendor)
    dispatch[
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_51_target_application_lineage_comparison(vendor)
    dispatch[
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_59_target_application_lineage_comparison(vendor)
    dispatch[
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_67_target_application_lineage_comparison(vendor)
    dispatch[
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_75_target_application_lineage_comparison(vendor)


def scaleup_summary(
    ready=True,
    target_mode="live_dryrun",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    adapter="arrow_money",
    failed_checks=0,
    dispatch_provided=True,
    dispatch_ready=True,
    dispatch_target_mode=None,
    dispatch_strategy=None,
    dispatch_market=None,
    dispatch_scenario_key="trigger_ticks=2",
    dispatch_batch_id="BDP-1",
    dispatch_requests=2,
    dispatch_acked_orders=2,
    dispatch_missing_request_acks=0,
    dispatch_rejected_orders=0,
    dispatch_unmatched_acks=0,
    dispatch_failed_checks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_required=None,
    route_provided=None,
    route_ready=None,
    route_target_mode=None,
    route_strategy=None,
    route_market=None,
    route_scenario_key=None,
    route_batch_id="BDP-0",
    route_requests=None,
    route_acked_orders=None,
    route_missing_request_acks=None,
    route_rejected_orders=None,
    route_unmatched_acks=None,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy=None,
    route_readiness_market=None,
    route_ready_pairs=1,
    route_gap_pairs=0,
    route_ops_launch_controls_present=True,
    route_ops_launch_controls_blocked_pairs=0,
    route_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    broker_route_readiness_required=True,
    broker_route_readiness_provided=True,
    broker_route_readiness_ready=True,
    broker_route_readiness_strategy=None,
    broker_route_readiness_market=None,
    broker_route_readiness_route_ready_pairs=1,
    broker_route_readiness_gap_pairs=0,
    broker_route_readiness_recommendation=None,
    broker_route_readiness_ops_launch_controls_ready=True,
    broker_route_readiness_ops_launch_control_failures="",
    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    dispatch_target_mode = target_mode if dispatch_target_mode is None else dispatch_target_mode
    dispatch_strategy = strategy if dispatch_strategy is None else dispatch_strategy
    dispatch_market = market if dispatch_market is None else dispatch_market
    route_required = dispatch_provided if route_required is None else route_required
    route_provided = dispatch_provided if route_provided is None else route_provided
    route_ready = dispatch_ready if route_ready is None else route_ready
    route_target_mode = dispatch_target_mode if route_target_mode is None else route_target_mode
    route_strategy = dispatch_strategy if route_strategy is None else route_strategy
    route_market = dispatch_market if route_market is None else route_market
    route_scenario_key = dispatch_scenario_key if route_scenario_key is None else route_scenario_key
    route_requests = dispatch_requests if route_requests is None else route_requests
    route_acked_orders = dispatch_acked_orders if route_acked_orders is None else route_acked_orders
    route_missing_request_acks = (
        dispatch_missing_request_acks if route_missing_request_acks is None else route_missing_request_acks
    )
    route_rejected_orders = dispatch_rejected_orders if route_rejected_orders is None else route_rejected_orders
    route_unmatched_acks = dispatch_unmatched_acks if route_unmatched_acks is None else route_unmatched_acks
    route_readiness_strategy = strategy if route_readiness_strategy is None else route_readiness_strategy
    route_readiness_market = market if route_readiness_market is None else route_readiness_market
    broker_route_readiness_strategy = (
        strategy if broker_route_readiness_strategy is None else broker_route_readiness_strategy
    )
    broker_route_readiness_market = (
        market if broker_route_readiness_market is None else broker_route_readiness_market
    )
    broker_route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if broker_route_readiness_recommendation is None and broker_route_readiness_ready
        else "complete_route_readiness_gaps"
        if broker_route_readiness_recommendation is None
        else broker_route_readiness_recommendation
    )
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "target_mode": target_mode,
                "strategy": strategy,
                "market": market,
                "scenario_key": "trigger_ticks=2",
                "adapter": adapter,
                "max_orders_per_session": 10,
                "max_notional_per_session": 100_000.0,
                "proof_refresh_provided": True,
                "proof_refresh_ready": True,
                "proof_refresh_strategy": strategy,
                "proof_refresh_market": market,
                "proof_refresh_mixed_identity": False,
                "proof_source": "latest",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "route_readiness_required": target_mode == "live_dryrun",
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_ready_pairs,
                "route_readiness_gap_pairs": route_gap_pairs,
                "route_readiness_ops_launch_controls_present": route_ops_launch_controls_present,
                "route_readiness_ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
                "route_readiness_recommendation": "eligible_for_live_dryrun_route_review"
                if route_readiness_ready
                else "complete_route_readiness_gaps",
                "broker_route_readiness_required": broker_route_readiness_required,
                "broker_route_readiness_provided": broker_route_readiness_provided,
                "broker_route_readiness_ready": broker_route_readiness_ready,
                "broker_route_readiness_strategy": broker_route_readiness_strategy,
                "broker_route_readiness_market": broker_route_readiness_market,
                "broker_route_readiness_route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "broker_route_readiness_gap_pairs": broker_route_readiness_gap_pairs,
                "broker_route_readiness_recommendation": broker_route_readiness_recommendation,
                "broker_route_readiness_ops_launch_controls_ready": (
                    broker_route_readiness_ops_launch_controls_ready
                ),
                "broker_route_readiness_ops_launch_control_failures": (
                    broker_route_readiness_ops_launch_control_failures
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "broker_dispatch_roundtrip_required": True,
                "broker_dispatch_roundtrip_provided": dispatch_provided,
                "broker_dispatch_roundtrip_ready": dispatch_ready,
                "broker_dispatch_roundtrip_target_mode": dispatch_target_mode,
                "broker_dispatch_roundtrip_strategy": dispatch_strategy,
                "broker_dispatch_roundtrip_market": dispatch_market,
                "broker_dispatch_roundtrip_scenario_key": dispatch_scenario_key,
                "broker_dispatch_roundtrip_batch_id": dispatch_batch_id,
                "broker_dispatch_roundtrip_requests": dispatch_requests,
                "broker_dispatch_roundtrip_acked_orders": dispatch_acked_orders,
                "broker_dispatch_roundtrip_missing_request_acks": dispatch_missing_request_acks,
                "broker_dispatch_roundtrip_rejected_orders": dispatch_rejected_orders,
                "broker_dispatch_roundtrip_unmatched_acks": dispatch_unmatched_acks,
                "broker_dispatch_roundtrip_failed_checks": dispatch_failed_checks,
                "broker_route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "broker_route_dispatch_roundtrip_required": route_required,
                "broker_route_dispatch_roundtrip_provided": route_provided,
                "broker_route_dispatch_roundtrip_ready": route_ready,
                "broker_route_dispatch_roundtrip_target_mode": route_target_mode,
                "broker_route_dispatch_roundtrip_strategy": route_strategy,
                "broker_route_dispatch_roundtrip_market": route_market,
                "broker_route_dispatch_roundtrip_scenario_key": route_scenario_key,
                "broker_route_dispatch_roundtrip_batch_id": route_batch_id,
                "broker_route_dispatch_roundtrip_requests": route_requests,
                "broker_route_dispatch_roundtrip_acked_orders": route_acked_orders,
                "broker_route_dispatch_roundtrip_missing_request_acks": route_missing_request_acks,
                "broker_route_dispatch_roundtrip_rejected_orders": route_rejected_orders,
                "broker_route_dispatch_roundtrip_unmatched_acks": route_unmatched_acks,
                "failed_checks": failed_checks if ready else max(1, failed_checks),
                "recommendation": "scale_up_with_controls" if ready else "do_not_scale",
            }
        ]
    )


def scaleup_config(
    target_mode="live_dryrun",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    adapter="arrow_money",
    dispatch_provided=True,
    dispatch_ready=True,
    dispatch_target_mode=None,
    dispatch_strategy=None,
    dispatch_market=None,
    dispatch_scenario_key="trigger_ticks=2",
    dispatch_batch_id="BDP-1",
    dispatch_requests=2,
    dispatch_acked_orders=2,
    dispatch_missing_request_acks=0,
    dispatch_rejected_orders=0,
    dispatch_unmatched_acks=0,
    dispatch_failed_checks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_required=None,
    route_provided=None,
    route_ready=None,
    route_target_mode=None,
    route_strategy=None,
    route_market=None,
    route_scenario_key=None,
    route_batch_id="BDP-0",
    route_requests=None,
    route_acked_orders=None,
    route_missing_request_acks=None,
    route_rejected_orders=None,
    route_unmatched_acks=None,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy=None,
    route_readiness_market=None,
    route_ready_pairs=1,
    route_gap_pairs=0,
    route_ops_launch_controls_present=True,
    route_ops_launch_controls_blocked_pairs=0,
    route_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    broker_route_readiness_required=True,
    broker_route_readiness_provided=True,
    broker_route_readiness_ready=True,
    broker_route_readiness_strategy=None,
    broker_route_readiness_market=None,
    broker_route_readiness_route_ready_pairs=1,
    broker_route_readiness_gap_pairs=0,
    broker_route_readiness_recommendation=None,
    broker_route_readiness_ops_launch_controls_ready=True,
    broker_route_readiness_ops_launch_control_failures="",
    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    dispatch_target_mode = target_mode if dispatch_target_mode is None else dispatch_target_mode
    dispatch_strategy = strategy if dispatch_strategy is None else dispatch_strategy
    dispatch_market = market if dispatch_market is None else dispatch_market
    route_required = dispatch_provided if route_required is None else route_required
    route_provided = dispatch_provided if route_provided is None else route_provided
    route_ready = dispatch_ready if route_ready is None else route_ready
    route_target_mode = dispatch_target_mode if route_target_mode is None else route_target_mode
    route_strategy = dispatch_strategy if route_strategy is None else route_strategy
    route_market = dispatch_market if route_market is None else route_market
    route_scenario_key = dispatch_scenario_key if route_scenario_key is None else route_scenario_key
    route_requests = dispatch_requests if route_requests is None else route_requests
    route_acked_orders = dispatch_acked_orders if route_acked_orders is None else route_acked_orders
    route_missing_request_acks = (
        dispatch_missing_request_acks if route_missing_request_acks is None else route_missing_request_acks
    )
    route_rejected_orders = dispatch_rejected_orders if route_rejected_orders is None else route_rejected_orders
    route_unmatched_acks = dispatch_unmatched_acks if route_unmatched_acks is None else route_unmatched_acks
    route_readiness_strategy = strategy if route_readiness_strategy is None else route_readiness_strategy
    route_readiness_market = market if route_readiness_market is None else route_readiness_market
    broker_route_readiness_strategy = (
        strategy if broker_route_readiness_strategy is None else broker_route_readiness_strategy
    )
    broker_route_readiness_market = (
        market if broker_route_readiness_market is None else broker_route_readiness_market
    )
    broker_route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if broker_route_readiness_recommendation is None and broker_route_readiness_ready
        else "complete_route_readiness_gaps"
        if broker_route_readiness_recommendation is None
        else broker_route_readiness_recommendation
    )
    return {
        "schema_version": 1,
        "ready": True,
        "target_mode": target_mode,
        "strategy": strategy,
        "market": market,
        "scenario_key": "trigger_ticks=2",
        "adapter": adapter,
        "identity": {
            "strategy": strategy,
            "market": market,
            "expected_strategy": strategy,
            "expected_market": market,
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "max_scale_multiplier": 1.0,
            "stop_loss": 5_000.0,
        },
        "proof_freshness": {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": strategy,
            "market": market,
            "mixed_identity": False,
            "proof_source": "latest",
        },
        "route_readiness": {
            "required": target_mode == "live_dryrun",
            "provided": route_readiness_provided,
            "ready": route_readiness_ready,
            "strategy": route_readiness_strategy,
            "market": route_readiness_market,
            "route_ready_pairs": route_ready_pairs,
            "gap_pairs": route_gap_pairs,
            "ops_launch_controls_present": route_ops_launch_controls_present,
            "ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
            "ops_broker_roundtrip_portfolio_breach_pairs": (
                route_ops_broker_roundtrip_portfolio_breach_pairs
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
            ),
            "recommendation": "eligible_for_live_dryrun_route_review"
            if route_readiness_ready
            else "complete_route_readiness_gaps",
        },
        "broker_readiness": {
            "adapter_schema_status": broker_schema_status,
            "schema_reviewed": broker_schema_reviewed,
            "schema_review_mode": broker_schema_review_mode,
            "route_readiness": {
                "required": broker_route_readiness_required,
                "provided": broker_route_readiness_provided,
                "ready": broker_route_readiness_ready,
                "strategy": broker_route_readiness_strategy,
                "market": broker_route_readiness_market,
                "route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "gap_pairs": broker_route_readiness_gap_pairs,
                "recommendation": broker_route_readiness_recommendation,
                "ops_launch_controls_ready": broker_route_readiness_ops_launch_controls_ready,
                "ops_launch_control_failures": broker_route_readiness_ops_launch_control_failures,
                "ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
            },
            "dispatch_roundtrip": {
                "required": True,
                "provided": dispatch_provided,
                "ready": dispatch_ready,
                "target_mode": dispatch_target_mode,
                "strategy": dispatch_strategy,
                "market": dispatch_market,
                "scenario_key": dispatch_scenario_key,
                "dispatch_batch_id": dispatch_batch_id,
                "requests": dispatch_requests,
                "acked_orders": dispatch_acked_orders,
                "missing_request_acks": dispatch_missing_request_acks,
                "rejected_orders": dispatch_rejected_orders,
                "unmatched_acks": dispatch_unmatched_acks,
                "failed_checks": dispatch_failed_checks,
                "route_enable_dispatch_roundtrip": {
                    "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                },
                "route_proof": {
                    "required": route_required,
                    "provided": route_provided,
                    "ready": route_ready,
                    "target_mode": route_target_mode,
                    "strategy": route_strategy,
                    "market": route_market,
                    "scenario_key": route_scenario_key,
                    "dispatch_batch_id": route_batch_id,
                    "requests": route_requests,
                    "acked_orders": route_acked_orders,
                    "missing_request_acks": route_missing_request_acks,
                    "rejected_orders": route_rejected_orders,
                    "unmatched_acks": route_unmatched_acks,
                },
            }
        },
    }


def shadow_broker_config(
    sessions=2,
    ready_sessions=2,
    vendor_data_readiness_sessions=2,
    vendor_data_readiness_provided_sessions=2,
    vendor_data_readiness_ready_sessions=2,
    vendor_data_readiness_failed_checks=0,
    adapter="arrow_money",
    adapter_count=1,
    route_sessions=2,
    route_ready_sessions=2,
    route_strategy="lead_lag_taker",
    route_market="india_nse_index_derivatives",
    route_gap_pairs=0,
    dispatch_sessions=2,
    dispatch_ready_sessions=2,
    dispatch_strategy="lead_lag_taker",
    dispatch_market="india_nse_index_derivatives",
    dispatch_scenario_count=1,
    dispatch_missing_request_acks=0,
    dispatch_rejected_orders=0,
    dispatch_unmatched_acks=0,
    route_dispatch_sessions=2,
    route_dispatch_ready_sessions=2,
    route_dispatch_strategy="lead_lag_taker",
    route_dispatch_market="india_nse_index_derivatives",
    route_dispatch_scenario_count=1,
):
    return {
        "sessions": sessions,
        "ready_sessions": ready_sessions,
        "broker_vendor_data_readiness": {
            "sessions": vendor_data_readiness_sessions,
            "provided_sessions": vendor_data_readiness_provided_sessions,
            "ready_sessions": vendor_data_readiness_ready_sessions,
            "failed_checks": vendor_data_readiness_failed_checks,
        },
        "adapter": adapter,
        "adapter_count": adapter_count,
        "route_readiness": {
            "sessions": route_sessions,
            "ready_sessions": route_ready_sessions,
            "strategy": route_strategy,
            "market": route_market,
            "max_gap_pairs": route_gap_pairs,
        },
        "dispatch_roundtrip": {
            "sessions": dispatch_sessions,
            "ready_sessions": dispatch_ready_sessions,
            "strategy": dispatch_strategy,
            "market": dispatch_market,
            "scenario_count": dispatch_scenario_count,
            "max_missing_request_acks": dispatch_missing_request_acks,
            "max_rejected_orders": dispatch_rejected_orders,
            "max_unmatched_acks": dispatch_unmatched_acks,
        },
        "route_dispatch_roundtrip": {
            "sessions": route_dispatch_sessions,
            "ready_sessions": route_dispatch_ready_sessions,
            "strategy": route_dispatch_strategy,
            "market": route_dispatch_market,
            "scenario_count": route_dispatch_scenario_count,
        },
    }


def vendor_market_data_batch_config(
    provided=True,
    ready=True,
    adapter="arrow_money",
    kind="ticks",
    manifest_run_type="vendor_market_data_batch_pipeline",
    market="india_nse_index_derivatives",
    dataset_count=2,
    ready_datasets=2,
    failed_datasets=0,
    ready_rate=1.0,
    unique_source_files=2,
    unique_header_fingerprints=1,
    source_file_fingerprint_coverage=1.0,
    min_mapping_coverage=1.0,
    unique_mapping_drafts=1,
    mapping_sources="vendor_intake_draft",
    mapping_source_mode="",
    mapping_application_count=0,
    unique_mapping_applications=0,
    target_application_coverage=0.0,
    comparison_accepted=True,
    comparison_failed_checks=0,
    datasets=None,
):
    if datasets is None:
        datasets = [
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
        ]
    return {
        "provided": provided,
        "ready": ready,
        "adapter": adapter,
        "kind": kind,
        "manifest_run_type": manifest_run_type,
        "market": market,
        "dataset_count": dataset_count,
        "ready_datasets": ready_datasets,
        "failed_datasets": failed_datasets,
        "ready_rate": ready_rate,
        "unique_source_files": unique_source_files,
        "unique_header_fingerprints": unique_header_fingerprints,
        "source_file_fingerprint_coverage": source_file_fingerprint_coverage,
        "min_mapping_coverage": min_mapping_coverage,
        "unique_mapping_drafts": unique_mapping_drafts,
        "mapping_sources": mapping_sources,
        "mapping_source_mode": mapping_source_mode,
        "mapping_application_count": mapping_application_count,
        "unique_mapping_applications": unique_mapping_applications,
        "target_application_coverage": target_application_coverage,
        "comparison": {
            "accepted": comparison_accepted,
            "failed_checks": comparison_failed_checks,
        },
        "datasets": datasets,
    }


def target_application_vendor_market_data_batch_config(**overrides):
    config = vendor_market_data_batch_config(
        mapping_sources="verified_target_application",
        mapping_source_mode="per_dataset_verified_target_application",
        mapping_application_count=2,
        unique_mapping_applications=2,
        target_application_coverage=1.0,
        datasets=[
            {
                "dataset": "day1",
                "ready": True,
                "source_file_sha256": "a" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "verified_target_application",
                "mapping_application_path": "applications/day1/application.json",
                "mapping_application_id": "mapping-app-day1",
                "mapping_application_sha256": "1" * 64,
                "mapping_scope_review_id": "scope-review-1",
                "mapping_scope_review_sha256": "2" * 64,
                "target_intake_receipt_id": "target-intake-day1",
                "applied_mapping_sha256": "3" * 64,
            },
            {
                "dataset": "day2",
                "ready": True,
                "source_file_sha256": "d" * 64,
                "source_header_sha256": "b" * 64,
                "mapping_draft_sha256": "c" * 64,
                "mapping_source": "verified_target_application",
                "mapping_application_path": "applications/day2/application.json",
                "mapping_application_id": "mapping-app-day2",
                "mapping_application_sha256": "4" * 64,
                "mapping_scope_review_id": "scope-review-1",
                "mapping_scope_review_sha256": "2" * 64,
                "target_intake_receipt_id": "target-intake-day2",
                "applied_mapping_sha256": "3" * 64,
            },
        ],
    )
    config.update(overrides)
    config.setdefault("application_lineage_consistency_required", True)
    config.setdefault("application_lineage_consistent", True)
    config.setdefault(
        "application_lineage_sha256",
        target_application_lineage_sha256(config["datasets"]),
    )
    return config


def with_scaleup_broker_vendor_batch_summary(
    summary,
    vendor,
    *,
    include_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage=True,
):
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    result = summary.copy()
    for key, value in vendor.items():
        if key == "comparison":
            result.loc[0, f"{prefix}_comparison_accepted"] = value["accepted"]
            result.loc[0, f"{prefix}_comparison_failed_checks"] = value["failed_checks"]
        elif key == "datasets":
            result.loc[0, f"{prefix}_datasets_json"] = json.dumps(value, sort_keys=True)
        else:
            result.loc[0, f"{prefix}_{key}"] = value
    if vendor.get("mapping_source_mode") == "per_dataset_verified_target_application":
        lineage = target_application_lineage_comparison(vendor)
        result.loc[0, "broker_vendor_market_data_batch_lineage_match_required"] = lineage[
            "required"
        ]
        result.loc[0, "broker_vendor_market_data_batch_lineage_matches"] = lineage[
            "matches"
        ]
        result.loc[0, "vendor_market_data_batch_application_lineage_sha256"] = lineage[
            "current_application_lineage_sha256"
        ]
        result.loc[0, "broker_vendor_market_data_batch_application_lineage_sha256"] = lineage[
            "broker_application_lineage_sha256"
        ]
        final_lineage = final_target_application_lineage_comparison(vendor)
        result.loc[0, f"{prefix}_lineage_match_required"] = final_lineage[
            "required"
        ]
        result.loc[0, f"{prefix}_lineage_matches"] = final_lineage["matches"]
        for field, value in final_lineage.items():
            if field not in {"required", "matches", "carried_application_lineage_sha256"}:
                result.loc[0, f"{prefix}_{field}"] = value
        scaleup_final = scaleup_final_target_application_lineage_comparison(
            vendor
        )
        scaleup_final_prefix = (
            "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_final_prefix}_lineage_match_required",
        ] = scaleup_final["required"]
        result.loc[0, f"{scaleup_final_prefix}_lineage_matches"] = (
            scaleup_final["matches"]
        )
        for field, value in scaleup_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{scaleup_final_prefix}_{field}"] = value
        scaleup_complete_final = (
            scaleup_complete_final_target_application_lineage_comparison(
                vendor
            )
        )
        scaleup_complete_final_prefix = (
            "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_complete_final_prefix}_lineage_match_required",
        ] = scaleup_complete_final["required"]
        result.loc[
            0,
            f"{scaleup_complete_final_prefix}_lineage_matches",
        ] = scaleup_complete_final["matches"]
        result.loc[
            0,
            f"{scaleup_complete_final_prefix}_scaleup_complete_final_review_carried_application_lineage_sha256",
        ] = scaleup_complete_final["carried_application_lineage_sha256"]
        for field, value in scaleup_complete_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[
                    0,
                    f"{scaleup_complete_final_prefix}_{field}",
                ] = value
        scaleup_extended_complete_final = (
            scaleup_view_35_target_application_lineage_comparison(vendor)
        )
        scaleup_extended_complete_final_prefix = (
            "broker_readiness_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_extended_complete_final_prefix}_lineage_match_required",
        ] = scaleup_extended_complete_final["required"]
        result.loc[
            0,
            f"{scaleup_extended_complete_final_prefix}_lineage_matches",
        ] = scaleup_extended_complete_final["matches"]
        result.loc[
            0,
            f"{scaleup_extended_complete_final_prefix}_scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        ] = scaleup_extended_complete_final[
            "carried_application_lineage_sha256"
        ]
        for field, value in scaleup_extended_complete_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[
                    0,
                    f"{scaleup_extended_complete_final_prefix}_{field}",
                ] = value
        scaleup_latest_extended_complete_final = (
            scaleup_view_43_target_application_lineage_comparison(vendor)
        )
        scaleup_latest_extended_complete_final_prefix = (
            "broker_readiness_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = scaleup_latest_extended_complete_final["required"]
        result.loc[
            0,
            f"{scaleup_latest_extended_complete_final_prefix}_lineage_matches",
        ] = scaleup_latest_extended_complete_final["matches"]
        result.loc[
            0,
            f"{scaleup_latest_extended_complete_final_prefix}_scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ] = scaleup_latest_extended_complete_final[
            "carried_application_lineage_sha256"
        ]
        for field, value in scaleup_latest_extended_complete_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[
                    0,
                    f"{scaleup_latest_extended_complete_final_prefix}_{field}",
                ] = value
        scaleup_current_latest_extended_complete_final = (
            scaleup_view_51_target_application_lineage_comparison(vendor)
        )
        scaleup_current_latest_extended_complete_final_prefix = (
            "broker_readiness_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = scaleup_current_latest_extended_complete_final["required"]
        result.loc[
            0,
            f"{scaleup_current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = scaleup_current_latest_extended_complete_final["matches"]
        for field, value in scaleup_current_latest_extended_complete_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[
                    0,
                    f"{scaleup_current_latest_extended_complete_final_prefix}_{field}",
                ] = value
        scaleup_reconciled_current_latest_extended_complete_final = (
            scaleup_view_59_target_application_lineage_comparison(vendor)
        )
        scaleup_reconciled_current_latest_extended_complete_final_prefix = (
            "broker_readiness_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = scaleup_reconciled_current_latest_extended_complete_final["required"]
        result.loc[
            0,
            f"{scaleup_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = scaleup_reconciled_current_latest_extended_complete_final["matches"]
        for field, value in (
            scaleup_reconciled_current_latest_extended_complete_final.items()
        ):
            if field in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                continue
            result.loc[
                0,
                f"{scaleup_reconciled_current_latest_extended_complete_final_prefix}_{field}",
            ] = value
        scaleup_verified_reconciled_current_latest_extended_complete_final = (
            scaleup_view_67_target_application_lineage_comparison(vendor)
        )
        scaleup_verified_reconciled_current_latest_extended_complete_final_prefix = (
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            f"{scaleup_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = scaleup_verified_reconciled_current_latest_extended_complete_final[
            "required"
        ]
        result.loc[
            0,
            f"{scaleup_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = scaleup_verified_reconciled_current_latest_extended_complete_final[
            "matches"
        ]
        for field, value in (
            scaleup_verified_reconciled_current_latest_extended_complete_final.items()
        ):
            if field in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                continue
            result.loc[
                0,
                f"{scaleup_verified_reconciled_current_latest_extended_complete_final_prefix}_{field}",
            ] = value
        if include_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage:
            scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final = (
                scaleup_view_75_target_application_lineage_comparison(vendor)
            )
            scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix = (
                "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_"
                "broker_dispatch_roundtrip_vendor_market_data_batch"
            )
            result.loc[
                0,
                f"{scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
            ] = scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final[
                "required"
            ]
            result.loc[
                0,
                f"{scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
            ] = scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final[
                "matches"
            ]
            for field, value in (
                scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final.items()
            ):
                if field in {
                    "required",
                    "matches",
                    "carried_application_lineage_sha256",
                }:
                    continue
                result.loc[
                    0,
                    f"{scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_{field}",
                ] = value
    return result


def broker_readiness_summary(
    ready=True,
    adapter="arrow_money",
    target_mode="live_dryrun",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    runtime_ready=True,
    runtime_halted=False,
    resume_provided=False,
    resume_ready=True,
    resume_strategy="lead_lag_taker",
    resume_market="india_nse_index_derivatives",
    resume_proof_ready=True,
    dispatch_provided=True,
    dispatch_ready=True,
    dispatch_target_mode="live_dryrun",
    dispatch_strategy="lead_lag_taker",
    dispatch_market="india_nse_index_derivatives",
    dispatch_scenario_key="trigger_ticks=2",
    dispatch_batch_id="BDP-1",
    dispatch_requests=2,
    dispatch_acked_orders=2,
    dispatch_missing_request_acks=0,
    dispatch_rejected_orders=0,
    dispatch_unmatched_acks=0,
    dispatch_failed_checks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_required=None,
    route_provided=None,
    route_ready=None,
    route_target_mode=None,
    route_strategy=None,
    route_market=None,
    route_scenario_key=None,
    route_batch_id="BDP-0",
    route_requests=None,
    route_acked_orders=None,
    route_missing_request_acks=None,
    route_rejected_orders=None,
    route_unmatched_acks=None,
    schema_reviewed=True,
    schema_review_mode="reviewed_vendor_mapping",
):
    route_required = dispatch_provided if route_required is None else route_required
    route_provided = dispatch_provided if route_provided is None else route_provided
    route_ready = dispatch_ready if route_ready is None else route_ready
    route_target_mode = dispatch_target_mode if route_target_mode is None else route_target_mode
    route_strategy = dispatch_strategy if route_strategy is None else route_strategy
    route_market = dispatch_market if route_market is None else route_market
    route_scenario_key = dispatch_scenario_key if route_scenario_key is None else route_scenario_key
    route_requests = dispatch_requests if route_requests is None else route_requests
    route_acked_orders = dispatch_acked_orders if route_acked_orders is None else route_acked_orders
    route_missing_request_acks = (
        dispatch_missing_request_acks if route_missing_request_acks is None else route_missing_request_acks
    )
    route_rejected_orders = dispatch_rejected_orders if route_rejected_orders is None else route_rejected_orders
    route_unmatched_acks = dispatch_unmatched_acks if route_unmatched_acks is None else route_unmatched_acks
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "schema_reviewed": schema_reviewed,
                "schema_review_mode": schema_review_mode,
                "runtime_session_provided": True,
                "runtime_session_ready": runtime_ready,
                "runtime_guard_action": "halt" if runtime_halted else "continue",
                "runtime_guard_halted": runtime_halted,
                "runtime_target_mode": target_mode,
                "runtime_strategy": strategy,
                "runtime_market": market,
                "resume_gate_provided": resume_provided,
                "resume_gate_ready": resume_ready,
                "resume_strategy": resume_strategy,
                "resume_market": resume_market,
                "resume_proof_refresh_ready": resume_proof_ready,
                "resume_proof_refresh_strategy": resume_strategy,
                "resume_proof_refresh_market": resume_market,
                "dispatch_roundtrip_provided": dispatch_provided,
                "dispatch_roundtrip_ready": dispatch_ready,
                "dispatch_roundtrip_target_mode": dispatch_target_mode,
                "dispatch_roundtrip_strategy": dispatch_strategy,
                "dispatch_roundtrip_market": dispatch_market,
                "dispatch_roundtrip_scenario_key": dispatch_scenario_key,
                "dispatch_roundtrip_batch_id": dispatch_batch_id,
                "dispatch_roundtrip_requests": dispatch_requests,
                "dispatch_roundtrip_acked_orders": dispatch_acked_orders,
                "dispatch_roundtrip_missing_request_acks": dispatch_missing_request_acks,
                "dispatch_roundtrip_rejected_orders": dispatch_rejected_orders,
                "dispatch_roundtrip_unmatched_acks": dispatch_unmatched_acks,
                "dispatch_roundtrip_failed_checks": dispatch_failed_checks,
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "route_dispatch_roundtrip_required": route_required,
                "route_dispatch_roundtrip_provided": route_provided,
                "route_dispatch_roundtrip_ready": route_ready,
                "route_dispatch_roundtrip_target_mode": route_target_mode,
                "route_dispatch_roundtrip_strategy": route_strategy,
                "route_dispatch_roundtrip_market": route_market,
                "route_dispatch_roundtrip_scenario_key": route_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_batch_id,
                "route_dispatch_roundtrip_requests": route_requests,
                "route_dispatch_roundtrip_acked_orders": route_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_unmatched_acks,
                "failed_checks": 0 if ready else 1,
                "recommendation": "broker_integration_ready"
                if ready and schema_reviewed
                else ("dry_run_only_until_vendor_schema_review" if ready else "fix_broker_readiness_gaps"),
            }
        ]
    )


def runtime_session_summary(
    ready=True,
    target_mode="live_dryrun",
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    halted=False,
    strategy_portfolio=False,
    portfolio_ready=True,
    portfolio_strategy=None,
    portfolio_market=None,
    portfolio_eligible=True,
    portfolio_allocation_notional=1200.0,
    canonical_leadlag=False,
):
    portfolio_strategy = strategy if portfolio_strategy is None else portfolio_strategy
    portfolio_market = market if portfolio_market is None else portfolio_market
    row = {
        "ready": ready,
        "guard_action": "halt" if halted else "continue",
        "halted": halted,
        "target_mode": target_mode,
        "strategy": strategy,
        "market": market,
        "failed_checks": 1 if halted or not ready else 0,
        "recommendation": "stop_routing_and_execute_halt_response" if halted else "continue_with_controls",
    }
    if strategy_portfolio or canonical_leadlag:
        row.update(
            {
                "strategy_portfolio_required": True,
                "strategy_portfolio_provided": True,
                "strategy_portfolio_ready": portfolio_ready,
                "strategy_portfolio_deployment_mode": "paper_shadow",
                "strategy_portfolio_allocation_mode": "readiness_weighted",
                "strategy_portfolio_capital_currency": "INR",
                "strategy_portfolio_selected_profile": (
                    "leadlag" if canonical_leadlag else "leadlag-live-dryrun"
                ),
                "strategy_portfolio_selected_strategy": portfolio_strategy,
                "strategy_portfolio_selected_market": portfolio_market,
                "strategy_portfolio_selected_eligible": portfolio_eligible,
                "strategy_portfolio_selected_allocation_weight": 0.0012,
                "strategy_portfolio_selected_allocation_notional": portfolio_allocation_notional,
                "strategy_portfolio_notional_cap_applied": True,
                "strategy_portfolio_min_strategy_count": 2,
                "strategy_portfolio_min_market_count": 1,
                "strategy_portfolio_max_strategy_weight": 0.60,
                "strategy_portfolio_max_market_weight": 0.90,
                "strategy_portfolio_allocated_strategy_count": 2,
                "strategy_portfolio_allocated_market_count": 1,
                "strategy_portfolio_top_strategy_by_weight": portfolio_strategy,
                "strategy_portfolio_top_market_by_weight": portfolio_market,
                "strategy_portfolio_max_strategy_allocation_weight": 0.45,
                "strategy_portfolio_max_market_allocation_weight": 0.80,
                "pre_portfolio_max_notional_per_session": 25_000.0,
            }
        )
        if canonical_leadlag:
            row.update(leadlag_lineage(prefix="strategy_portfolio_"))
            row[
                "strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
            ] = True
    return pd.DataFrame(
        [
            row
        ]
    )


def operator_review(
    approved=True,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    limits_ack=True,
):
    return pd.DataFrame(
        [
            {
                "reviewer": "ops",
                "approved": approved,
                "strategy": strategy,
                "market": market,
                "limits_acknowledged": limits_ack,
                "reason": "cutover reviewed",
            }
        ]
    )


def scaleup_checks(passed=True):
    return pd.DataFrame([{"check": "scaleup_ready", "passed": passed, "reason": "" if passed else "blocked"}])


def path_tail(value):
    return str(value).replace("\\", "/")


def runtime_lineage(scaleup_manifest_sha256):
    fields = {}
    for column in (*SCALEUP_PROVENANCE_COLUMNS, *RUNTIME_LINEAGE_COLUMNS):
        if column == "scaleup_dependency_count":
            fields[column] = 1
        elif column.endswith(("_path", "_sha256", "_error", "_run_type", "_id")):
            fields[column] = ""
        else:
            fields[column] = False
    fields.update(
        {
            "scaleup_manifest_required": True,
            "scaleup_manifest_provided": True,
            "scaleup_manifest_current": True,
            "scaleup_manifest_run_type": "scaleup_plan",
            "scaleup_manifest_sha256": scaleup_manifest_sha256,
            "scaleup_contract_consistent": True,
            "scaleup_non_authorizing": True,
            "scaleup_source_ready": True,
            "scaleup_provenance_gate_passed": True,
            "runtime_telemetry_scaleup_provenance_carried": True,
            "runtime_telemetry_scaleup_provenance_gate_passed": True,
            "runtime_telemetry_scaleup_manifest_sha256": scaleup_manifest_sha256,
            "runtime_telemetry_scaleup_manifest_matches_current": True,
            "runtime_telemetry_lineage_matches_current": True,
        }
    )
    return fields


def bind_broker_readiness_runtime_lineage(root, scaleup, broker, runtime):
    broker_summary_path = broker / "broker_readiness_summary.csv"
    broker_summary = pd.read_csv(broker_summary_path)
    for column in (
        "dispatch_roundtrip_provided",
        "dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_required",
        "route_dispatch_roundtrip_provided",
        "route_dispatch_roundtrip_ready",
    ):
        broker_summary.loc[0, column] = False
    broker_summary.to_csv(broker_summary_path, index=False)
    pd.DataFrame(
        [
            {
                "component": "runtime_session",
                "required": True,
                "provided": True,
                "ready": True,
            }
        ]
    ).to_csv(broker / "broker_readiness_items.csv", index=False)
    pd.DataFrame(
        [{"check": "runtime_session_ready", "passed": True, "reason": ""}]
    ).to_csv(broker / "broker_readiness_checks.csv", index=False)
    pd.DataFrame(columns=["priority"]).to_csv(
        broker / "broker_readiness_action_queue.csv",
        index=False,
    )
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "adapter": "arrow_money",
                "component_counts": {"failed_checks": 0},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (broker / "broker_readiness_runbook.md").write_text(
        "# Broker Readiness Fixture\n",
        encoding="utf-8",
    )
    broker_source = root / "broker_readiness_source.csv"
    pd.DataFrame([{"source": "fixture"}]).to_csv(broker_source, index=False)
    write_experiment_manifest(
        broker,
        run_type="broker_readiness",
        inputs={"source": broker_source},
        extra={"ready": True, "authorizes_submission": False},
    )
    current_broker_lineage = load_broker_readiness_lineage(
        broker / "broker_readiness_config.json"
    )
    assert current_broker_lineage["gate_passed"]
    broker_fields = broker_readiness_lineage_fields(current_broker_lineage)
    broker_inputs = {
        "broker_readiness_config": broker / "broker_readiness_config.json",
        **broker_readiness_lineage_manifest_inputs(current_broker_lineage),
    }

    scaleup_config_path = scaleup / "scaleup_config.json"
    scaleup_config_payload = json.loads(
        scaleup_config_path.read_text(encoding="utf-8")
    )
    scaleup_broker = scaleup_config_payload["broker_readiness"]
    scaleup_broker.update(
        {
            "required": True,
            "provided": True,
            "lineage": {
                field.removeprefix("broker_readiness_"): value
                for field, value in broker_fields.items()
            },
        }
    )
    scaleup_dispatch = scaleup_broker["dispatch_roundtrip"]
    scaleup_dispatch.update(
        {"required": False, "provided": False, "ready": False}
    )
    scaleup_dispatch["route_proof"].update(
        {"required": False, "provided": False, "ready": False}
    )
    scaleup_config_path.write_text(
        json.dumps(scaleup_config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    scaleup_summary_path = scaleup / "scaleup_summary.csv"
    scaleup_summary_frame = pd.read_csv(scaleup_summary_path)
    scaleup_summary_frame.loc[0, "broker_dispatch_roundtrip_required"] = False
    scaleup_summary_frame.loc[0, "broker_dispatch_roundtrip_provided"] = False
    scaleup_summary_frame.loc[0, "broker_dispatch_roundtrip_ready"] = False
    scaleup_summary_frame.loc[0, "broker_route_dispatch_roundtrip_required"] = False
    scaleup_summary_frame.loc[0, "broker_route_dispatch_roundtrip_provided"] = False
    scaleup_summary_frame.loc[0, "broker_route_dispatch_roundtrip_ready"] = False
    scaleup_plan_path = scaleup / "scaleup_plan.csv"
    scaleup_plan_frame = pd.read_csv(scaleup_plan_path)
    for field, value in broker_fields.items():
        scaleup_summary_frame.loc[0, field] = value
        scaleup_plan_frame.loc[0, field] = value
    scaleup_summary_frame.to_csv(scaleup_summary_path, index=False)
    scaleup_plan_frame.to_csv(scaleup_plan_path, index=False)
    write_experiment_manifest(
        scaleup,
        run_type="scaleup_plan",
        inputs={
            "source": root / "scaleup_source.csv",
            **broker_inputs,
        },
        extra={
            "ready": True,
            **broker_fields,
            "authorizes_submission": False,
        },
    )

    lineage = runtime_lineage(file_sha256(scaleup / "manifest.json"))
    lineage.update(
        {
            "scaleup_broker_readiness_required": True,
            "scaleup_broker_readiness_provided": True,
            **{
                f"scaleup_{field}": value
                for field, value in broker_fields.items()
            },
            "scaleup_broker_readiness_source_manifest_current": True,
            "scaleup_broker_readiness_source_manifest_sha256": broker_fields[
                "broker_readiness_manifest_sha256"
            ],
            "scaleup_broker_readiness_source_provenance_gate_passed": True,
            "scaleup_broker_readiness_matches_current": True,
            "runtime_telemetry_broker_readiness_manifest_sha256": broker_fields[
                "broker_readiness_manifest_sha256"
            ],
            "runtime_telemetry_broker_readiness_lineage_gate_passed": True,
            "runtime_telemetry_broker_readiness_matches_current": True,
        }
    )
    runtime_summary_path = runtime / "runtime_session_summary.csv"
    runtime_summary_frame = pd.read_csv(runtime_summary_path).astype(object)
    for column, value in lineage.items():
        runtime_summary_frame.loc[0, column] = value
    runtime_summary_frame.to_csv(runtime_summary_path, index=False)
    runtime_steps_path = runtime / "runtime_session_steps.csv"
    runtime_steps_frame = pd.read_csv(runtime_steps_path).astype(object)
    for column, value in lineage.items():
        runtime_steps_frame.loc[0, column] = value
    runtime_steps_frame.to_csv(runtime_steps_path, index=False)
    runtime_config_path = runtime / "runtime_session_config.json"
    runtime_config_payload = json.loads(
        runtime_config_path.read_text(encoding="utf-8")
    )
    runtime_config_payload["scaleup_provenance"] = {
        column: lineage[column] for column in SCALEUP_PROVENANCE_COLUMNS
    }
    runtime_config_payload["runtime_telemetry_lineage"] = {
        column: lineage[column] for column in RUNTIME_LINEAGE_COLUMNS
    }
    runtime_config_path.write_text(
        json.dumps(runtime_config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    remanifest_runtime_lineage_fixture(root, scaleup, broker, runtime)
    return broker_fields


def remanifest_runtime_lineage_fixture(root, scaleup, broker, runtime):
    runtime_summary = pd.read_csv(runtime / "runtime_session_summary.csv")
    runtime_row = json.loads(runtime_summary.to_json(orient="records"))[0]
    lineage = {
        column: runtime_row[column]
        for column in (*SCALEUP_PROVENANCE_COLUMNS, *RUNTIME_LINEAGE_COLUMNS)
    }
    leadlag = {
        column: value
        for column, value in runtime_row.items()
        if column.startswith("strategy_portfolio_leadlag_")
    }
    broker_lineage = load_broker_readiness_lineage(
        broker / "broker_readiness_config.json"
    )
    write_experiment_manifest(
        runtime,
        run_type="runtime_session_monitor",
        inputs={
            "scaleup_manifest": scaleup / "manifest.json",
            "scaleup_source": root / "scaleup_source.csv",
            "broker_readiness_config": broker / "broker_readiness_config.json",
            **broker_readiness_lineage_manifest_inputs(broker_lineage),
        },
        extra={
            "ready": True,
            "guard_action": "continue",
            **leadlag,
            **lineage,
            "authorizes_submission": False,
        },
    )


def write_inputs(
    root,
    *,
    target_mode="live_dryrun",
    operator=True,
    dispatch=True,
    canonical_leadlag=False,
):
    scaleup = root / "scaleup"
    broker = root / "broker"
    runtime = root / "runtime"
    scaleup.mkdir(parents=True)
    broker.mkdir()
    runtime.mkdir()
    scaleup_summary_frame = scaleup_summary(
        target_mode=target_mode,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
    )
    scaleup_summary_frame.loc[0, "proof_refresh_provided"] = False
    scaleup_summary_frame.loc[0, "proof_refresh_ready"] = False
    scaleup_summary_frame.loc[0, "proof_refresh_strategy"] = ""
    scaleup_summary_frame.loc[0, "proof_refresh_market"] = ""
    scaleup_summary_frame.loc[0, "proof_source"] = ""
    scaleup_summary_frame.loc[0, "authorizes_submission"] = False
    scaleup_summary_frame.to_csv(
        scaleup / "scaleup_summary.csv",
        index=False,
    )
    scaleup_checks().to_csv(scaleup / "scaleup_checks.csv", index=False)
    scaleup_config_payload = scaleup_config(
        target_mode=target_mode,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
    )
    scaleup_config_payload["failed_check_count"] = 0
    scaleup_config_payload["authorizes_submission"] = False
    scaleup_config_payload["proof_freshness"] = {
        "required": False,
        "requested": False,
        "provided": False,
        "reported_ready": False,
        "ready": False,
        "verified": False,
        "strategy": "",
        "market": "",
        "mixed_identity": False,
        "proof_source": "",
    }
    (scaleup / "scaleup_config.json").write_text(
        json.dumps(
            scaleup_config_payload,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "ready": True,
                "target_mode": target_mode,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(
        scaleup / "scaleup_plan.csv",
        index=False,
    )
    scaleup_source = root / "scaleup_source.csv"
    pd.DataFrame([{"source": "fixture"}]).to_csv(scaleup_source, index=False)
    write_experiment_manifest(
        scaleup,
        run_type="scaleup_plan",
        inputs={"source": scaleup_source},
        extra={"ready": True, "authorizes_submission": False},
    )
    broker_readiness_summary(
        target_mode=target_mode,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
    ).to_csv(broker / "broker_readiness_summary.csv", index=False)
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": dispatch,
                "adapter": "arrow_money",
                "dispatch_roundtrip": {"ready": dispatch, "target_mode": target_mode},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lineage = runtime_lineage(file_sha256(scaleup / "manifest.json"))
    runtime_summary = runtime_session_summary(
        target_mode=target_mode,
        canonical_leadlag=canonical_leadlag,
    )
    for column, value in lineage.items():
        runtime_summary[column] = value
    runtime_summary.to_csv(runtime / "runtime_session_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "step": "runtime_guard",
                "status": "continue",
                **lineage,
            }
        ]
    ).to_csv(runtime / "runtime_session_steps.csv", index=False)
    pd.DataFrame(columns=["priority"]).to_csv(
        runtime / "runtime_session_action_queue.csv",
        index=False,
    )
    runtime_config = {
        "schema_version": 1,
        "ready": True,
        "guard_action": "continue",
        "authorizes_submission": False,
        "scaleup_provenance": {
            column: lineage[column] for column in SCALEUP_PROVENANCE_COLUMNS
        },
        "runtime_telemetry_lineage": {
            column: lineage[column] for column in RUNTIME_LINEAGE_COLUMNS
        },
    }
    runtime_row = json.loads(runtime_summary.to_json(orient="records"))[0]
    runtime_manifest_leadlag = {
        column: value
        for column, value in runtime_row.items()
        if column.startswith("strategy_portfolio_leadlag_")
    }
    if canonical_leadlag:
        runtime_config["strategy_portfolio"] = {
            column.removeprefix("strategy_portfolio_"): value
            for column, value in runtime_row.items()
            if column.startswith("strategy_portfolio_")
        }
        runtime_config["strategy_portfolio"][
            "pre_portfolio_max_notional_per_session"
        ] = runtime_row["pre_portfolio_max_notional_per_session"]
    (runtime / "runtime_session_config.json").write_text(
        json.dumps(runtime_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (runtime / "runtime_session_runbook.md").write_text(
        "# Runtime Session Fixture\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        runtime,
        run_type="runtime_session_monitor",
        inputs={"scaleup_manifest": scaleup / "manifest.json", "scaleup_source": scaleup_source},
        extra={
            "ready": True,
            "guard_action": "continue",
            **runtime_manifest_leadlag,
            **lineage,
            "authorizes_submission": False,
        },
    )
    review_path = root / "operator_review.csv"
    if operator:
        operator_review().to_csv(review_path, index=False)
    return scaleup, broker, runtime, review_path


def write_proof_refresh_cutover_inputs(root):
    from tests.test_scaleup_runtime_provenance import (
        _write_proof_refresh_scaleup_bundle,
    )

    scaleup, proof_refresh, proof_source = (
        _write_proof_refresh_scaleup_bundle(
            root / "scaleup"
        )
    )
    runtime = root / "runtime"
    runtime_report = write_runtime_session_monitor(
        scaleup_dir=scaleup,
        output_dir=runtime,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )
    assert runtime_report.ready

    scaleup_config_payload = json.loads(
        (scaleup / "scaleup_config.json").read_text(
            encoding="utf-8"
        )
    )
    broker = root / "broker"
    broker.mkdir()
    pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": scaleup_config_payload["adapter"],
            }
        ]
    ).to_csv(
        broker / "broker_readiness_summary.csv",
        index=False,
    )
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "adapter": scaleup_config_payload["adapter"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    review_path = root / "operator_review.csv"
    operator_review(
        strategy=scaleup_config_payload["strategy"],
        market=scaleup_config_payload["market"],
    ).to_csv(review_path, index=False)
    thresholds = CutoverGateThresholds(
        target_mode=scaleup_config_payload["target_mode"],
        require_route_readiness=False,
        require_dispatch_roundtrip=False,
    )
    return (
        scaleup,
        broker,
        runtime,
        review_path,
        proof_refresh,
        proof_source,
        thresholds,
    )


def write_contract_identity_cutover_inputs(root):
    from tests.data_readiness_helpers import reseal_experiment_manifest
    from tests.test_scaleup_runtime_provenance import (
        _write_broker_readiness_bundle,
        _write_scaleup_bundle,
    )

    broker = root / "broker_readiness"
    broker_lineage = _write_broker_readiness_bundle(
        broker,
        contract_identity=True,
    )
    scaleup = _write_scaleup_bundle(
        root / "scaleup",
        broker_lineage,
    )
    broker_row = pd.read_csv(
        broker / "broker_readiness_summary.csv"
    ).iloc[0]
    scaleup_config_path = scaleup / "scaleup_config.json"
    scaleup_config_payload = json.loads(
        scaleup_config_path.read_text(encoding="utf-8")
    )
    scaleup_config_payload["target_mode"] = "live_dryrun"
    scaleup_config_payload["route_readiness"] = {
        "required": True,
        "provided": True,
        "ready": True,
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "route_ready_pairs": 1,
        "gap_pairs": 0,
        "ops_launch_controls_present": True,
        "ops_launch_controls_blocked_pairs": 0,
        "ops_broker_roundtrip_portfolio_breach_pairs": 0,
        "ops_broker_roundtrip_portfolio_concentration_breach_pairs": 0,
        "recommendation": "eligible_for_live_dryrun_route_review",
    }
    scaleup_config_payload["broker_readiness"][
        "dispatch_roundtrip"
    ] = {
        "required": True,
        "provided": True,
        "ready": True,
        "target_mode": "live_dryrun",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "dispatch_batch_id": broker_row[
            "dispatch_roundtrip_batch_id"
        ],
        "requests": int(broker_row["dispatch_roundtrip_requests"]),
        "acked_orders": int(
            broker_row["dispatch_roundtrip_acked_orders"]
        ),
        "missing_request_acks": int(
            broker_row["dispatch_roundtrip_missing_request_acks"]
        ),
        "rejected_orders": int(
            broker_row["dispatch_roundtrip_rejected_orders"]
        ),
        "unmatched_acks": int(
            broker_row["dispatch_roundtrip_unmatched_acks"]
        ),
        "failed_checks": int(
            broker_row["dispatch_roundtrip_failed_checks"]
        ),
        "route_enable_dispatch_roundtrip": {
            "failed_checks": int(
                broker_row[
                    "route_enable_dispatch_roundtrip_failed_checks"
                ]
            ),
        },
        "route_proof": {
            "required": True,
            "provided": True,
            "ready": True,
            "target_mode": "live_dryrun",
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "scenario_key": "trigger_ticks=2",
            "dispatch_batch_id": broker_row[
                "route_dispatch_roundtrip_batch_id"
            ],
            "requests": int(
                broker_row["route_dispatch_roundtrip_requests"]
            ),
            "acked_orders": int(
                broker_row[
                    "route_dispatch_roundtrip_acked_orders"
                ]
            ),
            "missing_request_acks": int(
                broker_row[
                    "route_dispatch_roundtrip_missing_request_acks"
                ]
            ),
            "rejected_orders": int(
                broker_row[
                    "route_dispatch_roundtrip_rejected_orders"
                ]
            ),
            "unmatched_acks": int(
                broker_row[
                    "route_dispatch_roundtrip_unmatched_acks"
                ]
            ),
        },
    }
    scaleup_config_path.write_text(
        json.dumps(scaleup_config_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name in ("scaleup_summary.csv", "scaleup_plan.csv"):
        path = scaleup / name
        frame = pd.read_csv(path)
        frame.loc[0, "target_mode"] = "live_dryrun"
        frame.to_csv(path, index=False)
    reseal_experiment_manifest(scaleup)

    runtime = root / "runtime"
    runtime_report = write_runtime_session_monitor(
        scaleup_dir=scaleup,
        output_dir=runtime,
        snapshot_ts_ns=1_000,
        as_of_ts_ns=1_500,
        max_telemetry_age_ns=1_000,
    )
    assert runtime_report.ready
    review_path = root / "operator_review.csv"
    operator_review().to_csv(review_path, index=False)
    return (
        scaleup,
        broker,
        runtime,
        review_path,
        broker_readiness_lineage_fields(broker_lineage),
    )


def test_cutover_gate_authorizes_clean_live_dryrun():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["target_mode"] == "live_dryrun"
    assert summary["strategy"] == "lead_lag_taker"
    assert bool(summary["runtime_session_ready"])
    assert bool(summary["operator_approval_required"])
    assert summary["recommendation"] == "allow_live_dryrun_cutover"
    assert int(summary["failed_check_count"]) == 0
    assert summary["primary_blocker_check"] == ""
    assert int(summary["action_queue_count"]) == 0
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.config["runtime_session"]["guard_action"] == "continue"
    assert report.config["limits"]["max_orders_per_session"] == 10
    assert bool(summary["scaleup_broker_schema_reviewed"])
    assert summary["scaleup_broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert bool(summary["broker_schema_reviewed"])
    assert summary["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["broker_readiness"]["schema_reviewed"]
    assert report.config["broker_readiness"]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert bool(summary["scaleup_route_readiness_required"])
    assert bool(summary["scaleup_route_readiness_ready"])
    assert summary["scaleup_route_readiness_strategy"] == "lead_lag_taker"
    assert report.config["scaleup_route_readiness"]["required"]
    assert report.config["scaleup_route_readiness"]["ready"]
    assert report.config["scaleup_route_readiness"]["market"] == "india_nse_index_derivatives"
    assert bool(summary["broker_dispatch_roundtrip_ready"])
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-1"
    assert int(summary["scaleup_dispatch_roundtrip_failed_checks"]) == 0
    assert int(summary["broker_dispatch_roundtrip_failed_checks"]) == 0
    assert int(summary["scaleup_route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert int(summary["broker_route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["scaleup_dispatch_roundtrip"]["failed_checks"] == 0
    assert report.config["scaleup_dispatch_roundtrip"]["route_enable_dispatch_roundtrip"]["failed_checks"] == 0
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["failed_checks"] == 0
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_enable_dispatch_roundtrip"][
        "failed_checks"
    ] == 0
    assert bool(summary["broker_route_dispatch_roundtrip_ready"])
    assert report.config["scaleup_dispatch_roundtrip"]["route_proof"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]["dispatch_batch_id"] == "BDP-0"


def test_cutover_gate_carries_shadow_broker_readiness_from_scaleup_config():
    config = scaleup_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert int(summary["scaleup_shadow_broker_readiness_sessions"]) == 2
    assert int(summary["scaleup_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["scaleup_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert summary["scaleup_shadow_broker_adapter"] == "arrow_money"
    assert summary["scaleup_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["scaleup_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["scaleup_shadow_broker_readiness"]["provided"]
    assert report.config["scaleup_shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert report.config["scaleup_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["scaleup_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["scaleup_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["scaleup_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_cutover_gate_carries_runtime_strategy_portfolio_allocation():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(strategy_portfolio=True),
        operator_review=operator_review(),
    )

    assert report.ready
    authorization = report.authorization.iloc[0]
    summary = report.summary.iloc[0]
    portfolio = report.config["runtime_session"]["strategy_portfolio"]
    assert bool(authorization["runtime_strategy_portfolio_required"])
    assert bool(summary["runtime_strategy_portfolio_ready"])
    assert summary["runtime_strategy_portfolio_deployment_mode"] == "paper_shadow"
    assert summary["runtime_strategy_portfolio_allocation_mode"] == "readiness_weighted"
    assert summary["runtime_strategy_portfolio_capital_currency"] == "INR"
    assert summary["runtime_strategy_portfolio_selected_profile"] == "leadlag-live-dryrun"
    assert summary["runtime_strategy_portfolio_selected_strategy"] == "lead_lag_taker"
    assert summary["runtime_strategy_portfolio_selected_market"] == "india_nse_index_derivatives"
    assert bool(summary["runtime_strategy_portfolio_selected_eligible"])
    assert summary["runtime_strategy_portfolio_selected_allocation_weight"] == 0.0012
    assert summary["runtime_strategy_portfolio_selected_allocation_notional"] == 1200.0
    assert bool(summary["runtime_strategy_portfolio_notional_cap_applied"])
    assert summary["runtime_strategy_portfolio_min_strategy_count"] == 2
    assert summary["runtime_strategy_portfolio_min_market_count"] == 1
    assert summary["runtime_strategy_portfolio_max_strategy_weight"] == 0.60
    assert summary["runtime_strategy_portfolio_max_market_weight"] == 0.90
    assert summary["runtime_strategy_portfolio_allocated_strategy_count"] == 2
    assert summary["runtime_strategy_portfolio_allocated_market_count"] == 1
    assert summary["runtime_strategy_portfolio_top_strategy_by_weight"] == "lead_lag_taker"
    assert summary["runtime_strategy_portfolio_top_market_by_weight"] == "india_nse_index_derivatives"
    assert summary["runtime_strategy_portfolio_max_strategy_allocation_weight"] == 0.45
    assert summary["runtime_strategy_portfolio_max_market_allocation_weight"] == 0.80
    assert summary["runtime_pre_portfolio_max_notional_per_session"] == 25_000.0
    assert portfolio["required"]
    assert portfolio["provided"]
    assert portfolio["ready"]
    assert portfolio["selected_strategy"] == "lead_lag_taker"
    assert portfolio["selected_market"] == "india_nse_index_derivatives"
    assert portfolio["selected_allocation_notional"] == 1200.0
    assert portfolio["min_strategy_count"] == 2
    assert portfolio["allocated_strategy_count"] == 2
    assert portfolio["top_strategy_by_weight"] == "lead_lag_taker"
    assert portfolio["max_strategy_allocation_weight"] == 0.45
    assert portfolio["pre_portfolio_max_notional_per_session"] == 25_000.0


def test_cutover_gate_carries_runtime_leadlag_edge_lineage():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(canonical_leadlag=True),
        operator_review=operator_review(),
    )

    assert report.ready
    authorization = report.authorization.iloc[0]
    summary = report.summary.iloc[0]
    portfolio = report.config["runtime_session"]["strategy_portfolio"]
    assert bool(
        authorization[
            "runtime_strategy_portfolio_leadlag_edge_lineage_required"
        ]
    )
    assert bool(summary["runtime_strategy_portfolio_leadlag_edge_lineage_ready"])
    assert bool(
        summary[
            "runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
        ]
    )
    assert summary["runtime_strategy_portfolio_leadlag_lineage_bound_stages"] == 5
    assert summary[
        "runtime_strategy_portfolio_leadlag_edge_lineage_contract_version"
    ] == "leadlag_edge_lineage/v1"
    assert summary[
        "runtime_strategy_portfolio_leadlag_edge_lineage_contract_sha256"
    ] == "c" * 64
    assert summary[
        "runtime_strategy_portfolio_leadlag_edge_latency_headroom_ns"
    ] == 2_000.0
    assert portfolio["leadlag_edge_lineage_matches_scaleup"]
    assert portfolio["leadlag_lineage_selected_stage_count"] == 5
    assert portfolio["leadlag_edge_lineage_contract_sha256"] == "c" * 64


@pytest.mark.parametrize(
    ("field", "value", "failed_check"),
    [
        (
            "strategy_portfolio_provided",
            False,
            "runtime_strategy_portfolio_provided",
        ),
        (
            "strategy_portfolio_leadlag_edge_lineage_required",
            False,
            "runtime_strategy_portfolio_leadlag_edge_lineage_required",
        ),
        (
            "strategy_portfolio_leadlag_edge_lineage_contract_sha256",
            "bad-contract-hash",
            "runtime_strategy_portfolio_leadlag_edge_lineage_ready",
        ),
        (
            "strategy_portfolio_leadlag_edge_lineage_matches_scaleup",
            False,
            "runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup",
        ),
    ],
)
def test_cutover_gate_blocks_bad_runtime_leadlag_edge_lineage(
    field,
    value,
    failed_check,
):
    runtime = runtime_session_summary(canonical_leadlag=True)
    runtime.loc[0, field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime,
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed_check in failed
    assert not bool(report.summary.iloc[0]["ready"])


def test_cutover_gate_blocks_bad_runtime_strategy_portfolio_allocation():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(
            strategy_portfolio=True,
            portfolio_ready=False,
            portfolio_strategy="surface_mm",
            portfolio_market="us_options_regular",
            portfolio_eligible=False,
            portfolio_allocation_notional=0.0,
        ),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_strategy_portfolio_ready",
        "runtime_strategy_portfolio_allocation_eligible",
        "runtime_strategy_portfolio_strategy_matches",
        "runtime_strategy_portfolio_market_matches",
        "runtime_strategy_portfolio_allocation_notional",
    } <= failed
    assert report.config["runtime_session"]["strategy_portfolio"]["selected_strategy"] == "surface_mm"


def test_cutover_gate_carries_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    config["data_readiness_comparison"] = {
        "vendor_market_data_batch": vendor_market_data_batch_config()
    }

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_vendor_market_data_batch"]
    assert report.ready
    assert summary["scaleup_vendor_market_data_batch_provided"]
    assert summary["scaleup_vendor_market_data_batch_ready"]
    assert summary["scaleup_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["scaleup_vendor_market_data_batch_kind"] == "ticks"
    assert int(summary["scaleup_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["scaleup_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["scaleup_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["scaleup_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["scaleup_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["scaleup_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["scaleup_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_cutover_gate_carries_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["dispatch_roundtrip"][
        "vendor_market_data_batch"
    ] = vendor_market_data_batch_config()

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
        "vendor_intake_draft"
    )
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_cutover_gate_carries_target_application_vendor_batch_from_scaleup_config():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    config["broker_readiness"]["dispatch_roundtrip"][
        "vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert bool(summary[f"{prefix}_application_lineage_consistency_required"])
    assert bool(summary[f"{prefix}_application_lineage_consistent"])
    assert bool(summary["scaleup_broker_vendor_market_data_batch_lineage_match_required"])
    assert bool(summary["scaleup_broker_vendor_market_data_batch_lineage_matches"])
    assert summary["scaleup_vendor_market_data_batch_application_lineage_sha256"] == (
        summary["scaleup_broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    assert summary[f"{prefix}_application_lineage_sha256"] == (
        summary["scaleup_broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    assert summary[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
    ] == summary["scaleup_broker_vendor_market_data_batch_application_lineage_sha256"]
    assert bool(summary[f"{prefix}_lineage_match_required"])
    assert bool(summary[f"{prefix}_lineage_matches"])
    expected_lineage_sha256 = summary[
        "scaleup_broker_vendor_market_data_batch_application_lineage_sha256"
    ]
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
    ):
        assert summary[f"{prefix}_{field}"] == expected_lineage_sha256
    summary_datasets = json.loads(summary[f"{prefix}_datasets_json"])
    assert summary_datasets[0]["mapping_application_id"] == "mapping-app-day1"
    assert summary_datasets[1]["applied_mapping_sha256"] == "3" * 64
    vendor = report.config[prefix]
    assert vendor["mapping_source_mode"] == "per_dataset_verified_target_application"
    assert vendor["mapping_application_count"] == 2
    assert vendor["unique_mapping_applications"] == 2
    assert vendor["target_application_coverage"] == 1.0
    assert vendor["application_lineage_consistency_required"]
    assert vendor["application_lineage_consistent"]
    assert len(vendor["application_lineage_sha256"]) == 64
    assert vendor["datasets"][0]["mapping_application_id"] == "mapping-app-day1"
    assert vendor["datasets"][1]["target_intake_receipt_id"] == "target-intake-day2"
    expected_checks = {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
        f"{prefix}_lineage_match_required",
        f"{prefix}_lineage_matches",
        f"{prefix}_source_lineage_sha256_matches",
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_application_lineage_consistent",
        f"{prefix}_final_lineage_match_required",
        f"{prefix}_final_lineage_matches",
        f"{prefix}_final_source_lineage_sha256_matches",
        f"{prefix}_final_broker_lineage_sha256_matches",
        f"{prefix}_final_application_lineage_sha256_matches",
        f"{prefix}_final_prior_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_final_prior_cutover_carried_lineage_sha256_matches",
        f"{prefix}_final_route_carried_lineage_sha256_matches",
        f"{prefix}_final_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_final_send_carried_lineage_sha256_matches",
        f"{prefix}_final_ack_carried_lineage_sha256_matches",
        f"{prefix}_final_roundtrip_carried_lineage_sha256_matches",
        f"{prefix}_final_readiness_carried_lineage_sha256_matches",
        f"{prefix}_final_scaleup_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_review_carried_lineage_sha256_matches",
    }
    scaleup_final_check_prefix = f"{prefix}_scaleup_final"
    expected_checks.update(
        {
            f"{scaleup_final_check_prefix}_lineage_match_required",
            f"{scaleup_final_check_prefix}_lineage_matches",
            f"{scaleup_final_check_prefix}_source_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_compatibility_scaleup_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_prior_scaleup_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_prior_cutover_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_route_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_dispatch_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_send_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_ack_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_roundtrip_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_readiness_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_scaleup_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_cutover_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_route_enable_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_dispatch_plan_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_send_packet_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_ack_reconciliation_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_roundtrip_final_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_broker_readiness_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_scaleup_final_review_carried_lineage_sha256_matches",
            f"{scaleup_final_check_prefix}_cutover_final_review_carried_lineage_sha256_matches",
        }
    )
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed
    lineage = report.config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["required"]
    assert lineage["matches"]
    assert lineage["current_application_lineage_sha256"] == lineage[
        "broker_application_lineage_sha256"
    ]
    assert lineage["scaleup_carried_application_lineage_sha256"] == lineage[
        "broker_application_lineage_sha256"
    ]
    assert lineage["cutover_carried_application_lineage_sha256"] == lineage[
        "broker_application_lineage_sha256"
    ]
    final_lineage = report.config[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
        "scaleup_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == expected_lineage_sha256
    scaleup_final_prefix = (
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        "scaleup_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{scaleup_final_prefix}_{field}"] == (
            expected_lineage_sha256
        )
    cutover_complete_final = report.config[
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_complete_final["required"]
    assert cutover_complete_final["matches"]
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
        "carried_application_lineage_sha256",
    ):
        assert cutover_complete_final[field] == expected_lineage_sha256
    scaleup_complete_final_prefix = (
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    extended_complete_final_digest_fields = (
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
        *extended_complete_final_digest_fields,
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{scaleup_complete_final_prefix}_{field}"] == (
            expected_lineage_sha256
        )
    cutover_extended_complete_final = report.config[
        "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_extended_complete_final["required"]
    assert cutover_extended_complete_final["matches"]
    for field in (
        *extended_complete_final_digest_fields,
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert cutover_extended_complete_final[field] == expected_lineage_sha256
    extended_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final"
    )
    expected_extended_checks = {
        f"{extended_check_prefix}_lineage_match_required",
        f"{extended_check_prefix}_lineage_matches",
        f"{extended_check_prefix}_source_lineage_sha256_matches",
        f"{extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{extended_check_prefix}_compatibility_scaleup_final_review_carried_lineage_sha256_matches",
        f"{extended_check_prefix}_scaleup_complete_final_review_carried_lineage_sha256_matches",
        f"{extended_check_prefix}_cutover_complete_final_review_carried_lineage_sha256_matches",
    }
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
        expected_extended_checks.add(
            f"{extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_extended_checks <= passed

    scaleup_extended_complete_final_prefix = (
        "scaleup_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    view_35_digest_fields = (
        *extended_complete_final_digest_fields,
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
        "send_complete_final_review_carried_application_lineage_sha256",
        "ack_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
    )
    assert bool(
        summary[f"{scaleup_extended_complete_final_prefix}_lineage_match_required"]
    )
    assert bool(
        summary[f"{scaleup_extended_complete_final_prefix}_lineage_matches"]
    )
    for field in (
        *view_35_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{scaleup_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    cutover_view_36 = report.config[
        "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_36["required"]
    assert cutover_view_36["matches"]
    for field in (
        *view_35_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert cutover_view_36[field] == expected_lineage_sha256
    view_35_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_extended_complete_final"
    )
    expected_view_35_checks = {
        f"{view_35_check_prefix}_lineage_match_required",
        f"{view_35_check_prefix}_lineage_matches",
        f"{view_35_check_prefix}_source_lineage_sha256_matches",
        f"{view_35_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{view_35_check_prefix}_compatibility_scaleup_complete_final_review_carried_lineage_sha256_matches",
        f"{view_35_check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_35_check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_35_check_prefix}_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
    }
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
        expected_view_35_checks.add(
            f"{view_35_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_view_35_checks <= passed

    scaleup_latest_extended_complete_final_prefix = (
        "scaleup_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    view_43_digest_fields = (
        *view_35_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
        "send_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    assert bool(
        summary[
            f"{scaleup_latest_extended_complete_final_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[
            f"{scaleup_latest_extended_complete_final_prefix}_lineage_matches"
        ]
    )
    for field in (
        *view_43_digest_fields,
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{scaleup_latest_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    cutover_view_44 = report.config[
        "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_44["required"]
    assert cutover_view_44["matches"]
    for field in (
        *view_43_digest_fields,
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert cutover_view_44[field] == expected_lineage_sha256
    view_43_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_latest_extended_complete_final"
    )
    expected_view_43_checks = {
        f"{view_43_check_prefix}_lineage_match_required",
        f"{view_43_check_prefix}_lineage_matches",
        f"{view_43_check_prefix}_source_lineage_sha256_matches",
        f"{view_43_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{view_43_check_prefix}_compatibility_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_43_check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_43_check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_43_check_prefix}_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    }
    for field in view_43_digest_fields:
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
        expected_view_43_checks.add(
            f"{view_43_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_view_43_checks <= passed

    scaleup_current_latest_extended_complete_final_prefix = (
        "scaleup_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    view_51_digest_fields = (
        *view_35_digest_fields,
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
        "send_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    view_51_stage_fields = (
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
            f"{scaleup_current_latest_extended_complete_final_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[
            f"{scaleup_current_latest_extended_complete_final_prefix}_lineage_matches"
        ]
    )
    for field in (
        *view_51_digest_fields,
        *view_51_stage_fields,
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[
            f"{scaleup_current_latest_extended_complete_final_prefix}_{field}"
        ] == expected_lineage_sha256
    cutover_view_52 = report.config[
        "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_52["required"]
    assert cutover_view_52["matches"]
    for field in (
        *view_51_digest_fields,
        *view_51_stage_fields,
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert cutover_view_52[field] == expected_lineage_sha256
    view_51_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_current_latest_extended_complete_final"
    )
    expected_view_51_checks = {
        f"{view_51_check_prefix}_lineage_match_required",
        f"{view_51_check_prefix}_lineage_matches",
        f"{view_51_check_prefix}_source_lineage_sha256_matches",
        f"{view_51_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{view_51_check_prefix}_compatibility_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_51_check_prefix}_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_51_check_prefix}_scaleup_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        f"{view_51_check_prefix}_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    }
    for field in view_51_digest_fields:
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
        expected_view_51_checks.add(
            f"{view_51_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    for field in view_51_stage_fields:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        expected_view_51_checks.add(
            f"{view_51_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_view_51_checks <= passed

    view_59_current_stage_fields = (
        "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    scaleup_view_59 = scaleup_view_59_target_application_lineage_comparison(vendor)
    assert len(scaleup_view_59) == 58
    scaleup_view_59_prefix = (
        "scaleup_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(summary[f"{scaleup_view_59_prefix}_lineage_match_required"])
    assert bool(summary[f"{scaleup_view_59_prefix}_lineage_matches"])
    for field, value in scaleup_view_59.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{scaleup_view_59_prefix}_{field}"] == value
    assert summary[
        f"{scaleup_view_59_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256

    cutover_view_60 = report.config[
        "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_cutover_view_60 = (
        cutover_view_60_target_application_lineage_comparison(vendor)
    )
    assert len(cutover_view_60) == 59
    assert cutover_view_60 == expected_cutover_view_60

    view_59_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_reconciled_current_latest_extended_complete_final"
    )
    expected_view_59_checks = {
        f"{view_59_check_prefix}_lineage_match_required",
        f"{view_59_check_prefix}_lineage_matches",
        f"{view_59_check_prefix}_source_lineage_sha256_matches",
        f"{view_59_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{view_59_check_prefix}_compatibility_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_59_check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_59_check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_59_check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        f"{view_59_check_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    }
    for field in view_51_digest_fields:
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
        expected_view_59_checks.add(
            f"{view_59_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    for field in (*view_51_stage_fields, *view_59_current_stage_fields):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        expected_view_59_checks.add(
            f"{view_59_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_view_59_checks <= passed

    view_67_review_fields = (
        "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    scaleup_view_67 = scaleup_view_67_target_application_lineage_comparison(
        vendor
    )
    assert len(scaleup_view_67) == 66
    scaleup_view_67_prefix = (
        "scaleup_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(summary[f"{scaleup_view_67_prefix}_lineage_match_required"])
    assert bool(summary[f"{scaleup_view_67_prefix}_lineage_matches"])
    for field, value in scaleup_view_67.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{scaleup_view_67_prefix}_{field}"] == value
    assert summary[
        f"{scaleup_view_67_prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256

    cutover_view_68 = report.config[
        "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_cutover_view_68 = (
        cutover_view_68_target_application_lineage_comparison(vendor)
    )
    assert len(cutover_view_68) == 67
    assert cutover_view_68 == expected_cutover_view_68

    view_67_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_view_67_checks = {
        f"{view_67_check_prefix}_lineage_match_required",
        f"{view_67_check_prefix}_lineage_matches",
        f"{view_67_check_prefix}_source_lineage_sha256_matches",
        f"{view_67_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{view_67_check_prefix}_compatibility_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_67_check_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        f"{view_67_check_prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    }
    for field in view_51_digest_fields:
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
        expected_view_67_checks.add(
            f"{view_67_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    for field in (
        *view_51_stage_fields,
        *view_59_current_stage_fields,
        *view_67_review_fields,
    ):
        stage = field.removesuffix("_carried_application_lineage_sha256")
        expected_view_67_checks.add(
            f"{view_67_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_view_67_checks <= passed

    scaleup_view_75_prefix = (
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    source_view_75 = scaleup_view_75_target_application_lineage_comparison(vendor)
    assert len(source_view_75) == 74
    assert bool(summary[f"{scaleup_view_75_prefix}_lineage_match_required"])
    assert bool(summary[f"{scaleup_view_75_prefix}_lineage_matches"])
    for field, value in source_view_75.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{scaleup_view_75_prefix}_{field}"] == value
    assert summary[
        f"{scaleup_view_75_prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256

    cutover_view_76 = report.config[
        "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_cutover_view_76 = (
        cutover_view_76_target_application_lineage_comparison(vendor)
    )
    assert len(cutover_view_76) == 75
    assert cutover_view_76 == expected_cutover_view_76

    view_75_check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_view_75_checks = {
        f"{view_75_check_prefix}_lineage_match_required",
        f"{view_75_check_prefix}_lineage_matches",
        f"{view_75_check_prefix}_source_lineage_sha256_matches",
        f"{view_75_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{view_75_check_prefix}_compatibility_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{view_75_check_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        f"{view_75_check_prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    }
    for field in set(source_view_75) - {
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
        expected_view_75_checks.add(
            f"{view_75_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    assert expected_view_75_checks <= passed


def test_cutover_gate_blocks_scaleup_view_35_drift_while_preserving_view_28():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch[
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_view_35_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_view_28 = report.config[
        "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        cutover_view_28["broker_application_lineage_sha256"]
        == lineage_sha256
    )
    assert (
        cutover_view_28[
            "scaleup_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        cutover_view_28["carried_application_lineage_sha256"]
        == lineage_sha256
    )
    assert cutover_view_28[
        "broker_application_lineage_sha256"
    ] != ("f" * 64)
    cutover_view_36 = report.config[
        "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_36["broker_application_lineage_sha256"] == "f" * 64
    assert (
        cutover_view_36[
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert cutover_view_36["carried_application_lineage_sha256"] == lineage_sha256


def test_cutover_gate_blocks_scaleup_view_43_drift_while_preserving_view_36():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    view_43 = scaleup_view_43_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    dispatch[
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_43
    summary = with_scaleup_broker_vendor_batch_summary(scaleup_summary(), vendor)
    prefix = (
        "broker_readiness_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{prefix}_lineage_match_required"] = view_43["required"]
    summary.loc[0, f"{prefix}_lineage_matches"] = view_43["matches"]
    for field, value in view_43.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "scaleup_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        summary.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_cutover_gate(
        scaleup_summary=summary,
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_view_36 = report.config[
        "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_36["required"]
    assert cutover_view_36["matches"]
    assert cutover_view_36["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        cutover_view_36[
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert cutover_view_36["carried_application_lineage_sha256"] == lineage_sha256
    assert cutover_view_36["broker_application_lineage_sha256"] != "f" * 64
    cutover_view_44 = report.config[
        "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_44["broker_application_lineage_sha256"] == "f" * 64
    assert (
        cutover_view_44[
            "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert cutover_view_44["carried_application_lineage_sha256"] == lineage_sha256


def test_cutover_gate_blocks_scaleup_view_51_drift_while_preserving_view_44():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    view_51 = scaleup_view_51_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    dispatch[
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_51
    summary = with_scaleup_broker_vendor_batch_summary(scaleup_summary(), vendor)
    prefix = (
        "broker_readiness_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{prefix}_lineage_match_required"] = view_51["required"]
    summary.loc[0, f"{prefix}_lineage_matches"] = view_51["matches"]
    for field, value in view_51.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
        }:
            continue
        summary.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_cutover_gate(
        scaleup_summary=summary,
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_view_44 = report.config[
        "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_44["required"]
    assert cutover_view_44["matches"]
    assert cutover_view_44["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        cutover_view_44[
            "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert cutover_view_44["carried_application_lineage_sha256"] == lineage_sha256
    assert cutover_view_44["broker_application_lineage_sha256"] != "f" * 64
    cutover_view_52 = report.config[
        "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_52["required"]
    assert cutover_view_52["matches"]
    assert cutover_view_52["broker_application_lineage_sha256"] == "f" * 64
    assert (
        cutover_view_52[
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        cutover_view_52[
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert cutover_view_52["carried_application_lineage_sha256"] == lineage_sha256


def test_cutover_gate_blocks_scaleup_view_59_drift_while_preserving_view_52():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    view_59 = scaleup_view_59_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    dispatch[
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_59
    summary = with_scaleup_broker_vendor_batch_summary(scaleup_summary(), vendor)
    prefix = (
        "broker_readiness_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{prefix}_lineage_match_required"] = view_59["required"]
    summary.loc[0, f"{prefix}_lineage_matches"] = view_59["matches"]
    for field, value in view_59.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
        }:
            continue
        summary.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_cutover_gate(
        scaleup_summary=summary,
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_view_52 = report.config[
        "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_52["required"]
    assert cutover_view_52["matches"]
    assert cutover_view_52["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        cutover_view_52[
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        cutover_view_52[
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert cutover_view_52["carried_application_lineage_sha256"] == lineage_sha256
    assert cutover_view_52["broker_application_lineage_sha256"] != "f" * 64
    cutover_view_60 = report.config[
        "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_60["required"]
    assert cutover_view_60["matches"]
    assert cutover_view_60["broker_application_lineage_sha256"] == "f" * 64
    assert (
        cutover_view_60[
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        cutover_view_60[
            "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert cutover_view_60["carried_application_lineage_sha256"] == lineage_sha256


def test_cutover_gate_blocks_scaleup_view_75_drift_while_preserving_view_68():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    drifted_view_75 = scaleup_view_75_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_75) == 74
    dispatch[
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = drifted_view_75
    summary = with_scaleup_broker_vendor_batch_summary(scaleup_summary(), vendor)
    prefix = (
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{prefix}_lineage_match_required"] = drifted_view_75[
        "required"
    ]
    summary.loc[0, f"{prefix}_lineage_matches"] = drifted_view_75["matches"]
    for field, value in drifted_view_75.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
        }:
            continue
        summary.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_cutover_gate(
        scaleup_summary=summary,
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_view_68 = report.config[
        "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_68 == cutover_view_68_target_application_lineage_comparison(
        vendor
    )
    assert cutover_view_68["broker_application_lineage_sha256"] == lineage_sha256
    assert cutover_view_68["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    cutover_view_76 = report.config[
        "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_76 == cutover_view_76_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
        cutover_lineage_sha256=lineage_sha256,
    )


def test_cutover_gate_requires_scaleup_view_75_lineage():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    cutover_view_68 = report.config[
        "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_68["required"]
    assert cutover_view_68["matches"]
    cutover_view_76 = report.config[
        "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not cutover_view_76["required"]
    assert not cutover_view_76["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_view_75_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_view_75 = dispatch[
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_view_75[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_blocks_scaleup_view_67_drift_while_preserving_view_60():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    drifted_view_67 = scaleup_view_67_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_67) == 66
    dispatch[
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = drifted_view_67
    summary = with_scaleup_broker_vendor_batch_summary(scaleup_summary(), vendor)
    prefix = (
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{prefix}_lineage_match_required"] = drifted_view_67[
        "required"
    ]
    summary.loc[0, f"{prefix}_lineage_matches"] = drifted_view_67["matches"]
    for field, value in drifted_view_67.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
        }:
            continue
        summary.loc[0, f"{prefix}_{field}"] = value

    report = evaluate_cutover_gate(
        scaleup_summary=summary,
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_view_60 = report.config[
        "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_60 == cutover_view_60_target_application_lineage_comparison(
        vendor
    )
    assert cutover_view_60["broker_application_lineage_sha256"] == lineage_sha256
    assert cutover_view_60["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    cutover_view_68 = report.config[
        "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_68["broker_application_lineage_sha256"] == (
        drifted_lineage_sha256
    )
    assert cutover_view_68[
        "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == drifted_lineage_sha256
    assert cutover_view_68[
        "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert cutover_view_68["carried_application_lineage_sha256"] == lineage_sha256


def test_cutover_gate_requires_scaleup_view_67_lineage_for_verified_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    cutover_view_68 = report.config[
        "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not cutover_view_68["required"]
    assert not cutover_view_68["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_verified_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_verified_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_verified_reconciled_current_latest_extended_complete_final_roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_verified_reconciled_current_latest_extended_complete_final_scaleup_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_view_67_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_view_67 = dispatch[
        "scaleup_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_view_67[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_requires_scaleup_view_59_lineage_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    cutover_view_60 = report.config[
        "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not cutover_view_60["required"]
    assert not cutover_view_60["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_reconciled_current_latest_extended_complete_final_roundtrip_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_reconciled_current_latest_extended_complete_final_scaleup_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_view_59_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_view_59 = dispatch[
        "scaleup_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_view_59[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_requires_scaleup_view_51_lineage_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    cutover_view_52 = report.config[
        "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not cutover_view_52["required"]
    assert not cutover_view_52["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_current_latest_extended_complete_final_roundtrip_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_current_latest_extended_complete_final_scaleup_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_view_51_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_view_51 = dispatch[
        "scaleup_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_view_51[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_requires_scaleup_view_43_lineage_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    cutover_view_44 = report.config[
        "cutover_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not cutover_view_44["required"]
    assert not cutover_view_44["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_latest_extended_complete_final_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_latest_extended_complete_final_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_view_43_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_view_43 = dispatch[
        "scaleup_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_view_43[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_requires_scaleup_view_35_lineage_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "scaleup_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    cutover_view_36 = report.config[
        "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not cutover_view_36["required"]
    assert not cutover_view_36["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_extended_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_extended_complete_final_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_view_35_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_view_35 = dispatch[
        "scaleup_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_view_35[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_blocks_scaleup_complete_final_lineage_drift():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_complete_final = (
        scaleup_complete_final_target_application_lineage_comparison(vendor)
    )
    for field in scaleup_complete_final:
        if field not in {"required", "matches"}:
            scaleup_complete_final[field] = "f" * 64
    dispatch[
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_complete_final

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    expected_lineage_sha256 = target_application_lineage_sha256(
        vendor["datasets"]
    )
    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    cutover_complete_final = report.config[
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_complete_final["broker_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    assert cutover_complete_final["scaleup_final_review_carried_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    assert cutover_complete_final["carried_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    cutover_extended_complete_final = report.config[
        "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_extended_complete_final[
        "broker_application_lineage_sha256"
    ] == scaleup_complete_final["broker_application_lineage_sha256"]
    assert cutover_extended_complete_final[
        "carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    assert (
        cutover_complete_final["broker_application_lineage_sha256"]
        != cutover_extended_complete_final["broker_application_lineage_sha256"]
    )


def test_cutover_gate_requires_scaleup_complete_final_lineage_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    dispatch.pop(
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final"
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
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final_source_lineage_sha256_matches",
        ),
        (
            "route_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final_route_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_complete_final_scaleup_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_complete_final_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)
    scaleup_complete_final = dispatch[
        "scaleup_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    scaleup_complete_final[field] = value

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_blocks_scaleup_final_lineage_drift():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    scaleup_final = {
        "required": True,
        "matches": True,
    }
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
        scaleup_final[field] = "f" * 64
    dispatch[
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_final

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_scaleup_carried_lineage_sha256_matches",
        f"{check_prefix}_cutover_final_review_carried_lineage_sha256_matches",
    } <= failed
    expected_lineage_sha256 = target_application_lineage_sha256(
        vendor["datasets"]
    )
    compatibility = report.config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert compatibility["current_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    assert compatibility["broker_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    assert compatibility["scaleup_carried_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    cutover_final = report.config[
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_final["broker_application_lineage_sha256"] == "f" * 64
    assert cutover_final["carried_application_lineage_sha256"] == (
        expected_lineage_sha256
    )


def test_cutover_gate_requires_scaleup_final_lineage_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    check_prefix = (
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final"
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
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_source_lineage_sha256_matches",
        ),
        (
            "broker_readiness_review_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_broker_readiness_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_scaleup_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_scaleup_final_lineage(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(
        config,
        vendor,
        **{field: value},
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_blocks_carried_target_application_lineage_drift():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    final_lineage = final_target_application_lineage_comparison(vendor)
    scaleup_final_lineage = scaleup_final_target_application_lineage_comparison(
        vendor
    )
    vendor["datasets"][1]["mapping_application_id"] = "mapping-app-replaced"
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = lineage
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_lineage
    dispatch[
        "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = scaleup_final_lineage

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert f"{prefix}_cutover_carried_lineage_sha256_matches" in failed
    assert f"{prefix}_cutover_review_carried_lineage_sha256_matches" in failed
    assert f"{prefix}_scaleup_carried_lineage_sha256_matches" not in failed
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_application_lineage_sha256"] == summary[
        "scaleup_broker_vendor_market_data_batch_application_lineage_sha256"
    ]
    assert summary[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
    ] != summary["scaleup_broker_vendor_market_data_batch_application_lineage_sha256"]


def test_cutover_gate_blocks_failed_scaleup_target_lineage_decisions():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistent=False,
    )
    lineage = target_application_lineage_comparison(vendor)
    lineage["matches"] = False
    lineage["current_application_lineage_sha256"] = "f" * 64
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = lineage
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_lineage_matches",
        f"{prefix}_source_lineage_sha256_matches",
        f"{prefix}_application_lineage_consistent",
    } <= failed


def test_cutover_gate_requires_final_lineage_comparison_for_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_final_lineage_match_required",
        f"{prefix}_final_lineage_matches",
    } <= failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        ),
        (
            "readiness_carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_final_scaleup_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_cutover_gate_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    dispatch[
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )
    add_scaleup_final_target_application_lineage(config, vendor)

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_cutover_gate_skips_final_lineage_for_non_reconciled_target():
    config = scaleup_config()
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    dispatch["vendor_market_data_batch_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    check_names = set(report.checks["check"])
    final_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_final_"
    assert not any(name.startswith(final_prefix) for name in check_names)


def test_cutover_gate_carries_target_application_vendor_batch_from_scaleup_summary():
    vendor = target_application_vendor_market_data_batch_config()
    summary_input = with_scaleup_broker_vendor_batch_summary(scaleup_summary(), vendor)

    report = evaluate_cutover_gate(
        scaleup_summary=summary_input,
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    carried = report.config[prefix]
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    assert carried["datasets"][1]["mapping_scope_review_id"] == "scope-review-1"
    final_lineage = report.config[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["scaleup_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]
    expected_lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    summary_prefix = (
        "scaleup_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(report.summary.iloc[0][f"{summary_prefix}_lineage_match_required"])
    assert bool(report.summary.iloc[0][f"{summary_prefix}_lineage_matches"])
    assert report.summary.iloc[0][
        f"{summary_prefix}_scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    assert report.summary.iloc[0][
        f"{summary_prefix}_cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    cutover_view_52 = report.config[
        "cutover_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_52["required"]
    assert cutover_view_52["matches"]
    assert (
        cutover_view_52[
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == expected_lineage_sha256
    )
    assert (
        cutover_view_52[
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == expected_lineage_sha256
    )
    assert cutover_view_52["carried_application_lineage_sha256"] == (
        expected_lineage_sha256
    )
    reconciled_summary_prefix = (
        "scaleup_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        report.summary.iloc[0][
            f"{reconciled_summary_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        report.summary.iloc[0][f"{reconciled_summary_prefix}_lineage_matches"]
    )
    assert report.summary.iloc[0][
        f"{reconciled_summary_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    assert report.summary.iloc[0][
        f"{reconciled_summary_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    cutover_view_60 = report.config[
        "cutover_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_60 == cutover_view_60_target_application_lineage_comparison(
        vendor
    )
    verified_summary_prefix = (
        "scaleup_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        report.summary.iloc[0][
            f"{verified_summary_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        report.summary.iloc[0][f"{verified_summary_prefix}_lineage_matches"]
    )
    assert report.summary.iloc[0][
        f"{verified_summary_prefix}_scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    assert report.summary.iloc[0][
        f"{verified_summary_prefix}_cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    cutover_view_68 = report.config[
        "cutover_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_68 == cutover_view_68_target_application_lineage_comparison(
        vendor
    )
    confirmed_summary_prefix = (
        "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(
        report.summary.iloc[0][
            f"{confirmed_summary_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        report.summary.iloc[0][f"{confirmed_summary_prefix}_lineage_matches"]
    )
    assert report.summary.iloc[0][
        f"{confirmed_summary_prefix}_scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    assert report.summary.iloc[0][
        f"{confirmed_summary_prefix}_cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == expected_lineage_sha256
    cutover_view_76 = report.config[
        "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_view_76 == cutover_view_76_target_application_lineage_comparison(
        vendor
    )


def test_cutover_gate_blocks_incomplete_target_application_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config(
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
    )
    vendor["datasets"][1]["mapping_application_sha256"] = ""
    config = scaleup_config()
    config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = vendor
    config["broker_readiness"]["dispatch_roundtrip"][
        "vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_target_application_lineage_comparison(vendor)
    add_scaleup_final_target_application_lineage(config, vendor)

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
    } <= failed


def test_cutover_gate_blocks_failed_broker_vendor_data_readiness_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["broker_vendor_data_readiness"] = {
        "provided": True,
        "ready": False,
        "failed_checks": 1,
    }
    config["broker_readiness"]["dispatch_roundtrip"][
        "vendor_market_data_batch"
    ] = vendor_market_data_batch_config()

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    summary = report.summary.iloc[0]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert summary["scaleup_broker_vendor_data_readiness_provided"]
    assert not summary["scaleup_broker_vendor_data_readiness_ready"]
    assert int(summary["scaleup_broker_vendor_data_readiness_failed_checks"]) == 1
    assert {
        "scaleup_broker_vendor_data_readiness_ready",
        "scaleup_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert report.config["scaleup_broker_vendor_data_readiness"] == {
        "provided": True,
        "ready": False,
        "failed_checks": 1,
    }
    assert report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_cutover_gate_blocks_bad_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"] = (
        vendor_market_data_batch_config(
            ready=False,
            adapter="irage",
            market="us_options_regular",
            dataset_count=0,
            ready_datasets=0,
            failed_datasets=1,
            ready_rate=0.0,
            unique_source_files=0,
            unique_header_fingerprints=0,
            source_file_fingerprint_coverage=0.0,
            min_mapping_coverage=0.0,
            unique_mapping_drafts=0,
            mapping_sources="",
            comparison_accepted=False,
            comparison_failed_checks=1,
            datasets=[],
        )
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["adapter"] == "irage"
    assert vendor["market"] == "us_options_regular"
    assert vendor["failed_datasets"] == 1


def test_cutover_gate_blocks_wrong_manifest_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"] = (
        vendor_market_data_batch_config(manifest_run_type="not_vendor_batch")
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_cutover_gate_prefers_broker_specific_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["vendor_market_data_batch"] = vendor_market_data_batch_config(
        ready=False,
        adapter="irage",
        market="us_options_regular",
        failed_datasets=1,
        comparison_failed_checks=1,
    )
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == (
        "india_nse_index_derivatives"
    )
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]


def test_cutover_gate_carries_roundtrip_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["unique_mapping_drafts"] == 1


def test_cutover_gate_blocks_wrong_manifest_roundtrip_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_cutover_gate_blocks_bad_broker_specific_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["vendor_market_data_batch"] = vendor_market_data_batch_config()
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        ready=False,
        adapter="irage",
        market="us_options_regular",
        dataset_count=0,
        ready_datasets=0,
        failed_datasets=1,
        ready_rate=0.0,
        unique_source_files=0,
        unique_header_fingerprints=0,
        source_file_fingerprint_coverage=0.0,
        min_mapping_coverage=0.0,
        unique_mapping_drafts=0,
        mapping_sources="",
        comparison_accepted=False,
        comparison_failed_checks=1,
        datasets=[],
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["adapter"] == "irage"
    assert vendor["market"] == "us_options_regular"
    assert vendor["failed_datasets"] == 1


def test_cutover_gate_blocks_wrong_manifest_broker_specific_broker_vendor_market_data_batch_from_scaleup_config():
    config = scaleup_config()
    dispatch = config["broker_readiness"]["dispatch_roundtrip"]
    dispatch["vendor_market_data_batch"] = vendor_market_data_batch_config()
    dispatch["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_cutover_gate_blocks_bad_shadow_broker_readiness_from_scaleup_config():
    config = scaleup_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        ready_sessions=1,
        vendor_data_readiness_ready_sessions=1,
        vendor_data_readiness_failed_checks=1,
        adapter="irage",
        adapter_count=2,
        route_ready_sessions=1,
        route_strategy="surface_mm",
        route_market="us_options_regular",
        route_gap_pairs=2,
        dispatch_ready_sessions=1,
        dispatch_strategy="surface_mm",
        dispatch_market="us_options_regular",
        dispatch_scenario_count=2,
        dispatch_missing_request_acks=1,
        dispatch_rejected_orders=1,
        dispatch_unmatched_acks=1,
        route_dispatch_ready_sessions=1,
        route_dispatch_strategy="surface_mm",
        route_dispatch_market="us_options_regular",
        route_dispatch_scenario_count=2,
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_shadow_broker_readiness_ready",
        "scaleup_shadow_broker_vendor_data_readiness_ready",
        "scaleup_shadow_broker_vendor_data_readiness_failed_checks",
        "scaleup_shadow_broker_adapter_matches",
        "scaleup_shadow_broker_adapter_consistent",
        "scaleup_shadow_broker_route_readiness_ready",
        "scaleup_shadow_broker_route_readiness_strategy_matches",
        "scaleup_shadow_broker_route_readiness_market_matches",
        "scaleup_shadow_broker_route_readiness_gap_pairs",
        "scaleup_shadow_broker_dispatch_roundtrip_ready",
        "scaleup_shadow_broker_dispatch_roundtrip_strategy_matches",
        "scaleup_shadow_broker_dispatch_roundtrip_market_matches",
        "scaleup_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "scaleup_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "scaleup_shadow_broker_dispatch_roundtrip_rejected_orders",
        "scaleup_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "scaleup_shadow_broker_route_dispatch_roundtrip_ready",
        "scaleup_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "scaleup_shadow_broker_route_dispatch_roundtrip_market_matches",
        "scaleup_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["scaleup_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["scaleup_shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["scaleup_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_cutover_gate_blocks_partial_shadow_broker_vendor_data_readiness_from_scaleup_config():
    config = scaleup_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        vendor_data_readiness_sessions=1,
        vendor_data_readiness_provided_sessions=1,
        vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "scaleup_shadow_broker_vendor_data_readiness_provided",
        "scaleup_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    assert int(report.summary.iloc[0]["scaleup_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["scaleup_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_cutover_gate_carries_broker_shadow_broker_readiness_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["scaleup_broker_shadow_broker_readiness_provided"]
    assert int(summary["scaleup_broker_shadow_broker_readiness_sessions"]) == 2
    assert int(summary["scaleup_broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["scaleup_broker_shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["scaleup_broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["scaleup_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["scaleup_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["scaleup_broker_shadow_broker_readiness"]["provided"]
    assert report.config["scaleup_broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert (
        report.config["scaleup_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
            "ready_sessions"
        ]
        == 2
    )
    assert report.config["scaleup_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["scaleup_broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["scaleup_broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_cutover_gate_blocks_bad_broker_shadow_broker_readiness_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            ready_sessions=1,
            vendor_data_readiness_ready_sessions=1,
            vendor_data_readiness_failed_checks=1,
            adapter="irage",
            adapter_count=2,
            route_ready_sessions=1,
            route_strategy="surface_mm",
            route_market="us_options_regular",
            route_gap_pairs=2,
            dispatch_ready_sessions=1,
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_count=2,
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
            route_dispatch_ready_sessions=1,
            route_dispatch_strategy="surface_mm",
            route_dispatch_market="us_options_regular",
            route_dispatch_scenario_count=2,
        ),
    }

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_broker_shadow_broker_readiness_ready",
        "scaleup_broker_shadow_broker_vendor_data_readiness_ready",
        "scaleup_broker_shadow_broker_vendor_data_readiness_failed_checks",
        "scaleup_broker_shadow_broker_adapter_matches",
        "scaleup_broker_shadow_broker_adapter_consistent",
        "scaleup_broker_shadow_broker_route_readiness_ready",
        "scaleup_broker_shadow_broker_route_readiness_strategy_matches",
        "scaleup_broker_shadow_broker_route_readiness_market_matches",
        "scaleup_broker_shadow_broker_route_readiness_gap_pairs",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_ready",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_market_matches",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "scaleup_broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_ready",
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "scaleup_broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["scaleup_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert (
        report.config["scaleup_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
            "failed_checks"
        ]
        == 1
    )
    assert report.config["scaleup_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2
    assert report.config["scaleup_broker_shadow_broker_readiness"]["dispatch_roundtrip"][
        "max_rejected_orders"
    ] == 1


def test_cutover_gate_blocks_partial_broker_shadow_broker_vendor_data_readiness_from_scaleup_config():
    config = scaleup_config()
    config["broker_readiness"]["shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            vendor_data_readiness_sessions=1,
            vendor_data_readiness_provided_sessions=1,
            vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "scaleup_broker_shadow_broker_vendor_data_readiness_provided",
        "scaleup_broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["scaleup_broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert (
        report.config["scaleup_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
            "provided_sessions"
        ]
        == 1
    )


def test_cutover_gate_live_dryrun_requires_route_readiness():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(route_readiness_provided=False, route_readiness_ready=False),
        scaleup_config=scaleup_config(route_readiness_provided=False, route_readiness_ready=False),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"scaleup_route_readiness_provided", "scaleup_route_readiness_ready"} <= failed
    assert report.config["scaleup_route_readiness"]["required"]
    assert not report.config["scaleup_route_readiness"]["provided"]


def test_cutover_gate_blocks_route_readiness_identity_mismatch():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        scaleup_config=scaleup_config(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"scaleup_route_readiness_strategy_matches", "scaleup_route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["scaleup_route_readiness_strategy"] == "surface_mm"
    assert report.config["scaleup_route_readiness"]["market"] == "us_options_regular"


def test_cutover_gate_blocks_stale_scaleup_route_readiness_ops_controls():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        scaleup_config=scaleup_config(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_route_readiness_ops_launch_controls_present",
        "scaleup_route_readiness_ops_launch_controls_blocked_pairs",
        "scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
        "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["scaleup_route_readiness_ops_launch_controls_present"])
    assert int(summary["scaleup_route_readiness_ops_launch_controls_blocked_pairs"]) == 1
    assert report.config["scaleup_route_readiness"]["ops_broker_roundtrip_portfolio_breach_pairs"] == 1
    assert report.config["scaleup_route_readiness"][
        "ops_broker_roundtrip_portfolio_concentration_breach_pairs"
    ] == 1


def test_cutover_gate_blocks_stale_scaleup_broker_route_readiness_ops_controls():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        scaleup_config=scaleup_config(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_broker_route_readiness_ops_launch_controls_ready",
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["scaleup_broker_route_readiness_ops_launch_controls_ready"])
    assert int(summary["scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) == 1
    route_proof = report.config["scaleup_broker_route_readiness"]
    assert route_proof["ops_launch_control_failures"] == "concentration breach on BANKNIFTY weekly"
    assert route_proof["ops_broker_roundtrip_portfolio_concentration_breach_runs"] == 1


def test_cutover_gate_live_dryrun_requires_dispatch_roundtrip():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(dispatch_provided=False, dispatch_ready=False),
        scaleup_config=scaleup_config(dispatch_provided=False, dispatch_ready=False),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(dispatch_provided=False, dispatch_ready=False),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_dispatch_roundtrip_provided",
        "scaleup_dispatch_roundtrip_ready",
        "broker_dispatch_roundtrip_provided",
        "broker_dispatch_roundtrip_ready",
    } <= failed
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["required"]


def test_cutover_gate_live_dryrun_requires_route_dispatch_roundtrip():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(route_provided=False, route_ready=False),
        scaleup_config=scaleup_config(route_provided=False, route_ready=False),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(route_provided=False, route_ready=False),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_route_dispatch_roundtrip_provided",
        "scaleup_route_dispatch_roundtrip_ready",
        "broker_route_dispatch_roundtrip_provided",
        "broker_route_dispatch_roundtrip_ready",
    } <= failed
    assert report.config["scaleup_dispatch_roundtrip"]["route_proof"]["required"]
    assert not report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]["provided"]


def test_cutover_gate_blocks_bad_broker_route_dispatch_roundtrip_quality():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(
            route_ready=False,
            route_target_mode="shadow",
            route_strategy="surface_mm",
            route_market="us_options_regular",
            route_scenario_key="wrong-scenario",
            route_batch_id="",
            route_requests=1,
            route_acked_orders=1,
            route_missing_request_acks=1,
            route_rejected_orders=1,
            route_unmatched_acks=1,
        ),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
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
        "route_dispatch_roundtrip_batch_matches",
    } <= failed
    route_proof = report.config["broker_readiness"]["dispatch_roundtrip"]["route_proof"]
    assert route_proof["strategy"] == "surface_mm"
    assert route_proof["missing_request_acks"] == 1


def test_cutover_gate_blocks_bad_broker_dispatch_roundtrip_quality():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(
            dispatch_ready=False,
            dispatch_target_mode="shadow",
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_key="wrong-scenario",
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
        ),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_ready",
        "broker_dispatch_roundtrip_target_mode_matches",
        "broker_dispatch_roundtrip_strategy_matches",
        "broker_dispatch_roundtrip_market_matches",
        "broker_dispatch_roundtrip_scenario_matches",
        "broker_dispatch_roundtrip_missing_request_acks",
        "broker_dispatch_roundtrip_rejected_orders",
        "broker_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["missing_request_acks"] == 1


def test_cutover_gate_blocks_dispatch_roundtrip_failed_checks():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(dispatch_failed_checks=1),
        scaleup_config=scaleup_config(dispatch_failed_checks=1),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(dispatch_failed_checks=1),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_dispatch_roundtrip_failed_checks",
        "broker_dispatch_roundtrip_failed_checks",
    } <= failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert int(report.summary.iloc[0]["scaleup_dispatch_roundtrip_failed_checks"]) == 1
    assert int(report.summary.iloc[0]["broker_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["scaleup_dispatch_roundtrip"]["failed_checks"] == 1
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["failed_checks"] == 1


def test_cutover_gate_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        scaleup_config=scaleup_config(route_enable_dispatch_roundtrip_failed_checks=1),
        scaleup_checks=scaleup_checks(),
        broker_readiness_summary=broker_readiness_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_route_enable_dispatch_roundtrip_failed_checks",
        "broker_route_enable_dispatch_roundtrip_failed_checks",
    } <= failed
    assert int(report.summary.iloc[0]["scaleup_route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert int(report.summary.iloc[0]["broker_route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["scaleup_dispatch_roundtrip"]["route_enable_dispatch_roundtrip"]["failed_checks"] == 1
    assert report.config["broker_readiness"]["dispatch_roundtrip"]["route_enable_dispatch_roundtrip"][
        "failed_checks"
    ] == 1


def test_cutover_gate_live_dryrun_requires_operator_review():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"operator_approved", "operator_identity_ack", "operator_limits_ack"} <= failed


def test_cutover_gate_blocks_runtime_identity_and_guard_breaks():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(
            ready=False,
            halted=True,
            strategy="surface_mm",
            market="us_options_regular",
        ),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "runtime_session_ready",
        "runtime_guard_continue",
        "runtime_strategy_matches",
        "runtime_market_matches",
    } <= failed


def test_cutover_gate_validates_supplied_resume_gate_identity():
    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=scaleup_config(),
        broker_readiness_summary=broker_readiness_summary(
            resume_provided=True,
            resume_strategy="surface_mm",
            resume_market="us_options_regular",
            resume_proof_ready=False,
        ),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_resume_strategy_matches",
        "broker_resume_market_matches",
        "broker_resume_proof_refresh_ready",
        "broker_resume_proof_refresh_strategy_matches",
        "broker_resume_proof_refresh_market_matches",
    } <= failed


def test_cutover_gate_carries_scaleup_resume_route_readiness():
    config = scaleup_config()
    route_proof = {
        "required": True,
        "provided": True,
        "ready": True,
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "route_ready_pairs": 1,
        "gap_pairs": 0,
        "recommendation": "route_ready",
        "ops_launch_controls_ready": True,
        "ops_launch_control_failures": "",
        "ops_broker_roundtrip_portfolio_safe_runs": 1,
        "ops_broker_roundtrip_portfolio_breach_runs": 0,
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
    }
    config["broker_readiness"]["resume_gate"] = {
        "broker_route_readiness": route_proof,
        "incident_broker_route_readiness": route_proof,
    }

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert summary["scaleup_broker_resume_broker_route_readiness_ready"]
    assert summary["scaleup_broker_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["scaleup_broker_resume_incident_broker_route_readiness_route_ready_pairs"] == 1
    assert report.config["scaleup_broker_resume_gate"]["broker_route_readiness"]["ready"]
    assert (
        report.config["scaleup_broker_resume_gate"]["incident_broker_route_readiness"][
            "ops_broker_roundtrip_portfolio_safe_runs"
        ]
        == 1
    )


def test_cutover_gate_blocks_bad_scaleup_resume_route_readiness():
    config = scaleup_config()
    config["broker_readiness"]["resume_gate"] = {
        "broker_route_readiness": {
            "required": True,
            "provided": True,
            "ready": False,
            "strategy": "surface_mm",
            "market": "us_options_regular",
            "route_ready_pairs": 0,
            "gap_pairs": 2,
            "recommendation": "complete_route_readiness_gaps",
            "ops_launch_controls_ready": False,
            "ops_launch_control_failures": "stale post-halt route proof",
            "ops_broker_roundtrip_portfolio_safe_runs": 0,
            "ops_broker_roundtrip_portfolio_breach_runs": 1,
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": 0,
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": 1,
        },
    }

    report = evaluate_cutover_gate(
        scaleup_summary=scaleup_summary(),
        scaleup_config=config,
        broker_readiness_summary=broker_readiness_summary(),
        runtime_session_summary=runtime_session_summary(),
        operator_review=operator_review(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "scaleup_broker_resume_broker_route_readiness_ready",
        "scaleup_broker_resume_broker_route_readiness_strategy_matches",
        "scaleup_broker_resume_broker_route_readiness_market_matches",
        "scaleup_broker_resume_broker_route_readiness_route_ready_pairs",
        "scaleup_broker_resume_broker_route_readiness_gap_pairs",
        "scaleup_broker_resume_broker_route_readiness_ops_launch_controls_ready",
        "scaleup_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "scaleup_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "scaleup_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "scaleup_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    assert report.summary.iloc[0]["scaleup_broker_resume_broker_route_readiness_market"] == "us_options_regular"
    assert report.config["scaleup_broker_resume_gate"]["broker_route_readiness"]["gap_pairs"] == 2


def test_write_cutover_gate_outputs_artifacts_and_catalog_entry(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(
        tmp_path,
        canonical_leadlag=True,
    )
    out_dir = tmp_path / "cutover"

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=out_dir,
    )

    assert report.ready
    assert (out_dir / "cutover_authorization.csv").exists()
    assert (out_dir / "cutover_checks.csv").exists()
    assert (out_dir / "cutover_summary.csv").exists()
    assert (out_dir / "cutover_action_queue.csv").exists()
    assert (out_dir / "cutover_config.json").exists()
    assert (out_dir / "cutover_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    saved_summary = pd.read_csv(out_dir / "cutover_summary.csv")
    saved_config = json.loads((out_dir / "cutover_config.json").read_text(encoding="utf-8"))
    assert int(saved_summary.loc[0, "action_queue_count"]) == 0
    assert saved_config["action_queue_count"] == 0
    assert saved_config["next_actions"] == []
    runbook = (out_dir / "cutover_runbook.md").read_text(encoding="utf-8")
    assert runbook.startswith("# Cutover Gate Runbook")
    assert "Lead-lag lineage matches scale-up: yes" in runbook
    assert "c" * 64 in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {item["path"] for item in manifest["artifacts"]}
    assert "cutover_action_queue.csv" in artifact_paths
    assert "cutover_runbook.md" in artifact_paths
    assert {
        "scaleup_summary",
        "scaleup_config",
        "scaleup_checks",
        "scaleup_manifest",
        "scaleup_artifacts",
        "scaleup_dependencies",
        "broker_readiness_summary",
        "broker_readiness_config",
        "runtime_session_summary",
        "operator_review",
    } <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["scaleup_summary"]["path"]).endswith("/scaleup/scaleup_summary.csv")
    assert path_tail(manifest["inputs"]["scaleup_config"]["path"]).endswith("/scaleup/scaleup_config.json")
    assert path_tail(manifest["inputs"]["scaleup_checks"]["path"]).endswith("/scaleup/scaleup_checks.csv")
    assert path_tail(manifest["inputs"]["broker_readiness_summary"]["path"]).endswith(
        "/broker/broker_readiness_summary.csv"
    )
    assert path_tail(manifest["inputs"]["broker_readiness_config"]["path"]).endswith(
        "/broker/broker_readiness_config.json"
    )
    assert path_tail(manifest["inputs"]["runtime_session_summary"]["path"]).endswith(
        "/runtime/runtime_session_summary.csv"
    )
    assert path_tail(manifest["inputs"]["operator_review"]["path"]).endswith("/operator_review.csv")
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "cutover_gate"
    assert catalog.catalog.iloc[0]["summary_file"] == "cutover_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])
    assert report.summary.iloc[0]["runtime_lineage_gate_passed"]
    assert report.summary.iloc[0]["scaleup_provenance_gate_passed"]
    assert report.summary.iloc[0]["runtime_scaleup_manifest_sha256"] == file_sha256(
        scaleup / "manifest.json"
    )
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert report.config["runtime_lineage"]["runtime_lineage_gate_passed"]
    assert report.config["scaleup_provenance"][
        "scaleup_provenance_gate_passed"
    ]
    assert report.config["runtime_session"]["strategy_portfolio"][
        "leadlag_edge_lineage_matches_scaleup"
    ]
    assert report.config["runtime_session"]["strategy_portfolio"][
        "leadlag_edge_lineage_contract_sha256"
    ] == "c" * 64
    assert not report.config["authorizes_submission"]
    assert {
        "runtime_session_manifest",
        "runtime_session_artifacts",
        "runtime_session_dependencies",
    } <= set(manifest["inputs"])
    assert manifest["extra"]["runtime_lineage_gate_passed"]
    assert manifest["extra"]["scaleup_provenance_gate_passed"]
    assert manifest["extra"][
        "runtime_strategy_portfolio_leadlag_edge_lineage_matches_scaleup"
    ]
    assert manifest["extra"][
        "runtime_strategy_portfolio_leadlag_edge_lineage_contract_sha256"
    ] == "c" * 64
    assert not manifest["extra"]["authorizes_submission"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="cutover_gate",
        require_input_fingerprints=True,
    ).passed
    (tmp_path / "scaleup_source.csv").write_text("source\nchanged\n", encoding="utf-8")
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="cutover_gate",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_cutover_revalidates_current_scaleup_proof_refresh_lineage(
    tmp_path,
):
    (
        scaleup,
        broker,
        runtime,
        review_path,
        proof_refresh,
        _,
        thresholds,
    ) = write_proof_refresh_cutover_inputs(tmp_path)
    out_dir = tmp_path / "cutover"

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=out_dir,
        thresholds=thresholds,
    )

    summary = report.summary.iloc[0]
    assert report.ready
    assert summary["scaleup_manifest_current"]
    assert summary["scaleup_contract_consistent"]
    assert summary["scaleup_provenance_gate_passed"]
    assert summary["scaleup_proof_refresh_active"]
    assert summary["scaleup_proof_refresh_verified"]
    assert summary[
        "scaleup_proof_refresh_source_semantically_verified"
    ]
    assert summary[
        "scaleup_proof_refresh_source_provenance_gate_passed"
    ]
    assert summary["scaleup_proof_refresh_matches_current"]
    assert summary[
        "scaleup_proof_refresh_manifest_sha256"
    ] == file_sha256(proof_refresh / "manifest.json")
    assert report.config["scaleup_provenance"][
        "scaleup_proof_refresh_matches_current"
    ]
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["extra"][
        "scaleup_proof_refresh_matches_current"
    ]
    assert {
        "scaleup_manifest",
        "scaleup_artifacts",
        "scaleup_dependencies",
    } <= set(manifest["inputs"])

    from tests.data_readiness_helpers import (
        reseal_experiment_manifest,
    )

    refresh_summary_path = (
        proof_refresh / "proof_refresh_summary.csv"
    )
    refresh_summary = pd.read_csv(refresh_summary_path)
    refresh_summary.loc[0, "proof_source"] = "latest"
    refresh_summary.to_csv(refresh_summary_path, index=False)
    reseal_experiment_manifest(proof_refresh)
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="cutover_gate",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_cutover_blocks_resealed_scaleup_proof_refresh_semantic_drift(
    tmp_path,
):
    (
        scaleup,
        broker,
        runtime,
        review_path,
        proof_refresh,
        _,
        thresholds,
    ) = write_proof_refresh_cutover_inputs(tmp_path)
    from tests.data_readiness_helpers import (
        reseal_experiment_manifest,
    )
    from tests.test_scaleup_runtime_provenance import (
        _refresh_scaleup_manifest,
    )

    refresh_summary_path = (
        proof_refresh / "proof_refresh_summary.csv"
    )
    refresh_summary = pd.read_csv(refresh_summary_path)
    refresh_summary.loc[0, "proof_source"] = "latest"
    refresh_summary.to_csv(refresh_summary_path, index=False)
    reseal_experiment_manifest(proof_refresh)
    refresh_sha = file_sha256(proof_refresh / "manifest.json")

    scaleup_config_path = scaleup / "scaleup_config.json"
    scaleup_config_payload = json.loads(
        scaleup_config_path.read_text(encoding="utf-8")
    )
    scaleup_config_payload["proof_freshness"]["manifest"][
        "sha256"
    ] = refresh_sha
    scaleup_config_path.write_text(
        json.dumps(
            scaleup_config_payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in ("scaleup_summary.csv", "scaleup_plan.csv"):
        path = scaleup / name
        frame = pd.read_csv(path)
        frame.loc[0, "proof_refresh_manifest_sha256"] = (
            refresh_sha
        )
        frame.to_csv(path, index=False)
    _refresh_scaleup_manifest(
        scaleup / "manifest.json",
        extra_updates={
            "proof_refresh_manifest_sha256": refresh_sha,
        },
    )
    assert verify_experiment_manifest(
        scaleup / "manifest.json",
        expected_run_type="scaleup_plan",
        require_input_fingerprints=True,
    ).passed

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
        thresholds=thresholds,
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert "scaleup_manifest_current" not in failed
    assert {
        "scaleup_contract_consistent",
        "scaleup_provenance_gate_passed",
        "scaleup_proof_refresh_source_semantically_verified",
        "scaleup_proof_refresh_source_provenance_gate_passed",
        "scaleup_proof_refresh_matches_current",
    } <= failed
    summary = report.summary.iloc[0]
    assert not summary["scaleup_contract_consistent"]
    assert not summary[
        "scaleup_proof_refresh_source_semantically_verified"
    ]
    assert not summary["scaleup_proof_refresh_matches_current"]
    action = report.action_queue.loc[
        report.action_queue["check"]
        == "scaleup_proof_refresh_matches_current"
    ].iloc[0]
    assert action["component"] == "proof_refresh"
    assert action["next_gate"] == "review-proof-refresh"
    assert verify_experiment_manifest(
        tmp_path / "cutover" / "manifest.json",
        expected_run_type="cutover_gate",
        require_input_fingerprints=True,
    ).passed


def test_cutover_revalidates_runtime_broker_readiness_lineage(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(
        tmp_path,
        target_mode="shadow",
    )
    broker_fields = bind_broker_readiness_runtime_lineage(
        tmp_path,
        scaleup,
        broker,
        runtime,
    )

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
        thresholds=CutoverGateThresholds(target_mode="shadow"),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert report.ready
    assert "runtime_lineage_broker_readiness_source_matches_scaleup" not in failed
    assert "runtime_lineage_broker_readiness_matches_current" not in failed
    assert report.summary.iloc[0][
        "runtime_lineage_current_broker_readiness_manifest_sha256"
    ] == broker_fields["broker_readiness_manifest_sha256"]
    assert report.config["runtime_lineage"][
        "runtime_lineage_broker_readiness_source_matches_scaleup"
    ]
    assert report.config["runtime_lineage"][
        "runtime_lineage_broker_readiness_matches_current"
    ]
    manifest = json.loads(
        (tmp_path / "cutover" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["extra"][
        "runtime_lineage_broker_readiness_source_matches_scaleup"
    ]
    assert manifest["extra"][
        "runtime_lineage_broker_readiness_matches_current"
    ]


def test_cutover_verifies_runtime_broker_contract_identity(tmp_path):
    (
        scaleup,
        broker,
        runtime,
        review_path,
        broker_fields,
    ) = write_contract_identity_cutover_inputs(tmp_path)
    out_dir = tmp_path / "cutover"

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=out_dir,
    )

    identity_sha256 = broker_fields[
        "broker_readiness_roundtrip_contract_identity_sha256"
    ]
    summary = report.summary.iloc[0]
    identity_checks = report.checks.loc[
        report.checks["check"].astype(str).str.contains(
            "contract_identity"
        )
    ]
    assert report.ready
    assert not identity_checks.empty
    assert identity_checks["passed"].astype(bool).all()
    assert summary[
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_sha256"
    ] == identity_sha256
    assert summary[
        "runtime_lineage_current_broker_readiness_"
        "contract_identity_sha256"
    ] == identity_sha256
    assert summary[
        "runtime_lineage_broker_readiness_"
        "contract_identity_matches_current"
    ]
    assert report.config["runtime_lineage"][
        "runtime_lineage_broker_readiness_"
        "contract_identity_matches_current"
    ]
    runbook = (out_dir / "cutover_runbook.md").read_text(
        encoding="utf-8"
    )
    assert f"Broker contract identity digest: `{identity_sha256}`" in runbook
    assert "Broker contract identity matches current: yes" in runbook
    lineage = load_cutover_lineage(out_dir / "cutover_config.json")
    assert lineage["gate_passed"]
    assert lineage["runtime_contract_identity_active"]
    assert lineage["runtime_contract_identity_matches_current"]
    assert (
        lineage["current_runtime_contract_identity_sha256"]
        == identity_sha256
    )


def test_cutover_blocks_remanifested_runtime_contract_identity_forgery(
    tmp_path,
):
    from tests.data_readiness_helpers import reseal_experiment_manifest

    (
        scaleup,
        broker,
        runtime,
        review_path,
        broker_fields,
    ) = write_contract_identity_cutover_inputs(tmp_path)
    identity_field = (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_sha256"
    )
    forged_sha256 = "f" * 64
    summary_path = runtime / "runtime_session_summary.csv"
    summary = pd.read_csv(summary_path).astype(object)
    summary.loc[0, identity_field] = forged_sha256
    summary.to_csv(summary_path, index=False)
    config_path = runtime / "runtime_session_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["runtime_telemetry_lineage"][identity_field] = forged_sha256
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = runtime / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extra"][identity_field] = forged_sha256
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(runtime)
    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type="runtime_session_monitor",
        require_input_fingerprints=True,
    ).passed

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
    )

    current_sha256 = broker_fields[
        "broker_readiness_roundtrip_contract_identity_sha256"
    ]
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.ready
    assert "runtime_session_manifest_current" not in failed
    assert "runtime_lineage_contract_consistent" not in failed
    assert {
        (
            "runtime_telemetry_broker_readiness_roundtrip_"
            "contract_identity_sha256_matches_current"
        ),
        (
            "runtime_lineage_broker_readiness_"
            "contract_identity_matches_current"
        ),
        "runtime_lineage_broker_readiness_matches_current",
        "runtime_lineage_gate_passed",
    } <= failed
    summary_row = report.summary.iloc[0]
    assert summary_row[identity_field] == forged_sha256
    assert summary_row[
        "runtime_lineage_current_broker_readiness_"
        "contract_identity_sha256"
    ] == current_sha256
    assert not summary_row[
        "runtime_lineage_broker_readiness_"
        "contract_identity_matches_current"
    ]
    action = report.action_queue.loc[
        report.action_queue["check"]
        == (
            "runtime_lineage_broker_readiness_"
            "contract_identity_matches_current"
        )
    ].iloc[0]
    assert action["component"] == "broker_readiness"
    assert action["next_gate"] == "review-broker-readiness"


def test_cutover_lineage_blocks_remanifested_contract_identity_forgery(
    tmp_path,
):
    from tests.data_readiness_helpers import reseal_experiment_manifest

    (
        scaleup,
        broker,
        runtime,
        review_path,
        _,
    ) = write_contract_identity_cutover_inputs(tmp_path)
    cutover = tmp_path / "cutover"
    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=cutover,
    )
    assert report.ready

    identity_field = (
        "runtime_telemetry_broker_readiness_roundtrip_"
        "contract_identity_sha256"
    )
    forged_sha256 = "e" * 64
    for name in ("cutover_authorization.csv", "cutover_summary.csv"):
        path = cutover / name
        frame = pd.read_csv(path).astype(object)
        frame.loc[0, identity_field] = forged_sha256
        frame.to_csv(path, index=False)
    config_path = cutover / "cutover_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["runtime_lineage"][identity_field] = forged_sha256
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = cutover / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["extra"][identity_field] = forged_sha256
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    reseal_experiment_manifest(cutover)
    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type="cutover_gate",
        require_input_fingerprints=True,
    ).passed

    lineage = load_cutover_lineage(config_path)

    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert lineage["runtime_contract_identity_active"]
    assert not lineage["runtime_lineage_matches_current"]
    assert not lineage["runtime_contract_identity_matches_current"]
    assert not lineage["gate_passed"]


def test_cutover_blocks_remanifested_runtime_over_stale_broker_readiness(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(
        tmp_path,
        target_mode="shadow",
    )
    bind_broker_readiness_runtime_lineage(
        tmp_path,
        scaleup,
        broker,
        runtime,
    )
    broker_config_path = broker / "broker_readiness_config.json"
    broker_config = json.loads(broker_config_path.read_text(encoding="utf-8"))
    broker_config["operator_note"] = "changed after runtime verification"
    broker_config_path.write_text(
        json.dumps(broker_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    remanifest_runtime_lineage_fixture(tmp_path, scaleup, broker, runtime)

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
        thresholds=CutoverGateThresholds(target_mode="shadow"),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "runtime_session_manifest_current" not in failed
    assert "runtime_lineage_broker_readiness_source_matches_scaleup" not in failed
    assert {
        "runtime_lineage_broker_readiness_matches_current",
        "runtime_lineage_gate_passed",
    } <= failed
    assert report.config["runtime_lineage"][
        "runtime_lineage_broker_readiness_source_matches_scaleup"
    ]
    assert not report.config["runtime_lineage"][
        "runtime_lineage_broker_readiness_matches_current"
    ]


def test_cutover_blocks_broker_readiness_source_substitution(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(
        tmp_path,
        target_mode="shadow",
    )
    bind_broker_readiness_runtime_lineage(
        tmp_path,
        scaleup,
        broker,
        runtime,
    )
    substituted_broker = tmp_path / "substituted_broker"
    shutil.copytree(broker, substituted_broker)

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=substituted_broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
        thresholds=CutoverGateThresholds(target_mode="shadow"),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {
        "runtime_lineage_broker_readiness_source_matches_scaleup",
        "runtime_lineage_broker_readiness_matches_current",
        "runtime_lineage_gate_passed",
    } <= failed
    assert not report.config["runtime_lineage"][
        "runtime_lineage_broker_readiness_source_matches_scaleup"
    ]
    action = report.action_queue.loc[
        report.action_queue["check"]
        == "runtime_lineage_broker_readiness_source_matches_scaleup"
    ].iloc[0]
    assert action["component"] == "broker_readiness"
    assert action["next_gate"] == "review-broker-readiness"


def test_cutover_blocks_drifted_runtime_lineage(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(tmp_path)
    (tmp_path / "scaleup_source.csv").write_text("source\nchanged\n", encoding="utf-8")

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {
        "scaleup_manifest_current",
        "scaleup_provenance_gate_passed",
        "runtime_session_manifest_current",
        "runtime_lineage_gate_passed",
    } <= failed
    assert report.action_queue.iloc[0]["next_gate"] == "plan-scaleup"
    assert "monitor-runtime-session" in set(
        report.action_queue["next_gate"]
    )


def test_cutover_blocks_remanifested_runtime_contract_and_authorization_drift(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(tmp_path)
    runtime_summary_path = runtime / "runtime_session_summary.csv"
    runtime_summary = pd.read_csv(runtime_summary_path)
    runtime_summary.loc[0, "scaleup_manifest_sha256"] = "d" * 64
    runtime_summary.to_csv(runtime_summary_path, index=False)
    runtime_config_path = runtime / "runtime_session_config.json"
    runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    runtime_config["authorizes_submission"] = True
    runtime_config_path.write_text(
        json.dumps(runtime_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lineage = runtime_lineage(file_sha256(scaleup / "manifest.json"))
    write_experiment_manifest(
        runtime,
        run_type="runtime_session_monitor",
        inputs={
            "scaleup_manifest": scaleup / "manifest.json",
            "scaleup_source": tmp_path / "scaleup_source.csv",
        },
        extra={
            "ready": True,
            "guard_action": "continue",
            **lineage,
            "authorizes_submission": False,
        },
    )

    report = write_cutover_gate_report(
        scaleup_dir=scaleup,
        broker_readiness_dir=broker,
        runtime_session_dir=runtime,
        operator_review_path=review_path,
        output_dir=tmp_path / "cutover",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "runtime_session_manifest_current" not in failed
    assert {
        "runtime_lineage_contract_consistent",
        "runtime_lineage_non_authorizing",
        "runtime_lineage_scaleup_matches_current",
        "runtime_lineage_gate_passed",
    } <= failed


def test_cutover_rejects_runtime_output_collision(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(tmp_path)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_cutover_gate_report(
            scaleup_dir=scaleup,
            broker_readiness_dir=broker,
            runtime_session_dir=runtime,
            operator_review_path=review_path,
            output_dir=runtime,
        )


def test_cli_cutover_gate_reads_launch_pipeline_broker_readiness_roots(tmp_path):
    cases = [
        ("leadlag", "06_broker_readiness"),
        ("surface_mm", "05_broker_readiness"),
    ]
    for family, broker_folder in cases:
        case_dir = tmp_path / family
        scaleup, _broker, runtime, review_path = write_inputs(case_dir)
        pipeline = case_dir / f"{family}_launch_pipeline"
        broker_readiness = pipeline / broker_folder
        out_dir = case_dir / "cutover"
        broker_readiness.mkdir(parents=True)
        broker_readiness_summary().to_csv(broker_readiness / "broker_readiness_summary.csv", index=False)
        (broker_readiness / "broker_readiness_config.json").write_text(
            json.dumps({"ready": True, "adapter": "arrow_money"}, indent=2) + "\n",
            encoding="utf-8",
        )

        code = main(
            [
                "review-cutover-gate",
                "--scaleup",
                str(scaleup),
                "--broker-readiness",
                str(pipeline),
                    "--operator-review",
                    str(review_path),
                    "--runtime-session",
                    str(runtime),
                    "--out",
                str(out_dir),
                "--fail-on-breach",
            ]
        )

        summary = pd.read_csv(out_dir / "cutover_summary.csv")
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert code == 0
        assert bool(summary.loc[0, "ready"])
        assert path_tail(manifest["inputs"]["scaleup_summary"]["path"]).endswith(
            f"/{family}/scaleup/scaleup_summary.csv"
        )
        assert path_tail(manifest["inputs"]["scaleup_config"]["path"]).endswith(
            f"/{family}/scaleup/scaleup_config.json"
        )
        assert path_tail(manifest["inputs"]["scaleup_checks"]["path"]).endswith(
            f"/{family}/scaleup/scaleup_checks.csv"
        )
        assert path_tail(manifest["inputs"]["broker_readiness_summary"]["path"]).endswith(
            f"/{family}_launch_pipeline/{broker_folder}/broker_readiness_summary.csv"
        )
        assert path_tail(manifest["inputs"]["broker_readiness_config"]["path"]).endswith(
            f"/{family}_launch_pipeline/{broker_folder}/broker_readiness_config.json"
        )


def test_cli_cutover_gate_blocks_target_sidecar_without_scaleup_final_lineage(
    tmp_path,
):
    scaleup, broker, runtime, review_path = write_inputs(tmp_path)
    vendor_input = target_application_vendor_market_data_batch_config()
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "adapter": "arrow_money",
                "dispatch_roundtrip": {
                    "provided": True,
                    "ready": True,
                    "target_mode": "live_dryrun",
                    "strategy": "lead_lag_taker",
                    "market": "india_nse_index_derivatives",
                    "broker_dispatch_roundtrip_vendor_market_data_batch": (
                        vendor_input
                    ),
                    "vendor_market_data_batch_lineage_comparison": (
                        target_application_lineage_comparison(vendor_input)
                    ),
                    "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                        final_target_application_lineage_comparison(vendor_input)
                    ),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cutover"

    code = main(
        [
            "review-cutover-gate",
            "--scaleup",
            str(scaleup),
            "--broker-readiness",
            str(broker),
            "--runtime-session",
            str(runtime),
            "--operator-review",
            str(review_path),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "cutover_summary.csv")
    checks = pd.read_csv(out_dir / "cutover_checks.csv")
    config = json.loads((out_dir / "cutover_config.json").read_text(encoding="utf-8"))
    vendor = config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_lineage_match_required",
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_final_lineage_matches",
    } <= failed
    assert bool(summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert (
        summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"]
        == "arrow_money"
    )
    assert int(summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode"] == (
        "per_dataset_verified_target_application"
    )
    assert int(
        summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count"]
    ) == 2
    assert int(
        summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications"]
    ) == 2
    assert summary.loc[0, "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage"] == 1.0
    assert bool(
        summary.loc[
            0,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistency_required",
        ]
    )
    assert bool(
        summary.loc[
            0,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        ]
    )
    assert bool(
        summary.loc[
            0,
            "scaleup_broker_vendor_market_data_batch_lineage_match_required",
        ]
    )
    assert bool(
        summary.loc[0, "scaleup_broker_vendor_market_data_batch_lineage_matches"]
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
    assert len(vendor["application_lineage_sha256"]) == 64
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64
    assert vendor["datasets"][1]["mapping_application_id"] == "mapping-app-day2"
    lineage = config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["required"]
    assert lineage["matches"]
    assert lineage["current_application_lineage_sha256"] == lineage[
        "broker_application_lineage_sha256"
    ]
    assert lineage["scaleup_carried_application_lineage_sha256"] == lineage[
        "broker_application_lineage_sha256"
    ]
    assert lineage["cutover_carried_application_lineage_sha256"] == lineage[
        "broker_application_lineage_sha256"
    ]
    final_lineage = config[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["readiness_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["scaleup_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]


def test_cli_cutover_gate_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(tmp_path)
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "adapter": "arrow_money",
                "dispatch_roundtrip": {
                    "provided": True,
                    "ready": True,
                    "target_mode": "live_dryrun",
                    "strategy": "lead_lag_taker",
                    "market": "india_nse_index_derivatives",
                    "broker_vendor_data_readiness": {
                        "provided": True,
                        "ready": False,
                        "failed_checks": 1,
                    },
                    "broker_dispatch_roundtrip_vendor_market_data_batch": (
                        vendor_market_data_batch_config()
                    ),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "cutover"

    code = main(
        [
            "review-cutover-gate",
            "--scaleup",
            str(scaleup),
            "--broker-readiness",
            str(broker),
            "--runtime-session",
            str(runtime),
            "--operator-review",
            str(review_path),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "cutover_summary.csv")
    checks = pd.read_csv(out_dir / "cutover_checks.csv")
    config = json.loads((out_dir / "cutover_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    vendor_readiness = config["scaleup_broker_vendor_data_readiness"]
    vendor_batch = config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "scaleup_broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "scaleup_broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "scaleup_broker_vendor_data_readiness_failed_checks"]) == 1
    assert {
        "scaleup_broker_vendor_data_readiness_ready",
        "scaleup_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert vendor_readiness == {
        "provided": True,
        "ready": False,
        "failed_checks": 1,
    }
    assert vendor_batch["ready"]
    assert vendor_batch["dataset_count"] == 2


def test_cli_cutover_gate_fails_without_operator_review(tmp_path):
    scaleup, broker, runtime, _review_path = write_inputs(tmp_path, operator=False)
    out_dir = tmp_path / "cutover"

    code = main(
        [
            "review-cutover-gate",
            "--scaleup",
            str(scaleup),
            "--broker-readiness",
            str(broker),
            "--runtime-session",
            str(runtime),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    assert code == 2
    summary = pd.read_csv(out_dir / "cutover_summary.csv")
    checks = pd.read_csv(out_dir / "cutover_checks.csv")
    queue = pd.read_csv(out_dir / "cutover_action_queue.csv")
    config = json.loads((out_dir / "cutover_config.json").read_text(encoding="utf-8"))
    assert not bool(summary.loc[0, "ready"])
    assert "operator_approved" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "action_queue_count"]) == 3
    assert int(summary.loc[0, "blocked_action_count"]) == 3
    assert summary.loc[0, "next_gate"] == "review-cutover-gate"
    assert queue.loc[0, "check"] == "operator_approved"
    assert queue.loc[0, "component"] == "operator_review"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli review-cutover-gate --help"
    assert config["primary_action"]["check"] == "operator_approved"
    assert len(config["blocked_actions"]) == 3


def test_cli_cutover_gate_can_fail_on_actions(tmp_path):
    scaleup, broker, runtime, _review_path = write_inputs(tmp_path, operator=False)
    out_dir = tmp_path / "cutover"

    code = main(
        [
            "review-cutover-gate",
            "--scaleup",
            str(scaleup),
            "--broker-readiness",
            str(broker),
            "--runtime-session",
            str(runtime),
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "cutover_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "action_queue_count"]) == 3
    assert summary.loc[0, "primary_action_status"] == "blocked"


def test_cli_cutover_gate_can_require_dispatch_roundtrip(tmp_path):
    scaleup, broker, runtime, review_path = write_inputs(tmp_path, target_mode="shadow", dispatch=False)
    out_dir = tmp_path / "cutover"

    code = main(
        [
            "review-cutover-gate",
            "--scaleup",
            str(scaleup),
            "--broker-readiness",
            str(broker),
            "--runtime-session",
            str(runtime),
            "--operator-review",
            str(review_path),
            "--out",
            str(out_dir),
            "--target-mode",
            "shadow",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "cutover_summary.csv")
    checks = pd.read_csv(out_dir / "cutover_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {"scaleup_dispatch_roundtrip_provided", "broker_dispatch_roundtrip_provided"} <= failed
