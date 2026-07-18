import hashlib
import json

import pandas as pd
import pytest

from hft_cli import main
from reports.broker_dispatch_roundtrip import (
    BrokerDispatchRoundTripThresholds,
    evaluate_broker_dispatch_roundtrip,
    write_broker_dispatch_roundtrip,
)
from reports.catalog import catalog_experiment_runs


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
        "scaleup_carried_application_lineage_sha256": lineage_sha256,
        "cutover_carried_application_lineage_sha256": lineage_sha256,
        "route_carried_application_lineage_sha256": lineage_sha256,
        "dispatch_carried_application_lineage_sha256": lineage_sha256,
        "send_carried_application_lineage_sha256": lineage_sha256,
        "ack_carried_application_lineage_sha256": lineage_sha256,
    }


def ack_final_target_application_lineage_comparison(vendor, **overrides):
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
        "scaleup_review_carried_application_lineage_sha256": lineage_sha256,
        "cutover_review_carried_application_lineage_sha256": lineage_sha256,
        "route_enable_review_carried_application_lineage_sha256": lineage_sha256,
        "dispatch_plan_review_carried_application_lineage_sha256": lineage_sha256,
        "send_packet_review_carried_application_lineage_sha256": lineage_sha256,
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def ack_complete_final_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
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
        "scaleup_review_carried_application_lineage_sha256": lineage_sha256,
        "cutover_review_carried_application_lineage_sha256": lineage_sha256,
        "route_enable_review_carried_application_lineage_sha256": lineage_sha256,
        "dispatch_plan_review_carried_application_lineage_sha256": lineage_sha256,
        "send_packet_review_carried_application_lineage_sha256": lineage_sha256,
        "ack_reconciliation_review_carried_application_lineage_sha256": lineage_sha256,
        "roundtrip_final_review_carried_application_lineage_sha256": lineage_sha256,
        "broker_readiness_review_carried_application_lineage_sha256": lineage_sha256,
        "scaleup_final_review_carried_application_lineage_sha256": lineage_sha256,
        "cutover_final_review_carried_application_lineage_sha256": lineage_sha256,
        "route_final_review_carried_application_lineage_sha256": lineage_sha256,
        "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
        "send_final_review_carried_application_lineage_sha256": lineage_sha256,
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def add_ack_complete_final_target_application_lineage(config, vendor, **overrides):
    config[
        "ack_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_complete_final_target_application_lineage_comparison(
        vendor,
        **overrides,
    )
    config[
        "ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_32_target_application_lineage_comparison(vendor)
    config[
        "ack_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_40_target_application_lineage_comparison(vendor)
    config[
        "ack_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_48_target_application_lineage_comparison(vendor)


def ack_view_32_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = ack_complete_final_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def ack_view_40_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = ack_view_32_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "ack_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def ack_view_48_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = ack_view_40_target_application_lineage_comparison(
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
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def path_tail(value):
    return str(value).replace("\\", "/")


def resume_route_proof(
    *,
    ready=True,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    route_ready_pairs=1,
    gap_pairs=0,
    ops_launch_controls_ready=True,
    ops_launch_control_failures="",
    safe_runs=1,
    breach_runs=0,
    concentration_ok_runs=1,
    concentration_breach_runs=0,
):
    return {
        "required": True,
        "provided": True,
        "ready": ready,
        "strategy": strategy,
        "market": market,
        "route_ready_pairs": route_ready_pairs,
        "gap_pairs": gap_pairs,
        "recommendation": (
            "eligible_for_live_dryrun_route_review" if ready else "complete_route_readiness_gaps"
        ),
        "ops_launch_controls_ready": ops_launch_controls_ready,
        "ops_launch_control_failures": ops_launch_control_failures,
        "ops_broker_roundtrip_portfolio_safe_runs": safe_runs,
        "ops_broker_roundtrip_portfolio_breach_runs": breach_runs,
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": concentration_ok_runs,
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": concentration_breach_runs,
    }


def dispatch_summary(
    ready=True,
    route_roundtrip_provided=True,
    route_roundtrip_ready=True,
    route_roundtrip_target_mode="live_dryrun",
    route_roundtrip_strategy="lead_lag_taker",
    route_roundtrip_market="india_nse_index_derivatives",
    route_roundtrip_scenario_key="trigger_ticks=2",
    route_roundtrip_batch_id="BDP-0",
    route_roundtrip_requests=2,
    route_roundtrip_acked_orders=2,
    route_roundtrip_missing_request_acks=0,
    route_roundtrip_rejected_orders=0,
    route_roundtrip_unmatched_acks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    route_ops_launch_controls_present=True,
    route_ops_launch_controls_blocked_pairs=0,
    route_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    broker_route_readiness_required=True,
    broker_route_readiness_provided=True,
    broker_route_readiness_ready=True,
    broker_route_readiness_strategy="lead_lag_taker",
    broker_route_readiness_market="india_nse_index_derivatives",
    broker_route_readiness_route_ready_pairs=1,
    broker_route_readiness_gap_pairs=0,
    broker_route_readiness_recommendation=None,
    broker_route_readiness_ops_launch_controls_ready=True,
    broker_route_readiness_ops_launch_control_failures="",
    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    dispatch_total_notional=1575.0,
    strategy_portfolio_required=False,
    strategy_portfolio_provided=False,
    strategy_portfolio_ready=False,
    strategy_portfolio_selected_strategy="lead_lag_taker",
    strategy_portfolio_selected_market="india_nse_index_derivatives",
    strategy_portfolio_selected_eligible=False,
    strategy_portfolio_selected_allocation_notional=0.0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
                "dispatch_state": "armed_dry_run" if ready else "disabled",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "dispatch_orders": 2,
                "dispatch_total_notional": dispatch_total_notional,
                "dispatch_batch_id": "BDP-1",
                "strategy_portfolio_required": strategy_portfolio_required,
                "strategy_portfolio_provided": strategy_portfolio_provided,
                "strategy_portfolio_ready": strategy_portfolio_ready,
                "strategy_portfolio_deployment_mode": "paper_shadow",
                "strategy_portfolio_allocation_mode": "readiness_weighted",
                "strategy_portfolio_capital_currency": "INR",
                "strategy_portfolio_selected_profile": "leadlag-live-dryrun",
                "strategy_portfolio_selected_strategy": strategy_portfolio_selected_strategy,
                "strategy_portfolio_selected_market": strategy_portfolio_selected_market,
                "strategy_portfolio_selected_eligible": strategy_portfolio_selected_eligible,
                "strategy_portfolio_selected_allocation_weight": 0.0012
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_selected_allocation_notional": strategy_portfolio_selected_allocation_notional,
                "strategy_portfolio_notional_cap_applied": bool(strategy_portfolio_selected_allocation_notional),
                "strategy_portfolio_min_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_min_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_max_strategy_weight": 0.60
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_max_market_weight": 0.90
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_allocated_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_allocated_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_top_strategy_by_weight": (
                    strategy_portfolio_selected_strategy
                    if strategy_portfolio_selected_allocation_notional
                    else ""
                ),
                "strategy_portfolio_top_market_by_weight": (
                    strategy_portfolio_selected_market if strategy_portfolio_selected_allocation_notional else ""
                ),
                "strategy_portfolio_max_strategy_allocation_weight": 0.45
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_max_market_allocation_weight": 0.80
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "pre_portfolio_max_notional_per_session": 25_000.0
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "dry_run_only": True,
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
                "route_readiness_ops_launch_controls_present": route_ops_launch_controls_present,
                "route_readiness_ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
                "route_broker_route_readiness_required": broker_route_readiness_required,
                "route_broker_route_readiness_provided": broker_route_readiness_provided,
                "route_broker_route_readiness_ready": broker_route_readiness_ready,
                "route_broker_route_readiness_strategy": broker_route_readiness_strategy,
                "route_broker_route_readiness_market": broker_route_readiness_market,
                "route_broker_route_readiness_route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "route_broker_route_readiness_gap_pairs": broker_route_readiness_gap_pairs,
                "route_broker_route_readiness_recommendation": broker_route_readiness_recommendation,
                "route_broker_route_readiness_ops_launch_controls_ready": (
                    broker_route_readiness_ops_launch_controls_ready
                ),
                "route_broker_route_readiness_ops_launch_control_failures": (
                    broker_route_readiness_ops_launch_control_failures
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "route_dispatch_roundtrip_required": True,
                "route_dispatch_roundtrip_provided": route_roundtrip_provided,
                "route_dispatch_roundtrip_ready": route_roundtrip_ready,
                "route_dispatch_roundtrip_target_mode": route_roundtrip_target_mode,
                "route_dispatch_roundtrip_strategy": route_roundtrip_strategy,
                "route_dispatch_roundtrip_market": route_roundtrip_market,
                "route_dispatch_roundtrip_scenario_key": route_roundtrip_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "route_dispatch_roundtrip_requests": route_roundtrip_requests,
                "route_dispatch_roundtrip_acked_orders": route_roundtrip_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_roundtrip_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_roundtrip_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_roundtrip_unmatched_acks,
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def dispatch_orders(route_roundtrip_batch_id="BDP-0"):
    return pd.DataFrame(
        [
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
        ]
    )


def send_summary(
    ready=True,
    strategy="lead_lag_taker",
    submission_enabled=False,
    route_roundtrip_provided=True,
    route_roundtrip_ready=True,
    route_roundtrip_target_mode="live_dryrun",
    route_roundtrip_strategy="lead_lag_taker",
    route_roundtrip_market="india_nse_index_derivatives",
    route_roundtrip_scenario_key="trigger_ticks=2",
    route_roundtrip_batch_id="BDP-0",
    route_roundtrip_requests=2,
    route_roundtrip_acked_orders=2,
    route_roundtrip_missing_request_acks=0,
    route_roundtrip_rejected_orders=0,
    route_roundtrip_unmatched_acks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    route_ops_launch_controls_present=True,
    route_ops_launch_controls_blocked_pairs=0,
    route_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    broker_route_readiness_required=True,
    broker_route_readiness_provided=True,
    broker_route_readiness_ready=True,
    broker_route_readiness_strategy="lead_lag_taker",
    broker_route_readiness_market="india_nse_index_derivatives",
    broker_route_readiness_route_ready_pairs=1,
    broker_route_readiness_gap_pairs=0,
    broker_route_readiness_recommendation=None,
    broker_route_readiness_ops_launch_controls_ready=True,
    broker_route_readiness_ops_launch_control_failures="",
    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    dispatch_total_notional=1575.0,
    strategy_portfolio_required=False,
    strategy_portfolio_provided=False,
    strategy_portfolio_ready=False,
    strategy_portfolio_selected_strategy="lead_lag_taker",
    strategy_portfolio_selected_market="india_nse_index_derivatives",
    strategy_portfolio_selected_eligible=False,
    strategy_portfolio_selected_allocation_notional=0.0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
                "request_state": "dry_run_send_packet_ready" if ready else "disabled",
                "target_mode": "live_dryrun",
                "strategy": strategy,
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "dispatch_batch_id": "BDP-1",
                "dispatch_orders": 2,
                "dispatch_total_notional": dispatch_total_notional,
                "strategy_portfolio_required": strategy_portfolio_required,
                "strategy_portfolio_provided": strategy_portfolio_provided,
                "strategy_portfolio_ready": strategy_portfolio_ready,
                "strategy_portfolio_deployment_mode": "paper_shadow",
                "strategy_portfolio_allocation_mode": "readiness_weighted",
                "strategy_portfolio_capital_currency": "INR",
                "strategy_portfolio_selected_profile": "leadlag-live-dryrun",
                "strategy_portfolio_selected_strategy": strategy_portfolio_selected_strategy,
                "strategy_portfolio_selected_market": strategy_portfolio_selected_market,
                "strategy_portfolio_selected_eligible": strategy_portfolio_selected_eligible,
                "strategy_portfolio_selected_allocation_weight": 0.0012
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_selected_allocation_notional": strategy_portfolio_selected_allocation_notional,
                "strategy_portfolio_notional_cap_applied": bool(strategy_portfolio_selected_allocation_notional),
                "strategy_portfolio_min_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_min_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_max_strategy_weight": 0.60
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_max_market_weight": 0.90
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_allocated_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_allocated_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_top_strategy_by_weight": (
                    strategy_portfolio_selected_strategy
                    if strategy_portfolio_selected_allocation_notional
                    else ""
                ),
                "strategy_portfolio_top_market_by_weight": (
                    strategy_portfolio_selected_market if strategy_portfolio_selected_allocation_notional else ""
                ),
                "strategy_portfolio_max_strategy_allocation_weight": 0.45
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_max_market_allocation_weight": 0.80
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "pre_portfolio_max_notional_per_session": 25_000.0
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "requests": 2,
                "dry_run_only": True,
                "submission_enabled": submission_enabled,
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
                "route_readiness_ops_launch_controls_present": route_ops_launch_controls_present,
                "route_readiness_ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
                "route_broker_route_readiness_required": broker_route_readiness_required,
                "route_broker_route_readiness_provided": broker_route_readiness_provided,
                "route_broker_route_readiness_ready": broker_route_readiness_ready,
                "route_broker_route_readiness_strategy": broker_route_readiness_strategy,
                "route_broker_route_readiness_market": broker_route_readiness_market,
                "route_broker_route_readiness_route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "route_broker_route_readiness_gap_pairs": broker_route_readiness_gap_pairs,
                "route_broker_route_readiness_recommendation": broker_route_readiness_recommendation,
                "route_broker_route_readiness_ops_launch_controls_ready": (
                    broker_route_readiness_ops_launch_controls_ready
                ),
                "route_broker_route_readiness_ops_launch_control_failures": (
                    broker_route_readiness_ops_launch_control_failures
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "route_dispatch_roundtrip_required": True,
                "route_dispatch_roundtrip_provided": route_roundtrip_provided,
                "route_dispatch_roundtrip_ready": route_roundtrip_ready,
                "route_dispatch_roundtrip_target_mode": route_roundtrip_target_mode,
                "route_dispatch_roundtrip_strategy": route_roundtrip_strategy,
                "route_dispatch_roundtrip_market": route_roundtrip_market,
                "route_dispatch_roundtrip_scenario_key": route_roundtrip_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "route_dispatch_roundtrip_requests": route_roundtrip_requests,
                "route_dispatch_roundtrip_acked_orders": route_roundtrip_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_roundtrip_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_roundtrip_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_roundtrip_unmatched_acks,
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def send_requests(submission_enabled=False, route_roundtrip_batch_id="BDP-0"):
    return pd.DataFrame(
        [
            {
                "request_id": "BDR-1",
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "submission_enabled": submission_enabled,
                "dry_run_only": True,
                "idempotency_key": "IDEMP-1",
                "request_payload_hash": "REQ-1",
                "payload_valid": True,
            },
            {
                "request_id": "BDR-2",
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "submission_enabled": False,
                "dry_run_only": True,
                "idempotency_key": "IDEMP-2",
                "request_payload_hash": "REQ-2",
                "payload_valid": True,
            },
        ]
    )


def ack_summary(
    passed=True,
    strategy="lead_lag_taker",
    acked_orders=2,
    missing=0,
    rejected=0,
    route_roundtrip_provided=True,
    route_roundtrip_ready=True,
    route_roundtrip_target_mode="live_dryrun",
    route_roundtrip_strategy="lead_lag_taker",
    route_roundtrip_market="india_nse_index_derivatives",
    route_roundtrip_scenario_key="trigger_ticks=2",
    route_roundtrip_batch_id="BDP-0",
    route_roundtrip_requests=2,
    route_roundtrip_acked_orders=2,
    route_roundtrip_missing_request_acks=0,
    route_roundtrip_rejected_orders=0,
    route_roundtrip_unmatched_acks=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    route_ops_launch_controls_present=True,
    route_ops_launch_controls_blocked_pairs=0,
    route_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    broker_route_readiness_required=True,
    broker_route_readiness_provided=True,
    broker_route_readiness_ready=True,
    broker_route_readiness_strategy="lead_lag_taker",
    broker_route_readiness_market="india_nse_index_derivatives",
    broker_route_readiness_route_ready_pairs=1,
    broker_route_readiness_gap_pairs=0,
    broker_route_readiness_recommendation=None,
    broker_route_readiness_ops_launch_controls_ready=True,
    broker_route_readiness_ops_launch_control_failures="",
    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    dispatch_total_notional=1575.0,
    strategy_portfolio_required=False,
    strategy_portfolio_provided=False,
    strategy_portfolio_ready=False,
    strategy_portfolio_selected_strategy="lead_lag_taker",
    strategy_portfolio_selected_market="india_nse_index_derivatives",
    strategy_portfolio_selected_eligible=False,
    strategy_portfolio_selected_allocation_notional=0.0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
                "passed": passed,
                "target_mode": "live_dryrun",
                "strategy": strategy,
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "dispatch_orders": 2,
                "dispatch_total_notional": dispatch_total_notional,
                "strategy_portfolio_required": strategy_portfolio_required,
                "strategy_portfolio_provided": strategy_portfolio_provided,
                "strategy_portfolio_ready": strategy_portfolio_ready,
                "strategy_portfolio_deployment_mode": "paper_shadow",
                "strategy_portfolio_allocation_mode": "readiness_weighted",
                "strategy_portfolio_capital_currency": "INR",
                "strategy_portfolio_selected_profile": "leadlag-live-dryrun",
                "strategy_portfolio_selected_strategy": strategy_portfolio_selected_strategy,
                "strategy_portfolio_selected_market": strategy_portfolio_selected_market,
                "strategy_portfolio_selected_eligible": strategy_portfolio_selected_eligible,
                "strategy_portfolio_selected_allocation_weight": 0.0012
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_selected_allocation_notional": strategy_portfolio_selected_allocation_notional,
                "strategy_portfolio_notional_cap_applied": bool(strategy_portfolio_selected_allocation_notional),
                "strategy_portfolio_min_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_min_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_max_strategy_weight": 0.60
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_max_market_weight": 0.90
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_allocated_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_allocated_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "strategy_portfolio_top_strategy_by_weight": (
                    strategy_portfolio_selected_strategy
                    if strategy_portfolio_selected_allocation_notional
                    else ""
                ),
                "strategy_portfolio_top_market_by_weight": (
                    strategy_portfolio_selected_market if strategy_portfolio_selected_allocation_notional else ""
                ),
                "strategy_portfolio_max_strategy_allocation_weight": 0.45
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "strategy_portfolio_max_market_allocation_weight": 0.80
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "pre_portfolio_max_notional_per_session": 25_000.0
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "acked_orders": acked_orders,
                "missing_acks": missing,
                "rejected_orders": rejected,
                "duplicate_ack_orders": 0,
                "unmatched_acks": 0,
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
                "route_readiness_ops_launch_controls_present": route_ops_launch_controls_present,
                "route_readiness_ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
                "route_broker_route_readiness_required": broker_route_readiness_required,
                "route_broker_route_readiness_provided": broker_route_readiness_provided,
                "route_broker_route_readiness_ready": broker_route_readiness_ready,
                "route_broker_route_readiness_strategy": broker_route_readiness_strategy,
                "route_broker_route_readiness_market": broker_route_readiness_market,
                "route_broker_route_readiness_route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "route_broker_route_readiness_gap_pairs": broker_route_readiness_gap_pairs,
                "route_broker_route_readiness_recommendation": broker_route_readiness_recommendation,
                "route_broker_route_readiness_ops_launch_controls_ready": (
                    broker_route_readiness_ops_launch_controls_ready
                ),
                "route_broker_route_readiness_ops_launch_control_failures": (
                    broker_route_readiness_ops_launch_control_failures
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "route_dispatch_roundtrip_required": True,
                "route_dispatch_roundtrip_provided": route_roundtrip_provided,
                "route_dispatch_roundtrip_ready": route_roundtrip_ready,
                "route_dispatch_roundtrip_target_mode": route_roundtrip_target_mode,
                "route_dispatch_roundtrip_strategy": route_roundtrip_strategy,
                "route_dispatch_roundtrip_market": route_roundtrip_market,
                "route_dispatch_roundtrip_scenario_key": route_roundtrip_scenario_key,
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "route_dispatch_roundtrip_requests": route_roundtrip_requests,
                "route_dispatch_roundtrip_acked_orders": route_roundtrip_acked_orders,
                "route_dispatch_roundtrip_missing_request_acks": route_roundtrip_missing_request_acks,
                "route_dispatch_roundtrip_rejected_orders": route_roundtrip_rejected_orders,
                "route_dispatch_roundtrip_unmatched_acks": route_roundtrip_unmatched_acks,
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "ack_rate": acked_orders / 2,
                "failed_checks": 0 if passed else 1,
            }
        ]
    )


def acknowledgements(
    missing_second=False,
    rejected_second=False,
    route_roundtrip_batch_id="BDP-0",
    ack_route_roundtrip_batch_ids=None,
):
    raw_route_batch_ids = (
        route_roundtrip_batch_id
        if ack_route_roundtrip_batch_ids is None
        else ack_route_roundtrip_batch_ids
    )
    return pd.DataFrame(
        [
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "dispatch_order_route_roundtrip_batch_id": route_roundtrip_batch_id,
                "ack_route_dispatch_roundtrip_batch_ids": raw_route_batch_ids,
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "ack_count": 1,
                "ack_status": "accepted",
                "broker_order_id": "BRK-1",
                "acked": True,
                "rejected": False,
                "duplicate_ack": False,
                "missing_ack": False,
            },
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "dispatch_order_route_roundtrip_batch_id": route_roundtrip_batch_id,
                "ack_route_dispatch_roundtrip_batch_ids": raw_route_batch_ids,
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "ack_count": 0 if missing_second else 1,
                "ack_status": "rejected" if rejected_second else ("" if missing_second else "accepted"),
                "broker_order_id": "" if missing_second else "BRK-2",
                "acked": not missing_second and not rejected_second,
                "rejected": rejected_second,
                "duplicate_ack": False,
                "missing_ack": missing_second,
            },
        ]
    )


def route_enable_config(
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    route_ops_launch_controls_present=True,
    route_ops_launch_controls_blocked_pairs=0,
    route_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    broker_route_readiness_required=True,
    broker_route_readiness_provided=True,
    broker_route_readiness_ready=True,
    broker_route_readiness_strategy="lead_lag_taker",
    broker_route_readiness_market="india_nse_index_derivatives",
    broker_route_readiness_route_ready_pairs=1,
    broker_route_readiness_gap_pairs=0,
    broker_route_readiness_recommendation=None,
    broker_route_readiness_ops_launch_controls_ready=True,
    broker_route_readiness_ops_launch_control_failures="",
    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    dispatch_total_notional=1575.0,
    strategy_portfolio_required=False,
    strategy_portfolio_provided=False,
    strategy_portfolio_ready=False,
    strategy_portfolio_selected_strategy="lead_lag_taker",
    strategy_portfolio_selected_market="india_nse_index_derivatives",
    strategy_portfolio_selected_eligible=False,
    strategy_portfolio_selected_allocation_notional=0.0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
    )
    broker_route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if broker_route_readiness_recommendation is None and broker_route_readiness_ready
        else "complete_route_readiness_gaps"
        if broker_route_readiness_recommendation is None
        else broker_route_readiness_recommendation
    )
    return {
        "broker_readiness": {
            "adapter_schema_status": broker_schema_status,
            "schema_reviewed": broker_schema_reviewed,
            "schema_review_mode": broker_schema_review_mode,
        },
        "route_readiness": {
            "required": route_readiness_required,
            "provided": route_readiness_provided,
            "ready": route_readiness_ready,
            "strategy": route_readiness_strategy,
            "market": route_readiness_market,
            "route_ready_pairs": route_readiness_route_ready_pairs,
            "gap_pairs": route_readiness_gap_pairs,
            "ops_launch_controls_present": route_ops_launch_controls_present,
            "ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
            "ops_broker_roundtrip_portfolio_breach_pairs": (
                route_ops_broker_roundtrip_portfolio_breach_pairs
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
            ),
            "recommendation": route_readiness_recommendation,
        },
        "route_broker_route_readiness": {
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
        "route_enable_dispatch_roundtrip": {
            "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
        },
        "strategy_portfolio": {
            "required": strategy_portfolio_required,
            "provided": strategy_portfolio_provided,
            "ready": strategy_portfolio_ready,
            "deployment_mode": "paper_shadow",
            "allocation_mode": "readiness_weighted",
            "capital_currency": "INR",
            "selected_profile": "leadlag-live-dryrun",
            "selected_strategy": strategy_portfolio_selected_strategy,
            "selected_market": strategy_portfolio_selected_market,
            "selected_eligible": strategy_portfolio_selected_eligible,
            "selected_allocation_weight": 0.0012
            if strategy_portfolio_selected_allocation_notional
            else 0.0,
            "selected_allocation_notional": strategy_portfolio_selected_allocation_notional,
            "notional_cap_applied": bool(strategy_portfolio_selected_allocation_notional),
            "min_strategy_count": 2 if strategy_portfolio_selected_allocation_notional else 0,
            "min_market_count": 1 if strategy_portfolio_selected_allocation_notional else 0,
            "max_strategy_weight": 0.60 if strategy_portfolio_selected_allocation_notional else 0.0,
            "max_market_weight": 0.90 if strategy_portfolio_selected_allocation_notional else 0.0,
            "allocated_strategy_count": 2 if strategy_portfolio_selected_allocation_notional else 0,
            "allocated_market_count": 1 if strategy_portfolio_selected_allocation_notional else 0,
            "top_strategy_by_weight": (
                strategy_portfolio_selected_strategy if strategy_portfolio_selected_allocation_notional else ""
            ),
            "top_market_by_weight": (
                strategy_portfolio_selected_market if strategy_portfolio_selected_allocation_notional else ""
            ),
            "max_strategy_allocation_weight": 0.45
            if strategy_portfolio_selected_allocation_notional
            else 0.0,
            "max_market_allocation_weight": 0.80
            if strategy_portfolio_selected_allocation_notional
            else 0.0,
            "pre_portfolio_max_notional_per_session": 25_000.0
            if strategy_portfolio_selected_allocation_notional
            else 0.0,
        },
        "upload": {
            "orders": 2,
            "total_notional": dispatch_total_notional,
            "output_file": "broker_upload_orders.csv",
        },
    }


def shadow_broker_config(
    sessions=2,
    ready_sessions=2,
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
    broker_vendor_data_readiness_sessions=2,
    broker_vendor_data_readiness_provided_sessions=2,
    broker_vendor_data_readiness_ready_sessions=2,
    broker_vendor_data_readiness_failed_checks=0,
):
    return {
        "sessions": sessions,
        "ready_sessions": ready_sessions,
        "adapter": adapter,
        "adapter_count": adapter_count,
        "broker_vendor_data_readiness": {
            "sessions": broker_vendor_data_readiness_sessions,
            "provided_sessions": broker_vendor_data_readiness_provided_sessions,
            "ready_sessions": broker_vendor_data_readiness_ready_sessions,
            "failed_checks": broker_vendor_data_readiness_failed_checks,
        },
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


def vendor_market_data_batch_config(*, manifest_run_type="vendor_market_data_batch_pipeline"):
    return {
        "provided": True,
        "ready": True,
        "adapter": "arrow_money",
        "kind": "ticks",
        "manifest_run_type": manifest_run_type,
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
        "comparison": {
            "accepted": True,
            "failed_checks": 0,
        },
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


def target_application_vendor_market_data_batch_config(**overrides):
    vendor = vendor_market_data_batch_config()
    vendor.update(
        {
            "mapping_sources": "verified_target_application",
            "mapping_source_mode": "per_dataset_verified_target_application",
            "mapping_application_count": 2,
            "unique_mapping_applications": 2,
            "target_application_coverage": 1.0,
            "datasets": [
                {
                    "dataset": "nifty_day1",
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
                    "dataset": "nifty_day2",
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
        }
    )
    vendor.update(overrides)
    vendor.setdefault("application_lineage_consistency_required", True)
    vendor.setdefault("application_lineage_consistent", True)
    vendor.setdefault(
        "application_lineage_sha256",
        target_application_lineage_sha256(vendor["datasets"]),
    )
    return vendor


def with_broker_vendor_batch_summary(summary, vendor, *, prefix):
    result = summary.copy()
    for key, value in vendor.items():
        if key == "comparison":
            result.loc[0, f"{prefix}_comparison_accepted"] = value["accepted"]
            result.loc[0, f"{prefix}_comparison_failed_checks"] = value["failed_checks"]
        elif key == "datasets":
            result.loc[0, f"{prefix}_datasets_json"] = json.dumps(value, sort_keys=True)
        else:
            result.loc[0, f"{prefix}_{key}"] = value
    if (
        prefix == "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
        and vendor.get("mapping_source_mode") == "per_dataset_verified_target_application"
    ):
        lineage = target_application_lineage_comparison(vendor)
        final_lineage = ack_final_target_application_lineage_comparison(vendor)
        complete_final_lineage = (
            ack_complete_final_target_application_lineage_comparison(vendor)
        )
        extended_complete_final_lineage = (
            ack_view_32_target_application_lineage_comparison(vendor)
        )
        latest_extended_complete_final_lineage_40 = (
            ack_view_40_target_application_lineage_comparison(vendor)
        )
        final_prefix = "send_broker_dispatch_roundtrip_vendor_market_data_batch"
        complete_final_prefix = (
            "send_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_prefix = (
            "send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        latest_extended_complete_final_40_prefix = (
            "send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            "ack_broker_vendor_market_data_batch_lineage_match_required",
        ] = lineage["required"]
        result.loc[
            0,
            "ack_broker_vendor_market_data_batch_lineage_matches",
        ] = lineage["matches"]
        result.loc[
            0,
            "ack_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["current_application_lineage_sha256"]
        result.loc[
            0,
            "ack_broker_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["broker_application_lineage_sha256"]
        for stage in ("scaleup", "cutover", "route", "dispatch", "send"):
            result.loc[
                0,
                f"{stage}_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ] = lineage[f"{stage}_carried_application_lineage_sha256"]
        result.loc[
            0,
            "ack_carried_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["ack_carried_application_lineage_sha256"]
        result.loc[0, f"{final_prefix}_lineage_match_required"] = final_lineage[
            "required"
        ]
        result.loc[0, f"{final_prefix}_lineage_matches"] = final_lineage["matches"]
        for field, value in final_lineage.items():
            if field not in {"required", "matches", "carried_application_lineage_sha256"}:
                result.loc[0, f"{final_prefix}_{field}"] = value
        result.loc[0, f"{complete_final_prefix}_lineage_match_required"] = (
            complete_final_lineage["required"]
        )
        result.loc[0, f"{complete_final_prefix}_lineage_matches"] = (
            complete_final_lineage["matches"]
        )
        for field, value in complete_final_lineage.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{complete_final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{extended_complete_final_prefix}_lineage_match_required",
        ] = extended_complete_final_lineage["required"]
        result.loc[
            0,
            f"{extended_complete_final_prefix}_lineage_matches",
        ] = extended_complete_final_lineage["matches"]
        for field, value in extended_complete_final_lineage.items():
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{extended_complete_final_prefix}_ack_extended_complete_final_review_carried_application_lineage_sha256",
                ] = value
            elif field not in {"required", "matches"}:
                result.loc[0, f"{extended_complete_final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{latest_extended_complete_final_40_prefix}_lineage_match_required",
        ] = latest_extended_complete_final_lineage_40["required"]
        result.loc[
            0,
            f"{latest_extended_complete_final_40_prefix}_lineage_matches",
        ] = latest_extended_complete_final_lineage_40["matches"]
        for field, value in latest_extended_complete_final_lineage_40.items():
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{latest_extended_complete_final_40_prefix}_ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
                ] = value
            elif field not in {"required", "matches"}:
                result.loc[
                    0,
                    f"{latest_extended_complete_final_40_prefix}_{field}",
                ] = value
    return result


def dirty_vendor_market_data_batch_config():
    vendor = vendor_market_data_batch_config()
    vendor.update(
        {
            "ready": False,
            "adapter": "irage",
            "market": "us_options_regular",
            "dataset_count": 3,
            "failed_datasets": 1,
            "source_file_fingerprint_coverage": 0.0,
            "min_mapping_coverage": 0.0,
            "unique_mapping_drafts": 0,
        }
    )
    vendor["comparison"] = {
        "accepted": False,
        "failed_checks": 2,
    }
    return vendor


def broker_vendor_data_readiness_config(*, provided=True, ready=True, failed_checks=0):
    return {
        "provided": provided,
        "ready": ready,
        "failed_checks": failed_checks,
    }


def write_inputs(tmp_path, *, missing_ack=False, route_readiness=True):
    dispatch = tmp_path / "dispatch"
    send = tmp_path / "send"
    ack = tmp_path / "ack"
    dispatch.mkdir()
    send.mkdir()
    ack.mkdir()
    dispatch_summary(
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    dispatch_orders().to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(
            route_enable_config(
                route_readiness_provided=route_readiness,
                route_readiness_ready=route_readiness,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (dispatch / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "broker_dispatch_plan",
                "inputs": {"route_enable_manifest": {"path": "route.json"}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    send_summary(
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(send / "broker_dispatch_send_summary.csv", index=False)
    send_requests().to_csv(send / "broker_dispatch_send_requests.csv", index=False)
    (send / "broker_dispatch_send_config.json").write_text(
        json.dumps(
            route_enable_config(
                route_readiness_provided=route_readiness,
                route_readiness_ready=route_readiness,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (send / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "broker_dispatch_send_packet",
                "inputs": {"dispatch_manifest": {"path": "dispatch.json"}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ack_summary(
        passed=not missing_ack,
        acked_orders=1 if missing_ack else 2,
        missing=1 if missing_ack else 0,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(
        ack / "broker_dispatch_ack_summary.csv",
        index=False,
    )
    acknowledgements(missing_second=missing_ack).to_csv(ack / "broker_dispatch_acknowledgements.csv", index=False)
    (ack / "broker_dispatch_ack_config.json").write_text(
        json.dumps(
            route_enable_config(
                route_readiness_provided=route_readiness,
                route_readiness_ready=route_readiness,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (ack / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "broker_dispatch_ack_reconciliation",
                "inputs": {"dispatch_manifest": {"path": "dispatch.json"}},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return dispatch, send, ack


def test_broker_dispatch_roundtrip_passes_complete_dry_run_evidence():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert summary["recommendation"] == "broker_dry_run_roundtrip_proved"
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert int(summary["action_queue_count"]) == 0
    assert int(summary["blocked_action_count"]) == 0
    assert summary["next_gate"] == ""
    assert report.config["action_queue_count"] == 0
    assert report.config["blocked_action_count"] == 0
    assert report.config["next_gate"] == ""
    assert report.config["next_gate_help_command"] == ""
    assert report.config["primary_action"] == {}
    assert report.config["next_actions"] == []
    assert report.orders["request_id"].tolist() == ["BDR-1", "BDR-2"]
    assert report.orders["acked"].tolist() == [True, True]
    assert report.orders["dispatch_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["request_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["ack_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["ack_raw_route_roundtrip_batch_ids"].tolist() == ["BDP-0", "BDP-0"]
    assert int(report.summary.iloc[0]["missing_request_acks"]) == 0
    assert bool(report.summary.iloc[0]["route_dispatch_roundtrip_ready"])
    assert report.summary.iloc[0]["broker_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(report.summary.iloc[0]["broker_schema_reviewed"])
    assert report.summary.iloc[0]["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["broker_readiness"]["schema_reviewed"]
    assert report.config["broker_readiness"]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["route_dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 0
    assert bool(report.summary.iloc[0]["route_readiness_required"])
    assert bool(report.summary.iloc[0]["route_readiness_ready"])
    assert report.summary.iloc[0]["route_readiness_strategy"] == "lead_lag_taker"
    assert report.config["route_readiness"]["required"]
    assert report.config["route_readiness"]["market"] == "india_nse_index_derivatives"
    assert bool(report.summary.iloc[0]["route_readiness_ops_launch_controls_present"])
    assert int(report.summary.iloc[0]["route_readiness_ops_launch_controls_blocked_pairs"]) == 0
    assert int(report.summary.iloc[0]["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) == 0
    assert report.config["route_readiness"]["ops_launch_controls_present"]
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_concentration_breach_pairs"] == 0
    assert bool(report.summary.iloc[0]["route_broker_route_readiness_ready"])
    assert report.summary.iloc[0]["route_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(report.summary.iloc[0]["route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    assert report.config["route_broker_route_readiness"]["ops_launch_controls_ready"]
    assert report.config["route_broker_route_readiness"]["ops_broker_roundtrip_portfolio_concentration_ok_runs"] == 1


def test_broker_dispatch_roundtrip_fails_closed_without_required_ack_lineage():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        thresholds=BrokerDispatchRoundTripThresholds(
            require_ack_lineage=True
        ),
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool), "check"
        ]
    )
    assert not report.passed
    assert {
        "broker_dispatch_ack_lineage_provided",
        "broker_dispatch_ack_manifest_current",
        "broker_dispatch_ack_lineage_contract_consistent",
        "broker_dispatch_ack_non_authorizing",
        "broker_dispatch_ack_send_lineage_gate_passed",
        "broker_dispatch_ack_send_matches_current",
        "broker_dispatch_ack_expected_send_matches_current",
        "broker_dispatch_ack_lineage_gate_passed",
    } <= failed
    assert set(report.action_queue["component"]) == {
        "broker_dispatch_ack"
    }
    assert set(report.action_queue["next_gate"]) == {
        "reconcile-broker-dispatch"
    }


def test_broker_dispatch_roundtrip_carries_route_broker_resume_gate():
    config = route_enable_config()
    config["route_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(),
        "incident_broker_route_readiness": resume_route_proof(route_ready_pairs=2),
    }

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    resume_gate = report.config["route_broker_resume_gate"]
    assert bool(summary["route_broker_resume_broker_route_readiness_ready"])
    assert summary["route_broker_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["route_broker_resume_incident_broker_route_readiness_route_ready_pairs"]) == 2
    assert resume_gate["broker_route_readiness"]["ready"]
    assert resume_gate["broker_route_readiness"]["ops_launch_controls_ready"]
    assert resume_gate["incident_broker_route_readiness"]["route_ready_pairs"] == 2


def test_broker_dispatch_roundtrip_blocks_bad_route_broker_resume_gate():
    config = route_enable_config()
    config["route_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(
            ready=False,
            strategy="surface_mm",
            market="us_options_regular",
            route_ready_pairs=0,
            gap_pairs=2,
            ops_launch_controls_ready=False,
            ops_launch_control_failures="resume route proof stale after halt",
            safe_runs=0,
            breach_runs=1,
            concentration_ok_runs=0,
            concentration_breach_runs=1,
        ),
    }

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_resume_broker_route_readiness_ready",
        "route_broker_resume_broker_route_readiness_identity_match",
        "route_broker_resume_broker_route_readiness_route_ready_pairs",
        "route_broker_resume_broker_route_readiness_gap_pairs",
        "route_broker_resume_broker_route_readiness_ops_launch_controls_ready",
        "route_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "route_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "route_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "route_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert summary["route_broker_resume_broker_route_readiness_market"] == "us_options_regular"
    assert report.config["route_broker_resume_gate"]["broker_route_readiness"]["gap_pairs"] == 2
    assert report.config["next_gate"] == "review-resume-gate"
    assert report.action_queue is not None
    assert report.action_queue.iloc[0]["component"] == "resume_gate"


def test_broker_dispatch_roundtrip_carries_strategy_portfolio_allocation():
    config = route_enable_config(
        strategy_portfolio_required=True,
        strategy_portfolio_provided=True,
        strategy_portfolio_ready=True,
        strategy_portfolio_selected_eligible=True,
        strategy_portfolio_selected_allocation_notional=2_000.0,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    portfolio = report.config["strategy_portfolio"]
    assert summary["dispatch_total_notional"] == 1_575.0
    assert bool(summary["strategy_portfolio_required"])
    assert bool(summary["strategy_portfolio_provided"])
    assert bool(summary["strategy_portfolio_ready"])
    assert summary["strategy_portfolio_deployment_mode"] == "paper_shadow"
    assert summary["strategy_portfolio_allocation_mode"] == "readiness_weighted"
    assert summary["strategy_portfolio_capital_currency"] == "INR"
    assert summary["strategy_portfolio_selected_profile"] == "leadlag-live-dryrun"
    assert summary["strategy_portfolio_selected_strategy"] == "lead_lag_taker"
    assert summary["strategy_portfolio_selected_market"] == "india_nse_index_derivatives"
    assert bool(summary["strategy_portfolio_selected_eligible"])
    assert summary["strategy_portfolio_selected_allocation_weight"] == 0.0012
    assert summary["strategy_portfolio_selected_allocation_notional"] == 2_000.0
    assert bool(summary["strategy_portfolio_notional_cap_applied"])
    assert summary["strategy_portfolio_min_strategy_count"] == 2
    assert summary["strategy_portfolio_min_market_count"] == 1
    assert summary["strategy_portfolio_max_strategy_weight"] == 0.60
    assert summary["strategy_portfolio_max_market_weight"] == 0.90
    assert summary["strategy_portfolio_allocated_strategy_count"] == 2
    assert summary["strategy_portfolio_allocated_market_count"] == 1
    assert summary["strategy_portfolio_top_strategy_by_weight"] == "lead_lag_taker"
    assert summary["strategy_portfolio_top_market_by_weight"] == "india_nse_index_derivatives"
    assert summary["strategy_portfolio_max_strategy_allocation_weight"] == 0.45
    assert summary["strategy_portfolio_max_market_allocation_weight"] == 0.80
    assert summary["pre_portfolio_max_notional_per_session"] == 25_000.0
    assert report.config["dispatch_total_notional"] == 1_575.0
    assert portfolio["required"]
    assert portfolio["provided"]
    assert portfolio["ready"]
    assert portfolio["selected_allocation_notional"] == 2_000.0
    assert portfolio["min_strategy_count"] == 2
    assert portfolio["allocated_strategy_count"] == 2
    assert portfolio["top_strategy_by_weight"] == "lead_lag_taker"
    assert portfolio["max_strategy_allocation_weight"] == 0.45


def test_broker_dispatch_roundtrip_blocks_dispatch_above_strategy_portfolio_allocation():
    config = route_enable_config(
        strategy_portfolio_required=True,
        strategy_portfolio_provided=True,
        strategy_portfolio_ready=True,
        strategy_portfolio_selected_eligible=True,
        strategy_portfolio_selected_allocation_notional=1_200.0,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_notional_within_strategy_portfolio_allocation" in failed
    assert report.config["primary_blocker"]["check"] == "dispatch_notional_within_strategy_portfolio_allocation"
    assert report.config["dispatch_total_notional"] == 1_575.0


def test_broker_dispatch_roundtrip_blocks_strategy_portfolio_market_mismatch():
    config = route_enable_config(
        strategy_portfolio_required=True,
        strategy_portfolio_provided=True,
        strategy_portfolio_ready=True,
        strategy_portfolio_selected_eligible=True,
        strategy_portfolio_selected_allocation_notional=2_000.0,
    )
    bad_send_config = route_enable_config(
        strategy_portfolio_required=True,
        strategy_portfolio_provided=True,
        strategy_portfolio_ready=True,
        strategy_portfolio_selected_market="us_options_regular",
        strategy_portfolio_selected_eligible=True,
        strategy_portfolio_selected_allocation_notional=2_000.0,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=bad_send_config,
        ack_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "strategy_portfolio_market_matches" in failed
    assert report.config["primary_blocker"]["check"] == "strategy_portfolio_market_matches"


def test_broker_dispatch_roundtrip_carries_shadow_broker_readiness():
    config = route_enable_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert bool(summary["shadow_broker_readiness_provided"])
    assert int(summary["shadow_broker_readiness_sessions"]) == 2
    assert int(summary["shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["shadow_broker_adapter"] == "arrow_money"
    assert summary["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["shadow_broker_readiness"]["provided"]
    assert report.config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_roundtrip_blocks_dirty_shadow_broker_readiness():
    clean_config = route_enable_config()
    clean_config["shadow_broker_readiness"] = shadow_broker_config()
    bad_config = route_enable_config()
    bad_config["shadow_broker_readiness"] = shadow_broker_config(
        ready_sessions=1,
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
        broker_vendor_data_readiness_ready_sessions=1,
        broker_vendor_data_readiness_failed_checks=1,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=clean_config,
        send_config=clean_config,
        ack_config=bad_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_broker_readiness_ready",
        "shadow_broker_vendor_data_readiness_ready",
        "shadow_broker_vendor_data_readiness_failed_checks",
        "shadow_broker_adapter_match",
        "shadow_broker_adapter_consistent",
        "shadow_broker_route_readiness_ready",
        "shadow_broker_route_readiness_identity_match",
        "shadow_broker_route_readiness_gap_pairs",
        "shadow_broker_dispatch_roundtrip_ready",
        "shadow_broker_dispatch_roundtrip_identity_match",
        "shadow_broker_dispatch_roundtrip_scenario_consistent",
        "shadow_broker_dispatch_roundtrip_missing_request_acks",
        "shadow_broker_dispatch_roundtrip_rejected_orders",
        "shadow_broker_dispatch_roundtrip_unmatched_acks",
        "shadow_broker_route_dispatch_roundtrip_ready",
        "shadow_broker_route_dispatch_roundtrip_identity_match",
        "shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.summary.iloc[0]["shadow_broker_adapter"] == "arrow_money"
    assert int(report.summary.iloc[0]["shadow_broker_vendor_data_readiness_failed_checks"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_roundtrip_blocks_partial_shadow_broker_vendor_data_readiness():
    config = route_enable_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        broker_vendor_data_readiness_sessions=1,
        broker_vendor_data_readiness_provided_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "shadow_broker_vendor_data_readiness_provided",
        "shadow_broker_vendor_data_readiness_ready",
    } <= failed
    assert int(report.summary.iloc[0]["shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["provided_sessions"] == 1


def test_broker_dispatch_roundtrip_carries_broker_shadow_broker_readiness():
    config = route_enable_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert bool(summary["broker_shadow_broker_readiness_provided"])
    assert int(summary["broker_shadow_broker_readiness_sessions"]) == 2
    assert int(summary["broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["broker_shadow_broker_readiness"]["provided"]
    assert report.config["broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert report.config["broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_roundtrip_carries_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_vendor_market_data_batch"] = vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_vendor_market_data_batch"]
    assert report.passed
    assert summary["roundtrip_vendor_market_data_batch_provided"]
    assert summary["roundtrip_vendor_market_data_batch_ready"]
    assert summary["roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["roundtrip_vendor_market_data_batch_manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert int(summary["roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["roundtrip_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor_config["provided"]
    assert vendor_config["ready"]
    assert vendor_config["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor_config["source_file_fingerprint_coverage"] == 1.0
    assert vendor_config["min_mapping_coverage"] == 1.0
    assert vendor_config["unique_mapping_drafts"] == 1
    assert vendor_config["comparison"]["accepted"]
    assert len(vendor_config["datasets"]) == 2
    assert vendor_config["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_dispatch_roundtrip_carries_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.passed
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
        "vendor_intake_draft"
    )
    assert vendor_config["provided"]
    assert vendor_config["ready"]
    assert vendor_config["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor_config["source_file_fingerprint_coverage"] == 1.0
    assert vendor_config["min_mapping_coverage"] == 1.0
    assert vendor_config["unique_mapping_drafts"] == 1
    assert vendor_config["comparison"]["accepted"]
    assert len(vendor_config["datasets"]) == 2
    assert vendor_config["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_dispatch_roundtrip_carries_target_application_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert report.passed
    prefix = "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert bool(summary[f"{prefix}_application_lineage_consistency_required"])
    assert bool(summary[f"{prefix}_application_lineage_consistent"])
    summary_datasets = json.loads(summary[f"{prefix}_datasets_json"])
    assert summary_datasets[0]["mapping_application_id"] == "mapping-app-day1"
    assert summary_datasets[1]["applied_mapping_sha256"] == "3" * 64
    carried = report.config[prefix]
    assert carried["mapping_source_mode"] == "per_dataset_verified_target_application"
    assert carried["mapping_application_count"] == 2
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["application_lineage_consistency_required"]
    assert carried["application_lineage_consistent"]
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    assert carried["application_lineage_sha256"] == lineage_sha256
    assert carried["datasets"][1]["target_intake_receipt_id"] == "target-intake-day2"
    lineage = report.config[f"{prefix}_lineage_comparison"]
    assert lineage == {
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
    }
    final_lineage = report.config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
        "cutover_review_carried_application_lineage_sha256",
        "route_enable_review_carried_application_lineage_sha256",
        "dispatch_plan_review_carried_application_lineage_sha256",
        "send_packet_review_carried_application_lineage_sha256",
        "ack_reconciliation_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == lineage_sha256
    complete_prefix = (
        "ack_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert summary[f"{complete_prefix}_lineage_match_required"]
    assert summary[f"{complete_prefix}_lineage_matches"]
    complete_fields = (
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
    )
    for field in complete_fields:
        assert summary[f"{complete_prefix}_{field}"] == lineage_sha256
    complete_final_lineage = report.config[
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert complete_final_lineage["required"]
    assert complete_final_lineage["matches"]
    for field in (*complete_fields, "carried_application_lineage_sha256"):
        assert complete_final_lineage[field] == lineage_sha256
    extended_prefix = (
        "ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    extended_review_fields = (
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
        "send_complete_final_review_carried_application_lineage_sha256",
        "ack_extended_complete_final_review_carried_application_lineage_sha256",
    )
    assert summary[f"{extended_prefix}_lineage_match_required"]
    assert summary[f"{extended_prefix}_lineage_matches"]
    for field in (*complete_fields, *extended_review_fields):
        assert summary[f"{extended_prefix}_{field}"] == lineage_sha256
    assert (
        summary[
            f"{extended_prefix}_roundtrip_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    extended_complete_final_lineage = report.config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert extended_complete_final_lineage["required"]
    assert extended_complete_final_lineage["matches"]
    for field in (
        *complete_fields,
        *extended_review_fields,
        "carried_application_lineage_sha256",
    ):
        assert extended_complete_final_lineage[field] == lineage_sha256
    ack_latest_40_prefix = (
        "ack_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    ack_view_40 = ack_view_40_target_application_lineage_comparison(vendor)
    for field, expected in ack_view_40.items():
        if field in {"required", "matches"}:
            continue
        summary_field = (
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256"
            if field == "carried_application_lineage_sha256"
            else field
        )
        assert summary[f"{ack_latest_40_prefix}_{summary_field}"] == expected
    assert (
        summary[
            f"{ack_latest_40_prefix}_roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    roundtrip_view_41 = report.config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert roundtrip_view_41["required"]
    assert roundtrip_view_41["matches"]
    for field, expected in ack_view_40.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
        }:
            continue
        assert roundtrip_view_41[field] == expected
    assert roundtrip_view_41[
        "ack_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert (
        roundtrip_view_41["carried_application_lineage_sha256"]
        == lineage_sha256
    )
    complete_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final"
    )
    expected_checks = {
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        "broker_dispatch_roundtrip_vendor_market_data_batch_retained_lineage_consistency_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_retained_application_lineage_consistent",
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_scaleup_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_cutover_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_route_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_send_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_ack_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_broker_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_application_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_prior_scaleup_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_prior_cutover_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_route_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_dispatch_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_send_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_ack_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_roundtrip_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_scaleup_review_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_cutover_review_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_route_enable_review_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_dispatch_plan_review_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_send_packet_review_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_lineage_match_required",
        f"{complete_check_prefix}_lineage_matches",
        f"{complete_check_prefix}_source_lineage_sha256_matches",
        f"{complete_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{complete_check_prefix}_compatibility_ack_review_lineage_sha256_matches",
        f"{complete_check_prefix}_prior_scaleup_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_prior_cutover_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_route_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_dispatch_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_send_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_ack_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_roundtrip_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_readiness_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_scaleup_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_cutover_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_route_enable_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_send_packet_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_ack_reconciliation_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_broker_readiness_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_scaleup_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_cutover_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_route_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_dispatch_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_send_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_ack_complete_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_roundtrip_complete_final_review_carried_lineage_sha256_matches",
    }
    extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_ack_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{extended_check_prefix}_lineage_match_required",
            f"{extended_check_prefix}_lineage_matches",
            f"{extended_check_prefix}_source_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_ack_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    extended_carried_stages = (
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
    )
    expected_checks.update(
        f"{extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        for stage in extended_carried_stages
    )
    expected_checks.update(
        f"{extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        for stage in (
            "scaleup_complete_final_review",
            "cutover_complete_final_review",
            "route_complete_final_review",
            "dispatch_complete_final_review",
            "send_complete_final_review",
            "ack_extended_complete_final_review",
            "roundtrip_extended_complete_final_review",
        )
    )
    view_40_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "ack_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{view_40_check_prefix}_lineage_match_required",
            f"{view_40_check_prefix}_lineage_matches",
            f"{view_40_check_prefix}_source_lineage_sha256_matches",
            f"{view_40_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_40_check_prefix}_compatibility_ack_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_route_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_send_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_ack_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_40_check_prefix}_roundtrip_latest_extended_complete_final_review_carried_lineage_sha256_matches",
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
        expected_checks.add(
            f"{view_40_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


def test_broker_dispatch_roundtrip_blocks_ack_complete_final_lineage_drift():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    complete_final_sha256 = "f" * 64
    add_ack_complete_final_target_application_lineage(
        ack_config,
        vendor,
        lineage_sha256=complete_final_sha256,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    complete_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{complete_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{complete_check_prefix}_compatibility_ack_review_lineage_sha256_matches",
        f"{complete_check_prefix}_roundtrip_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    final_lineage = report.config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    assert final_lineage["broker_application_lineage_sha256"] != complete_final_sha256
    complete_final_lineage = report.config[
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        complete_final_lineage["broker_application_lineage_sha256"]
        == complete_final_sha256
    )
    assert complete_final_lineage["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_roundtrip_blocks_ack_view_32_drift_while_preserving_view_24():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_config[
        "ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_32_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "ack_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_ack_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_roundtrip_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    complete_final_lineage = report.config[
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        complete_final_lineage["broker_application_lineage_sha256"]
        == lineage_sha256
    )
    assert (
        complete_final_lineage[
            "ack_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        complete_final_lineage["carried_application_lineage_sha256"]
        == lineage_sha256
    )
    assert complete_final_lineage["broker_application_lineage_sha256"] != "f" * 64
    extended_complete_final_lineage = report.config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        extended_complete_final_lineage["broker_application_lineage_sha256"]
        == "f" * 64
    )
    assert (
        extended_complete_final_lineage[
            "ack_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        extended_complete_final_lineage["carried_application_lineage_sha256"]
        == lineage_sha256
    )


def test_broker_dispatch_roundtrip_blocks_ack_view_40_drift_while_preserving_view_33():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_config[
        "ack_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_40_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "ack_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_ack_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_roundtrip_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    roundtrip_view_33 = report.config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert roundtrip_view_33["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        roundtrip_view_33[
            "ack_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        roundtrip_view_33["carried_application_lineage_sha256"]
        == lineage_sha256
    )
    assert roundtrip_view_33["broker_application_lineage_sha256"] != "f" * 64
    roundtrip_view_41 = report.config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert roundtrip_view_41["broker_application_lineage_sha256"] == "f" * 64
    assert (
        roundtrip_view_41[
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        roundtrip_view_41["carried_application_lineage_sha256"]
        == lineage_sha256
    )


def test_broker_dispatch_roundtrip_preserves_view_41_when_ack_view_48_differs():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_config[
        "ack_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_48_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert report.passed
    roundtrip_view_41 = report.config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert roundtrip_view_41["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        roundtrip_view_41[
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert roundtrip_view_41["carried_application_lineage_sha256"] == lineage_sha256
    assert roundtrip_view_41["broker_application_lineage_sha256"] != "f" * 64


def test_broker_dispatch_roundtrip_requires_ack_view_40_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_config.pop(
        "ack_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "ack_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    roundtrip_view_41 = report.config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not roundtrip_view_41["required"]
    assert not roundtrip_view_41["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_latest_extended_complete_final_roundtrip_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_latest_extended_complete_final_ack_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_roundtrip_blocks_invalid_ack_view_40_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_view_40 = ack_config[
        "ack_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    ack_view_40[field] = value

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_roundtrip_uses_ack_compatibility_lineage_before_ack_final():
    compatibility_sha256 = "a" * 64
    final_sha256 = "b" * 64
    ack_config = route_enable_config()
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": compatibility_sha256,
        "broker_application_lineage_sha256": compatibility_sha256,
        "scaleup_carried_application_lineage_sha256": compatibility_sha256,
        "cutover_carried_application_lineage_sha256": compatibility_sha256,
        "route_carried_application_lineage_sha256": compatibility_sha256,
        "dispatch_carried_application_lineage_sha256": compatibility_sha256,
        "send_carried_application_lineage_sha256": compatibility_sha256,
        "ack_carried_application_lineage_sha256": compatibility_sha256,
    }
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": final_sha256,
        "broker_application_lineage_sha256": final_sha256,
        "send_carried_application_lineage_sha256": final_sha256,
        "ack_carried_application_lineage_sha256": final_sha256,
        "send_packet_review_carried_application_lineage_sha256": final_sha256,
        "carried_application_lineage_sha256": "c" * 64,
    }

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=route_enable_config(),
        send_config=route_enable_config(),
        ack_config=ack_config,
    )

    assert report.passed
    lineage = report.config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["current_application_lineage_sha256"] == compatibility_sha256
    assert lineage["broker_application_lineage_sha256"] == compatibility_sha256
    assert lineage["ack_carried_application_lineage_sha256"] == compatibility_sha256


def test_broker_dispatch_roundtrip_carries_target_application_batch_from_component_summaries():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_input = with_broker_vendor_batch_summary(
        dispatch_summary(),
        vendor,
        prefix="route_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    send_input = with_broker_vendor_batch_summary(
        send_summary(),
        vendor,
        prefix="dispatch_broker_dispatch_roundtrip_vendor_market_data_batch",
    )
    ack_input = with_broker_vendor_batch_summary(
        ack_summary(),
        vendor,
        prefix="ack_broker_dispatch_roundtrip_vendor_market_data_batch",
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_input,
        dispatch_orders=dispatch_orders(),
        send_summary=send_input,
        send_requests=send_requests(),
        ack_summary=ack_input,
        acknowledgements=acknowledgements(),
        dispatch_config=route_enable_config(),
        send_config=route_enable_config(),
        ack_config=route_enable_config(),
    )

    assert report.passed
    prefix = "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    carried = report.config[prefix]
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    assert carried["datasets"][1]["mapping_scope_review_id"] == "scope-review-1"
    final_lineage = report.config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage[
        "ack_reconciliation_review_carried_application_lineage_sha256"
    ] == final_lineage["broker_application_lineage_sha256"]
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]
    extended_complete_final_lineage = report.config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert extended_complete_final_lineage["required"]
    assert extended_complete_final_lineage["matches"]
    assert (
        extended_complete_final_lineage[
            "ack_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == extended_complete_final_lineage["broker_application_lineage_sha256"]
    )
    assert (
        extended_complete_final_lineage["carried_application_lineage_sha256"]
        == extended_complete_final_lineage["broker_application_lineage_sha256"]
    )


def test_broker_dispatch_roundtrip_blocks_target_batch_without_ack_lineage_comparison():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_ack_carried_lineage_sha256_matches",
    } <= failed


def test_broker_dispatch_roundtrip_requires_final_lineage_comparison_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
    } <= failed


def test_broker_dispatch_roundtrip_requires_ack_complete_final_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed


def test_broker_dispatch_roundtrip_requires_ack_view_32_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_config.pop(
        "ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "ack_extended_complete_final"
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
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "matches",
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
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_roundtrip_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )
    add_ack_complete_final_target_application_lineage(ack_config, vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final_source_lineage_sha256_matches",
        ),
        (
            "route_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final_route_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_complete_final_ack_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_roundtrip_blocks_invalid_ack_complete_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(
        ack_config,
        vendor,
        **{field: value},
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_extended_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_ack_extended_complete_final_ack_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_roundtrip_blocks_invalid_ack_view_32_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)
    ack_config[
        "ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_view_32_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_roundtrip_does_not_require_final_comparison_when_consistency_is_absent():
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    check_names = set(report.checks["check"])
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch_final_"
    assert not any(name.startswith(prefix) for name in check_names)
    extended_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "ack_extended_complete_final_"
    )
    assert not any(name.startswith(extended_prefix) for name in check_names)
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_final_review_carried_lineage_sha256_matches"
        not in check_names
    )


def test_broker_dispatch_roundtrip_blocks_target_application_downgrade_and_lineage_drift():
    vendor = target_application_vendor_market_data_batch_config()
    dirty_vendor = target_application_vendor_market_data_batch_config(
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
    )
    dirty_vendor["datasets"][1]["mapping_application_id"] = "mapping-app-replaced"
    dirty_vendor["datasets"][1]["mapping_application_sha256"] = ""
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_carried_lineage_sha256_matches",
    } <= failed


def test_broker_dispatch_roundtrip_recomputes_target_lineage_after_ack():
    acknowledged_vendor = target_application_vendor_market_data_batch_config()
    reviewed_vendor = json.loads(json.dumps(acknowledged_vendor))
    reviewed_vendor["datasets"][1]["mapping_application_id"] = "mapping-app-post-ack-drift"
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = reviewed_vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = reviewed_vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = reviewed_vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(acknowledged_vendor)
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(acknowledged_vendor)
    add_ack_complete_final_target_application_lineage(
        ack_config,
        acknowledged_vendor,
    )

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_carried_lineage_sha256_matches"
        in failed
    )
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_final_review_carried_lineage_sha256_matches"
        in failed
    )
    comparison = report.config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert comparison["ack_carried_application_lineage_sha256"] == (
        target_application_lineage_sha256(acknowledged_vendor["datasets"])
    )
    assert comparison["roundtrip_carried_application_lineage_sha256"] == (
        target_application_lineage_sha256(reviewed_vendor["datasets"])
    )


@pytest.mark.parametrize(
    ("comparison_overrides", "vendor_overrides", "expected_check"),
    [
        (
            {"matches": False},
            {},
            "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ),
        (
            {"current_application_lineage_sha256": "f" * 64},
            {},
            "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        ),
        (
            {},
            {"application_lineage_consistent": False},
            "broker_dispatch_roundtrip_vendor_market_data_batch_retained_application_lineage_consistent",
        ),
    ],
)
def test_broker_dispatch_roundtrip_blocks_failed_ack_target_lineage_decision(
    comparison_overrides,
    vendor_overrides,
    expected_check,
):
    vendor = target_application_vendor_market_data_batch_config(**vendor_overrides)
    comparison = target_application_lineage_comparison(vendor)
    comparison.update(comparison_overrides)
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = comparison
    ack_config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = ack_final_target_application_lineage_comparison(vendor)
    add_ack_complete_final_target_application_lineage(ack_config, vendor)

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_check in failed


def test_broker_dispatch_roundtrip_blocks_failed_broker_vendor_data_readiness():
    vendor = vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config(
        ready=False,
        failed_checks=1,
    )
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    wrapper_config = report.config["roundtrip_broker_vendor_data_readiness"]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert {
        "broker_vendor_data_readiness_ready",
        "broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary["roundtrip_broker_vendor_data_readiness_provided"])
    assert not bool(summary["roundtrip_broker_vendor_data_readiness_ready"])
    assert int(summary["roundtrip_broker_vendor_data_readiness_failed_checks"]) == 1
    assert wrapper_config["provided"]
    assert not wrapper_config["ready"]
    assert wrapper_config["failed_checks"] == 1
    assert vendor_config["provided"]
    assert vendor_config["ready"]
    assert vendor_config["unique_mapping_drafts"] == 1


def test_broker_dispatch_roundtrip_blocks_dirty_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dirty_vendor = dirty_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "broker_dispatch_roundtrip_vendor_market_data_batch_identity_match",
        "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count_consistent",
        "broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    assert report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]["adapter"] == "arrow_money"
    assert report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]["failed_datasets"] == 1


def test_broker_dispatch_roundtrip_blocks_wrong_manifest_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dirty_vendor = vendor_market_data_batch_config(manifest_run_type="not_vendor_batch")
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert vendor_config["manifest_run_type"] == "vendor_market_data_batch_pipeline"


def test_broker_dispatch_roundtrip_carries_direct_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.passed
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor_config["adapter"] == "arrow_money"
    assert vendor_config["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor_config["unique_mapping_drafts"] == 1


def test_broker_dispatch_roundtrip_blocks_wrong_manifest_direct_vendor_market_data_batch():
    dirty_vendor = vendor_market_data_batch_config(manifest_run_type="not_vendor_batch")
    dispatch_config = route_enable_config()
    dispatch_config["roundtrip_vendor_market_data_batch"] = dirty_vendor
    send_config = route_enable_config()
    send_config["roundtrip_vendor_market_data_batch"] = dirty_vendor
    ack_config = route_enable_config()
    ack_config["roundtrip_vendor_market_data_batch"] = dirty_vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor_config["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_roundtrip_prefers_roundtrip_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dirty_vendor = dirty_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor
    ack_config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert vendor_config["adapter"] == "arrow_money"
    assert vendor_config["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor_config["source_file_fingerprint_coverage"] == 1.0
    assert vendor_config["min_mapping_coverage"] == 1.0
    assert vendor_config["unique_mapping_drafts"] == 1
    assert vendor_config["comparison"]["accepted"]


def test_broker_dispatch_roundtrip_blocks_dirty_roundtrip_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dirty_vendor = dirty_vendor_market_data_batch_config()
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "broker_dispatch_roundtrip_vendor_market_data_batch_identity_match",
        "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count_consistent",
        "broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor_config["source_file_fingerprint_coverage"] == 0.0
    assert vendor_config["min_mapping_coverage"] == 0.0
    assert vendor_config["failed_datasets"] == 1
    assert not vendor_config["comparison"]["accepted"]


def test_broker_dispatch_roundtrip_blocks_wrong_manifest_roundtrip_broker_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    dirty_vendor = vendor_market_data_batch_config(manifest_run_type="not_vendor_batch")
    dispatch_config = route_enable_config()
    dispatch_config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    send_config = route_enable_config()
    send_config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config = route_enable_config()
    ack_config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    ack_config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=dispatch_config,
        send_config=send_config,
        ack_config=ack_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor_config = report.config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert vendor_config["manifest_run_type"] == "vendor_market_data_batch_pipeline"


def test_cli_broker_dispatch_roundtrip_hydrates_broker_vendor_data_from_manifest_chain(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path)
    broker_config = dispatch / "broker_readiness_config.json"
    cutover_manifest = dispatch / "cutover_manifest.json"
    route_manifest = dispatch / "route_enable_manifest.json"
    broker_config.write_text(
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
                        vendor_market_data_batch_config()
                    ),
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    cutover_manifest.write_text(
        json.dumps(
            {
                "run_type": "cutover_gate",
                "inputs": {
                    "broker_readiness_config": {
                        "path": str(broker_config),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    route_manifest.write_text(
        json.dumps(
            {
                "run_type": "route_enable_packet",
                "inputs": {
                    "cutover_manifest": {
                        "path": str(cutover_manifest),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (dispatch / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "broker_dispatch_plan",
                "inputs": {
                    "route_enable_manifest": {
                        "path": str(route_manifest),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "roundtrip"

    code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip_summary.csv")
    config = json.loads((out_dir / "broker_dispatch_roundtrip_config.json").read_text(encoding="utf-8"))
    vendor = config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 0
    assert bool(summary.loc[0, "passed"])
    assert bool(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert (
        summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"]
        == "arrow_money"
    )
    assert int(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    mapping_source_mode = summary.loc[
        0,
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
    ]
    assert pd.isna(mapping_source_mode) or mapping_source_mode == ""
    assert int(
        summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count"]
    ) == 0
    assert int(
        summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications"]
    ) == 0
    assert summary.loc[0, "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage"] == 0.0
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["mapping_source_mode"] == ""
    assert vendor["mapping_application_count"] == 0
    assert vendor["unique_mapping_applications"] == 0
    assert vendor["target_application_coverage"] == 0.0
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64
    assert vendor["datasets"][1]["mapping_source"] == "vendor_intake_draft"


def test_cli_broker_dispatch_roundtrip_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path)
    broker_config = dispatch / "broker_readiness_config.json"
    cutover_manifest = dispatch / "cutover_manifest.json"
    route_manifest = dispatch / "route_enable_manifest.json"
    broker_config.write_text(
        json.dumps(
            {
                "ready": False,
                "adapter": "arrow_money",
                "broker_vendor_data_readiness": broker_vendor_data_readiness_config(
                    ready=False,
                    failed_checks=1,
                ),
                "dispatch_roundtrip": {
                    "provided": True,
                    "ready": True,
                    "target_mode": "live_dryrun",
                    "strategy": "lead_lag_taker",
                    "market": "india_nse_index_derivatives",
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
    cutover_manifest.write_text(
        json.dumps(
            {
                "run_type": "cutover_gate",
                "inputs": {
                    "broker_readiness_config": {
                        "path": str(broker_config),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    route_manifest.write_text(
        json.dumps(
            {
                "run_type": "route_enable_packet",
                "inputs": {
                    "cutover_manifest": {
                        "path": str(cutover_manifest),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (dispatch / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "broker_dispatch_plan",
                "inputs": {
                    "route_enable_manifest": {
                        "path": str(route_manifest),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "roundtrip"

    code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_roundtrip_checks.csv")
    config = json.loads((out_dir / "broker_dispatch_roundtrip_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    wrapper = config["roundtrip_broker_vendor_data_readiness"]
    vendor = config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert {
        "broker_vendor_data_readiness_ready",
        "broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary.loc[0, "roundtrip_broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "roundtrip_broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "roundtrip_broker_vendor_data_readiness_failed_checks"]) == 1
    assert wrapper["provided"]
    assert not wrapper["ready"]
    assert wrapper["failed_checks"] == 1
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["unique_mapping_drafts"] == 1


def test_broker_dispatch_roundtrip_blocks_dirty_broker_shadow_broker_readiness():
    clean_config = route_enable_config()
    clean_config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }
    bad_config = route_enable_config()
    bad_config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            ready_sessions=1,
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
            broker_vendor_data_readiness_ready_sessions=1,
            broker_vendor_data_readiness_failed_checks=1,
        ),
    }

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=clean_config,
        send_config=clean_config,
        ack_config=bad_config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_shadow_broker_readiness_ready",
        "broker_shadow_broker_vendor_data_readiness_ready",
        "broker_shadow_broker_vendor_data_readiness_failed_checks",
        "broker_shadow_broker_adapter_match",
        "broker_shadow_broker_adapter_consistent",
        "broker_shadow_broker_route_readiness_ready",
        "broker_shadow_broker_route_readiness_identity_match",
        "broker_shadow_broker_route_readiness_gap_pairs",
        "broker_shadow_broker_dispatch_roundtrip_ready",
        "broker_shadow_broker_dispatch_roundtrip_identity_match",
        "broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "broker_shadow_broker_route_dispatch_roundtrip_ready",
        "broker_shadow_broker_route_dispatch_roundtrip_identity_match",
        "broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.summary.iloc[0]["broker_shadow_broker_adapter"] == "arrow_money"
    assert int(report.summary.iloc[0]["broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 1
    assert report.config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_roundtrip_blocks_partial_broker_shadow_broker_vendor_data_readiness():
    config = route_enable_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(),
        dispatch_config=config,
        send_config=config,
        ack_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "broker_shadow_broker_vendor_data_readiness_provided",
        "broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    assert int(report.summary.iloc[0]["broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert (
        report.config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
            "provided_sessions"
        ]
        == 1
    )


def test_broker_dispatch_roundtrip_requires_route_readiness():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(route_readiness_provided=False, route_readiness_ready=False),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(route_readiness_provided=False, route_readiness_ready=False),
        send_requests=send_requests(),
        ack_summary=ack_summary(route_readiness_provided=False, route_readiness_ready=False),
        acknowledgements=acknowledgements(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_provided", "route_readiness_ready"} <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_broker_dispatch_roundtrip_blocks_route_readiness_identity_mismatch():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(route_readiness_strategy="surface_mm"),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(route_readiness_market="us_options_regular"),
        send_requests=send_requests(),
        ack_summary=ack_summary(route_readiness_strategy="lead_lag_taker"),
        acknowledgements=acknowledgements(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_readiness_identity_match" in failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "india_nse_index_derivatives"


def test_broker_dispatch_roundtrip_blocks_stale_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        acknowledgements=acknowledgements(),
        ack_config=route_enable_config(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_ops_launch_controls_present",
        "route_readiness_ops_launch_controls_blocked_pairs",
        "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["route_readiness_ops_launch_controls_present"])
    assert int(summary["route_readiness_ops_launch_controls_blocked_pairs"]) == 1
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_breach_pairs"] == 1
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_concentration_breach_pairs"] == 1


def test_broker_dispatch_roundtrip_blocks_stale_route_broker_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        acknowledgements=acknowledgements(),
        ack_config=route_enable_config(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_route_readiness_ops_launch_controls_ready",
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["route_broker_route_readiness_ops_launch_controls_ready"])
    assert int(summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) == 1
    route_proof = report.config["route_broker_route_readiness"]
    assert route_proof["ops_launch_control_failures"] == "concentration breach on BANKNIFTY weekly"
    assert route_proof["ops_broker_roundtrip_portfolio_concentration_breach_runs"] == 1


def test_broker_dispatch_roundtrip_requires_route_roundtrip_proof():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        dispatch_orders=dispatch_orders(route_roundtrip_batch_id=""),
        send_summary=send_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        send_requests=send_requests(route_roundtrip_batch_id=""),
        ack_summary=ack_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        acknowledgements=acknowledgements(route_roundtrip_batch_id=""),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_roundtrip_blocks_dirty_route_roundtrip_chain():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(route_roundtrip_batch_id="BDP-X"),
        send_requests=send_requests(route_roundtrip_batch_id="BDP-X"),
        ack_summary=ack_summary(
            route_roundtrip_ready=False,
            route_roundtrip_target_mode="shadow",
            route_roundtrip_batch_id="BDP-0",
            route_roundtrip_acked_orders=1,
            route_roundtrip_missing_request_acks=1,
            route_roundtrip_rejected_orders=1,
            route_roundtrip_unmatched_acks=1,
        ),
        acknowledgements=acknowledgements(route_roundtrip_batch_id="BDP-0"),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_identity_match",
        "route_dispatch_roundtrip_batch_consistent",
        "route_dispatch_roundtrip_request_counts_match",
        "route_dispatch_roundtrip_missing_request_acks",
        "route_dispatch_roundtrip_rejected_orders",
        "route_dispatch_roundtrip_unmatched_acks",
    } <= failed


def test_broker_dispatch_roundtrip_blocks_raw_ack_route_batch_mismatch():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(),
        send_requests=send_requests(),
        ack_summary=ack_summary(),
        acknowledgements=acknowledgements(ack_route_roundtrip_batch_ids="BDP-OLD"),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_dispatch_roundtrip_batch_consistent" in failed
    assert report.orders["ack_route_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.orders["ack_raw_route_roundtrip_batch_ids"].tolist() == ["BDP-OLD", "BDP-OLD"]


def test_broker_dispatch_roundtrip_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        send_requests=send_requests(),
        ack_summary=ack_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        acknowledgements=acknowledgements(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_roundtrip_reads_nested_route_enable_dispatch_roundtrip_failed_checks(tmp_path):
    config_files = {
        "dispatch": "broker_dispatch_config.json",
        "send": "broker_dispatch_send_config.json",
        "ack": "broker_dispatch_ack_config.json",
    }
    for component, config_file in config_files.items():
        root = tmp_path / component
        root.mkdir()
        dispatch, send, ack = write_inputs(root)
        component_dir = {"dispatch": dispatch, "send": send, "ack": ack}[component]
        (component_dir / config_file).write_text(
            json.dumps(
                route_enable_config(route_enable_dispatch_roundtrip_failed_checks=1),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        report = write_broker_dispatch_roundtrip(
            dispatch_dir=dispatch,
            send_dir=send,
            ack_dir=ack,
            output_dir=root / "roundtrip",
        )

        assert not report.passed
        failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
        assert "route_enable_dispatch_roundtrip_failed_checks" in failed
        assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
        assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_roundtrip_blocks_identity_submission_and_missing_acks():
    report = evaluate_broker_dispatch_roundtrip(
        dispatch_summary=dispatch_summary(ready=False),
        dispatch_orders=dispatch_orders(),
        send_summary=send_summary(strategy="parity", submission_enabled=True),
        send_requests=send_requests(submission_enabled=True),
        ack_summary=ack_summary(passed=False, strategy="parity", acked_orders=1, missing=1, rejected=1),
        acknowledgements=acknowledgements(missing_second=True, rejected_second=True),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed >= {
        "dispatch_ready",
        "ack_passed",
        "identity_match",
        "submission_disabled",
        "all_requests_acked",
        "missing_request_acks",
        "rejected_orders",
        "component_failed_checks",
    }
    assert report.summary.iloc[0]["recommendation"] == "investigate_broker_dry_run_roundtrip"


def test_write_broker_dispatch_roundtrip_outputs_artifacts_and_catalog_entry(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path)
    out_dir = tmp_path / "roundtrip"

    report = write_broker_dispatch_roundtrip(
        dispatch_dir=dispatch,
        send_dir=send,
        ack_dir=ack,
        output_dir=out_dir,
    )

    assert report.passed
    assert (out_dir / "broker_dispatch_roundtrip_orders.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_checks.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_summary.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_action_queue.csv").exists()
    assert (out_dir / "broker_dispatch_roundtrip_config.json").exists()
    assert (out_dir / "broker_dispatch_roundtrip_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "broker_dispatch_roundtrip_action_queue.csv")
    summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip_summary.csv")
    config = json.loads((out_dir / "broker_dispatch_roundtrip_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_dispatch_roundtrip_runbook.md").read_text(encoding="utf-8")
    assert action_queue.empty
    assert int(summary.loc[0, "action_queue_count"]) == 0
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert config["action_queue_count"] == 0
    assert config["next_actions"] == []
    assert "# Broker Dispatch Round-Trip Runbook" in runbook
    assert "No broker dispatch round-trip actions." in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    expected_inputs = {
        "dispatch_summary": "/broker_dispatch_summary.csv",
        "dispatch_orders": "/broker_dispatch_orders.csv",
        "dispatch_config": "/broker_dispatch_config.json",
        "dispatch_manifest": "/manifest.json",
        "send_summary": "/broker_dispatch_send_summary.csv",
        "send_requests": "/broker_dispatch_send_requests.csv",
        "send_config": "/broker_dispatch_send_config.json",
        "send_manifest": "/manifest.json",
        "ack_summary": "/broker_dispatch_ack_summary.csv",
        "acknowledgements": "/broker_dispatch_acknowledgements.csv",
        "ack_config": "/broker_dispatch_ack_config.json",
        "ack_manifest": "/manifest.json",
    }
    for name, suffix in expected_inputs.items():
        assert path_tail(manifest["inputs"][name]["path"]).endswith(suffix)
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "broker_dispatch_roundtrip_action_queue.csv" in artifact_paths
    assert "broker_dispatch_roundtrip_runbook.md" in artifact_paths
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_roundtrip"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_roundtrip_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_roundtrip_fails_on_missing_ack(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path, missing_ack=True)
    out_dir = tmp_path / "roundtrip"
    blocked_dir = tmp_path / "roundtrip_blocked"
    actions_dir = tmp_path / "roundtrip_actions"

    code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_roundtrip_checks.csv")
    queue = pd.read_csv(out_dir / "broker_dispatch_roundtrip_action_queue.csv")
    config = json.loads((out_dir / "broker_dispatch_roundtrip_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "missing_request_acks" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "missing_request_acks" in set(queue["check"])
    row = queue.set_index("check").loc["missing_request_acks"]
    assert row["component"] == "broker_dispatch_ack"
    assert row["next_gate"] == "reconcile-broker-dispatch"
    assert row["next_gate_help_command"] == "python -m hft_cli reconcile-broker-dispatch --help"
    assert config["blocked_action_count"] >= 1
    assert config["primary_action_status"] == "blocked"

    blocked_code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(blocked_dir),
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(actions_dir),
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


def test_cli_broker_dispatch_roundtrip_can_require_route_readiness(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path, route_readiness=False)
    out_dir = tmp_path / "roundtrip"

    code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_roundtrip_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_roundtrip_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "route_readiness_provided" in failed
