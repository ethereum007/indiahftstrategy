import hashlib
import json

import pandas as pd
import pytest

from hft_cli import main
from reports.broker_dispatch import (
    BrokerDispatchThresholds,
    evaluate_broker_dispatch_plan,
    write_broker_dispatch_plan,
)
from reports.catalog import catalog_experiment_runs
from reports.manifest import file_sha256, verify_experiment_manifest, write_experiment_manifest
from reports.operational_lineage import (
    cutover_lineage_fields,
    empty_runtime_session_lineage,
    load_cutover_lineage,
    runtime_session_lineage_fields,
)


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
    }


def route_final_target_application_lineage_comparison(vendor, **overrides):
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def route_complete_final_target_application_lineage_comparison(
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def route_view_29_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = route_complete_final_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "route_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def route_view_37_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = route_view_29_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "route_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def route_view_45_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = route_view_37_target_application_lineage_comparison(
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
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def route_view_53_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = route_view_29_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "route_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
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
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def add_route_complete_final_target_application_lineage(
    config,
    vendor,
    **overrides,
):
    config[
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_complete_final_target_application_lineage_comparison(
        vendor,
        **overrides,
    )
    config[
        "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_view_29_target_application_lineage_comparison(vendor)
    config[
        "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_view_37_target_application_lineage_comparison(vendor)
    config[
        "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_view_45_target_application_lineage_comparison(vendor)
    config[
        "route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_view_53_target_application_lineage_comparison(vendor)


def resume_route_proof(
    *,
    required=True,
    provided=True,
    ready=True,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
    route_ready_pairs=1,
    gap_pairs=0,
    recommendation="eligible_for_live_dryrun_route_review",
    ops_launch_controls_ready=True,
    ops_launch_control_failures="",
    ops_broker_roundtrip_portfolio_safe_runs=1,
    ops_broker_roundtrip_portfolio_breach_runs=0,
    ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    return {
        "required": required,
        "provided": provided,
        "ready": ready,
        "strategy": strategy,
        "market": market,
        "route_ready_pairs": route_ready_pairs,
        "gap_pairs": gap_pairs,
        "recommendation": recommendation,
        "ops_launch_controls_ready": ops_launch_controls_ready,
        "ops_launch_control_failures": ops_launch_control_failures,
        "ops_broker_roundtrip_portfolio_safe_runs": ops_broker_roundtrip_portfolio_safe_runs,
        "ops_broker_roundtrip_portfolio_breach_runs": ops_broker_roundtrip_portfolio_breach_runs,
        "ops_broker_roundtrip_portfolio_concentration_ok_runs": (
            ops_broker_roundtrip_portfolio_concentration_ok_runs
        ),
        "ops_broker_roundtrip_portfolio_concentration_breach_runs": (
            ops_broker_roundtrip_portfolio_concentration_breach_runs
        ),
    }


def route_summary(
    ready=True,
    upload_orders=2,
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
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy=None,
    route_readiness_market=None,
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    strategy_portfolio_required=False,
    strategy_portfolio_provided=False,
    strategy_portfolio_ready=False,
    strategy_portfolio_selected_strategy="lead_lag_taker",
    strategy_portfolio_selected_market="india_nse_index_derivatives",
    strategy_portfolio_selected_eligible=False,
    strategy_portfolio_selected_allocation_notional=0.0,
):
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
    route_readiness_strategy = dispatch_strategy if route_readiness_strategy is None else route_readiness_strategy
    route_readiness_market = dispatch_market if route_readiness_market is None else route_readiness_market
    broker_route_readiness_strategy = (
        dispatch_strategy if broker_route_readiness_strategy is None else broker_route_readiness_strategy
    )
    broker_route_readiness_market = (
        dispatch_market if broker_route_readiness_market is None else broker_route_readiness_market
    )
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
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "route_state": "enabled" if ready else "disabled",
                "upload_orders": upload_orders,
                "max_orders_per_session": 10,
                "max_notional_per_session": 100_000.0,
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
                "cutover_broker_route_readiness_required": broker_route_readiness_required,
                "cutover_broker_route_readiness_provided": broker_route_readiness_provided,
                "cutover_broker_route_readiness_ready": broker_route_readiness_ready,
                "cutover_broker_route_readiness_strategy": broker_route_readiness_strategy,
                "cutover_broker_route_readiness_market": broker_route_readiness_market,
                "cutover_broker_route_readiness_route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "cutover_broker_route_readiness_gap_pairs": broker_route_readiness_gap_pairs,
                "cutover_broker_route_readiness_recommendation": broker_route_readiness_recommendation,
                "cutover_broker_route_readiness_ops_launch_controls_ready": (
                    broker_route_readiness_ops_launch_controls_ready
                ),
                "cutover_broker_route_readiness_ops_launch_control_failures": (
                    broker_route_readiness_ops_launch_control_failures
                ),
                "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "dispatch_roundtrip_required": True,
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
                "route_dispatch_roundtrip_required": True,
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
                "recommendation": "enable_broker_route" if ready else "keep_broker_route_disabled",
            }
        ]
    )


def route_config(
    enabled=True,
    upload_orders=2,
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
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy=None,
    route_readiness_market=None,
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
    strategy_portfolio_required=False,
    strategy_portfolio_provided=False,
    strategy_portfolio_ready=False,
    strategy_portfolio_selected_strategy="lead_lag_taker",
    strategy_portfolio_selected_market="india_nse_index_derivatives",
    strategy_portfolio_selected_eligible=False,
    strategy_portfolio_selected_allocation_notional=0.0,
):
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
    route_readiness_strategy = dispatch_strategy if route_readiness_strategy is None else route_readiness_strategy
    route_readiness_market = dispatch_market if route_readiness_market is None else route_readiness_market
    broker_route_readiness_strategy = (
        dispatch_strategy if broker_route_readiness_strategy is None else broker_route_readiness_strategy
    )
    broker_route_readiness_market = (
        dispatch_market if broker_route_readiness_market is None else broker_route_readiness_market
    )
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
        "schema_version": 1,
        "route_enabled": enabled,
        "route_state": "enabled" if enabled else "disabled",
        "target_mode": "live_dryrun",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": "arrow_money",
        "broker_readiness": {
            "adapter_schema_status": broker_schema_status,
            "schema_reviewed": broker_schema_reviewed,
            "schema_review_mode": broker_schema_review_mode,
        },
        "limits": {
            "max_orders_per_session": 10,
            "max_notional_per_session": 100_000.0,
            "stop_loss": 5_000.0,
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
            "selected_allocation_weight": 0.0012 if strategy_portfolio_selected_allocation_notional else 0.0,
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
            "ready": True,
            "orders": upload_orders,
            "output_file": "broker_upload_orders.csv",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
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
        "cutover_broker_route_readiness": {
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
                "required": True,
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
        },
    }


def shadow_broker_config(
    sessions=2,
    ready_sessions=2,
    broker_vendor_data_readiness_sessions=2,
    broker_vendor_data_readiness_provided_sessions=2,
    broker_vendor_data_readiness_ready_sessions=2,
    broker_vendor_data_readiness_failed_checks=0,
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
            "sessions": broker_vendor_data_readiness_sessions,
            "provided_sessions": broker_vendor_data_readiness_provided_sessions,
            "ready_sessions": broker_vendor_data_readiness_ready_sessions,
            "failed_checks": broker_vendor_data_readiness_failed_checks,
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
    )
    config.update(overrides)
    config.setdefault("application_lineage_consistency_required", True)
    config.setdefault("application_lineage_consistent", True)
    config.setdefault(
        "application_lineage_sha256",
        target_application_lineage_sha256(config["datasets"]),
    )
    return config


def with_route_broker_vendor_batch_summary(summary, vendor):
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        final_lineage = route_final_target_application_lineage_comparison(vendor)
        route_complete_final = (
            route_complete_final_target_application_lineage_comparison(vendor)
        )
        route_view_29 = route_view_29_target_application_lineage_comparison(vendor)
        route_view_37 = route_view_37_target_application_lineage_comparison(vendor)
        route_view_45 = route_view_45_target_application_lineage_comparison(vendor)
        route_view_53 = route_view_53_target_application_lineage_comparison(vendor)
        final_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
        complete_final_prefix = (
            "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_prefix = (
            "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_37_prefix = (
            "cutover_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_45_prefix = (
            "cutover_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_53_prefix = (
            "cutover_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            "cutover_broker_vendor_market_data_batch_lineage_match_required",
        ] = lineage["required"]
        result.loc[
            0,
            "cutover_broker_vendor_market_data_batch_lineage_matches",
        ] = lineage["matches"]
        result.loc[
            0,
            "cutover_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["current_application_lineage_sha256"]
        result.loc[
            0,
            "cutover_broker_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["broker_application_lineage_sha256"]
        result.loc[
            0,
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["scaleup_carried_application_lineage_sha256"]
        result.loc[
            0,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["cutover_carried_application_lineage_sha256"]
        result.loc[
            0,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["route_carried_application_lineage_sha256"]
        result.loc[0, f"{final_prefix}_lineage_match_required"] = final_lineage[
            "required"
        ]
        result.loc[0, f"{final_prefix}_lineage_matches"] = final_lineage["matches"]
        for field, value in final_lineage.items():
            if field not in {"required", "matches", "carried_application_lineage_sha256"}:
                result.loc[0, f"{final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{complete_final_prefix}_lineage_match_required",
        ] = route_complete_final["required"]
        result.loc[0, f"{complete_final_prefix}_lineage_matches"] = (
            route_complete_final["matches"]
        )
        for field, value in route_complete_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{complete_final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{extended_complete_final_prefix}_lineage_match_required",
        ] = route_view_29["required"]
        result.loc[
            0,
            f"{extended_complete_final_prefix}_lineage_matches",
        ] = route_view_29["matches"]
        for field, value in route_view_29.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{extended_complete_final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{extended_complete_final_prefix}_route_complete_final_review_carried_application_lineage_sha256",
        ] = route_view_29["carried_application_lineage_sha256"]
        result.loc[
            0,
            f"{extended_complete_final_37_prefix}_lineage_match_required",
        ] = route_view_37["required"]
        result.loc[
            0,
            f"{extended_complete_final_37_prefix}_lineage_matches",
        ] = route_view_37["matches"]
        for field, value in route_view_37.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[
                    0,
                    f"{extended_complete_final_37_prefix}_{field}",
                ] = value
        result.loc[
            0,
            f"{extended_complete_final_37_prefix}_route_extended_complete_final_review_carried_application_lineage_sha256",
        ] = route_view_37["carried_application_lineage_sha256"]
        result.loc[
            0,
            f"{extended_complete_final_45_prefix}_lineage_match_required",
        ] = route_view_45["required"]
        result.loc[
            0,
            f"{extended_complete_final_45_prefix}_lineage_matches",
        ] = route_view_45["matches"]
        for field, value in route_view_45.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[
                    0,
                    f"{extended_complete_final_45_prefix}_{field}",
                ] = value
        result.loc[
            0,
            f"{extended_complete_final_45_prefix}_route_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ] = route_view_45["carried_application_lineage_sha256"]
        result.loc[
            0,
            f"{extended_complete_final_53_prefix}_lineage_match_required",
        ] = route_view_53["required"]
        result.loc[
            0,
            f"{extended_complete_final_53_prefix}_lineage_matches",
        ] = route_view_53["matches"]
        for field, value in route_view_53.items():
            if field in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                continue
            result.loc[
                0,
                f"{extended_complete_final_53_prefix}_{field}",
            ] = value
        result.loc[
            0,
            f"{extended_complete_final_53_prefix}_route_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        ] = route_view_53["carried_application_lineage_sha256"]
    return result


def broker_vendor_data_readiness_config(provided=True, ready=True, failed_checks=0):
    return {
        "provided": provided,
        "ready": ready,
        "failed_checks": failed_checks,
    }


def upload_orders(duplicate=False):
    second_id = "ORD-1" if duplicate else "ORD-2"
    return pd.DataFrame(
        [
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY24JUN22500CE",
                "transaction_type": "BUY",
                "quantity": 75,
                "order_type": "LIMIT",
                "product": "MIS",
                "price": 10.0,
                "validity": "DAY",
                "client_order_id": "ORD-1",
                "tag": "shadow_nse",
            },
            {
                "exchange": "NFO",
                "tradingsymbol": "NIFTY24JUN22500PE",
                "transaction_type": "SELL",
                "quantity": 75,
                "order_type": "LIMIT",
                "product": "MIS",
                "price": 11.0,
                "validity": "DAY",
                "client_order_id": second_id,
                "tag": "shadow_nse",
            },
        ]
    )


def path_tail(value):
    return str(value).replace("\\", "/")


def cutover_runtime_lineage():
    state = empty_runtime_session_lineage(required=True)
    state.update(
        {
            "provided": True,
            "manifest_current": True,
            "manifest_run_type": "runtime_session_monitor",
            "manifest_path": "runtime/manifest.json",
            "manifest_sha256": "a" * 64,
            "contract_consistent": True,
            "non_authorizing": True,
            "scaleup_matches_current": True,
            "gate_passed": True,
            "scaleup_research_family_bound": True,
            "scaleup_research_family_provenance_current": True,
            "scaleup_research_family_id": "india-leadlag-v1",
            "scaleup_research_family_registration_id": "RF-INDIA-LEADLAG-1",
            "scaleup_research_family_manifest_sha256": "b" * 64,
            "runtime_telemetry_lineage_matches_current": True,
        }
    )
    return runtime_session_lineage_fields(state)


def refresh_cutover_manifest(cutover):
    runtime_lineage = cutover_runtime_lineage()
    inputs = {"cutover_source": cutover.parent / "cutover_source.csv"}
    broker_config = cutover / "broker_readiness_config.json"
    if broker_config.is_file():
        inputs["broker_readiness_config"] = broker_config
    write_experiment_manifest(
        cutover,
        run_type="cutover_gate",
        inputs=inputs,
        extra={
            "ready": True,
            **runtime_lineage,
            "authorizes_submission": False,
        },
    )


def write_cutover_fixture(root):
    cutover = root / "cutover"
    cutover.mkdir(parents=True)
    runtime_lineage = cutover_runtime_lineage()
    summary = pd.DataFrame(
        [{"ready": True, **runtime_lineage, "authorizes_submission": False}]
    )
    summary.to_csv(cutover / "cutover_summary.csv", index=False)
    summary.to_csv(cutover / "cutover_authorization.csv", index=False)
    pd.DataFrame([{"check": "fixture", "passed": True}]).to_csv(
        cutover / "cutover_checks.csv", index=False
    )
    pd.DataFrame(columns=["priority", "action"]).to_csv(
        cutover / "cutover_action_queue.csv", index=False
    )
    (cutover / "cutover_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "runtime_lineage": runtime_lineage,
                "authorizes_submission": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (cutover / "cutover_runbook.md").write_text("# Cutover Fixture\n", encoding="utf-8")
    pd.DataFrame([{"source": "fixture"}]).to_csv(root / "cutover_source.csv", index=False)
    refresh_cutover_manifest(cutover)
    return cutover


def refresh_route_manifest(route, *, lineage_override=None, sync_lineage=True):
    cutover = route.parent / "cutover"
    lineage = lineage_override or cutover_lineage_fields(
        load_cutover_lineage(cutover / "cutover_config.json")
    )
    if sync_lineage:
        summary_path = route / "route_enable_summary.csv"
        summary = pd.read_csv(summary_path)
        packet_path = route / "route_enable_packet.csv"
        packet = pd.read_csv(packet_path)
        for column, value in lineage.items():
            summary[column] = value
            packet[column] = value
        summary.to_csv(summary_path, index=False)
        packet.to_csv(packet_path, index=False)
        config_path = route / "route_enable_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["cutover_lineage"] = lineage
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    write_experiment_manifest(
        route,
        run_type="route_enable_packet",
        inputs={
            "cutover_manifest": cutover / "manifest.json",
            "route_source": route.parent / "route_source.csv",
        },
        extra={
            "ready": bool(pd.read_csv(route / "route_enable_summary.csv").iloc[0]["ready"]),
            **lineage,
            "authorizes_submission": False,
        },
    )


def write_inputs(root, *, route_ready=True, duplicate=False, dispatch=True, route_readiness=True):
    cutover = write_cutover_fixture(root)
    route = root / "route_enable"
    upload = root / "upload"
    route.mkdir(parents=True)
    upload.mkdir()
    lineage = cutover_lineage_fields(
        load_cutover_lineage(cutover / "cutover_config.json")
    )
    summary = route_summary(
        route_ready,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    )
    for column, value in lineage.items():
        summary[column] = value
    summary["authorizes_submission"] = False
    summary.to_csv(route / "route_enable_summary.csv", index=False)
    config = route_config(
        route_ready,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    )
    config["cutover_lineage"] = lineage
    config["authorizes_submission"] = False
    (route / "route_enable_config.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    packet = summary.copy()
    packet["route_enabled"] = route_ready
    packet.to_csv(route / "route_enable_packet.csv", index=False)
    pd.DataFrame([{"check": "fixture", "passed": route_ready}]).to_csv(
        route / "route_enable_checks.csv", index=False
    )
    pd.DataFrame(columns=["priority", "action"]).to_csv(
        route / "route_enable_action_queue.csv", index=False
    )
    (route / "route_enable_runbook.md").write_text("# Route Enable Fixture\n", encoding="utf-8")
    pd.DataFrame([{"source": "fixture"}]).to_csv(root / "route_source.csv", index=False)
    refresh_route_manifest(route)
    upload_orders(duplicate).to_csv(upload / "broker_upload_orders.csv", index=False)
    return route, upload


def test_broker_dispatch_plan_creates_dry_run_idempotent_batch():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=route_config(),
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["dispatch_state"] == "armed_dry_run"
    assert summary["recommendation"] == "ready_for_broker_dryrun_dispatch"
    assert report.dispatch_orders["dry_run_only"].tolist() == [True, True]
    assert report.dispatch_orders["dispatch_action"].tolist() == ["dry_run_submit", "dry_run_submit"]
    assert report.dispatch_orders["source_order_id"].tolist() == ["ORD-1", "ORD-2"]
    assert report.dispatch_orders["dispatch_batch_id"].nunique() == 1
    assert report.config["dry_run_only"]
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.dispatch_orders["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.summary.iloc[0]["route_dispatch_roundtrip_ready"]
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
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


def test_broker_dispatch_carries_strategy_portfolio_allocation():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=2_000.0,
        ),
        route_enable_config=route_config(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=2_000.0,
        ),
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
    )

    assert report.ready
    summary = report.summary.iloc[0]
    portfolio = report.config["strategy_portfolio"]
    assert report.dispatch_orders["source_order_notional"].tolist() == [750.0, 825.0]
    assert summary["dispatch_total_notional"] == 1_575.0
    assert bool(summary["strategy_portfolio_required"])
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
    assert portfolio["required"]
    assert portfolio["provided"]
    assert portfolio["ready"]
    assert portfolio["selected_allocation_notional"] == 2_000.0
    assert portfolio["min_strategy_count"] == 2
    assert portfolio["allocated_strategy_count"] == 2
    assert portfolio["top_strategy_by_weight"] == "lead_lag_taker"
    assert portfolio["max_strategy_allocation_weight"] == 0.45
    assert report.config["upload"]["total_notional"] == 1_575.0


def test_broker_dispatch_blocks_upload_above_strategy_portfolio_allocation():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1_200.0,
        ),
        route_enable_config=route_config(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1_200.0,
        ),
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_notional_within_strategy_portfolio_allocation" in failed
    assert report.config["primary_blocker"]["check"] == "dispatch_notional_within_strategy_portfolio_allocation"
    assert report.config["upload"]["total_notional"] == 1_575.0


def test_broker_dispatch_carries_route_shadow_broker_readiness():
    config = route_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_readiness_sessions"]) == 2
    assert int(summary["shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["shadow_broker_adapter"] == "arrow_money"
    assert summary["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["shadow_broker_readiness"]["provided"]
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert report.config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_blocks_bad_route_shadow_broker_readiness():
    config = route_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        ready_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
        broker_vendor_data_readiness_failed_checks=1,
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

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_shadow_broker_readiness_ready",
        "route_shadow_broker_vendor_data_readiness_ready",
        "route_shadow_broker_vendor_data_readiness_failed_checks",
        "route_shadow_broker_adapter_matches",
        "route_shadow_broker_adapter_consistent",
        "route_shadow_broker_route_readiness_ready",
        "route_shadow_broker_route_readiness_strategy_matches",
        "route_shadow_broker_route_readiness_market_matches",
        "route_shadow_broker_route_readiness_gap_pairs",
        "route_shadow_broker_dispatch_roundtrip_ready",
        "route_shadow_broker_dispatch_roundtrip_strategy_matches",
        "route_shadow_broker_dispatch_roundtrip_market_matches",
        "route_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "route_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "route_shadow_broker_dispatch_roundtrip_rejected_orders",
        "route_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "route_shadow_broker_route_dispatch_roundtrip_ready",
        "route_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "route_shadow_broker_route_dispatch_roundtrip_market_matches",
        "route_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_blocks_partial_route_shadow_broker_vendor_data_readiness():
    config = route_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        broker_vendor_data_readiness_sessions=1,
        broker_vendor_data_readiness_provided_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "route_shadow_broker_vendor_data_readiness_provided",
        "route_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_broker_dispatch_carries_route_broker_shadow_broker_readiness():
    config = route_config()
    config["cutover_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["route_broker_shadow_broker_readiness_provided"]
    assert int(summary["route_broker_shadow_broker_readiness_sessions"]) == 2
    assert int(summary["route_broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["route_broker_shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["route_broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["route_broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["route_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["route_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["route_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["route_broker_shadow_broker_readiness"]["provided"]
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "ready_sessions"
    ] == 2
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["route_broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["route_broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_carries_route_vendor_market_data_batch():
    config = route_config()
    config["cutover_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["route_vendor_market_data_batch"]
    assert report.ready
    assert summary["route_vendor_market_data_batch_provided"]
    assert summary["route_vendor_market_data_batch_ready"]
    assert summary["route_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["route_vendor_market_data_batch_kind"] == "ticks"
    assert summary["route_vendor_market_data_batch_manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert int(summary["route_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["route_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["route_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["route_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["route_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["route_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["route_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_dispatch_carries_route_broker_vendor_market_data_batch():
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
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


def test_broker_dispatch_carries_target_application_vendor_batch_from_route_config():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor_input = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor_input
    config[f"{input_prefix}_lineage_comparison"] = target_application_lineage_comparison(
        vendor_input
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor_input)
    add_route_complete_final_target_application_lineage(config, vendor_input)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert summary[f"{prefix}_application_lineage_consistency_required"]
    assert summary[f"{prefix}_application_lineage_consistent"]
    assert summary["route_broker_vendor_market_data_batch_lineage_match_required"]
    assert summary["route_broker_vendor_market_data_batch_lineage_matches"]
    assert summary["route_vendor_market_data_batch_application_lineage_sha256"] == lineage_sha256
    assert (
        summary["route_broker_vendor_market_data_batch_application_lineage_sha256"]
        == lineage_sha256
    )
    assert (
        summary[
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        summary[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert summary[f"{prefix}_application_lineage_sha256"] == lineage_sha256
    assert (
        summary[
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
        == lineage_sha256
    )
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
    assert vendor["application_lineage_sha256"] == lineage_sha256
    assert vendor["datasets"][1]["target_intake_receipt_id"] == "target-intake-day2"
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
    }
    final_lineage = report.config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == lineage_sha256
    route_complete_prefix = (
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        "cutover_final_review_carried_application_lineage_sha256",
        "route_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{route_complete_prefix}_{field}"] == lineage_sha256
    dispatch_complete_final = report.config[
        "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_complete_final["required"]
    assert dispatch_complete_final["matches"]
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
        "carried_application_lineage_sha256",
    ):
        assert dispatch_complete_final[field] == lineage_sha256
    route_extended_complete_prefix = (
        "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{route_extended_complete_prefix}_{field}"] == (
            lineage_sha256
        )
    dispatch_extended_complete_final = report.config[
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_extended_complete_final["required"]
    assert dispatch_extended_complete_final["matches"]
    for field in (
        *extended_complete_final_digest_fields,
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert dispatch_extended_complete_final[field] == lineage_sha256
    route_extended_complete_37_prefix = (
        "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    extended_complete_final_37_digest_fields = (
        *extended_complete_final_digest_fields,
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
        "send_complete_final_review_carried_application_lineage_sha256",
        "ack_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
    )
    for field in (
        *extended_complete_final_37_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{route_extended_complete_37_prefix}_{field}"] == (
            lineage_sha256
        )
    dispatch_extended_complete_final_38 = report.config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_extended_complete_final_38["required"]
    assert dispatch_extended_complete_final_38["matches"]
    for field in (
        *extended_complete_final_37_digest_fields,
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert dispatch_extended_complete_final_38[field] == lineage_sha256
    route_latest_extended_complete_45_prefix = (
        "route_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    latest_extended_complete_final_45_digest_fields = (
        *extended_complete_final_37_digest_fields,
        "route_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256",
        "send_extended_complete_final_review_carried_application_lineage_sha256",
        "ack_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256",
    )
    for field in (
        *latest_extended_complete_final_45_digest_fields,
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "route_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{route_latest_extended_complete_45_prefix}_{field}"] == (
            lineage_sha256
        )
    dispatch_latest_extended_complete_final_46 = report.config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_latest_extended_complete_final_46["required"]
    assert dispatch_latest_extended_complete_final_46["matches"]
    for field in (
        *latest_extended_complete_final_45_digest_fields,
        "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "route_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert dispatch_latest_extended_complete_final_46[field] == lineage_sha256
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
        f"{prefix}_route_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_carried_lineage_sha256_matches",
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
        f"{prefix}_final_cutover_review_carried_lineage_sha256_matches",
        f"{prefix}_final_route_enable_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_lineage_match_required",
        f"{prefix}_route_final_lineage_matches",
        f"{prefix}_route_final_source_lineage_sha256_matches",
        f"{prefix}_route_final_compatibility_broker_lineage_sha256_matches",
        f"{prefix}_route_final_compatibility_route_carried_lineage_sha256_matches",
        f"{prefix}_route_final_prior_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_route_final_prior_cutover_carried_lineage_sha256_matches",
        f"{prefix}_route_final_route_carried_lineage_sha256_matches",
        f"{prefix}_route_final_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_route_final_send_carried_lineage_sha256_matches",
        f"{prefix}_route_final_ack_carried_lineage_sha256_matches",
        f"{prefix}_route_final_roundtrip_carried_lineage_sha256_matches",
        f"{prefix}_route_final_readiness_carried_lineage_sha256_matches",
        f"{prefix}_route_final_scaleup_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_cutover_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_route_enable_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_send_packet_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_broker_readiness_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_scaleup_final_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_cutover_final_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_route_final_review_carried_lineage_sha256_matches",
        f"{prefix}_route_final_dispatch_final_review_carried_lineage_sha256_matches",
    }
    extended_check_prefix = f"{prefix}_route_complete_final"
    expected_checks.update(
        {
            f"{extended_check_prefix}_lineage_match_required",
            f"{extended_check_prefix}_lineage_matches",
            f"{extended_check_prefix}_source_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_route_final_review_carried_lineage_sha256_matches",
            f"{extended_check_prefix}_scaleup_complete_final_review_carried_lineage_sha256_matches",
            f"{extended_check_prefix}_cutover_complete_final_review_carried_lineage_sha256_matches",
            f"{extended_check_prefix}_route_complete_final_review_carried_lineage_sha256_matches",
            f"{extended_check_prefix}_dispatch_complete_final_review_carried_lineage_sha256_matches",
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
        expected_checks.add(
            f"{extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    view_37_check_prefix = f"{prefix}_route_extended_complete_final"
    expected_checks.update(
        {
            f"{view_37_check_prefix}_lineage_match_required",
            f"{view_37_check_prefix}_lineage_matches",
            f"{view_37_check_prefix}_source_lineage_sha256_matches",
            f"{view_37_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_37_check_prefix}_compatibility_route_complete_final_review_carried_lineage_sha256_matches",
            f"{view_37_check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_37_check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_37_check_prefix}_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_37_check_prefix}_route_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_37_check_prefix}_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
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
            f"{view_37_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    view_45_check_prefix = f"{prefix}_route_latest_extended_complete_final"
    expected_checks.update(
        {
            f"{view_45_check_prefix}_lineage_match_required",
            f"{view_45_check_prefix}_lineage_matches",
            f"{view_45_check_prefix}_source_lineage_sha256_matches",
            f"{view_45_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_45_check_prefix}_compatibility_route_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_45_check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_45_check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_45_check_prefix}_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_45_check_prefix}_route_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_45_check_prefix}_dispatch_latest_extended_complete_final_review_carried_lineage_sha256_matches",
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
        "route_extended_complete_final_review",
        "dispatch_extended_complete_final_review",
        "send_extended_complete_final_review",
        "ack_latest_extended_complete_final_review",
        "roundtrip_latest_extended_complete_final_review",
    ):
        expected_checks.add(
            f"{view_45_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


def test_broker_dispatch_blocks_route_complete_final_lineage_drift():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor_input = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    config[input_prefix] = vendor_input
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor_input)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor_input)
    config[
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_complete_final_target_application_lineage_comparison(
        vendor_input,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_route_carried_lineage_sha256_matches",
        f"{check_prefix}_dispatch_final_review_carried_lineage_sha256_matches",
    } <= failed
    dispatch_final = report.config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_final["broker_application_lineage_sha256"] == lineage_sha256
    assert dispatch_final["carried_application_lineage_sha256"] == lineage_sha256
    dispatch_complete_final = report.config[
        "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_complete_final["broker_application_lineage_sha256"] == "f" * 64
    assert dispatch_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_broker_dispatch_blocks_route_view_29_lineage_drift():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor_input = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    config[input_prefix] = vendor_input
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor_input)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor_input)
    add_route_complete_final_target_application_lineage(config, vendor_input)
    config[
        "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_view_29_target_application_lineage_comparison(
        vendor_input,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_route_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_dispatch_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    dispatch_final = report.config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    dispatch_complete_final = report.config[
        "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_final["broker_application_lineage_sha256"] == lineage_sha256
    assert dispatch_final["carried_application_lineage_sha256"] == lineage_sha256
    assert dispatch_complete_final["broker_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert dispatch_complete_final[
        "route_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert dispatch_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    dispatch_extended_complete_final = report.config[
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_extended_complete_final["broker_application_lineage_sha256"] == (
        "f" * 64
    )
    assert dispatch_extended_complete_final[
        "carried_application_lineage_sha256"
    ] == lineage_sha256


def test_broker_dispatch_blocks_route_view_37_drift_while_preserving_view_30():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    config[
        "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_view_37_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_route_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    dispatch_view_30 = report.config[
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_view_30["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        dispatch_view_30[
            "route_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert dispatch_view_30["carried_application_lineage_sha256"] == lineage_sha256
    assert dispatch_view_30["broker_application_lineage_sha256"] != "f" * 64
    dispatch_view_38 = report.config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_view_38["broker_application_lineage_sha256"] == "f" * 64
    assert (
        dispatch_view_38[
            "route_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert dispatch_view_38["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_blocks_route_view_45_drift_while_preserving_view_38():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    view_45 = route_view_45_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    config[
        "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_45
    summary = with_route_broker_vendor_batch_summary(route_summary(), vendor)
    view_45_prefix = (
        "cutover_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{view_45_prefix}_lineage_match_required"] = view_45[
        "required"
    ]
    summary.loc[0, f"{view_45_prefix}_lineage_matches"] = view_45["matches"]
    for field, value in view_45.items():
        if field in {"required", "matches"}:
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "route_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        summary.loc[0, f"{view_45_prefix}_{field}"] = value

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=summary,
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "route_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_route_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_dispatch_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    dispatch_view_38 = report.config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_view_38["required"]
    assert dispatch_view_38["matches"]
    assert dispatch_view_38["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        dispatch_view_38[
            "route_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert dispatch_view_38["carried_application_lineage_sha256"] == lineage_sha256
    assert dispatch_view_38["broker_application_lineage_sha256"] != "f" * 64
    dispatch_view_46 = report.config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_view_46["broker_application_lineage_sha256"] == "f" * 64
    assert (
        dispatch_view_46[
            "route_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert dispatch_view_46["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_preserves_view_46_when_route_view_53_differs():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    view_53 = route_view_53_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    config[
        "route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_53
    summary = with_route_broker_vendor_batch_summary(route_summary(), vendor)
    view_53_prefix = (
        "cutover_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{view_53_prefix}_lineage_match_required"] = view_53[
        "required"
    ]
    summary.loc[0, f"{view_53_prefix}_lineage_matches"] = view_53["matches"]
    for field, value in view_53.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        summary.loc[0, f"{view_53_prefix}_{field}"] = value
    summary.loc[
        0,
        f"{view_53_prefix}_route_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] = view_53["carried_application_lineage_sha256"]

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=summary,
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    dispatch_view_46 = report.config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert dispatch_view_46["required"]
    assert dispatch_view_46["matches"]
    assert dispatch_view_46["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        dispatch_view_46[
            "route_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert dispatch_view_46["carried_application_lineage_sha256"] == lineage_sha256
    assert dispatch_view_46["broker_application_lineage_sha256"] != "f" * 64


def test_broker_dispatch_requires_route_view_45_lineage_for_reconciled_target():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "route_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    dispatch_view_46 = report.config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not dispatch_view_46["required"]
    assert not dispatch_view_46["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_latest_extended_complete_final_send_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_latest_extended_complete_final_route_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_blocks_invalid_route_view_45_lineage(
    field,
    value,
    expected_failed_check,
):
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    route_view_45 = config[
        "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    route_view_45[field] = value

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_requires_route_view_37_lineage_for_reconciled_target():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    dispatch_view_38 = report.config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not dispatch_view_38["required"]
    assert not dispatch_view_38["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_extended_complete_final_route_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_blocks_invalid_route_view_37_lineage(
    field,
    value,
    expected_failed_check,
):
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    route_view_37 = config[
        "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    route_view_37[field] = value

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_requires_route_view_29_lineage_for_reconciled_target():
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    check_prefix = (
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final"
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
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final_source_lineage_sha256_matches",
        ),
        (
            "route_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final_route_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_complete_final_route_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_blocks_invalid_route_view_29_lineage(
    field,
    value,
    expected_failed_check,
):
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor = target_application_vendor_market_data_batch_config()
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)
    route_view_29 = config[
        "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    route_view_29[field] = value

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_carries_target_application_vendor_batch_from_route_summary():
    vendor = target_application_vendor_market_data_batch_config()
    summary_input = with_route_broker_vendor_batch_summary(route_summary(), vendor)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=summary_input,
        route_enable_config=route_config(),
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    carried = report.config[prefix]
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    assert carried["datasets"][1]["mapping_scope_review_id"] == "scope-review-1"
    final_lineage = report.config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["cutover_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["route_enable_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]


def test_broker_dispatch_uses_cutover_compatibility_lineage_before_route_final():
    compatibility_sha256 = "a" * 64
    final_sha256 = "b" * 64
    config = route_config()
    config[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": compatibility_sha256,
        "broker_application_lineage_sha256": compatibility_sha256,
        "scaleup_carried_application_lineage_sha256": compatibility_sha256,
        "cutover_carried_application_lineage_sha256": compatibility_sha256,
        "route_carried_application_lineage_sha256": compatibility_sha256,
    }
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": final_sha256,
        "broker_application_lineage_sha256": final_sha256,
        "scaleup_carried_application_lineage_sha256": final_sha256,
        "cutover_carried_application_lineage_sha256": final_sha256,
        "route_carried_application_lineage_sha256": final_sha256,
        "carried_application_lineage_sha256": "c" * 64,
    }

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    lineage = report.config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["current_application_lineage_sha256"] == compatibility_sha256
    assert lineage["broker_application_lineage_sha256"] == compatibility_sha256
    assert lineage["route_carried_application_lineage_sha256"] == compatibility_sha256


def test_broker_dispatch_blocks_incomplete_target_application_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config(
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
    )
    vendor["datasets"][1]["mapping_application_sha256"] = ""
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
    } <= failed


def test_broker_dispatch_blocks_target_application_lineage_drift_after_route_enable():
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = lineage
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    route_complete_final = (
        route_complete_final_target_application_lineage_comparison(vendor)
    )
    vendor["datasets"][1]["mapping_application_sha256"] = "9" * 64
    config[
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_complete_final

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert f"{output_prefix}_dispatch_carried_lineage_sha256_matches" in failed
    assert f"{output_prefix}_dispatch_plan_review_carried_lineage_sha256_matches" in failed
    assert {
        f"{output_prefix}_source_lineage_sha256_matches",
        f"{output_prefix}_scaleup_carried_lineage_sha256_matches",
        f"{output_prefix}_cutover_carried_lineage_sha256_matches",
        f"{output_prefix}_route_carried_lineage_sha256_matches",
        f"{output_prefix}_final_route_enable_review_carried_lineage_sha256_matches",
    } <= passed


@pytest.mark.parametrize(
    ("lineage_mutation", "vendor_overrides", "expected_check"),
    [
        (
            {"matches": False},
            {},
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ),
        (
            {"current_application_lineage_sha256": "f" * 64},
            {},
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        ),
        (
            {},
            {"application_lineage_consistent": False},
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        ),
    ],
)
def test_broker_dispatch_blocks_failed_route_target_lineage_decisions(
    lineage_mutation,
    vendor_overrides,
    expected_check,
):
    vendor = target_application_vendor_market_data_batch_config(**vendor_overrides)
    lineage = target_application_lineage_comparison(vendor)
    lineage.update(lineage_mutation)
    config = route_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = lineage
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert expected_check in failed


def test_broker_dispatch_requires_final_lineage_comparison_for_reconciled_target():
    config = route_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    add_route_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{output_prefix}_final_lineage_match_required",
        f"{output_prefix}_final_lineage_matches",
    } <= failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        ),
        (
            "readiness_carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_final_route_enable_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    config = route_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )
    add_route_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_requires_route_complete_final_lineage_for_reconciled_target():
    config = route_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    check_prefix = f"{output_prefix}_route_final"
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
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_final_source_lineage_sha256_matches",
        ),
        (
            "cutover_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_final_cutover_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_route_final_route_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_blocks_invalid_route_complete_final_lineage(
    field,
    value,
    expected_failed_check,
):
    config = route_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = route_final_target_application_lineage_comparison(vendor)
    add_route_complete_final_target_application_lineage(
        config,
        vendor,
        **{field: value},
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_skips_final_lineage_for_non_reconciled_target():
    config = route_config()
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    input_prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert report.ready
    check_names = set(report.checks["check"])
    final_prefix = f"{output_prefix}_final_"
    assert not any(name.startswith(final_prefix) for name in check_names)
    assert f"{output_prefix}_dispatch_plan_review_carried_lineage_sha256_matches" not in check_names


def test_broker_dispatch_blocks_failed_route_broker_vendor_data_readiness():
    config = route_config()
    config["cutover_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config(
        ready=False,
        failed_checks=1,
    )
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    readiness = report.config["route_broker_vendor_data_readiness"]
    assert {
        "route_broker_vendor_data_readiness_ready",
        "route_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert summary["route_broker_vendor_data_readiness_provided"]
    assert not summary["route_broker_vendor_data_readiness_ready"]
    assert int(summary["route_broker_vendor_data_readiness_failed_checks"]) == 1
    assert readiness["provided"]
    assert not readiness["ready"]
    assert readiness["failed_checks"] == 1
    assert report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_broker_dispatch_blocks_bad_route_broker_vendor_market_data_batch():
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
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

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["adapter"] == "irage"
    assert vendor["market"] == "us_options_regular"
    assert vendor["failed_datasets"] == 1


def test_broker_dispatch_blocks_wrong_manifest_route_broker_vendor_market_data_batch():
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_carries_roundtrip_broker_vendor_market_data_batch():
    config = route_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["unique_mapping_drafts"] == 1


def test_broker_dispatch_blocks_wrong_manifest_roundtrip_vendor_market_data_batch():
    config = route_config()
    config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_prefers_route_broker_vendor_market_data_batch():
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        ready=False,
        adapter="irage",
        market="us_options_regular",
        failed_datasets=1,
        comparison_failed_checks=1,
    )
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
        upload_file_hash="abc123",
        thresholds=BrokerDispatchThresholds(require_dispatch_roundtrip=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == (
        "india_nse_index_derivatives"
    )
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["comparison"]["accepted"]


def test_broker_dispatch_blocks_bad_route_broker_vendor_market_data_batch_when_preferred():
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
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

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["adapter"] == "irage"
    assert vendor["market"] == "us_options_regular"
    assert vendor["failed_datasets"] == 1


def test_broker_dispatch_blocks_wrong_manifest_route_broker_vendor_market_data_batch_when_preferred():
    config = route_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["route_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_blocks_bad_route_broker_shadow_broker_readiness():
    config = route_config()
    config["cutover_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            ready_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
            broker_vendor_data_readiness_failed_checks=1,
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

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_shadow_broker_readiness_ready",
        "route_broker_shadow_broker_vendor_data_readiness_ready",
        "route_broker_shadow_broker_vendor_data_readiness_failed_checks",
        "route_broker_shadow_broker_adapter_matches",
        "route_broker_shadow_broker_adapter_consistent",
        "route_broker_shadow_broker_route_readiness_ready",
        "route_broker_shadow_broker_route_readiness_strategy_matches",
        "route_broker_shadow_broker_route_readiness_market_matches",
        "route_broker_shadow_broker_route_readiness_gap_pairs",
        "route_broker_shadow_broker_dispatch_roundtrip_ready",
        "route_broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "route_broker_shadow_broker_dispatch_roundtrip_market_matches",
        "route_broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "route_broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "route_broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "route_broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "route_broker_shadow_broker_route_dispatch_roundtrip_ready",
        "route_broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "route_broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "route_broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "failed_checks"
    ] == 1
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_blocks_partial_route_broker_shadow_broker_vendor_data_readiness():
    config = route_config()
    config["cutover_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "route_broker_shadow_broker_vendor_data_readiness_provided",
        "route_broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["route_broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_broker_dispatch_requires_route_readiness():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(route_readiness_provided=False, route_readiness_ready=False),
        route_enable_config=route_config(route_readiness_provided=False, route_readiness_ready=False),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_provided", "route_readiness_ready"} <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_broker_dispatch_blocks_route_readiness_identity_mismatch():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        route_enable_config=route_config(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_strategy_matches", "route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "us_options_regular"


def test_broker_dispatch_blocks_stale_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        route_enable_config=route_config(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        upload_orders=upload_orders(),
    )

    assert not report.ready
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


def test_broker_dispatch_blocks_stale_route_broker_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        route_enable_config=route_config(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        upload_orders=upload_orders(),
    )

    assert not report.ready
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


def test_broker_dispatch_carries_route_resume_route_readiness():
    config = route_config()
    config["cutover_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(),
        "incident_broker_route_readiness": resume_route_proof(route_ready_pairs=2),
    }

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["route_broker_resume_broker_route_readiness_ready"])
    assert summary["route_broker_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["route_broker_resume_incident_broker_route_readiness_route_ready_pairs"]) == 2
    assert report.config["route_broker_resume_gate"]["broker_route_readiness"]["ready"]
    assert (
        report.config["route_broker_resume_gate"]["incident_broker_route_readiness"]["route_ready_pairs"]
        == 2
    )


def test_broker_dispatch_blocks_bad_route_resume_route_readiness():
    config = route_config()
    config["cutover_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(
            ready=False,
            strategy="surface_mm",
            market="us_options_regular",
            route_ready_pairs=0,
            gap_pairs=2,
            recommendation="complete_route_gaps",
            ops_launch_controls_ready=False,
            ops_launch_control_failures="missing post-halt launch controls",
            ops_broker_roundtrip_portfolio_safe_runs=0,
            ops_broker_roundtrip_portfolio_breach_runs=1,
            ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
    }

    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=config,
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_broker_resume_broker_route_readiness_ready",
        "route_broker_resume_broker_route_readiness_strategy_matches",
        "route_broker_resume_broker_route_readiness_market_matches",
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


def test_broker_dispatch_requires_nested_route_dispatch_roundtrip():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(route_provided=False, route_ready=False),
        route_enable_config=route_config(route_provided=False, route_ready=False),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]
    assert not report.config["route_dispatch_roundtrip"]["provided"]


def test_broker_dispatch_requires_route_dispatch_roundtrip():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(dispatch_provided=False, dispatch_ready=False),
        route_enable_config=route_config(dispatch_provided=False, dispatch_ready=False),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_blocks_bad_route_dispatch_roundtrip_quality():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(
            dispatch_ready=False,
            dispatch_target_mode="shadow",
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_key="wrong-scenario",
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
        ),
        route_enable_config=route_config(
            dispatch_ready=False,
            dispatch_target_mode="shadow",
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_key="wrong-scenario",
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
        ),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_target_mode_matches",
        "route_dispatch_roundtrip_strategy_matches",
        "route_dispatch_roundtrip_market_matches",
        "route_dispatch_roundtrip_scenario_matches",
        "route_dispatch_roundtrip_missing_request_acks",
        "route_dispatch_roundtrip_rejected_orders",
        "route_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert report.config["route_dispatch_roundtrip"]["missing_request_acks"] == 1


def test_broker_dispatch_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        route_enable_config=route_config(route_enable_dispatch_roundtrip_failed_checks=1),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_reads_nested_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=route_config(route_enable_dispatch_roundtrip_failed_checks=1),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_blocks_duplicate_source_order_ids():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(),
        route_enable_config=route_config(),
        upload_orders=upload_orders(duplicate=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "unique_source_order_id" in failed


def test_broker_dispatch_blocks_disabled_route_enable():
    report = evaluate_broker_dispatch_plan(
        route_enable_summary=route_summary(ready=False),
        route_enable_config=route_config(enabled=False),
        upload_orders=upload_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enabled" in failed


def test_write_broker_dispatch_plan_outputs_artifacts_and_catalog_entry(tmp_path):
    route, upload = write_inputs(tmp_path)
    out_dir = tmp_path / "dispatch"

    report = write_broker_dispatch_plan(
        route_enable_dir=route,
        upload_pack_dir=upload,
        output_dir=out_dir,
    )

    assert report.ready
    assert (out_dir / "broker_dispatch_orders.csv").exists()
    assert (out_dir / "broker_dispatch_checks.csv").exists()
    assert (out_dir / "broker_dispatch_summary.csv").exists()
    assert (out_dir / "broker_dispatch_action_queue.csv").exists()
    assert (out_dir / "broker_dispatch_config.json").exists()
    assert (out_dir / "broker_dispatch_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    action_queue = pd.read_csv(out_dir / "broker_dispatch_action_queue.csv")
    config = json.loads((out_dir / "broker_dispatch_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_dispatch_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert action_queue.empty
    assert int(summary.loc[0, "action_queue_count"]) == 0
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert config["action_queue_count"] == 0
    assert config["next_actions"] == []
    assert runbook.startswith("# Broker Dispatch Runbook")
    assert "No broker dispatch actions." in runbook
    assert "broker_dispatch_action_queue.csv" in artifact_paths
    assert "broker_dispatch_runbook.md" in artifact_paths
    assert {"route_enable_summary", "route_enable_config", "route_enable_manifest", "upload_orders"} <= set(
        manifest["inputs"]
    )
    assert path_tail(manifest["inputs"]["route_enable_summary"]["path"]).endswith(
        "/route_enable/route_enable_summary.csv"
    )
    assert path_tail(manifest["inputs"]["route_enable_config"]["path"]).endswith(
        "/route_enable/route_enable_config.json"
    )
    assert path_tail(manifest["inputs"]["route_enable_manifest"]["path"]).endswith(
        "/route_enable/manifest.json"
    )
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_plan"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])
    assert bool(summary.loc[0, "route_enable_lineage_gate_passed"])
    assert summary.loc[0, "route_enable_manifest_sha256"] == file_sha256(route / "manifest.json")
    assert (
        summary.loc[0, "route_enable_cutover_runtime_scaleup_research_family_id"]
        == "india-leadlag-v1"
    )
    dispatch_orders = pd.read_csv(out_dir / "broker_dispatch_orders.csv")
    assert set(dispatch_orders["route_enable_cutover_runtime_scaleup_research_family_id"]) == {
        "india-leadlag-v1"
    }
    assert dispatch_orders["route_enable_lineage_gate_passed"].astype(bool).all()
    assert not dispatch_orders["authorizes_submission"].astype(bool).any()
    assert not bool(summary.loc[0, "authorizes_submission"])
    assert config["route_enable_lineage"]["route_enable_lineage_gate_passed"]
    assert not config["authorizes_submission"]
    assert {"route_enable_artifacts", "route_enable_dependencies"} <= set(manifest["inputs"])
    assert manifest["extra"]["route_enable_lineage_gate_passed"]
    assert not manifest["extra"]["authorizes_submission"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="broker_dispatch_plan",
        require_input_fingerprints=True,
    ).passed
    (tmp_path / "route_source.csv").write_text("source\nchanged\n", encoding="utf-8")
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="broker_dispatch_plan",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_broker_dispatch_blocks_drifted_route_enable_lineage(tmp_path):
    route, upload = write_inputs(tmp_path)
    (tmp_path / "route_source.csv").write_text("source\nchanged\n", encoding="utf-8")

    report = write_broker_dispatch_plan(
        route_enable_dir=route,
        upload_pack_dir=upload,
        output_dir=tmp_path / "dispatch",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {"route_enable_manifest_current", "route_enable_lineage_gate_passed"} <= failed
    assert report.action_queue.iloc[0]["next_gate"] == "review-route-enable"


def test_broker_dispatch_blocks_remanifested_route_contract_and_authorization_drift(tmp_path):
    route, upload = write_inputs(tmp_path)
    packet_path = route / "route_enable_packet.csv"
    packet = pd.read_csv(packet_path)
    packet.loc[0, "cutover_runtime_scaleup_research_family_id"] = "relabeled-family"
    packet.to_csv(packet_path, index=False)
    config_path = route / "route_enable_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["authorizes_submission"] = True
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    refresh_route_manifest(route, sync_lineage=False)

    report = write_broker_dispatch_plan(
        route_enable_dir=route,
        upload_pack_dir=upload,
        output_dir=tmp_path / "dispatch",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "route_enable_manifest_current" not in failed
    assert {
        "route_enable_lineage_contract_consistent",
        "route_enable_non_authorizing",
        "route_enable_lineage_gate_passed",
    } <= failed


def test_broker_dispatch_blocks_consistent_route_relabel_detached_from_cutover(tmp_path):
    route, upload = write_inputs(tmp_path)
    config = json.loads((route / "route_enable_config.json").read_text(encoding="utf-8"))
    detached_lineage = dict(config["cutover_lineage"])
    detached_lineage["cutover_runtime_scaleup_research_family_id"] = "relabeled-family"
    refresh_route_manifest(route, lineage_override=detached_lineage)

    report = write_broker_dispatch_plan(
        route_enable_dir=route,
        upload_pack_dir=upload,
        output_dir=tmp_path / "dispatch",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "route_enable_manifest_current" not in failed
    assert "route_enable_lineage_contract_consistent" not in failed
    assert "route_enable_non_authorizing" not in failed
    assert {
        "route_enable_cutover_matches_current",
        "route_enable_lineage_gate_passed",
    } <= failed


def test_broker_dispatch_rejects_route_output_collision(tmp_path):
    route, upload = write_inputs(tmp_path)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_broker_dispatch_plan(
            route_enable_dir=route,
            upload_pack_dir=upload,
            output_dir=route,
        )


def test_cli_broker_dispatch_hydrates_broker_vendor_data_from_route_manifest_chain(tmp_path):
    route, upload = write_inputs(tmp_path)
    cutover = tmp_path / "cutover"
    broker_config = cutover / "broker_readiness_config.json"
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
    refresh_cutover_manifest(cutover)
    refresh_route_manifest(route)
    out_dir = tmp_path / "dispatch"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    config = json.loads((out_dir / "broker_dispatch_config.json").read_text(encoding="utf-8"))
    vendor = config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert int(summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "route_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64


def test_cli_broker_dispatch_blocks_target_sidecar_without_route_lineage(tmp_path):
    route, upload = write_inputs(tmp_path)
    cutover = tmp_path / "cutover"
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    broker_config = cutover / "broker_readiness_config.json"
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
                    "broker_dispatch_roundtrip_vendor_market_data_batch": vendor,
                    "vendor_market_data_batch_lineage_comparison": {
                        "required": lineage["required"],
                        "matches": lineage["matches"],
                        "current_application_lineage_sha256": lineage[
                            "current_application_lineage_sha256"
                        ],
                        "broker_application_lineage_sha256": lineage[
                            "broker_application_lineage_sha256"
                        ],
                        "carried_application_lineage_sha256": lineage[
                            "scaleup_carried_application_lineage_sha256"
                        ],
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    refresh_cutover_manifest(cutover)
    refresh_route_manifest(route)
    out_dir = tmp_path / "dispatch"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_route_carried_lineage_sha256_matches",
        f"{prefix}_final_lineage_match_required",
        f"{prefix}_final_lineage_matches",
    } <= failed


def test_cli_broker_dispatch_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    route, upload = write_inputs(tmp_path)
    cutover = tmp_path / "cutover"
    broker_config = cutover / "broker_readiness_config.json"
    broker_config.write_text(
        json.dumps(
            {
                "ready": True,
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
    refresh_cutover_manifest(cutover)
    refresh_route_manifest(route)
    out_dir = tmp_path / "dispatch"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_checks.csv")
    config = json.loads((out_dir / "broker_dispatch_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    readiness = config["route_broker_vendor_data_readiness"]
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        "route_broker_vendor_data_readiness_ready",
        "route_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary.loc[0, "route_broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "route_broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "route_broker_vendor_data_readiness_failed_checks"]) == 1
    assert readiness["provided"]
    assert not readiness["ready"]
    assert readiness["failed_checks"] == 1
    assert config["route_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_cli_broker_dispatch_reads_launch_pipeline_upload_roots(tmp_path):
    cases = [
        ("leadlag", "05_upload_pack"),
        ("imbalance", "05_upload_pack"),
        ("parity", "05_upload_pack"),
        ("surface_mm", "04_upload_pack"),
    ]
    for family, upload_folder in cases:
        case_dir = tmp_path / family
        route, _upload = write_inputs(case_dir)
        pipeline = case_dir / f"{family}_launch_pipeline"
        upload_dir = pipeline / upload_folder
        out_dir = case_dir / "dispatch"
        upload_dir.mkdir(parents=True)
        upload_orders().to_csv(upload_dir / "broker_upload_orders.csv", index=False)

        code = main(
            [
                "plan-broker-dispatch",
                "--route-enable",
                str(route),
                "--upload-pack",
                str(pipeline),
                "--out",
                str(out_dir),
                "--fail-on-breach",
            ]
        )

        summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
        dispatch = pd.read_csv(out_dir / "broker_dispatch_orders.csv")
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert code == 0
        assert bool(summary.loc[0, "ready"])
        assert len(dispatch) == 2
        assert path_tail(manifest["inputs"]["route_enable_summary"]["path"]).endswith(
            f"/{family}/route_enable/route_enable_summary.csv"
        )
        assert path_tail(manifest["inputs"]["route_enable_config"]["path"]).endswith(
            f"/{family}/route_enable/route_enable_config.json"
        )
        assert path_tail(manifest["inputs"]["route_enable_manifest"]["path"]).endswith(
            f"/{family}/route_enable/manifest.json"
        )
        assert path_tail(manifest["inputs"]["upload_orders"]["path"]).endswith(
            f"/{family}_launch_pipeline/{upload_folder}/broker_upload_orders.csv"
        )


def test_cli_broker_dispatch_fails_on_disabled_route(tmp_path):
    route, upload = write_inputs(tmp_path, route_ready=False)
    out_dir = tmp_path / "dispatch"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_checks.csv")
    action_queue = pd.read_csv(out_dir / "broker_dispatch_action_queue.csv")
    config = json.loads((out_dir / "broker_dispatch_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_enabled" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "action_queue_count"]) >= 1
    assert int(summary.loc[0, "blocked_action_count"]) >= 1
    assert summary.loc[0, "next_gate"] == "review-route-enable"
    assert summary.loc[0, "next_gate_help_command"] == "python -m hft_cli review-route-enable --help"
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "component"] == "route_enable"
    assert action_queue.loc[0, "check"] == "route_enabled"
    assert action_queue.loc[0, "next_gate"] == "review-route-enable"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli review-route-enable --help"
    assert config["action_queue_count"] >= 1
    assert config["blocked_action_count"] >= 1
    assert config["primary_action"]["check"] == "route_enabled"
    assert config["next_actions"][0]["next_gate"] == "review-route-enable"


def test_cli_broker_dispatch_can_fail_on_actions(tmp_path):
    route, upload = write_inputs(tmp_path, route_ready=False)
    out_dir = tmp_path / "dispatch"
    blocked_dir = tmp_path / "dispatch_blocked"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--fail-on-actions",
        ]
    )
    blocked_code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(blocked_dir),
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    action_queue = pd.read_csv(out_dir / "broker_dispatch_action_queue.csv")
    assert code == 2
    assert blocked_code == 2
    assert int(summary.loc[0, "action_queue_count"]) == len(action_queue)
    assert int(summary.loc[0, "blocked_action_count"]) >= 1
    assert action_queue.loc[0, "next_gate"] == "review-route-enable"


def test_cli_broker_dispatch_can_require_dispatch_roundtrip(tmp_path):
    route, upload = write_inputs(tmp_path, dispatch=False)
    out_dir = tmp_path / "dispatch"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_dispatch_roundtrip_provided" in failed


def test_cli_broker_dispatch_can_require_route_readiness(tmp_path):
    route, upload = write_inputs(tmp_path, route_readiness=False)
    out_dir = tmp_path / "dispatch"

    code = main(
        [
            "plan-broker-dispatch",
            "--route-enable",
            str(route),
            "--upload-pack",
            str(upload),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_readiness_provided" in failed
