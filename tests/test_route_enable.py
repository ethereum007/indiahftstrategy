import hashlib
import json

import pandas as pd
import pytest

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import file_sha256, verify_experiment_manifest, write_experiment_manifest
from reports.operational_lineage import (
    empty_runtime_session_lineage,
    runtime_session_lineage_fields,
)
from reports.route_enable import (
    RouteEnableThresholds,
    evaluate_route_enable_packet,
    write_route_enable_packet,
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
    }


def cutover_final_target_application_lineage_comparison(vendor, **overrides):
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def cutover_complete_final_target_application_lineage_comparison(
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def cutover_view_28_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = cutover_complete_final_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "cutover_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def add_cutover_complete_final_target_application_lineage(
    config,
    vendor,
    **overrides,
):
    config[
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = cutover_complete_final_target_application_lineage_comparison(
        vendor,
        **overrides,
    )


def cutover_summary(
    ready=True,
    max_orders=10,
    max_notional=100_000.0,
    adapter="arrow_money",
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
                "adapter": adapter,
                "max_orders_per_session": max_orders,
                "max_notional_per_session": max_notional,
                "runtime_strategy_portfolio_required": strategy_portfolio_required,
                "runtime_strategy_portfolio_provided": strategy_portfolio_provided,
                "runtime_strategy_portfolio_ready": strategy_portfolio_ready,
                "runtime_strategy_portfolio_deployment_mode": "paper_shadow",
                "runtime_strategy_portfolio_allocation_mode": "readiness_weighted",
                "runtime_strategy_portfolio_capital_currency": "INR",
                "runtime_strategy_portfolio_selected_profile": "leadlag-live-dryrun",
                "runtime_strategy_portfolio_selected_strategy": strategy_portfolio_selected_strategy,
                "runtime_strategy_portfolio_selected_market": strategy_portfolio_selected_market,
                "runtime_strategy_portfolio_selected_eligible": strategy_portfolio_selected_eligible,
                "runtime_strategy_portfolio_selected_allocation_weight": 0.0012
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "runtime_strategy_portfolio_selected_allocation_notional": (
                    strategy_portfolio_selected_allocation_notional
                ),
                "runtime_strategy_portfolio_notional_cap_applied": bool(
                    strategy_portfolio_selected_allocation_notional
                ),
                "runtime_strategy_portfolio_min_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "runtime_strategy_portfolio_min_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "runtime_strategy_portfolio_max_strategy_weight": 0.60
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "runtime_strategy_portfolio_max_market_weight": 0.90
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "runtime_strategy_portfolio_allocated_strategy_count": 2
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "runtime_strategy_portfolio_allocated_market_count": 1
                if strategy_portfolio_selected_allocation_notional
                else 0,
                "runtime_strategy_portfolio_top_strategy_by_weight": (
                    strategy_portfolio_selected_strategy
                    if strategy_portfolio_selected_allocation_notional
                    else ""
                ),
                "runtime_strategy_portfolio_top_market_by_weight": (
                    strategy_portfolio_selected_market if strategy_portfolio_selected_allocation_notional else ""
                ),
                "runtime_strategy_portfolio_max_strategy_allocation_weight": 0.45
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "runtime_strategy_portfolio_max_market_allocation_weight": 0.80
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "runtime_pre_portfolio_max_notional_per_session": 25_000.0
                if strategy_portfolio_selected_allocation_notional
                else 0.0,
                "proof_refresh_ready": True,
                "proof_refresh_strategy": "lead_lag_taker",
                "proof_refresh_market": "india_nse_index_derivatives",
                "broker_schema_status": broker_schema_status,
                "broker_schema_reviewed": broker_schema_reviewed,
                "broker_schema_review_mode": broker_schema_review_mode,
                "broker_resume_gate_ready": False,
                "broker_resume_proof_refresh_ready": False,
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
                "scaleup_route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
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
                "scaleup_route_readiness_required": route_readiness_required,
                "scaleup_route_readiness_provided": route_readiness_provided,
                "scaleup_route_readiness_ready": route_readiness_ready,
                "scaleup_route_readiness_strategy": route_readiness_strategy,
                "scaleup_route_readiness_market": route_readiness_market,
                "scaleup_route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "scaleup_route_readiness_gap_pairs": route_readiness_gap_pairs,
                "scaleup_route_readiness_recommendation": route_readiness_recommendation,
                "scaleup_route_readiness_ops_launch_controls_present": route_ops_launch_controls_present,
                "scaleup_route_readiness_ops_launch_controls_blocked_pairs": route_ops_launch_controls_blocked_pairs,
                "scaleup_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "scaleup_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
                "scaleup_broker_route_readiness_required": broker_route_readiness_required,
                "scaleup_broker_route_readiness_provided": broker_route_readiness_provided,
                "scaleup_broker_route_readiness_ready": broker_route_readiness_ready,
                "scaleup_broker_route_readiness_strategy": broker_route_readiness_strategy,
                "scaleup_broker_route_readiness_market": broker_route_readiness_market,
                "scaleup_broker_route_readiness_route_ready_pairs": broker_route_readiness_route_ready_pairs,
                "scaleup_broker_route_readiness_gap_pairs": broker_route_readiness_gap_pairs,
                "scaleup_broker_route_readiness_recommendation": broker_route_readiness_recommendation,
                "scaleup_broker_route_readiness_ops_launch_controls_ready": (
                    broker_route_readiness_ops_launch_controls_ready
                ),
                "scaleup_broker_route_readiness_ops_launch_control_failures": (
                    broker_route_readiness_ops_launch_control_failures
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "scaleup_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "failed_checks": 0 if ready else 1,
                "recommendation": "allow_live_dryrun_cutover" if ready else "keep_cutover_disabled",
            }
        ]
    )


def cutover_config(
    max_orders=10,
    max_notional=100_000.0,
    adapter="arrow_money",
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
        "ready": True,
        "target_mode": "live_dryrun",
        "strategy": "lead_lag_taker",
        "market": "india_nse_index_derivatives",
        "scenario_key": "trigger_ticks=2",
        "adapter": adapter,
        "limits": {
            "max_orders_per_session": max_orders,
            "max_notional_per_session": max_notional,
            "stop_loss": 5_000.0,
        },
        "proof_freshness": {
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
        },
        "runtime_session": {
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
                    strategy_portfolio_selected_strategy
                    if strategy_portfolio_selected_allocation_notional
                    else ""
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
            }
        },
        "scaleup_route_readiness": {
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
        "scaleup_broker_route_readiness": {
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
        "broker_readiness": {
            "adapter_schema_status": broker_schema_status,
            "schema_reviewed": broker_schema_reviewed,
            "schema_review_mode": broker_schema_review_mode,
            "resume_gate": {
                "provided": False,
                "ready": False,
                "proof_refresh_ready": False,
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
            },
        },
        "scaleup_dispatch_roundtrip": {
            "route_enable_dispatch_roundtrip": {
                "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
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


def with_cutover_broker_vendor_batch_summary(summary, vendor):
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
        final_lineage = cutover_final_target_application_lineage_comparison(vendor)
        cutover_complete_final = (
            cutover_complete_final_target_application_lineage_comparison(vendor)
        )
        final_prefix = "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"
        complete_final_prefix = (
            "scaleup_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        ] = cutover_complete_final["required"]
        result.loc[0, f"{complete_final_prefix}_lineage_matches"] = (
            cutover_complete_final["matches"]
        )
        for field, value in cutover_complete_final.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{complete_final_prefix}_{field}"] = value
    return result


def broker_vendor_data_readiness_config(provided=True, ready=True, failed_checks=0):
    return {
        "provided": provided,
        "ready": ready,
        "failed_checks": failed_checks,
    }


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


def upload_summary(ready=True, orders=2, adapter="arrow_money"):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "orders": orders,
                "target_columns": 16,
                "lifecycle_orders": orders,
                "replace_orders": 1 if orders > 1 else 0,
                "failed_checks": 0 if ready else 1,
                "output_file": "broker_upload_orders.csv",
                "mapping_file": "broker_upload_mapping.csv",
                "recommendation": "dry_run_or_paper_review" if ready else "review_vendor_schema",
            }
        ]
    )


def order_export_summary(ready=True, orders=2, adapter="arrow_money", total_notional=25_000.0):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "launch_mode": "shadow",
                "scenario_key": "trigger_ticks=2",
                "orders": orders,
                "total_qty": 150,
                "total_notional": total_notional,
                "max_order_notional": total_notional / max(orders, 1),
                "failed_checks": 0 if ready else 1,
            }
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
            "scaleup_manifest_required": True,
            "scaleup_manifest_provided": True,
            "scaleup_manifest_current": True,
            "scaleup_manifest_run_type": "scaleup_plan",
            "scaleup_manifest_path": "scaleup/manifest.json",
            "scaleup_manifest_sha256": "b" * 64,
            "scaleup_contract_consistent": True,
            "scaleup_non_authorizing": True,
            "scaleup_source_ready": True,
            "scaleup_provenance_gate_passed": True,
            "scaleup_research_family_bound": True,
            "scaleup_research_family_provenance_current": True,
            "scaleup_research_family_id": "india-leadlag-v1",
            "scaleup_research_family_registration_id": "RF-INDIA-LEADLAG-1",
            "scaleup_research_family_manifest_sha256": "c" * 64,
            "runtime_telemetry_scaleup_provenance_carried": True,
            "runtime_telemetry_scaleup_provenance_gate_passed": True,
            "runtime_telemetry_scaleup_manifest_sha256": "b" * 64,
            "runtime_telemetry_scaleup_manifest_matches_current": True,
            "runtime_telemetry_research_family_bound": True,
            "runtime_telemetry_research_family_provenance_current": True,
            "runtime_telemetry_research_family_id": "india-leadlag-v1",
            "runtime_telemetry_research_family_registration_id": "RF-INDIA-LEADLAG-1",
            "runtime_telemetry_research_family_manifest_sha256": "c" * 64,
            "runtime_telemetry_research_family_matches_current": True,
            "runtime_telemetry_lineage_matches_current": True,
        }
    )
    return runtime_session_lineage_fields(state)


def refresh_cutover_manifest(cutover):
    lineage = cutover_runtime_lineage()
    write_experiment_manifest(
        cutover,
        run_type="cutover_gate",
        inputs={
            "broker_readiness_config": cutover / "broker_readiness_config.json",
            "cutover_source": cutover.parent / "cutover_source.csv",
        },
        extra={
            "ready": bool(pd.read_csv(cutover / "cutover_summary.csv").iloc[0]["ready"]),
            **lineage,
            "authorizes_submission": False,
        },
    )


def write_inputs(
    root,
    *,
    cutover_ready=True,
    upload_ready=True,
    upload_orders=2,
    export_notional=25_000.0,
    dispatch=True,
    route_readiness=True,
):
    cutover = root / "cutover"
    upload = root / "upload"
    export = root / "export"
    cutover.mkdir(parents=True)
    upload.mkdir()
    export.mkdir()
    lineage = cutover_runtime_lineage()
    summary = cutover_summary(
        ready=cutover_ready,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    )
    for column, value in lineage.items():
        summary[column] = value
    summary["authorizes_submission"] = False
    summary.to_csv(cutover / "cutover_summary.csv", index=False)
    config = cutover_config(
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    )
    config["runtime_lineage"] = lineage
    config["authorizes_submission"] = False
    (cutover / "cutover_config.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame([{"route_enabled": cutover_ready, "authorizes_submission": False}]).to_csv(
        cutover / "cutover_authorization.csv", index=False
    )
    pd.DataFrame([{"check": "fixture", "passed": cutover_ready}]).to_csv(
        cutover / "cutover_checks.csv", index=False
    )
    pd.DataFrame(columns=["priority", "action"]).to_csv(
        cutover / "cutover_action_queue.csv", index=False
    )
    (cutover / "cutover_runbook.md").write_text("# Cutover Fixture\n", encoding="utf-8")
    (cutover / "broker_readiness_config.json").write_text("{}\n", encoding="utf-8")
    pd.DataFrame([{"source": "fixture"}]).to_csv(root / "cutover_source.csv", index=False)
    refresh_cutover_manifest(cutover)
    upload_summary(ready=upload_ready, orders=upload_orders).to_csv(upload / "broker_upload_summary.csv", index=False)
    order_export_summary(orders=upload_orders, total_notional=export_notional).to_csv(
        export / "broker_order_summary.csv",
        index=False,
    )
    return cutover, upload, export


def test_route_enable_accepts_ready_cutover_and_upload_pack():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=cutover_config(),
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    packet = report.packet.iloc[0]
    assert bool(packet["route_enabled"])
    assert packet["route_state"] == "enabled"
    assert packet["target_mode"] == "live_dryrun"
    assert packet["adapter"] == "arrow_money"
    assert int(packet["upload_orders"]) == 2
    assert report.summary.iloc[0]["recommendation"] == "enable_broker_route"
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert report.config["route_enabled"]
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.config["upload"]["output_file"] == "broker_upload_orders.csv"
    assert bool(report.summary.iloc[0]["broker_schema_reviewed"])
    assert report.summary.iloc[0]["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["broker_readiness"]["schema_reviewed"]
    assert report.config["broker_readiness"]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert bool(report.summary.iloc[0]["dispatch_roundtrip_ready"])
    assert report.config["dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-1"
    assert int(report.summary.iloc[0]["dispatch_roundtrip_failed_checks"]) == 0
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["dispatch_roundtrip"]["failed_checks"] == 0
    assert report.config["dispatch_roundtrip"]["route_enable_dispatch_roundtrip"]["failed_checks"] == 0
    assert bool(report.summary.iloc[0]["route_dispatch_roundtrip_ready"])
    assert report.config["dispatch_roundtrip"]["route_proof"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["dispatch_roundtrip"]["route_proof"]["requests"] == 2
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
    assert bool(report.summary.iloc[0]["cutover_broker_route_readiness_ready"])
    assert report.summary.iloc[0]["cutover_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(report.summary.iloc[0]["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    assert report.config["cutover_broker_route_readiness"]["ops_launch_controls_ready"]
    assert report.config["cutover_broker_route_readiness"]["ops_broker_roundtrip_portfolio_concentration_ok_runs"] == 1


def test_route_enable_carries_strategy_portfolio_allocation():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
            max_notional=1200.0,
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
        ),
        cutover_config=cutover_config(
            max_notional=1200.0,
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
        ),
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(total_notional=1_000.0),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    packet = report.packet.iloc[0]
    summary = report.summary.iloc[0]
    portfolio = report.config["strategy_portfolio"]
    assert bool(packet["strategy_portfolio_required"])
    assert bool(summary["strategy_portfolio_ready"])
    assert summary["strategy_portfolio_deployment_mode"] == "paper_shadow"
    assert summary["strategy_portfolio_allocation_mode"] == "readiness_weighted"
    assert summary["strategy_portfolio_capital_currency"] == "INR"
    assert summary["strategy_portfolio_selected_profile"] == "leadlag-live-dryrun"
    assert summary["strategy_portfolio_selected_strategy"] == "lead_lag_taker"
    assert summary["strategy_portfolio_selected_market"] == "india_nse_index_derivatives"
    assert bool(summary["strategy_portfolio_selected_eligible"])
    assert summary["strategy_portfolio_selected_allocation_weight"] == 0.0012
    assert summary["strategy_portfolio_selected_allocation_notional"] == 1200.0
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
    assert portfolio["selected_allocation_notional"] == 1200.0
    assert portfolio["min_strategy_count"] == 2
    assert portfolio["allocated_strategy_count"] == 2
    assert portfolio["top_strategy_by_weight"] == "lead_lag_taker"
    assert portfolio["max_strategy_allocation_weight"] == 0.45
    assert portfolio["pre_portfolio_max_notional_per_session"] == 25_000.0


def test_route_enable_blocks_order_export_above_strategy_portfolio_allocation():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
            max_notional=2_500.0,
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
        ),
        cutover_config=cutover_config(
            max_notional=2_500.0,
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1200.0,
        ),
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(total_notional=1_500.0),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "order_export_notional_within_strategy_portfolio_allocation" in failed
    assert "order_export_notional_within_cutover_limit" not in failed
    assert report.config["primary_blocker"]["check"] == "order_export_notional_within_strategy_portfolio_allocation"


def test_route_enable_carries_cutover_shadow_broker_readiness():
    config = cutover_config()
    config["scaleup_shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
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


def test_route_enable_blocks_bad_cutover_shadow_broker_readiness():
    config = cutover_config()
    config["scaleup_shadow_broker_readiness"] = shadow_broker_config(
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

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_shadow_broker_readiness_ready",
        "cutover_shadow_broker_vendor_data_readiness_ready",
        "cutover_shadow_broker_vendor_data_readiness_failed_checks",
        "cutover_shadow_broker_adapter_matches",
        "cutover_shadow_broker_adapter_consistent",
        "cutover_shadow_broker_route_readiness_ready",
        "cutover_shadow_broker_route_readiness_strategy_matches",
        "cutover_shadow_broker_route_readiness_market_matches",
        "cutover_shadow_broker_route_readiness_gap_pairs",
        "cutover_shadow_broker_dispatch_roundtrip_ready",
        "cutover_shadow_broker_dispatch_roundtrip_strategy_matches",
        "cutover_shadow_broker_dispatch_roundtrip_market_matches",
        "cutover_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "cutover_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "cutover_shadow_broker_dispatch_roundtrip_rejected_orders",
        "cutover_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "cutover_shadow_broker_route_dispatch_roundtrip_ready",
        "cutover_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "cutover_shadow_broker_route_dispatch_roundtrip_market_matches",
        "cutover_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_route_enable_blocks_partial_cutover_shadow_broker_vendor_data_readiness():
    config = cutover_config()
    config["scaleup_shadow_broker_readiness"] = shadow_broker_config(
        broker_vendor_data_readiness_sessions=1,
        broker_vendor_data_readiness_provided_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "cutover_shadow_broker_vendor_data_readiness_provided",
        "cutover_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_route_enable_carries_cutover_broker_shadow_broker_readiness():
    config = cutover_config()
    config["scaleup_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert summary["cutover_broker_shadow_broker_readiness_provided"]
    assert int(summary["cutover_broker_shadow_broker_readiness_sessions"]) == 2
    assert int(summary["cutover_broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["cutover_broker_shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["cutover_broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["cutover_broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["cutover_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["cutover_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["cutover_broker_shadow_broker_readiness"]["provided"]
    assert report.config["cutover_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "ready_sessions"
    ] == 2
    assert report.config["cutover_broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["cutover_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["cutover_broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["cutover_broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_route_enable_carries_cutover_vendor_market_data_batch():
    config = cutover_config()
    config["scaleup_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["cutover_vendor_market_data_batch"]
    assert report.ready
    assert summary["cutover_vendor_market_data_batch_provided"]
    assert summary["cutover_vendor_market_data_batch_ready"]
    assert summary["cutover_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["cutover_vendor_market_data_batch_kind"] == "ticks"
    assert summary["cutover_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["cutover_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["cutover_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["cutover_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["cutover_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["cutover_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["cutover_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["cutover_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_route_enable_carries_cutover_broker_vendor_market_data_batch():
    config = cutover_config()
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert (
        summary[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"
        ]
        == 1.0
    )
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
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


def test_route_enable_carries_target_application_vendor_batch_from_cutover_config():
    config = cutover_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor_input = target_application_vendor_market_data_batch_config()
    config[prefix] = vendor_input
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor_input)
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor_input)
    )
    add_cutover_complete_final_target_application_lineage(config, vendor_input)

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert summary[f"{prefix}_application_lineage_consistency_required"]
    assert summary[f"{prefix}_application_lineage_consistent"]
    assert summary["cutover_broker_vendor_market_data_batch_lineage_match_required"]
    assert summary["cutover_broker_vendor_market_data_batch_lineage_matches"]
    assert summary["cutover_vendor_market_data_batch_application_lineage_sha256"] == lineage_sha256
    assert (
        summary["cutover_broker_vendor_market_data_batch_application_lineage_sha256"]
        == lineage_sha256
    )
    assert (
        summary[
            "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert summary[f"{prefix}_application_lineage_sha256"] == lineage_sha256
    assert (
        summary[
            "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
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
    }
    final_lineage = report.config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == lineage_sha256
    cutover_complete_prefix = (
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
    ):
        assert summary[f"{cutover_complete_prefix}_{field}"] == lineage_sha256
    route_complete_final = report.config[
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert route_complete_final["required"]
    assert route_complete_final["matches"]
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
        "carried_application_lineage_sha256",
    ):
        assert route_complete_final[field] == lineage_sha256
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
        f"{prefix}_route_enable_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_lineage_match_required",
        f"{prefix}_cutover_final_lineage_matches",
        f"{prefix}_cutover_final_source_lineage_sha256_matches",
        f"{prefix}_cutover_final_compatibility_broker_lineage_sha256_matches",
        f"{prefix}_cutover_final_compatibility_cutover_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_prior_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_prior_cutover_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_route_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_send_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_ack_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_roundtrip_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_readiness_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_scaleup_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_cutover_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_route_enable_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_send_packet_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_broker_readiness_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_scaleup_final_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_cutover_final_review_carried_lineage_sha256_matches",
        f"{prefix}_cutover_final_route_final_review_carried_lineage_sha256_matches",
    }
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


def test_route_enable_blocks_cutover_complete_final_lineage_drift():
    config = cutover_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor_input = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    config[prefix] = vendor_input
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor_input)
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor_input)
    )
    config[
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = cutover_complete_final_target_application_lineage_comparison(
        vendor_input,
        lineage_sha256="f" * 64,
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert not report.ready
    check_prefix = f"{prefix}_cutover_final"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_cutover_carried_lineage_sha256_matches",
        f"{check_prefix}_route_final_review_carried_lineage_sha256_matches",
    } <= failed
    compatibility = report.config[f"{prefix}_lineage_comparison"]
    route_final = report.config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert compatibility["broker_application_lineage_sha256"] == lineage_sha256
    assert route_final["broker_application_lineage_sha256"] == lineage_sha256
    assert route_final["carried_application_lineage_sha256"] == lineage_sha256
    route_complete_final = report.config[
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert route_complete_final["broker_application_lineage_sha256"] == "f" * 64
    assert route_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_route_enable_preserves_view_20_contract_when_cutover_view_28_differs():
    config = cutover_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    vendor_input = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    config[prefix] = vendor_input
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor_input)
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor_input)
    )
    add_cutover_complete_final_target_application_lineage(config, vendor_input)
    config[
        "cutover_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = cutover_view_28_target_application_lineage_comparison(
        vendor_input,
        lineage_sha256="f" * 64,
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    cutover_final = report.config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    route_final = report.config[
        "route_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert cutover_final["broker_application_lineage_sha256"] == lineage_sha256
    assert cutover_final["carried_application_lineage_sha256"] == lineage_sha256
    assert route_final["broker_application_lineage_sha256"] == lineage_sha256
    assert route_final["cutover_final_review_carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert route_final["carried_application_lineage_sha256"] == lineage_sha256


def test_route_enable_carries_target_application_vendor_batch_from_cutover_summary():
    vendor = target_application_vendor_market_data_batch_config()
    summary_input = with_cutover_broker_vendor_batch_summary(cutover_summary(), vendor)

    report = evaluate_route_enable_packet(
        cutover_summary=summary_input,
        cutover_config=cutover_config(),
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    carried = report.config[prefix]
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    assert carried["datasets"][1]["mapping_scope_review_id"] == "scope-review-1"
    final_lineage = report.config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["scaleup_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["cutover_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]


def test_route_enable_blocks_incomplete_target_application_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config(
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
    )
    vendor["datasets"][1]["mapping_application_sha256"] = ""
    config = cutover_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = cutover_final_target_application_lineage_comparison(vendor)
    add_cutover_complete_final_target_application_lineage(config, vendor)

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
    } <= failed


def test_route_enable_blocks_target_application_lineage_drift_after_cutover():
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    config = cutover_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = lineage
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor)
    )
    cutover_complete_final = (
        cutover_complete_final_target_application_lineage_comparison(vendor)
    )
    vendor["datasets"][1]["mapping_application_sha256"] = "9" * 64
    config[
        "cutover_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = cutover_complete_final

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert f"{prefix}_route_carried_lineage_sha256_matches" in failed
    assert f"{prefix}_route_enable_review_carried_lineage_sha256_matches" in failed
    assert {
        f"{prefix}_source_lineage_sha256_matches",
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_final_cutover_review_carried_lineage_sha256_matches",
    } <= passed


@pytest.mark.parametrize(
    ("lineage_mutation", "vendor_overrides", "expected_check"),
    [
        (
            {"matches": False},
            {},
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ),
        (
            {"current_application_lineage_sha256": "f" * 64},
            {},
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        ),
        (
            {},
            {"application_lineage_consistent": False},
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        ),
    ],
)
def test_route_enable_blocks_failed_cutover_target_lineage_decisions(
    lineage_mutation,
    vendor_overrides,
    expected_check,
):
    vendor = target_application_vendor_market_data_batch_config(**vendor_overrides)
    lineage = target_application_lineage_comparison(vendor)
    lineage.update(lineage_mutation)
    config = cutover_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = lineage
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor)
    )
    add_cutover_complete_final_target_application_lineage(config, vendor)

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert expected_check in failed


def test_route_enable_requires_final_lineage_comparison_for_reconciled_target():
    config = cutover_config()
    vendor = target_application_vendor_market_data_batch_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    add_cutover_complete_final_target_application_lineage(config, vendor)

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
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
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        ),
        (
            "readiness_carried_application_lineage_sha256",
            "f" * 64,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_final_cutover_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_route_enable_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    config = cutover_config()
    vendor = target_application_vendor_market_data_batch_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(
            vendor,
            **{field: value},
        )
    )
    add_cutover_complete_final_target_application_lineage(config, vendor)

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_route_enable_requires_cutover_complete_final_lineage_for_reconciled_target():
    config = cutover_config()
    vendor = target_application_vendor_market_data_batch_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor)
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    check_prefix = f"{prefix}_cutover_final"
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
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_cutover_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_cutover_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_cutover_final_source_lineage_sha256_matches",
        ),
        (
            "scaleup_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_cutover_final_scaleup_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_cutover_final_cutover_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_route_enable_blocks_invalid_cutover_complete_final_lineage(
    field,
    value,
    expected_failed_check,
):
    config = cutover_config()
    vendor = target_application_vendor_market_data_batch_config()
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[f"{prefix}_lineage_comparison"] = (
        cutover_final_target_application_lineage_comparison(vendor)
    )
    add_cutover_complete_final_target_application_lineage(
        config,
        vendor,
        **{field: value},
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_route_enable_skips_final_lineage_for_non_reconciled_target():
    config = cutover_config()
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[prefix] = vendor
    config[
        "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert report.ready
    check_names = set(report.checks["check"])
    final_prefix = f"{prefix}_final_"
    assert not any(name.startswith(final_prefix) for name in check_names)
    assert f"{prefix}_route_enable_review_carried_lineage_sha256_matches" not in check_names


def test_route_enable_blocks_failed_cutover_broker_vendor_data_readiness():
    config = cutover_config()
    config["scaleup_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config(
        ready=False,
        failed_checks=1,
    )
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    readiness = report.config["cutover_broker_vendor_data_readiness"]
    assert {
        "cutover_broker_vendor_data_readiness_ready",
        "cutover_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert summary["cutover_broker_vendor_data_readiness_provided"]
    assert not summary["cutover_broker_vendor_data_readiness_ready"]
    assert int(summary["cutover_broker_vendor_data_readiness_failed_checks"]) == 1
    assert readiness["provided"]
    assert not readiness["ready"]
    assert readiness["failed_checks"] == 1
    assert report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_route_enable_blocks_bad_cutover_broker_vendor_market_data_batch():
    config = cutover_config()
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
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

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["adapter"] == "irage"
    assert vendor["market"] == "us_options_regular"
    assert vendor["failed_datasets"] == 1


def test_route_enable_blocks_wrong_manifest_cutover_broker_vendor_market_data_batch():
    config = cutover_config()
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_route_enable_prefers_cutover_broker_vendor_market_data_batch():
    config = cutover_config()
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        ready=False,
        adapter="irage",
        market="us_options_regular",
        failed_datasets=1,
        comparison_failed_checks=1,
    )
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == (
        "india_nse_index_derivatives"
    )
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]


def test_route_enable_carries_roundtrip_broker_vendor_market_data_batch():
    config = cutover_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
        order_export_summary=order_export_summary(),
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    summary = report.summary.iloc[0]
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert (
        summary[
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"
        ]
        == 1.0
    )
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1


def test_route_enable_blocks_wrong_manifest_roundtrip_vendor_market_data_batch():
    config = cutover_config()
    config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_route_enable_blocks_bad_cutover_broker_vendor_market_data_batch_when_preferred():
    config = cutover_config()
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
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

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_ready",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["adapter"] == "irage"
    assert vendor["market"] == "us_options_regular"
    assert vendor["failed_datasets"] == 1


def test_route_enable_blocks_wrong_manifest_cutover_broker_vendor_market_data_batch_when_preferred():
    config = cutover_config()
    config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_route_enable_blocks_bad_cutover_broker_shadow_broker_readiness():
    config = cutover_config()
    config["scaleup_broker_shadow_broker_readiness"] = {
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

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_broker_shadow_broker_readiness_ready",
        "cutover_broker_shadow_broker_vendor_data_readiness_ready",
        "cutover_broker_shadow_broker_vendor_data_readiness_failed_checks",
        "cutover_broker_shadow_broker_adapter_matches",
        "cutover_broker_shadow_broker_adapter_consistent",
        "cutover_broker_shadow_broker_route_readiness_ready",
        "cutover_broker_shadow_broker_route_readiness_strategy_matches",
        "cutover_broker_shadow_broker_route_readiness_market_matches",
        "cutover_broker_shadow_broker_route_readiness_gap_pairs",
        "cutover_broker_shadow_broker_dispatch_roundtrip_ready",
        "cutover_broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "cutover_broker_shadow_broker_dispatch_roundtrip_market_matches",
        "cutover_broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "cutover_broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "cutover_broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "cutover_broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_ready",
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "cutover_broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["cutover_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "failed_checks"
    ] == 1
    assert report.config["cutover_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["cutover_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2
    assert report.config["cutover_broker_shadow_broker_readiness"]["dispatch_roundtrip"][
        "max_rejected_orders"
    ] == 1


def test_route_enable_blocks_partial_cutover_broker_shadow_broker_vendor_data_readiness():
    config = cutover_config()
    config["scaleup_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "cutover_broker_shadow_broker_vendor_data_readiness_provided",
        "cutover_broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["cutover_broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["cutover_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_route_enable_live_dryrun_requires_cutover_route_readiness():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(route_readiness_provided=False, route_readiness_ready=False),
        cutover_config=cutover_config(route_readiness_provided=False, route_readiness_ready=False),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"cutover_route_readiness_provided", "cutover_route_readiness_ready"} <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_route_enable_blocks_cutover_route_readiness_identity_mismatch():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        cutover_config=cutover_config(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"cutover_route_readiness_strategy_matches", "cutover_route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "us_options_regular"


def test_route_enable_blocks_stale_cutover_route_readiness_ops_controls():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        cutover_config=cutover_config(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_route_readiness_ops_launch_controls_present",
        "cutover_route_readiness_ops_launch_controls_blocked_pairs",
        "cutover_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs",
        "cutover_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["route_readiness_ops_launch_controls_present"])
    assert int(summary["route_readiness_ops_launch_controls_blocked_pairs"]) == 1
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_breach_pairs"] == 1
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_concentration_breach_pairs"] == 1


def test_route_enable_blocks_stale_cutover_broker_route_readiness_ops_controls():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        cutover_config=cutover_config(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_broker_route_readiness_ops_launch_controls_ready",
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["cutover_broker_route_readiness_ops_launch_controls_ready"])
    assert int(summary["cutover_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs"]) == 1
    route_proof = report.config["cutover_broker_route_readiness"]
    assert route_proof["ops_launch_control_failures"] == "concentration breach on BANKNIFTY weekly"
    assert route_proof["ops_broker_roundtrip_portfolio_concentration_breach_runs"] == 1


def test_route_enable_carries_cutover_resume_route_readiness():
    config = cutover_config()
    config["scaleup_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(),
        "incident_broker_route_readiness": resume_route_proof(route_ready_pairs=2),
    }

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["cutover_broker_resume_broker_route_readiness_ready"])
    assert summary["cutover_broker_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["cutover_broker_resume_incident_broker_route_readiness_route_ready_pairs"]) == 2
    assert report.config["cutover_broker_resume_gate"]["broker_route_readiness"]["ready"]
    assert (
        report.config["cutover_broker_resume_gate"]["incident_broker_route_readiness"][
            "route_ready_pairs"
        ]
        == 2
    )


def test_route_enable_blocks_bad_cutover_resume_route_readiness():
    config = cutover_config()
    config["scaleup_broker_resume_gate"] = {
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

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_broker_resume_broker_route_readiness_ready",
        "cutover_broker_resume_broker_route_readiness_strategy_matches",
        "cutover_broker_resume_broker_route_readiness_market_matches",
        "cutover_broker_resume_broker_route_readiness_route_ready_pairs",
        "cutover_broker_resume_broker_route_readiness_gap_pairs",
        "cutover_broker_resume_broker_route_readiness_ops_launch_controls_ready",
        "cutover_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "cutover_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "cutover_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "cutover_broker_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert summary["cutover_broker_resume_broker_route_readiness_market"] == "us_options_regular"
    assert report.config["cutover_broker_resume_gate"]["broker_route_readiness"]["gap_pairs"] == 2
    assert report.config["next_gate"] == "review-resume-gate"


def test_route_enable_requires_cutover_dispatch_roundtrip():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(dispatch_provided=False, dispatch_ready=False),
        cutover_config=cutover_config(dispatch_provided=False, dispatch_ready=False),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"cutover_dispatch_roundtrip_provided", "cutover_dispatch_roundtrip_ready"} <= failed
    assert report.config["dispatch_roundtrip"]["required"]


def test_route_enable_requires_cutover_route_dispatch_roundtrip():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(route_provided=False, route_ready=False),
        cutover_config=cutover_config(route_provided=False, route_ready=False),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_route_dispatch_roundtrip_provided",
        "cutover_route_dispatch_roundtrip_ready",
    } <= failed
    assert report.config["dispatch_roundtrip"]["route_proof"]["required"]
    assert not report.config["dispatch_roundtrip"]["route_proof"]["provided"]


def test_route_enable_blocks_bad_cutover_route_dispatch_roundtrip_quality():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
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
        cutover_config=cutover_config(
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
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_route_dispatch_roundtrip_ready",
        "cutover_route_dispatch_roundtrip_target_mode_matches",
        "cutover_route_dispatch_roundtrip_strategy_matches",
        "cutover_route_dispatch_roundtrip_market_matches",
        "cutover_route_dispatch_roundtrip_scenario_matches",
        "cutover_route_dispatch_roundtrip_batch_id_provided",
        "cutover_route_dispatch_roundtrip_request_count_matches",
        "cutover_route_dispatch_roundtrip_missing_request_acks",
        "cutover_route_dispatch_roundtrip_rejected_orders",
        "cutover_route_dispatch_roundtrip_unmatched_acks",
    } <= failed
    route_proof = report.config["dispatch_roundtrip"]["route_proof"]
    assert route_proof["strategy"] == "surface_mm"
    assert route_proof["missing_request_acks"] == 1


def test_route_enable_blocks_bad_cutover_dispatch_roundtrip_quality():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(
            dispatch_ready=False,
            dispatch_target_mode="shadow",
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_key="wrong-scenario",
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
        ),
        cutover_config=cutover_config(
            dispatch_ready=False,
            dispatch_target_mode="shadow",
            dispatch_strategy="surface_mm",
            dispatch_market="us_options_regular",
            dispatch_scenario_key="wrong-scenario",
            dispatch_missing_request_acks=1,
            dispatch_rejected_orders=1,
            dispatch_unmatched_acks=1,
        ),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_dispatch_roundtrip_ready",
        "cutover_dispatch_roundtrip_target_mode_matches",
        "cutover_dispatch_roundtrip_strategy_matches",
        "cutover_dispatch_roundtrip_market_matches",
        "cutover_dispatch_roundtrip_scenario_matches",
        "cutover_dispatch_roundtrip_missing_request_acks",
        "cutover_dispatch_roundtrip_rejected_orders",
        "cutover_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert report.config["dispatch_roundtrip"]["missing_request_acks"] == 1


def test_route_enable_blocks_dispatch_roundtrip_failed_checks():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(dispatch_failed_checks=1),
        cutover_config=cutover_config(dispatch_failed_checks=1),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "cutover_dispatch_roundtrip_failed_checks" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert int(report.summary.iloc[0]["dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["dispatch_roundtrip"]["failed_checks"] == 1


def test_route_enable_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        cutover_config=cutover_config(route_enable_dispatch_roundtrip_failed_checks=1),
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "cutover_route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["dispatch_roundtrip"]["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_route_enable_blocks_order_count_and_notional_limit_breaches():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(max_orders=1, max_notional=10_000.0),
        cutover_config=cutover_config(max_orders=1, max_notional=10_000.0),
        upload_summary=upload_summary(orders=2),
        order_export_summary=order_export_summary(orders=2, total_notional=25_000.0),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"upload_orders_within_cutover_limit", "order_export_notional_within_cutover_limit"} <= failed
    assert report.summary.iloc[0]["route_state"] == "disabled"


def test_route_enable_blocks_unready_cutover_and_upload_pack():
    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(ready=False),
        cutover_config=cutover_config(),
        upload_summary=upload_summary(ready=False),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"cutover_ready", "upload_ready"} <= failed


def test_write_route_enable_packet_outputs_artifacts_and_catalog_entry(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)
    out_dir = tmp_path / "route_enable"

    report = write_route_enable_packet(
        cutover_dir=cutover,
        upload_pack_dir=upload,
        order_export_dir=export,
        output_dir=out_dir,
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    assert report.ready
    assert (out_dir / "route_enable_packet.csv").exists()
    assert (out_dir / "route_enable_checks.csv").exists()
    assert (out_dir / "route_enable_summary.csv").exists()
    assert (out_dir / "route_enable_action_queue.csv").exists()
    assert (out_dir / "route_enable_config.json").exists()
    assert (out_dir / "route_enable_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    saved_summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    saved_config = json.loads((out_dir / "route_enable_config.json").read_text(encoding="utf-8"))
    assert int(saved_summary.loc[0, "action_queue_count"]) == 0
    assert saved_config["action_queue_count"] == 0
    assert saved_config["next_actions"] == []
    assert (out_dir / "route_enable_runbook.md").read_text(encoding="utf-8").startswith(
        "# Route Enable Runbook"
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {item["path"] for item in manifest["artifacts"]}
    assert "route_enable_action_queue.csv" in artifact_paths
    assert "route_enable_runbook.md" in artifact_paths
    assert {"cutover_summary", "cutover_config", "cutover_manifest", "upload_pack", "order_export"} <= set(
        manifest["inputs"]
    )
    assert path_tail(manifest["inputs"]["cutover_summary"]["path"]).endswith("/cutover/cutover_summary.csv")
    assert path_tail(manifest["inputs"]["cutover_config"]["path"]).endswith("/cutover/cutover_config.json")
    assert path_tail(manifest["inputs"]["cutover_manifest"]["path"]).endswith("/cutover/manifest.json")
    assert path_tail(manifest["inputs"]["upload_pack"]["path"]).endswith("/upload/broker_upload_summary.csv")
    assert path_tail(manifest["inputs"]["order_export"]["path"]).endswith("/export/broker_order_summary.csv")
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "route_enable_packet"
    assert catalog.catalog.iloc[0]["summary_file"] == "route_enable_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])
    assert report.summary.iloc[0]["cutover_lineage_gate_passed"]
    assert report.summary.iloc[0]["cutover_manifest_sha256"] == file_sha256(cutover / "manifest.json")
    assert (
        report.summary.iloc[0]["cutover_runtime_scaleup_research_family_id"]
        == "india-leadlag-v1"
    )
    assert not bool(report.packet.iloc[0]["authorizes_submission"])
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert report.config["cutover_lineage"]["cutover_lineage_gate_passed"]
    assert not report.config["authorizes_submission"]
    assert {"cutover_artifacts", "cutover_dependencies"} <= set(manifest["inputs"])
    assert manifest["extra"]["cutover_lineage_gate_passed"]
    assert not manifest["extra"]["authorizes_submission"]
    assert verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="route_enable_packet",
        require_input_fingerprints=True,
    ).passed
    (tmp_path / "cutover_source.csv").write_text("source\nchanged\n", encoding="utf-8")
    drifted = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="route_enable_packet",
        require_input_fingerprints=True,
    )
    assert not drifted.passed
    assert drifted.error == "input_drift"


def test_route_enable_blocks_drifted_cutover_lineage(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)
    (tmp_path / "cutover_source.csv").write_text("source\nchanged\n", encoding="utf-8")

    report = write_route_enable_packet(
        cutover_dir=cutover,
        upload_pack_dir=upload,
        order_export_dir=export,
        output_dir=tmp_path / "route_enable",
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert {"cutover_manifest_current", "cutover_lineage_gate_passed"} <= failed


def test_route_enable_blocks_remanifested_cutover_contract_and_authorization_drift(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)
    summary_path = cutover / "cutover_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "runtime_scaleup_research_family_id"] = "relabeled-family"
    summary.to_csv(summary_path, index=False)
    config_path = cutover / "cutover_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["authorizes_submission"] = True
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    refresh_cutover_manifest(cutover)

    report = write_route_enable_packet(
        cutover_dir=cutover,
        upload_pack_dir=upload,
        order_export_dir=export,
        output_dir=tmp_path / "route_enable",
        thresholds=RouteEnableThresholds(require_order_export_ready=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert "cutover_manifest_current" not in failed
    assert {
        "cutover_lineage_contract_consistent",
        "cutover_non_authorizing",
        "cutover_lineage_gate_passed",
    } <= failed


def test_route_enable_rejects_cutover_output_collision(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_route_enable_packet(
            cutover_dir=cutover,
            upload_pack_dir=upload,
            order_export_dir=export,
            output_dir=cutover,
            thresholds=RouteEnableThresholds(require_order_export_ready=True),
        )


def test_cli_route_enable_hydrates_broker_vendor_data_from_cutover_manifest(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)
    (cutover / "broker_readiness_config.json").write_text(
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
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-order-export",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    config = json.loads((out_dir / "route_enable_config.json").read_text(encoding="utf-8"))
    vendor = config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert (
        summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"]
        == "arrow_money"
    )
    assert int(summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert (
        summary.loc[
            0,
            "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        ]
        == 1.0
    )
    assert (
        summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"]
        == 1.0
    )
    assert (
        int(summary.loc[0, "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"])
        == 1
    )
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64


def test_cli_route_enable_blocks_target_sidecar_without_cutover_lineage(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    (cutover / "broker_readiness_config.json").write_text(
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
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-order-export",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    checks = pd.read_csv(out_dir / "route_enable_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    prefix = "cutover_broker_dispatch_roundtrip_vendor_market_data_batch"
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_final_lineage_match_required",
        f"{prefix}_final_lineage_matches",
    } <= failed


def test_cli_route_enable_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    cutover, upload, export = write_inputs(tmp_path)
    (cutover / "broker_readiness_config.json").write_text(
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
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-order-export",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    checks = pd.read_csv(out_dir / "route_enable_checks.csv")
    config = json.loads((out_dir / "route_enable_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    readiness = config["cutover_broker_vendor_data_readiness"]
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        "cutover_broker_vendor_data_readiness_ready",
        "cutover_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary.loc[0, "cutover_broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "cutover_broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "cutover_broker_vendor_data_readiness_failed_checks"]) == 1
    assert readiness["provided"]
    assert not readiness["ready"]
    assert readiness["failed_checks"] == 1
    assert config["cutover_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_cli_route_enable_reads_launch_pipeline_upload_and_export_roots(tmp_path):
    cases = [
        ("leadlag", "04_export", "05_upload_pack"),
        ("imbalance", "04_export", "05_upload_pack"),
        ("parity", "04_export", "05_upload_pack"),
        ("surface_mm", "03_export", "04_upload_pack"),
    ]
    for family, export_folder, upload_folder in cases:
        case_dir = tmp_path / family
        cutover, _upload, _export = write_inputs(case_dir)
        pipeline = case_dir / f"{family}_launch_pipeline"
        export_dir = pipeline / export_folder
        upload_dir = pipeline / upload_folder
        out_dir = case_dir / "route_enable"
        export_dir.mkdir(parents=True)
        upload_dir.mkdir(parents=True)
        upload_summary().to_csv(upload_dir / "broker_upload_summary.csv", index=False)
        order_export_summary().to_csv(export_dir / "broker_order_summary.csv", index=False)

        code = main(
            [
                "review-route-enable",
                "--cutover",
                str(cutover),
                "--upload-pack",
                str(pipeline),
                "--order-export",
                str(pipeline),
                "--out",
                str(out_dir),
                "--require-order-export",
                "--fail-on-breach",
            ]
        )

        summary = pd.read_csv(out_dir / "route_enable_summary.csv")
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert code == 0
        assert bool(summary.loc[0, "ready"])
        assert path_tail(manifest["inputs"]["cutover_summary"]["path"]).endswith(
            f"/{family}/cutover/cutover_summary.csv"
        )
        assert path_tail(manifest["inputs"]["cutover_config"]["path"]).endswith(
            f"/{family}/cutover/cutover_config.json"
        )
        assert path_tail(manifest["inputs"]["cutover_manifest"]["path"]).endswith(
            f"/{family}/cutover/manifest.json"
        )
        assert path_tail(manifest["inputs"]["upload_pack"]["path"]).endswith(
            f"/{family}_launch_pipeline/{upload_folder}/broker_upload_summary.csv"
        )
        assert path_tail(manifest["inputs"]["order_export"]["path"]).endswith(
            f"/{family}_launch_pipeline/{export_folder}/broker_order_summary.csv"
        )


def test_cli_route_enable_fails_when_cutover_not_ready(tmp_path):
    cutover, upload, export = write_inputs(tmp_path, cutover_ready=False)
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-order-export",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    checks = pd.read_csv(out_dir / "route_enable_checks.csv")
    queue = pd.read_csv(out_dir / "route_enable_action_queue.csv")
    config = json.loads((out_dir / "route_enable_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "cutover_ready" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "action_queue_count"]) >= 1
    assert int(summary.loc[0, "blocked_action_count"]) >= 1
    assert summary.loc[0, "next_gate"] == "review-cutover-gate"
    assert queue.loc[0, "check"] == "cutover_ready"
    assert queue.loc[0, "component"] == "cutover_gate"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli review-cutover-gate --help"
    assert config["primary_action"]["check"] == "cutover_ready"


def test_cli_route_enable_can_fail_on_actions(tmp_path):
    cutover, upload, export = write_inputs(tmp_path, cutover_ready=False)
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-order-export",
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "action_queue_count"]) >= 1
    assert summary.loc[0, "primary_action_status"] == "blocked"


def test_cli_route_enable_can_require_dispatch_roundtrip(tmp_path):
    cutover, upload, export = write_inputs(tmp_path, dispatch=False)
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    checks = pd.read_csv(out_dir / "route_enable_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "cutover_dispatch_roundtrip_provided" in failed


def test_cli_route_enable_can_require_route_readiness(tmp_path):
    cutover, upload, export = write_inputs(tmp_path, route_readiness=False)
    out_dir = tmp_path / "route_enable"

    code = main(
        [
            "review-route-enable",
            "--cutover",
            str(cutover),
            "--upload-pack",
            str(upload),
            "--order-export",
            str(export),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "route_enable_summary.csv")
    checks = pd.read_csv(out_dir / "route_enable_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "cutover_route_readiness_provided" in failed
