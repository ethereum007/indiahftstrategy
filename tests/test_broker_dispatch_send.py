import hashlib
import json

import pandas as pd
import pytest

from hft_cli import main
from reports.broker_dispatch_ack import (
    BrokerDispatchAckThresholds,
    write_broker_dispatch_acknowledgements,
)
from reports.broker_dispatch_roundtrip import (
    BrokerDispatchRoundTripThresholds,
    write_broker_dispatch_roundtrip,
)
from reports.broker_dispatch_send import (
    evaluate_broker_dispatch_send_packet,
    write_broker_dispatch_send_packet,
)
from reports.catalog import catalog_experiment_runs
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from reports.operational_lineage import (
    cutover_lineage_fields,
    empty_runtime_session_lineage,
    load_broker_dispatch_ack_lineage,
    load_broker_dispatch_send_lineage,
    load_cutover_lineage,
    load_route_enable_lineage,
    route_enable_lineage_fields,
    runtime_session_lineage_fields,
)


def path_tail(value):
    return str(value).replace("\\", "/")


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
    }


def dispatch_final_target_application_lineage_comparison(vendor, **overrides):
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def dispatch_complete_final_target_application_lineage_comparison(
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def dispatch_view_30_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_complete_final_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def dispatch_view_38_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_30_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "dispatch_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def dispatch_view_46_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_38_target_application_lineage_comparison(
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
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def dispatch_view_54_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_30_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
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
            "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def dispatch_view_62_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_54_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.pop(
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
        None,
    )
    comparison.update(
        {
            "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def send_view_63_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_62_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def dispatch_view_70_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_62_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def dispatch_view_78_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_70_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def send_view_71_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_70_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def send_view_79_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_78_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "send_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def send_view_55_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = dispatch_view_54_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def add_dispatch_complete_final_target_application_lineage(
    config,
    vendor,
    **overrides,
):
    config[
        "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_complete_final_target_application_lineage_comparison(
        vendor,
        **overrides,
    )
    config[
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_30_target_application_lineage_comparison(vendor)
    config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_38_target_application_lineage_comparison(vendor)
    config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_46_target_application_lineage_comparison(vendor)
    config[
        "dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_54_target_application_lineage_comparison(vendor)
    config[
        "dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_62_target_application_lineage_comparison(vendor)
    config[
        "dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_70_target_application_lineage_comparison(vendor)
    config[
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_78_target_application_lineage_comparison(vendor)


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
    state="armed_dry_run",
    target_mode="live_dryrun",
    adapter="arrow_money",
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
                "dispatch_state": state,
                "target_mode": target_mode,
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": adapter,
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
                "strategy_portfolio_selected_strategy": "lead_lag_taker",
                "strategy_portfolio_selected_market": "india_nse_index_derivatives",
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
                    "lead_lag_taker" if strategy_portfolio_selected_allocation_notional else ""
                ),
                "strategy_portfolio_top_market_by_weight": (
                    "india_nse_index_derivatives" if strategy_portfolio_selected_allocation_notional else ""
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
                "dry_run_only": True,
                "failed_checks": 0 if ready else 1,
                "recommendation": "ready_for_broker_dryrun_dispatch"
                if ready
                else "keep_dispatch_disabled",
            }
        ]
    )


def dispatch_orders(*, dry_run=True, malformed_payload=False, route_roundtrip_batch_id="BDP-0"):
    payloads = [
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
            "client_order_id": "ORD-2",
            "tag": "shadow_nse",
        },
    ]
    rows = []
    for index, payload in enumerate(payloads, start=1):
        payload_json = json.dumps(payload, sort_keys=True)
        if malformed_payload and index == 2:
            payload_json = "{bad-json"
        rows.append(
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_sequence": index,
                "dispatch_order_id": f"DSP-{index}",
                "dispatch_action": "dry_run_submit",
                "dry_run_only": dry_run if index == 1 else True,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "adapter": "arrow_money",
                "source_order_id": f"ORD-{index}",
                "source_payload_hash": f"hash-{index}",
                "upload_file_hash": "upload-hash",
                "route_enable_hash": "route-hash",
                "route_dispatch_roundtrip_batch_id": route_roundtrip_batch_id,
                "order_payload_json": payload_json,
            }
        )
    return pd.DataFrame(rows)


def dispatch_config(
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
            "selected_strategy": "lead_lag_taker",
            "selected_market": "india_nse_index_derivatives",
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
            "top_strategy_by_weight": "lead_lag_taker" if strategy_portfolio_selected_allocation_notional else "",
            "top_market_by_weight": (
                "india_nse_index_derivatives" if strategy_portfolio_selected_allocation_notional else ""
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


def with_dispatch_broker_vendor_batch_summary(summary, vendor):
    prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        final_lineage = dispatch_final_target_application_lineage_comparison(vendor)
        complete_final_lineage = (
            dispatch_complete_final_target_application_lineage_comparison(vendor)
        )
        extended_complete_final_lineage = (
            dispatch_view_30_target_application_lineage_comparison(vendor)
        )
        extended_complete_final_lineage_38 = (
            dispatch_view_38_target_application_lineage_comparison(vendor)
        )
        latest_extended_complete_final_lineage_46 = (
            dispatch_view_46_target_application_lineage_comparison(vendor)
        )
        current_latest_extended_complete_final_lineage_54 = (
            dispatch_view_54_target_application_lineage_comparison(vendor)
        )
        reconciled_current_latest_extended_complete_final_lineage_62 = (
            dispatch_view_62_target_application_lineage_comparison(vendor)
        )
        verified_reconciled_current_latest_extended_complete_final_lineage_70 = (
            dispatch_view_70_target_application_lineage_comparison(vendor)
        )
        confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_78 = (
            dispatch_view_78_target_application_lineage_comparison(vendor)
        )
        final_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
        complete_final_prefix = (
            "route_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_prefix = (
            "route_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_38_prefix = (
            "route_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        latest_extended_complete_final_46_prefix = (
            "route_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        current_latest_extended_complete_final_54_prefix = (
            "route_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        reconciled_current_latest_extended_complete_final_62_prefix = (
            "route_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        verified_reconciled_current_latest_extended_complete_final_70_prefix = (
            "route_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        confirmed_verified_reconciled_current_latest_extended_complete_final_78_prefix = (
            "route_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            "route_broker_vendor_market_data_batch_lineage_match_required",
        ] = lineage["required"]
        result.loc[
            0,
            "route_broker_vendor_market_data_batch_lineage_matches",
        ] = lineage["matches"]
        result.loc[
            0,
            "route_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["current_application_lineage_sha256"]
        result.loc[
            0,
            "route_broker_vendor_market_data_batch_application_lineage_sha256",
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
        result.loc[
            0,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["dispatch_carried_application_lineage_sha256"]
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
        ] = complete_final_lineage["required"]
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
        result.loc[0, f"{extended_complete_final_prefix}_lineage_matches"] = (
            extended_complete_final_lineage["matches"]
        )
        for field, value in extended_complete_final_lineage.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{extended_complete_final_prefix}_dispatch_complete_final_review_carried_application_lineage_sha256",
                ] = value
            else:
                result.loc[0, f"{extended_complete_final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{extended_complete_final_38_prefix}_lineage_match_required",
        ] = extended_complete_final_lineage_38["required"]
        result.loc[0, f"{extended_complete_final_38_prefix}_lineage_matches"] = (
            extended_complete_final_lineage_38["matches"]
        )
        for field, value in extended_complete_final_lineage_38.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{extended_complete_final_38_prefix}_dispatch_extended_complete_final_review_carried_application_lineage_sha256",
                ] = value
            else:
                result.loc[0, f"{extended_complete_final_38_prefix}_{field}"] = value
        result.loc[
            0,
            f"{latest_extended_complete_final_46_prefix}_lineage_match_required",
        ] = latest_extended_complete_final_lineage_46["required"]
        result.loc[
            0,
            f"{latest_extended_complete_final_46_prefix}_lineage_matches",
        ] = latest_extended_complete_final_lineage_46["matches"]
        for field, value in latest_extended_complete_final_lineage_46.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{latest_extended_complete_final_46_prefix}_dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256",
                ] = value
            else:
                result.loc[
                    0,
                    f"{latest_extended_complete_final_46_prefix}_{field}",
                ] = value
        result.loc[
            0,
            f"{current_latest_extended_complete_final_54_prefix}_lineage_match_required",
        ] = current_latest_extended_complete_final_lineage_54["required"]
        result.loc[
            0,
            f"{current_latest_extended_complete_final_54_prefix}_lineage_matches",
        ] = current_latest_extended_complete_final_lineage_54["matches"]
        for field, value in current_latest_extended_complete_final_lineage_54.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{current_latest_extended_complete_final_54_prefix}_dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                ] = value
            else:
                result.loc[
                    0,
                    f"{current_latest_extended_complete_final_54_prefix}_{field}",
                ] = value
        result.loc[
            0,
            f"{reconciled_current_latest_extended_complete_final_62_prefix}_lineage_match_required",
        ] = reconciled_current_latest_extended_complete_final_lineage_62["required"]
        result.loc[
            0,
            f"{reconciled_current_latest_extended_complete_final_62_prefix}_lineage_matches",
        ] = reconciled_current_latest_extended_complete_final_lineage_62["matches"]
        for field, value in reconciled_current_latest_extended_complete_final_lineage_62.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                result.loc[
                    0,
                    f"{reconciled_current_latest_extended_complete_final_62_prefix}_dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
                ] = value
            else:
                result.loc[
                    0,
                    f"{reconciled_current_latest_extended_complete_final_62_prefix}_{field}",
                ] = value
        result.loc[
            0,
            f"{verified_reconciled_current_latest_extended_complete_final_70_prefix}_lineage_match_required",
        ] = verified_reconciled_current_latest_extended_complete_final_lineage_70[
            "required"
        ]
        result.loc[
            0,
            f"{verified_reconciled_current_latest_extended_complete_final_70_prefix}_lineage_matches",
        ] = verified_reconciled_current_latest_extended_complete_final_lineage_70[
            "matches"
        ]
        for field, value in (
            verified_reconciled_current_latest_extended_complete_final_lineage_70.items()
        ):
            if field in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                continue
            result.loc[
                0,
                f"{verified_reconciled_current_latest_extended_complete_final_70_prefix}_{field}",
            ] = value
        result.loc[
            0,
            f"{confirmed_verified_reconciled_current_latest_extended_complete_final_78_prefix}_lineage_match_required",
        ] = confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_78[
            "required"
        ]
        result.loc[
            0,
            f"{confirmed_verified_reconciled_current_latest_extended_complete_final_78_prefix}_lineage_matches",
        ] = confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_78[
            "matches"
        ]
        for field, value in (
            confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_78.items()
        ):
            if field in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                continue
            result.loc[
                0,
                f"{confirmed_verified_reconciled_current_latest_extended_complete_final_78_prefix}_{field}",
            ] = value
    return result


def broker_vendor_data_readiness_config(*, provided=True, ready=True, failed_checks=0):
    return {
        "provided": provided,
        "ready": ready,
        "failed_checks": failed_checks,
    }


def dirty_vendor_market_data_batch_config():
    vendor = vendor_market_data_batch_config()
    vendor.update(
        {
            "ready": False,
            "adapter": "irage",
            "market": "us_options_regular",
            "dataset_count": 0,
            "ready_datasets": 0,
            "failed_datasets": 1,
            "ready_rate": 0.0,
            "unique_source_files": 0,
            "unique_header_fingerprints": 0,
            "source_file_fingerprint_coverage": 0.0,
            "min_mapping_coverage": 0.0,
            "unique_mapping_drafts": 0,
            "mapping_sources": "",
            "datasets": [],
        }
    )
    vendor["comparison"] = {"accepted": False, "failed_checks": 1}
    return vendor


def _write_cutover_source(tmp_path, *, broker_readiness_config=None):
    root = tmp_path / "cutover"
    root.mkdir()
    runtime_lineage = runtime_session_lineage_fields(empty_runtime_session_lineage())
    runtime_lineage["runtime_lineage_gate_passed"] = True
    summary = {
        **runtime_lineage,
        "ready": True,
        "authorizes_submission": False,
    }
    pd.DataFrame([summary]).to_csv(root / "cutover_summary.csv", index=False)
    pd.DataFrame(
        [{"ready": True, "authorizes_submission": False}]
    ).to_csv(root / "cutover_authorization.csv", index=False)
    pd.DataFrame([{"check": "fixture", "passed": True}]).to_csv(
        root / "cutover_checks.csv", index=False
    )
    pd.DataFrame(columns=["check"]).to_csv(
        root / "cutover_action_queue.csv", index=False
    )
    (root / "cutover_config.json").write_text(
        json.dumps(
            {
                "ready": True,
                "runtime_lineage": runtime_lineage,
                "authorizes_submission": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "cutover_runbook.md").write_text("# Cutover fixture\n", encoding="utf-8")
    source = root / "runtime_source.txt"
    source.write_text("current\n", encoding="utf-8")
    inputs = {"runtime_source": source}
    if broker_readiness_config is not None:
        broker_config_path = root / "broker_readiness_config.json"
        broker_config_path.write_text(
            json.dumps(broker_readiness_config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        inputs["broker_readiness_config"] = broker_config_path
    write_experiment_manifest(
        root,
        run_type="cutover_gate",
        inputs=inputs,
        extra={**runtime_lineage, "ready": True, "authorizes_submission": False},
    )
    return root


def _write_route_source(tmp_path, cutover):
    root = tmp_path / "route_enable"
    root.mkdir()
    cutover_lineage = load_cutover_lineage(cutover / "cutover_config.json")
    assert cutover_lineage["gate_passed"]
    lineage_fields = cutover_lineage_fields(cutover_lineage)
    pd.DataFrame(
        [{**lineage_fields, "ready": True, "authorizes_submission": False}]
    ).to_csv(root / "route_enable_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                **lineage_fields,
                "route_enabled": True,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(root / "route_enable_packet.csv", index=False)
    pd.DataFrame([{"check": "fixture", "passed": True}]).to_csv(
        root / "route_enable_checks.csv", index=False
    )
    pd.DataFrame(columns=["check"]).to_csv(
        root / "route_enable_action_queue.csv", index=False
    )
    (root / "route_enable_config.json").write_text(
        json.dumps(
            {
                "route_enabled": True,
                "cutover_lineage": lineage_fields,
                "authorizes_submission": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "route_enable_runbook.md").write_text(
        "# Route-enable fixture\n", encoding="utf-8"
    )
    write_experiment_manifest(
        root,
        run_type="route_enable_packet",
        inputs={"cutover_manifest": cutover / "manifest.json"},
        extra={**lineage_fields, "ready": True, "authorizes_submission": False},
    )
    return root


def _manifest_input_values(value):
    if isinstance(value, list):
        return [_manifest_input_values(item) for item in value]
    if isinstance(value, dict) and value.get("path"):
        return value["path"]
    return value


def _refresh_manifest(manifest_path, *, extra_updates=None):
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = {
        name: _manifest_input_values(value)
        for name, value in payload.get("inputs", {}).items()
    }
    extra = dict(payload.get("extra", {}))
    extra.update(extra_updates or {})
    write_experiment_manifest(
        manifest_path.parent,
        run_type=payload["run_type"],
        parameters=payload.get("parameters", {}),
        inputs=inputs,
        extra=extra,
    )


def write_dispatch(
    tmp_path,
    *,
    ready=True,
    state="armed_dry_run",
    route_roundtrip=True,
    route_readiness=True,
    broker_readiness_config=None,
):
    cutover = _write_cutover_source(
        tmp_path,
        broker_readiness_config=broker_readiness_config,
    )
    route = _write_route_source(tmp_path, cutover)
    route_lineage = load_route_enable_lineage(route / "route_enable_config.json")
    assert route_lineage["gate_passed"]
    lineage_fields = route_enable_lineage_fields(route_lineage)

    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    summary = dispatch_summary(
        ready=ready,
        state=state,
        route_roundtrip_provided=route_roundtrip,
        route_roundtrip_ready=route_roundtrip,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    )
    for column, value in lineage_fields.items():
        summary[column] = value
    summary["authorizes_submission"] = False
    summary.to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    orders = dispatch_orders()
    for column, value in lineage_fields.items():
        orders[column] = value
    orders["authorizes_submission"] = False
    orders.to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
    config = dispatch_config(
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    )
    config.update(
        {
            "ready": ready,
            "dispatch_state": state,
            "dispatch_batch_id": "BDP-1",
            "target_mode": "live_dryrun",
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "scenario_key": "trigger_ticks=2",
            "adapter": "arrow_money",
            "dry_run_only": True,
            "authorizes_submission": False,
            "route_enable_lineage": lineage_fields,
        }
    )
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame([{"check": "fixture", "passed": True}]).to_csv(
        dispatch / "broker_dispatch_checks.csv", index=False
    )
    pd.DataFrame(columns=["check"]).to_csv(
        dispatch / "broker_dispatch_action_queue.csv", index=False
    )
    (dispatch / "broker_dispatch_runbook.md").write_text(
        "# Broker-dispatch fixture\n", encoding="utf-8"
    )
    write_experiment_manifest(
        dispatch,
        run_type="broker_dispatch_plan",
        inputs={"route_enable_manifest": route / "manifest.json"},
        extra={**lineage_fields, "ready": ready, "authorizes_submission": False},
    )
    return dispatch


def _rewrite_dispatch_lineage_field(dispatch, column, value):
    summary_path = dispatch / "broker_dispatch_summary.csv"
    orders_path = dispatch / "broker_dispatch_orders.csv"
    config_path = dispatch / "broker_dispatch_config.json"
    summary = pd.read_csv(summary_path)
    orders = pd.read_csv(orders_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary[column] = value
    orders[column] = value
    config["route_enable_lineage"][column] = value
    summary.to_csv(summary_path, index=False)
    orders.to_csv(orders_path, index=False)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(dispatch / "manifest.json", extra_updates={column: value})


def _rewrite_send_dispatch_lineage_field(send, column, value):
    summary_path = send / "broker_dispatch_send_summary.csv"
    requests_path = send / "broker_dispatch_send_requests.csv"
    config_path = send / "broker_dispatch_send_config.json"
    summary = pd.read_csv(summary_path)
    requests = pd.read_csv(requests_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary[column] = value
    requests[column] = value
    requests["request_payload_json"] = requests["request_payload_json"].map(
        lambda raw: json.dumps(
            {**json.loads(raw), column: value},
            sort_keys=True,
        )
    )
    config["broker_dispatch_lineage"][column] = value
    summary.to_csv(summary_path, index=False)
    _write_rehashed_send_requests(send, requests)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(send / "manifest.json", extra_updates={column: value})


def _write_rehashed_send_requests(send, requests):
    requests = requests.copy()
    for index in range(len(requests)):
        payload_hash = hashlib.sha256(
            json.dumps(
                json.loads(requests.loc[index, "request_payload_json"]),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        requests.loc[index, "request_payload_hash"] = payload_hash
        requests.loc[index, "idempotency_key"] = f"IDEMP-{payload_hash[:24]}"
        requests.loc[index, "request_id"] = (
            f"BDR-{index + 1:06d}-{payload_hash[:12]}"
        )
    requests.to_csv(send / "broker_dispatch_send_requests.csv", index=False)
    expected_acks_path = send / "broker_dispatch_expected_acks.csv"
    expected_acks = pd.read_csv(expected_acks_path)
    request_lookup = requests.set_index("dispatch_order_id")
    for column in ("request_id", "idempotency_key"):
        expected_acks[column] = expected_acks["dispatch_order_id"].map(
            request_lookup[column]
        )
    expected_acks.to_csv(expected_acks_path, index=False)


def _write_verified_ack_chain(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    ack_log = tmp_path / "broker_dispatch_acks.csv"
    orders = pd.read_csv(dispatch / "broker_dispatch_orders.csv")
    pd.DataFrame(
        [
            {
                "dispatch_order_id": row.dispatch_order_id,
                "source_order_id": row.source_order_id,
                "route_dispatch_roundtrip_batch_id": (
                    row.route_dispatch_roundtrip_batch_id
                ),
                "broker_order_id": f"ACK-{index + 1}",
                "ack_status": "dry_run_accepted",
                "ack_ts_ns": 1_000_000 + index,
            }
            for index, row in enumerate(orders.itertuples(index=False))
        ]
    ).to_csv(ack_log, index=False)
    ack = tmp_path / "ack"
    write_broker_dispatch_acknowledgements(
        dispatch_dir=dispatch,
        send_dir=send,
        acks_path=ack_log,
        output_dir=ack,
        thresholds=BrokerDispatchAckThresholds(require_send_packet=True),
    )
    return dispatch, send, ack


def _rewrite_ack_send_lineage_field(ack, column, value):
    summary_path = ack / "broker_dispatch_ack_summary.csv"
    acknowledgements_path = ack / "broker_dispatch_acknowledgements.csv"
    config_path = ack / "broker_dispatch_ack_config.json"
    summary = pd.read_csv(summary_path)
    acknowledgements_frame = pd.read_csv(acknowledgements_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary[column] = value
    acknowledgements_frame[column] = value
    config["broker_dispatch_send_lineage"][column] = value
    summary.to_csv(summary_path, index=False)
    acknowledgements_frame.to_csv(acknowledgements_path, index=False)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(ack / "manifest.json", extra_updates={column: value})


def test_broker_dispatch_send_packet_prepares_non_submitting_requests():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
    )

    assert report.ready
    assert report.summary.iloc[0]["request_state"] == "dry_run_send_packet_ready"
    assert report.summary.iloc[0]["recommendation"] == "ready_for_non_submitting_broker_sender_review"
    assert report.config["failed_check_count"] == 0
    assert report.config["primary_blocker"] == {}
    assert report.config["action_queue_count"] == 0
    assert report.config["next_actions"] == []
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert int(report.summary.iloc[0]["failed_check_count"]) == 0
    assert report.summary.iloc[0]["primary_blocker_check"] == ""
    assert int(report.summary.iloc[0]["action_queue_count"]) == 0
    assert report.requests["endpoint"].tolist() == [
        "arrow_money.orders.dry_run_submit",
        "arrow_money.orders.dry_run_submit",
    ]
    assert report.requests["submission_enabled"].tolist() == [False, False]
    assert report.requests["idempotency_key"].nunique() == 2
    request_payload = json.loads(report.requests.iloc[0]["request_payload_json"])
    assert request_payload["submission_enabled"] is False
    assert request_payload["dry_run_only"] is True
    assert request_payload["route_dispatch_roundtrip_batch_id"] == "BDP-0"
    assert request_payload["order"]["client_order_id"] == "ORD-1"
    assert report.requests["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.expected_acks["dispatch_order_id"].tolist() == ["DSP-1", "DSP-2"]
    assert report.expected_acks["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
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


def test_broker_dispatch_send_carries_route_broker_resume_gate():
    config = dispatch_config()
    config["route_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(),
        "incident_broker_route_readiness": resume_route_proof(route_ready_pairs=2),
    }

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert report.ready
    summary = report.summary.iloc[0]
    resume_gate = report.config["route_broker_resume_gate"]
    assert bool(summary["route_broker_resume_broker_route_readiness_ready"])
    assert summary["route_broker_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["route_broker_resume_incident_broker_route_readiness_route_ready_pairs"]) == 2
    assert resume_gate["broker_route_readiness"]["ready"]
    assert resume_gate["broker_route_readiness"]["ops_launch_controls_ready"]
    assert resume_gate["incident_broker_route_readiness"]["route_ready_pairs"] == 2


def test_broker_dispatch_send_blocks_bad_route_broker_resume_gate():
    config = dispatch_config()
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

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
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
    assert report.action_queue is not None
    assert report.action_queue.iloc[0]["component"] == "resume_gate"


def test_broker_dispatch_send_carries_strategy_portfolio_allocation():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=2_000.0,
        ),
        dispatch_orders=dispatch_orders(),
        dispatch_config=dispatch_config(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=2_000.0,
        ),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    portfolio = report.config["strategy_portfolio"]
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
    assert report.config["dispatch_total_notional"] == 1_575.0
    assert portfolio["required"]
    assert portfolio["provided"]
    assert portfolio["ready"]
    assert portfolio["selected_allocation_notional"] == 2_000.0
    assert portfolio["min_strategy_count"] == 2
    assert portfolio["allocated_strategy_count"] == 2
    assert portfolio["top_strategy_by_weight"] == "lead_lag_taker"
    assert portfolio["max_strategy_allocation_weight"] == 0.45


def test_broker_dispatch_send_blocks_dispatch_above_strategy_portfolio_allocation():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1_200.0,
        ),
        dispatch_orders=dispatch_orders(),
        dispatch_config=dispatch_config(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1_200.0,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_notional_within_strategy_portfolio_allocation" in failed
    assert report.config["primary_blocker"]["check"] == "dispatch_notional_within_strategy_portfolio_allocation"
    assert report.config["dispatch_total_notional"] == 1_575.0


def test_broker_dispatch_send_carries_dispatch_shadow_broker_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
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


def test_broker_dispatch_send_blocks_bad_dispatch_shadow_broker_readiness():
    config = dispatch_config()
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

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_shadow_broker_readiness_ready",
        "dispatch_shadow_broker_vendor_data_readiness_ready",
        "dispatch_shadow_broker_vendor_data_readiness_failed_checks",
        "dispatch_shadow_broker_adapter_matches",
        "dispatch_shadow_broker_adapter_consistent",
        "dispatch_shadow_broker_route_readiness_ready",
        "dispatch_shadow_broker_route_readiness_strategy_matches",
        "dispatch_shadow_broker_route_readiness_market_matches",
        "dispatch_shadow_broker_route_readiness_gap_pairs",
        "dispatch_shadow_broker_dispatch_roundtrip_ready",
        "dispatch_shadow_broker_dispatch_roundtrip_strategy_matches",
        "dispatch_shadow_broker_dispatch_roundtrip_market_matches",
        "dispatch_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "dispatch_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "dispatch_shadow_broker_dispatch_roundtrip_rejected_orders",
        "dispatch_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "dispatch_shadow_broker_route_dispatch_roundtrip_ready",
        "dispatch_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "dispatch_shadow_broker_route_dispatch_roundtrip_market_matches",
        "dispatch_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_send_blocks_partial_dispatch_shadow_broker_vendor_data_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        broker_vendor_data_readiness_sessions=1,
        broker_vendor_data_readiness_provided_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "dispatch_shadow_broker_vendor_data_readiness_provided",
        "dispatch_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_broker_dispatch_send_carries_route_broker_shadow_broker_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
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


def test_broker_dispatch_send_carries_dispatch_vendor_market_data_batch():
    config = dispatch_config()
    config["route_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_vendor_market_data_batch"]
    assert report.ready
    assert summary["dispatch_vendor_market_data_batch_provided"]
    assert summary["dispatch_vendor_market_data_batch_ready"]
    assert summary["dispatch_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["dispatch_vendor_market_data_batch_kind"] == "ticks"
    assert summary["dispatch_vendor_market_data_batch_manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert int(summary["dispatch_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["dispatch_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["dispatch_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["dispatch_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["dispatch_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["dispatch_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["dispatch_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_dispatch_send_blocks_wrong_manifest_vendor_market_data_batch():
    config = dispatch_config()
    config["route_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_vendor_market_data_batch"]
    assert "dispatch_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["dispatch_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_send_carries_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
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


def test_broker_dispatch_send_carries_target_application_vendor_batch_from_dispatch_config():
    vendor_input = target_application_vendor_market_data_batch_config()
    lineage_input = target_application_lineage_comparison(vendor_input)
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor_input
    config[f"{input_prefix}_lineage_comparison"] = lineage_input
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor_input)
    add_dispatch_complete_final_target_application_lineage(config, vendor_input)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert report.ready
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert summary[f"{prefix}_application_lineage_consistency_required"]
    assert summary[f"{prefix}_application_lineage_consistent"]
    assert summary[f"{prefix}_application_lineage_sha256"] == lineage_sha256
    assert summary["dispatch_broker_vendor_market_data_batch_lineage_match_required"]
    assert summary["dispatch_broker_vendor_market_data_batch_lineage_matches"]
    assert (
        summary[
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
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
        "send_carried_application_lineage_sha256": lineage_sha256,
    }
    final_lineage = report.config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == lineage_sha256
    dispatch_complete_prefix = (
        "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        "dispatch_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{dispatch_complete_prefix}_{field}"] == lineage_sha256
    send_complete_final = report.config[
        "send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_complete_final["required"]
    assert send_complete_final["matches"]
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
        "carried_application_lineage_sha256",
    ):
        assert send_complete_final[field] == lineage_sha256
    dispatch_extended_prefix = (
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        "dispatch_final_review_carried_application_lineage_sha256",
        "send_final_review_carried_application_lineage_sha256",
        "ack_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_complete_final_review_carried_application_lineage_sha256",
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
        "send_complete_final_review_carried_application_lineage_sha256",
    ):
        assert summary[f"{dispatch_extended_prefix}_{field}"] == lineage_sha256
    send_extended_complete_final = report.config[
        "send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_extended_complete_final["required"]
    assert send_extended_complete_final["matches"]
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
        "scaleup_complete_final_review_carried_application_lineage_sha256",
        "cutover_complete_final_review_carried_application_lineage_sha256",
        "route_complete_final_review_carried_application_lineage_sha256",
        "dispatch_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    ):
        assert send_extended_complete_final[field] == lineage_sha256
    dispatch_extended_38_prefix = (
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    dispatch_view_38 = dispatch_view_38_target_application_lineage_comparison(
        vendor_input
    )
    for field, expected in dispatch_view_38.items():
        if field in {"required", "matches"}:
            continue
        summary_field = (
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256"
            if field == "carried_application_lineage_sha256"
            else field
        )
        assert summary[f"{dispatch_extended_38_prefix}_{summary_field}"] == (
            expected
        )
    assert (
        summary[
            f"{dispatch_extended_38_prefix}_send_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    send_view_39 = report.config[
        "send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_39["required"]
    assert send_view_39["matches"]
    for field, expected in dispatch_view_38.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
        }:
            continue
        assert send_view_39[field] == expected
    assert send_view_39[
        "dispatch_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert send_view_39["carried_application_lineage_sha256"] == lineage_sha256
    dispatch_latest_prefix = (
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    dispatch_view_46 = dispatch_view_46_target_application_lineage_comparison(
        vendor_input
    )
    view_46_compatibility_only_fields = {
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    }
    assert summary[f"{dispatch_latest_prefix}_lineage_match_required"]
    assert summary[f"{dispatch_latest_prefix}_lineage_matches"]
    for field, expected in dispatch_view_46.items():
        if field in {
            "required",
            "matches",
            *view_46_compatibility_only_fields,
        }:
            continue
        summary_field = (
            "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256"
            if field == "carried_application_lineage_sha256"
            else field
        )
        assert summary[f"{dispatch_latest_prefix}_{summary_field}"] == expected
    assert (
        summary[
            f"{dispatch_latest_prefix}_send_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    send_view_47 = report.config[
        "send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_47["required"]
    assert send_view_47["matches"]
    for field, expected in dispatch_view_46.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
            *view_46_compatibility_only_fields,
        }:
            continue
        assert send_view_47[field] == expected
    assert (
        send_view_47[
            "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert send_view_47["carried_application_lineage_sha256"] == lineage_sha256
    dispatch_current_prefix = (
        "dispatch_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    dispatch_view_54 = dispatch_view_54_target_application_lineage_comparison(
        vendor_input
    )
    assert summary[f"{dispatch_current_prefix}_lineage_match_required"]
    assert summary[f"{dispatch_current_prefix}_lineage_matches"]
    for field, expected in dispatch_view_54.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_current_prefix}_{field}"] == expected
    assert (
        summary[
            f"{dispatch_current_prefix}_dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        summary[
            f"{dispatch_current_prefix}_send_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    send_view_55 = report.config[
        "send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_55 == send_view_55_target_application_lineage_comparison(
        vendor_input
    )
    assert len(send_view_55) == 54
    dispatch_view_62 = dispatch_view_62_target_application_lineage_comparison(
        vendor_input
    )
    assert len(dispatch_view_62) == 61
    dispatch_reconciled_prefix = (
        "dispatch_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert summary[f"{dispatch_reconciled_prefix}_lineage_match_required"]
    assert summary[f"{dispatch_reconciled_prefix}_lineage_matches"]
    for field, expected in dispatch_view_62.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_reconciled_prefix}_{field}"] == expected
    assert summary[
        f"{dispatch_reconciled_prefix}_send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    send_view_63 = report.config[
        "send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_63 == send_view_63_target_application_lineage_comparison(
        vendor_input
    )
    assert len(send_view_63) == 62
    dispatch_view_70 = dispatch_view_70_target_application_lineage_comparison(
        vendor_input
    )
    assert len(dispatch_view_70) == 69
    dispatch_verified_prefix = (
        "dispatch_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert summary[f"{dispatch_verified_prefix}_lineage_match_required"]
    assert summary[f"{dispatch_verified_prefix}_lineage_matches"]
    for field, expected in dispatch_view_70.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_verified_prefix}_{field}"] == expected
    assert summary[
        f"{dispatch_verified_prefix}_send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    send_view_71 = report.config[
        "send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_71 == send_view_71_target_application_lineage_comparison(
        vendor_input
    )
    assert len(send_view_71) == 70
    dispatch_view_78 = dispatch_view_78_target_application_lineage_comparison(
        vendor_input
    )
    assert len(dispatch_view_78) == 77
    dispatch_confirmed_prefix = (
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert summary[f"{dispatch_confirmed_prefix}_lineage_match_required"]
    assert summary[f"{dispatch_confirmed_prefix}_lineage_matches"]
    for field, expected in dispatch_view_78.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_confirmed_prefix}_{field}"] == expected
    assert summary[
        f"{dispatch_confirmed_prefix}_send_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    send_view_79 = report.config[
        "send_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_79 == send_view_79_target_application_lineage_comparison(
        vendor_input
    )
    assert len(send_view_79) == 78
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
        f"{prefix}_send_carried_lineage_sha256_matches",
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
        f"{prefix}_final_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{prefix}_send_packet_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_lineage_match_required",
        f"{prefix}_dispatch_final_lineage_matches",
        f"{prefix}_dispatch_final_source_lineage_sha256_matches",
        f"{prefix}_dispatch_final_compatibility_broker_lineage_sha256_matches",
        f"{prefix}_dispatch_final_compatibility_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_prior_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_prior_cutover_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_route_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_send_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_ack_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_roundtrip_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_readiness_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_scaleup_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_cutover_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_route_enable_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_send_packet_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_broker_readiness_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_scaleup_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_cutover_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_route_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_dispatch_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_final_send_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_lineage_match_required",
        f"{prefix}_dispatch_complete_final_lineage_matches",
        f"{prefix}_dispatch_complete_final_source_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_compatibility_broker_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_compatibility_dispatch_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_prior_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_prior_cutover_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_route_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_send_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_ack_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_roundtrip_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_readiness_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_scaleup_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_cutover_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_route_enable_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_send_packet_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_broker_readiness_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_scaleup_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_cutover_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_route_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_dispatch_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_send_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_ack_complete_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_roundtrip_complete_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_scaleup_complete_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_cutover_complete_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_route_complete_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_dispatch_complete_final_review_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
    }
    view_38_check_prefix = f"{prefix}_dispatch_extended_complete_final"
    expected_checks.update(
        {
            f"{view_38_check_prefix}_lineage_match_required",
            f"{view_38_check_prefix}_lineage_matches",
            f"{view_38_check_prefix}_source_lineage_sha256_matches",
            f"{view_38_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_38_check_prefix}_compatibility_dispatch_complete_final_review_carried_lineage_sha256_matches",
            f"{view_38_check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_38_check_prefix}_scaleup_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_38_check_prefix}_cutover_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_38_check_prefix}_route_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_38_check_prefix}_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_38_check_prefix}_send_extended_complete_final_review_carried_lineage_sha256_matches",
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
            f"{view_38_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    view_46_check_prefix = f"{prefix}_dispatch_latest_extended_complete_final"
    expected_checks.update(
        {
            f"{view_46_check_prefix}_lineage_match_required",
            f"{view_46_check_prefix}_lineage_matches",
            f"{view_46_check_prefix}_source_lineage_sha256_matches",
            f"{view_46_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_46_check_prefix}_compatibility_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_46_check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_46_check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_46_check_prefix}_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_46_check_prefix}_route_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_46_check_prefix}_dispatch_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_46_check_prefix}_send_latest_extended_complete_final_review_carried_lineage_sha256_matches",
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
            f"{view_46_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    view_54_check_prefix = f"{prefix}_dispatch_current_latest_extended_complete_final"
    expected_checks.update(
        {
            f"{view_54_check_prefix}_lineage_match_required",
            f"{view_54_check_prefix}_lineage_matches",
            f"{view_54_check_prefix}_source_lineage_sha256_matches",
            f"{view_54_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_54_check_prefix}_compatibility_send_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_roundtrip_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_scaleup_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_cutover_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_route_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_dispatch_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_dispatch_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{view_54_check_prefix}_send_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    view_62_check_prefix = (
        f"{prefix}_dispatch_reconciled_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{view_62_check_prefix}_lineage_match_required",
            f"{view_62_check_prefix}_lineage_matches",
            f"{view_62_check_prefix}_source_lineage_sha256_matches",
            f"{view_62_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_62_check_prefix}_compatibility_send_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_scaleup_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_cutover_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_route_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_dispatch_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_dispatch_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{view_62_check_prefix}_send_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    view_62_special_fields = {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }
    for field in dispatch_view_62:
        if field in view_62_special_fields:
            continue
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_checks.add(
            f"{view_62_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    view_70_check_prefix = (
        f"{prefix}_dispatch_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{view_70_check_prefix}_lineage_match_required",
            f"{view_70_check_prefix}_lineage_matches",
            f"{view_70_check_prefix}_source_lineage_sha256_matches",
            f"{view_70_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_70_check_prefix}_compatibility_send_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_70_check_prefix}_dispatch_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{view_70_check_prefix}_send_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    view_70_special_fields = {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }
    for field in dispatch_view_70:
        if field in view_70_special_fields:
            continue
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_checks.add(
            f"{view_70_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    view_78_check_prefix = (
        f"{prefix}_dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{view_78_check_prefix}_lineage_match_required",
            f"{view_78_check_prefix}_lineage_matches",
            f"{view_78_check_prefix}_source_lineage_sha256_matches",
            f"{view_78_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{view_78_check_prefix}_compatibility_send_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{view_78_check_prefix}_dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{view_78_check_prefix}_send_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    view_78_special_fields = {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }
    for field in dispatch_view_78:
        if field in view_78_special_fields:
            continue
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_checks.add(
            f"{view_78_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


def test_broker_dispatch_send_carries_target_application_vendor_batch_from_dispatch_summary():
    vendor = target_application_vendor_market_data_batch_config()
    summary_input = with_dispatch_broker_vendor_batch_summary(dispatch_summary(), vendor)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=summary_input,
        dispatch_orders=dispatch_orders(),
        dispatch_config=dispatch_config(),
    )

    assert report.ready
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    carried = report.config[prefix]
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    assert carried["datasets"][1]["mapping_scope_review_id"] == "scope-review-1"
    final_lineage = report.config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["route_enable_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["dispatch_plan_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]
    extended_lineage = report.config[
        "send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert extended_lineage["required"]
    assert extended_lineage["matches"]
    assert extended_lineage[
        "dispatch_complete_final_review_carried_application_lineage_sha256"
    ] == extended_lineage["broker_application_lineage_sha256"]
    assert extended_lineage["carried_application_lineage_sha256"] == extended_lineage[
        "broker_application_lineage_sha256"
    ]
    send_view_55 = report.config[
        "send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_55 == send_view_55_target_application_lineage_comparison(vendor)
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch_view_62 = dispatch_view_62_target_application_lineage_comparison(vendor)
    dispatch_view_62_prefix = (
        "dispatch_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    for field, value in dispatch_view_62.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_view_62_prefix}_{field}"] == value
    assert summary[
        f"{dispatch_view_62_prefix}_send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    send_view_63 = report.config[
        "send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_63 == send_view_63_target_application_lineage_comparison(
        vendor
    )
    dispatch_view_70 = dispatch_view_70_target_application_lineage_comparison(vendor)
    dispatch_view_70_prefix = (
        "dispatch_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    for field, value in dispatch_view_70.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_view_70_prefix}_{field}"] == value
    assert summary[
        f"{dispatch_view_70_prefix}_send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    send_view_71 = report.config[
        "send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_71 == send_view_71_target_application_lineage_comparison(
        vendor
    )
    dispatch_view_78 = dispatch_view_78_target_application_lineage_comparison(vendor)
    dispatch_view_78_prefix = (
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    for field, value in dispatch_view_78.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{dispatch_view_78_prefix}_{field}"] == value
    assert summary[
        f"{dispatch_view_78_prefix}_send_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    send_view_79 = report.config[
        "send_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_79 == send_view_79_target_application_lineage_comparison(
        vendor
    )


def test_broker_dispatch_send_uses_route_compatibility_lineage_before_dispatch_final():
    compatibility_sha256 = "a" * 64
    final_sha256 = "b" * 64
    config = dispatch_config()
    config[
        "route_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": compatibility_sha256,
        "broker_application_lineage_sha256": compatibility_sha256,
        "scaleup_carried_application_lineage_sha256": compatibility_sha256,
        "cutover_carried_application_lineage_sha256": compatibility_sha256,
        "route_carried_application_lineage_sha256": compatibility_sha256,
        "dispatch_carried_application_lineage_sha256": compatibility_sha256,
    }
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": final_sha256,
        "broker_application_lineage_sha256": final_sha256,
        "scaleup_carried_application_lineage_sha256": final_sha256,
        "cutover_carried_application_lineage_sha256": final_sha256,
        "route_carried_application_lineage_sha256": final_sha256,
        "dispatch_carried_application_lineage_sha256": final_sha256,
        "carried_application_lineage_sha256": "c" * 64,
    }

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert report.ready
    lineage = report.config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["current_application_lineage_sha256"] == compatibility_sha256
    assert lineage["broker_application_lineage_sha256"] == compatibility_sha256
    assert lineage["dispatch_carried_application_lineage_sha256"] == compatibility_sha256


def test_broker_dispatch_send_blocks_dispatch_complete_final_lineage_drift():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    complete_final_sha256 = "f" * 64
    config[
        "dispatch_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        **{
            field: complete_final_sha256
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
            )
        },
    }

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_dispatch_carried_lineage_sha256_matches",
        f"{check_prefix}_send_final_review_carried_lineage_sha256_matches",
    } <= failed
    final_lineage = report.config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert final_lineage["dispatch_plan_review_carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    assert final_lineage["broker_application_lineage_sha256"] != complete_final_sha256
    send_complete_final = report.config[
        "send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_complete_final["broker_application_lineage_sha256"] == (
        complete_final_sha256
    )
    assert send_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_broker_dispatch_send_blocks_dispatch_view_30_lineage_drift():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config[
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_30_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_dispatch_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_final = report.config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    send_complete_final = report.config[
        "send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_final["broker_application_lineage_sha256"] == lineage_sha256
    assert send_final["carried_application_lineage_sha256"] == lineage_sha256
    assert send_complete_final["broker_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert send_complete_final[
        "dispatch_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert send_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    send_extended_complete_final = report.config[
        "send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_extended_complete_final["broker_application_lineage_sha256"] == (
        "f" * 64
    )
    assert send_extended_complete_final[
        "dispatch_complete_final_review_carried_application_lineage_sha256"
    ] == "f" * 64
    assert send_extended_complete_final["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_broker_dispatch_send_blocks_dispatch_view_38_drift_while_preserving_view_31():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_38_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_dispatch_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_view_31 = report.config[
        "send_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_31["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        send_view_31[
            "dispatch_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert send_view_31["carried_application_lineage_sha256"] == lineage_sha256
    assert send_view_31["broker_application_lineage_sha256"] != "f" * 64
    send_view_39 = report.config[
        "send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_39["broker_application_lineage_sha256"] == "f" * 64
    assert (
        send_view_39[
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert send_view_39["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_send_blocks_dispatch_view_46_drift_while_preserving_view_39():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_46_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_view_39 = report.config[
        "send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_39["required"]
    assert send_view_39["matches"]
    assert send_view_39["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        send_view_39[
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert send_view_39["carried_application_lineage_sha256"] == lineage_sha256
    assert send_view_39["broker_application_lineage_sha256"] != "f" * 64
    send_view_47 = report.config[
        "send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_47["broker_application_lineage_sha256"] == "f" * 64
    assert (
        send_view_47[
            "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert send_view_47["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_send_blocks_dispatch_view_54_drift_while_preserving_view_47():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    view_54 = dispatch_view_54_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    config[
        "dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_54
    summary = with_dispatch_broker_vendor_batch_summary(dispatch_summary(), vendor)
    view_54_prefix = (
        "route_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{view_54_prefix}_lineage_match_required"] = view_54[
        "required"
    ]
    summary.loc[0, f"{view_54_prefix}_lineage_matches"] = view_54["matches"]
    for field, value in view_54.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        summary.loc[0, f"{view_54_prefix}_{field}"] = value
    summary.loc[
        0,
        f"{view_54_prefix}_dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
    ] = view_54["carried_application_lineage_sha256"]

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=summary,
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_send_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_view_47 = report.config[
        "send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_47["required"]
    assert send_view_47["matches"]
    assert send_view_47["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        send_view_47[
            "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert send_view_47["carried_application_lineage_sha256"] == lineage_sha256
    assert send_view_47["broker_application_lineage_sha256"] != "f" * 64
    send_view_55 = report.config[
        "send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_55["broker_application_lineage_sha256"] == "f" * 64
    assert (
        send_view_55[
            "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert send_view_55["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_send_blocks_dispatch_view_62_drift_while_preserving_view_55():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    view_62 = dispatch_view_62_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )
    config[
        "dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_62
    summary = with_dispatch_broker_vendor_batch_summary(dispatch_summary(), vendor)
    view_62_prefix = (
        "route_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{view_62_prefix}_lineage_match_required"] = view_62[
        "required"
    ]
    summary.loc[0, f"{view_62_prefix}_lineage_matches"] = view_62["matches"]
    for field, value in view_62.items():
        if field in {"required", "matches"}:
            continue
        summary_field = (
            "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            if field == "carried_application_lineage_sha256"
            else field
        )
        summary.loc[0, f"{view_62_prefix}_{summary_field}"] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=summary,
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_send_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_view_55 = report.config[
        "send_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_55 == send_view_55_target_application_lineage_comparison(vendor)
    assert send_view_55["broker_application_lineage_sha256"] == lineage_sha256
    assert send_view_55["broker_application_lineage_sha256"] != "f" * 64
    send_view_63 = report.config[
        "send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_send_view_63 = dict(view_62)
    expected_send_view_63[
        "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] = lineage_sha256
    expected_send_view_63["carried_application_lineage_sha256"] = lineage_sha256
    assert send_view_63 == expected_send_view_63


def test_broker_dispatch_send_blocks_dispatch_view_70_drift_while_preserving_view_63():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    drifted_view_70 = dispatch_view_70_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_70) == 69
    config[
        "dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = drifted_view_70
    summary = with_dispatch_broker_vendor_batch_summary(dispatch_summary(), vendor)
    view_70_prefix = (
        "route_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{view_70_prefix}_lineage_match_required"] = (
        drifted_view_70["required"]
    )
    summary.loc[0, f"{view_70_prefix}_lineage_matches"] = drifted_view_70[
        "matches"
    ]
    for field, value in drifted_view_70.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        summary.loc[0, f"{view_70_prefix}_{field}"] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=summary,
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_send_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_view_63 = report.config[
        "send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_63 == send_view_63_target_application_lineage_comparison(
        vendor
    )
    assert send_view_63["broker_application_lineage_sha256"] == lineage_sha256
    assert send_view_63["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    send_view_71 = report.config[
        "send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert len(send_view_71) == 70
    assert send_view_71["broker_application_lineage_sha256"] == (
        drifted_lineage_sha256
    )
    assert send_view_71[
        "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == drifted_lineage_sha256
    assert send_view_71[
        "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert send_view_71["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_send_blocks_dispatch_view_78_drift_while_preserving_view_71():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)

    drifted_view_78 = dispatch_view_78_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_78) == 77
    config[
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = drifted_view_78

    summary = with_dispatch_broker_vendor_batch_summary(dispatch_summary(), vendor)
    additive_prefix = (
        "route_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    summary.loc[0, f"{additive_prefix}_lineage_match_required"] = drifted_view_78[
        "required"
    ]
    summary.loc[0, f"{additive_prefix}_lineage_matches"] = drifted_view_78[
        "matches"
    ]
    for field, value in drifted_view_78.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        summary.loc[0, f"{additive_prefix}_{field}"] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=summary,
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_send_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_send_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    send_view_71 = report.config[
        "send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert send_view_71 == send_view_71_target_application_lineage_comparison(
        vendor
    )
    assert send_view_71["broker_application_lineage_sha256"] == lineage_sha256
    assert send_view_71["broker_application_lineage_sha256"] != drifted_lineage_sha256
    send_view_79 = report.config[
        "send_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert len(send_view_79) == 78
    assert send_view_79["broker_application_lineage_sha256"] == drifted_lineage_sha256
    assert send_view_79[
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == drifted_lineage_sha256
    assert send_view_79[
        "send_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
    ] == lineage_sha256
    assert send_view_79["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_send_requires_dispatch_view_78_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    send_view_79 = report.config[
        "send_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not send_view_79["required"]
    assert not send_view_79["matches"]


@pytest.mark.parametrize(
    ("field", "value", "failed_check_suffix"),
    [
        ("required", False, "lineage_match_required"),
        ("matches", False, "lineage_matches"),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "source_lineage_sha256_matches",
        ),
        (
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_78_lineage(
    field,
    value,
    failed_check_suffix,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    view_78 = config[
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    view_78[field] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        f"{failed_check_suffix}"
    ) in failed


def test_broker_dispatch_send_requires_dispatch_view_70_lineage_for_verified_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check = report.checks.set_index("check").loc[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_verified_reconciled_current_latest_extended_complete_final_lineage_match_required"
    ]
    assert not bool(check["passed"])
    send_view_71 = report.config[
        "send_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not send_view_71["required"]
    assert not send_view_71["matches"]


@pytest.mark.parametrize(
    ("field", "value", "failed_check_suffix"),
    [
        ("required", False, "lineage_match_required"),
        ("matches", False, "lineage_matches"),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "source_lineage_sha256_matches",
        ),
        (
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_70_lineage(
    field,
    value,
    failed_check_suffix,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    view_70 = dispatch_view_70_target_application_lineage_comparison(vendor)
    view_70[field] = value
    config[
        "dispatch_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_70

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        f"dispatch_verified_reconciled_current_latest_extended_complete_final_{failed_check_suffix}"
        in failed
    )


def test_broker_dispatch_send_requires_dispatch_view_62_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check = report.checks.set_index("check").loc[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_reconciled_current_latest_extended_complete_final_lineage_match_required"
    ]
    assert not bool(check["passed"])
    send_view_63 = report.config[
        "send_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not send_view_63["required"]
    assert not send_view_63["matches"]


@pytest.mark.parametrize(
    ("field", "value", "failed_check_suffix"),
    [
        ("required", False, "lineage_match_required"),
        ("matches", False, "lineage_matches"),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "source_lineage_sha256_matches",
        ),
        (
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_62_lineage(
    field,
    value,
    failed_check_suffix,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    view_62 = dispatch_view_62_target_application_lineage_comparison(vendor)
    view_62[field] = value
    config[
        "dispatch_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = view_62

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        f"dispatch_reconciled_current_latest_extended_complete_final_{failed_check_suffix}"
        in failed
    )


def test_broker_dispatch_send_requires_dispatch_view_54_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert f"{check_prefix}_lineage_match_required" in failed


@pytest.mark.parametrize(
    ("field", "value", "failed_suffix"),
    [
        ("required", False, "lineage_match_required"),
        ("matches", False, "lineage_matches"),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "source_lineage_sha256_matches",
        ),
        (
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "roundtrip_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_54_lineage(
    field,
    value,
    failed_suffix,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    view_54 = config[
        "dispatch_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    view_54[field] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_"
        "dispatch_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert f"{check_prefix}_{failed_suffix}" in failed


def test_broker_dispatch_send_requires_dispatch_view_46_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    send_view_47 = report.config[
        "send_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not send_view_47["required"]
    assert not send_view_47["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final_send_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_latest_extended_complete_final_dispatch_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_46_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    dispatch_view_46 = config[
        "dispatch_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    dispatch_view_46[field] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_send_requires_dispatch_view_38_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = (
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    send_view_39 = report.config[
        "send_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not send_view_39["required"]
    assert not send_view_39["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_extended_complete_final_dispatch_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_38_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    dispatch_view_38 = config[
        "dispatch_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    dispatch_view_38[field] = value

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_send_blocks_incomplete_target_application_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config(
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
    )
    vendor["datasets"][1]["mapping_application_sha256"] = ""
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
    } <= failed


def test_broker_dispatch_send_blocks_target_application_lineage_drift_after_dispatch_plan():
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = lineage
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    vendor["datasets"][1]["mapping_application_sha256"] = "9" * 64

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert f"{output_prefix}_send_carried_lineage_sha256_matches" in failed
    assert f"{output_prefix}_send_packet_review_carried_lineage_sha256_matches" in failed
    assert {
        f"{output_prefix}_source_lineage_sha256_matches",
        f"{output_prefix}_scaleup_carried_lineage_sha256_matches",
        f"{output_prefix}_cutover_carried_lineage_sha256_matches",
        f"{output_prefix}_route_carried_lineage_sha256_matches",
        f"{output_prefix}_dispatch_carried_lineage_sha256_matches",
        f"{output_prefix}_final_dispatch_plan_review_carried_lineage_sha256_matches",
    } <= passed


@pytest.mark.parametrize(
    ("lineage_mutation", "vendor_overrides", "expected_check"),
    [
        (
            {"matches": False},
            {},
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ),
        (
            {"current_application_lineage_sha256": "f" * 64},
            {},
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        ),
        (
            {},
            {"application_lineage_consistent": False},
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        ),
    ],
)
def test_broker_dispatch_send_blocks_failed_dispatch_target_lineage_decisions(
    lineage_mutation,
    vendor_overrides,
    expected_check,
):
    vendor = target_application_vendor_market_data_batch_config(**vendor_overrides)
    lineage = target_application_lineage_comparison(vendor)
    lineage.update(lineage_mutation)
    config = dispatch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = lineage
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.ready
    assert expected_check in failed


def test_broker_dispatch_send_requires_final_lineage_comparison_for_reconciled_target():
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    add_dispatch_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
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
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        ),
        (
            "readiness_carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_final_dispatch_plan_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )
    add_dispatch_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_send_requires_dispatch_complete_final_lineage():
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = f"{output_prefix}_dispatch_final"
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
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_final_source_lineage_sha256_matches",
        ),
        (
            "cutover_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_final_cutover_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_final_dispatch_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_complete_final_lineage(
    field,
    value,
    expected_failed_check,
):
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(
        config,
        vendor,
        **{field: value},
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_send_requires_dispatch_view_30_lineage():
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    check_prefix = f"{output_prefix}_dispatch_complete_final"
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
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_complete_final_source_lineage_sha256_matches",
        ),
        (
            "route_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_complete_final_route_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dispatch_complete_final_dispatch_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_send_blocks_invalid_dispatch_view_30_lineage(
    field,
    value,
    expected_failed_check,
):
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_final_target_application_lineage_comparison(vendor)
    add_dispatch_complete_final_target_application_lineage(config, vendor)
    config[
        "dispatch_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = dispatch_view_30_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_send_skips_final_lineage_for_non_reconciled_target():
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    input_prefix = "route_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert report.ready
    check_names = set(report.checks["check"])
    final_prefix = f"{output_prefix}_final_"
    assert not any(name.startswith(final_prefix) for name in check_names)
    assert f"{output_prefix}_send_packet_review_carried_lineage_sha256_matches" not in check_names


def test_broker_dispatch_send_blocks_failed_broker_vendor_data_readiness():
    config = dispatch_config()
    config["route_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config(
        ready=False,
        failed_checks=1,
    )
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    readiness = report.config["dispatch_broker_vendor_data_readiness"]
    assert {
        "dispatch_broker_vendor_data_readiness_ready",
        "dispatch_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert summary["dispatch_broker_vendor_data_readiness_provided"]
    assert not summary["dispatch_broker_vendor_data_readiness_ready"]
    assert int(summary["dispatch_broker_vendor_data_readiness_failed_checks"]) == 1
    assert readiness["provided"]
    assert not readiness["ready"]
    assert readiness["failed_checks"] == 1
    assert report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_broker_dispatch_send_prefers_dispatch_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor_market_data_batch_config()
    config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == (
        "india_nse_index_derivatives"
    )
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]


def test_broker_dispatch_send_blocks_wrong_manifest_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_send_carries_roundtrip_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.ready
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["unique_mapping_drafts"] == 1


def test_broker_dispatch_send_blocks_wrong_manifest_roundtrip_vendor_market_data_batch():
    config = dispatch_config()
    config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_send_carries_dispatch_broker_vendor_market_data_batch_when_preferred():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
    } <= failed
    assert not summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "irage"
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == "us_options_regular"
    assert vendor["adapter"] == "irage"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 0.0
    assert vendor["min_mapping_coverage"] == 0.0
    assert vendor["unique_mapping_drafts"] == 0
    assert vendor["failed_datasets"] == 1
    assert not vendor["comparison"]["accepted"]


def test_broker_dispatch_send_blocks_wrong_manifest_dispatch_broker_vendor_market_data_batch_when_preferred():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_send_blocks_bad_route_broker_shadow_broker_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
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

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_broker_shadow_broker_readiness_ready",
        "dispatch_broker_shadow_broker_vendor_data_readiness_ready",
        "dispatch_broker_shadow_broker_vendor_data_readiness_failed_checks",
        "dispatch_broker_shadow_broker_adapter_matches",
        "dispatch_broker_shadow_broker_adapter_consistent",
        "dispatch_broker_shadow_broker_route_readiness_ready",
        "dispatch_broker_shadow_broker_route_readiness_strategy_matches",
        "dispatch_broker_shadow_broker_route_readiness_market_matches",
        "dispatch_broker_shadow_broker_route_readiness_gap_pairs",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_ready",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_market_matches",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "dispatch_broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "dispatch_broker_shadow_broker_route_dispatch_roundtrip_ready",
        "dispatch_broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "dispatch_broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "dispatch_broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "failed_checks"
    ] == 1
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_send_blocks_partial_route_broker_shadow_broker_vendor_data_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        dispatch_config=config,
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "dispatch_broker_shadow_broker_vendor_data_readiness_provided",
        "dispatch_broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["route_broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_broker_dispatch_send_requires_route_readiness():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_readiness_provided=False, route_readiness_ready=False),
        dispatch_orders=dispatch_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_provided", "route_readiness_ready"} <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_broker_dispatch_send_blocks_route_readiness_identity_mismatch():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        dispatch_orders=dispatch_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_strategy_matches", "route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "us_options_regular"


def test_broker_dispatch_send_blocks_stale_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        dispatch_orders=dispatch_orders(),
        dispatch_config=dispatch_config(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
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


def test_broker_dispatch_send_blocks_stale_route_broker_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        dispatch_orders=dispatch_orders(),
        dispatch_config=dispatch_config(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
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


def test_broker_dispatch_send_requires_route_roundtrip_proof():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        dispatch_orders=dispatch_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_send_blocks_bad_route_roundtrip_quality():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(
            route_roundtrip_ready=False,
            route_roundtrip_target_mode="shadow",
            route_roundtrip_strategy="surface_mm",
            route_roundtrip_market="us_options_regular",
            route_roundtrip_scenario_key="wrong-scenario",
            route_roundtrip_missing_request_acks=1,
            route_roundtrip_rejected_orders=1,
            route_roundtrip_unmatched_acks=1,
        ),
        dispatch_orders=dispatch_orders(),
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


def test_broker_dispatch_send_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        dispatch_orders=dispatch_orders(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.summary.iloc[0]["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1
    assert report.config["broker_readiness"]["schema_reviewed"]


def test_broker_dispatch_send_reads_nested_route_enable_dispatch_roundtrip_failed_checks(tmp_path):
    dispatch = write_dispatch(tmp_path)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(dispatch_config(route_enable_dispatch_roundtrip_failed_checks=1), indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=tmp_path / "dispatch_send",
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_send_blocks_route_roundtrip_batch_mismatch():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(route_roundtrip_batch_id="BDP-0"),
        dispatch_orders=dispatch_orders(route_roundtrip_batch_id="BDP-OLD"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"dispatch_order_route_roundtrip_batch_matches", "request_route_roundtrip_batch_matches"} <= failed
    assert report.summary.iloc[0]["route_dispatch_roundtrip_batch_id"] == "BDP-0"
    assert report.requests["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-OLD", "BDP-OLD"]


def test_broker_dispatch_send_packet_blocks_unready_non_dry_run_and_bad_payloads():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(ready=False, state="disabled"),
        dispatch_orders=dispatch_orders(dry_run=False, malformed_payload=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed >= {"dispatch_ready", "dispatch_armed_dry_run", "dry_run_only", "payloads_valid"}
    assert report.summary.iloc[0]["recommendation"] == "keep_broker_sender_disabled"


def test_write_broker_dispatch_send_packet_outputs_artifacts_and_catalog_entry(tmp_path):
    dispatch = write_dispatch(tmp_path)
    out_dir = tmp_path / "dispatch_send"

    report = write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=out_dir)

    assert report.ready
    assert (out_dir / "broker_dispatch_send_requests.csv").exists()
    assert (out_dir / "broker_dispatch_expected_acks.csv").exists()
    assert (out_dir / "broker_dispatch_send_checks.csv").exists()
    assert (out_dir / "broker_dispatch_send_summary.csv").exists()
    assert (out_dir / "broker_dispatch_send_action_queue.csv").exists()
    assert (out_dir / "broker_dispatch_send_config.json").exists()
    assert (out_dir / "broker_dispatch_send_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    requests = pd.read_csv(out_dir / "broker_dispatch_send_requests.csv")
    action_queue = pd.read_csv(out_dir / "broker_dispatch_send_action_queue.csv")
    config = json.loads((out_dir / "broker_dispatch_send_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_dispatch_send_runbook.md").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {path_tail(item["path"]) for item in manifest["artifacts"]}
    assert action_queue.empty
    assert int(summary.loc[0, "action_queue_count"]) == 0
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert config["action_queue_count"] == 0
    assert config["next_actions"] == []
    assert not config["authorizes_submission"]
    assert config["broker_dispatch_lineage"]["broker_dispatch_lineage_gate_passed"]
    assert bool(summary.loc[0, "broker_dispatch_lineage_gate_passed"])
    assert bool(summary.loc[0, "broker_dispatch_route_enable_matches_current"])
    assert not bool(summary.loc[0, "authorizes_submission"])
    assert requests["broker_dispatch_lineage_gate_passed"].astype(bool).all()
    assert not requests["authorizes_submission"].astype(bool).any()
    request_payload = json.loads(requests.loc[0, "request_payload_json"])
    assert request_payload["broker_dispatch_lineage_gate_passed"] is True
    assert request_payload["authorizes_submission"] is False
    assert runbook.startswith("# Broker Dispatch Send Runbook")
    assert "No broker dispatch send actions." in runbook
    assert "broker_dispatch_send_action_queue.csv" in artifact_paths
    assert "broker_dispatch_send_runbook.md" in artifact_paths
    assert path_tail(manifest["inputs"]["dispatch_summary"]["path"]).endswith(
        "/broker_dispatch_summary.csv"
    )
    assert path_tail(manifest["inputs"]["dispatch_orders"]["path"]).endswith(
        "/broker_dispatch_orders.csv"
    )
    assert path_tail(manifest["inputs"]["dispatch_config"]["path"]).endswith(
        "/broker_dispatch_config.json"
    )
    assert path_tail(manifest["inputs"]["dispatch_manifest"]["path"]).endswith(
        "/manifest.json"
    )
    assert "broker_dispatch_artifacts" in manifest["inputs"]
    assert "broker_dispatch_dependencies" in manifest["inputs"]
    assert manifest["extra"]["broker_dispatch_lineage_gate_passed"]
    assert manifest["extra"]["authorizes_submission"] is False
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_send_packet"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_send_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_broker_dispatch_send_lineage_verifies_complete_current_packet(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)

    lineage = load_broker_dispatch_send_lineage(
        send / "broker_dispatch_send_config.json",
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["provided"]
    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert lineage["non_authorizing"]
    assert lineage["broker_dispatch_matches_current"]
    assert lineage["expected_dispatch_matches_current"]
    assert lineage["gate_passed"]


def test_cli_broker_dispatch_ack_requires_verified_send_packet(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    acks_path = tmp_path / "broker_acks.csv"
    acks = pd.read_csv(send / "broker_dispatch_expected_acks.csv")
    acks["broker_order_id"] = [f"ACK-{index + 1}" for index in range(len(acks))]
    acks["ack_status"] = "dry_run_accepted"
    acks["ack_ts_ns"] = range(1_000_000, 1_000_000 + len(acks))
    acks.to_csv(acks_path, index=False)
    out = tmp_path / "dispatch_ack"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--require-send-packet",
            "--acks",
            str(acks_path),
            "--out",
            str(out),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out / "broker_dispatch_ack_summary.csv")
    config = json.loads(
        (out / "broker_dispatch_ack_config.json").read_text(encoding="utf-8")
    )
    assert code == 0
    assert bool(summary.loc[0, "passed"])
    assert bool(summary.loc[0, "broker_dispatch_send_lineage_gate_passed"])
    assert config["broker_dispatch_send_lineage"][
        "broker_dispatch_send_lineage_gate_passed"
    ]
    assert not config["authorizes_submission"]
    with pytest.raises(ValueError, match="must not overwrite"):
        main(
            [
                "reconcile-broker-dispatch",
                "--dispatch",
                str(dispatch),
                "--send",
                str(send),
                "--require-send-packet",
                "--acks",
                str(acks_path),
                "--out",
                str(send / "ack"),
            ]
        )


def test_broker_dispatch_ack_lineage_closes_final_roundtrip(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)

    lineage = load_broker_dispatch_ack_lineage(
        ack / "broker_dispatch_ack_config.json",
        expected_broker_dispatch_send_config_path=(
            send / "broker_dispatch_send_config.json"
        ),
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )
    report = write_broker_dispatch_roundtrip(
        dispatch_dir=dispatch,
        send_dir=send,
        ack_dir=ack,
        output_dir=tmp_path / "roundtrip",
        thresholds=BrokerDispatchRoundTripThresholds(
            require_ack_lineage=True
        ),
    )

    assert lineage["provided"]
    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert lineage["non_authorizing"]
    assert lineage["send_lineage_gate_passed"]
    assert lineage["send_matches_current"]
    assert lineage["expected_send_matches_current"]
    assert lineage["gate_passed"]
    assert report.passed
    assert report.orders["broker_dispatch_ack_lineage_gate_passed"].map(
        bool
    ).all()
    assert not report.orders["authorizes_submission"].map(bool).any()
    assert report.config["broker_dispatch_ack_lineage"][
        "broker_dispatch_ack_lineage_gate_passed"
    ]
    assert not report.config["authorizes_submission"]
    assert verify_experiment_manifest(
        tmp_path / "roundtrip" / "manifest.json",
        expected_run_type="broker_dispatch_roundtrip",
        require_input_fingerprints=True,
    ).passed
    cli_code = main(
        [
            "review-broker-dispatch-roundtrip",
            "--dispatch",
            str(dispatch),
            "--send",
            str(send),
            "--ack",
            str(ack),
            "--out",
            str(tmp_path / "roundtrip_cli"),
            "--require-ack-lineage",
            "--fail-on-breach",
        ]
    )
    assert cli_code == 0
    with pytest.raises(ValueError, match="must not overwrite"):
        write_broker_dispatch_roundtrip(
            dispatch_dir=dispatch,
            send_dir=send,
            ack_dir=ack,
            output_dir=ack / "roundtrip",
            thresholds=BrokerDispatchRoundTripThresholds(
                require_ack_lineage=True
            ),
        )


def test_broker_dispatch_ack_lineage_blocks_row_contract_mismatch(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)
    acknowledgements_path = ack / "broker_dispatch_acknowledgements.csv"
    acknowledgement_rows = pd.read_csv(acknowledgements_path)
    acknowledgement_rows.loc[
        0, "broker_dispatch_send_manifest_sha256"
    ] = "f" * 64
    acknowledgement_rows.to_csv(acknowledgements_path, index=False)
    _refresh_manifest(ack / "manifest.json")

    lineage = load_broker_dispatch_ack_lineage(
        ack / "broker_dispatch_ack_config.json",
        expected_broker_dispatch_send_config_path=(
            send / "broker_dispatch_send_config.json"
        ),
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert not lineage["contract_consistent"]
    assert lineage["send_matches_current"]
    assert not lineage["gate_passed"]
    assert "broker_dispatch_ack_rows_broker_dispatch_send_manifest_sha256_mismatch" in (
        lineage["contract_error"]
    )


def test_broker_dispatch_ack_lineage_blocks_consistent_send_relabel(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)
    _rewrite_ack_send_lineage_field(
        ack,
        "broker_dispatch_send_manifest_sha256",
        "f" * 64,
    )

    lineage = load_broker_dispatch_ack_lineage(
        ack / "broker_dispatch_ack_config.json",
        expected_broker_dispatch_send_config_path=(
            send / "broker_dispatch_send_config.json"
        ),
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert lineage["send_lineage_gate_passed"]
    assert not lineage["send_matches_current"]
    assert not lineage["expected_send_matches_current"]
    assert not lineage["gate_passed"]


def test_broker_dispatch_ack_lineage_blocks_authorizing_claim(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)
    summary_path = ack / "broker_dispatch_ack_summary.csv"
    acknowledgements_path = ack / "broker_dispatch_acknowledgements.csv"
    config_path = ack / "broker_dispatch_ack_config.json"
    summary = pd.read_csv(summary_path)
    acknowledgement_rows = pd.read_csv(acknowledgements_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary["authorizes_submission"] = True
    acknowledgement_rows["authorizes_submission"] = True
    config["authorizes_submission"] = True
    summary.to_csv(summary_path, index=False)
    acknowledgement_rows.to_csv(acknowledgements_path, index=False)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(
        ack / "manifest.json",
        extra_updates={"authorizes_submission": True},
    )

    lineage = load_broker_dispatch_ack_lineage(
        ack / "broker_dispatch_ack_config.json",
        expected_broker_dispatch_send_config_path=(
            send / "broker_dispatch_send_config.json"
        ),
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert not lineage["non_authorizing"]
    assert lineage["send_matches_current"]
    assert not lineage["gate_passed"]


def test_broker_dispatch_ack_lineage_blocks_stale_ack_artifact(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)
    summary_path = ack / "broker_dispatch_ack_summary.csv"
    summary_path.write_text(
        summary_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    lineage = load_broker_dispatch_ack_lineage(
        ack / "broker_dispatch_ack_config.json",
        expected_broker_dispatch_send_config_path=(
            send / "broker_dispatch_send_config.json"
        ),
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert not lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert lineage["send_matches_current"]
    assert not lineage["gate_passed"]


def test_broker_dispatch_ack_lineage_recomputes_ack_counts(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)
    summary_path = ack / "broker_dispatch_ack_summary.csv"
    config_path = ack / "broker_dispatch_ack_config.json"
    summary = pd.read_csv(summary_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary["acked_orders"] = 0
    config["acked_orders"] = 0
    summary.to_csv(summary_path, index=False)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(ack / "manifest.json")

    lineage = load_broker_dispatch_ack_lineage(
        ack / "broker_dispatch_ack_config.json",
        expected_broker_dispatch_send_config_path=(
            send / "broker_dispatch_send_config.json"
        ),
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert not lineage["contract_consistent"]
    assert "broker_dispatch_ack_summary_acked_orders_mismatch" in lineage[
        "contract_error"
    ]
    assert "broker_dispatch_ack_config_acked_orders_mismatch" in lineage[
        "contract_error"
    ]
    assert not lineage["gate_passed"]


def test_broker_dispatch_roundtrip_blocks_wrong_send_source(tmp_path):
    dispatch, send, ack = _write_verified_ack_chain(tmp_path)
    other_send = tmp_path / "other_send"
    write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=other_send,
    )

    report = write_broker_dispatch_roundtrip(
        dispatch_dir=dispatch,
        send_dir=other_send,
        ack_dir=ack,
        output_dir=tmp_path / "roundtrip",
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
        "broker_dispatch_ack_expected_send_matches_current",
        "broker_dispatch_ack_lineage_gate_passed",
    } <= failed
    action = report.action_queue.set_index("check").loc[
        "broker_dispatch_ack_expected_send_matches_current"
    ]
    assert action["component"] == "broker_dispatch_ack"
    assert action["next_gate"] == "reconcile-broker-dispatch"


def test_broker_dispatch_send_lineage_blocks_request_contract_mismatch(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    requests_path = send / "broker_dispatch_send_requests.csv"
    requests = pd.read_csv(requests_path)
    requests["broker_dispatch_manifest_sha256"] = "f" * 64
    requests.to_csv(requests_path, index=False)
    _refresh_manifest(send / "manifest.json")

    lineage = load_broker_dispatch_send_lineage(
        send / "broker_dispatch_send_config.json",
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert not lineage["contract_consistent"]
    assert lineage["broker_dispatch_matches_current"]
    assert not lineage["gate_passed"]
    assert "broker_dispatch_send_requests_broker_dispatch_manifest_sha256_mismatch" in (
        lineage["contract_error"]
    )


def test_broker_dispatch_send_lineage_blocks_payload_hash_mismatch(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    requests_path = send / "broker_dispatch_send_requests.csv"
    requests = pd.read_csv(requests_path)
    payload = json.loads(requests.loc[0, "request_payload_json"])
    payload["order"]["quantity"] = 9_999
    requests.loc[0, "request_payload_json"] = json.dumps(payload, sort_keys=True)
    requests.to_csv(requests_path, index=False)
    _refresh_manifest(send / "manifest.json")

    lineage = load_broker_dispatch_send_lineage(
        send / "broker_dispatch_send_config.json",
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert not lineage["contract_consistent"]
    assert "broker_dispatch_send_request_hash_contract_mismatch" in lineage[
        "contract_error"
    ]
    assert not lineage["gate_passed"]


def test_broker_dispatch_send_lineage_blocks_expected_ack_template_mismatch(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    expected_acks_path = send / "broker_dispatch_expected_acks.csv"
    expected_acks = pd.read_csv(expected_acks_path)
    expected_acks.loc[0, "request_id"] = "REQ-DETACHED"
    expected_acks.to_csv(expected_acks_path, index=False)
    _refresh_manifest(send / "manifest.json")

    lineage = load_broker_dispatch_send_lineage(
        send / "broker_dispatch_send_config.json",
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert not lineage["contract_consistent"]
    assert lineage["broker_dispatch_matches_current"]
    assert not lineage["gate_passed"]
    assert "broker_dispatch_send_expected_ack_template_mismatch" in lineage[
        "contract_error"
    ]


def test_broker_dispatch_send_lineage_blocks_consistent_dispatch_relabel(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    _rewrite_send_dispatch_lineage_field(
        send,
        "broker_dispatch_manifest_sha256",
        "f" * 64,
    )

    lineage = load_broker_dispatch_send_lineage(
        send / "broker_dispatch_send_config.json",
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert lineage["broker_dispatch_lineage_gate_passed"]
    assert not lineage["broker_dispatch_matches_current"]
    assert not lineage["expected_dispatch_matches_current"]
    assert not lineage["gate_passed"]


def test_broker_dispatch_send_lineage_blocks_authorizing_packet(tmp_path):
    dispatch = write_dispatch(tmp_path)
    send = tmp_path / "dispatch_send"
    write_broker_dispatch_send_packet(dispatch_dir=dispatch, output_dir=send)
    summary_path = send / "broker_dispatch_send_summary.csv"
    requests_path = send / "broker_dispatch_send_requests.csv"
    config_path = send / "broker_dispatch_send_config.json"
    summary = pd.read_csv(summary_path)
    requests = pd.read_csv(requests_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary["authorizes_submission"] = True
    requests["authorizes_submission"] = True
    requests["request_payload_json"] = requests["request_payload_json"].map(
        lambda raw: json.dumps(
            {**json.loads(raw), "authorizes_submission": True},
            sort_keys=True,
        )
    )
    config["authorizes_submission"] = True
    summary.to_csv(summary_path, index=False)
    _write_rehashed_send_requests(send, requests)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(
        send / "manifest.json",
        extra_updates={"authorizes_submission": True},
    )

    lineage = load_broker_dispatch_send_lineage(
        send / "broker_dispatch_send_config.json",
        expected_broker_dispatch_config_path=(
            dispatch / "broker_dispatch_config.json"
        ),
    )

    assert lineage["manifest_current"]
    assert lineage["contract_consistent"]
    assert not lineage["non_authorizing"]
    assert lineage["broker_dispatch_matches_current"]
    assert not lineage["gate_passed"]


def test_broker_dispatch_send_blocks_recursive_route_source_drift(tmp_path):
    dispatch = write_dispatch(tmp_path)
    (tmp_path / "cutover" / "runtime_source.txt").write_text(
        "drifted\n", encoding="utf-8"
    )

    report = write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=tmp_path / "dispatch_send",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert bool(summary["broker_dispatch_manifest_current"])
    assert bool(summary["broker_dispatch_lineage_contract_consistent"])
    assert not bool(summary["broker_dispatch_route_enable_matches_current"])
    assert {
        "broker_dispatch_route_enable_matches_current",
        "broker_dispatch_lineage_gate_passed",
    } <= failed


def test_broker_dispatch_send_blocks_cross_artifact_lineage_mismatch(tmp_path):
    dispatch = write_dispatch(tmp_path)
    orders_path = dispatch / "broker_dispatch_orders.csv"
    orders = pd.read_csv(orders_path)
    orders["route_enable_manifest_sha256"] = "f" * 64
    orders.to_csv(orders_path, index=False)
    _refresh_manifest(dispatch / "manifest.json")

    report = write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=tmp_path / "dispatch_send",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert bool(summary["broker_dispatch_manifest_current"])
    assert not bool(summary["broker_dispatch_lineage_contract_consistent"])
    assert bool(summary["broker_dispatch_route_enable_matches_current"])
    assert {
        "broker_dispatch_lineage_contract_consistent",
        "broker_dispatch_lineage_gate_passed",
    } <= failed


def test_broker_dispatch_send_blocks_consistent_route_relabel(tmp_path):
    dispatch = write_dispatch(tmp_path)
    _rewrite_dispatch_lineage_field(
        dispatch,
        "route_enable_manifest_sha256",
        "f" * 64,
    )

    report = write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=tmp_path / "dispatch_send",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert not report.ready
    assert bool(summary["broker_dispatch_manifest_current"])
    assert bool(summary["broker_dispatch_lineage_contract_consistent"])
    assert bool(summary["broker_dispatch_route_enable_lineage_gate_passed"])
    assert not bool(summary["broker_dispatch_route_enable_matches_current"])
    assert "broker_dispatch_route_enable_matches_current" in failed


def test_broker_dispatch_send_blocks_authorizing_dispatch_claim(tmp_path):
    dispatch = write_dispatch(tmp_path)
    summary_path = dispatch / "broker_dispatch_summary.csv"
    orders_path = dispatch / "broker_dispatch_orders.csv"
    config_path = dispatch / "broker_dispatch_config.json"
    summary = pd.read_csv(summary_path)
    orders = pd.read_csv(orders_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    summary["authorizes_submission"] = True
    orders["authorizes_submission"] = True
    config["authorizes_submission"] = True
    summary.to_csv(summary_path, index=False)
    orders.to_csv(orders_path, index=False)
    config_path.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _refresh_manifest(
        dispatch / "manifest.json",
        extra_updates={"authorizes_submission": True},
    )

    report = write_broker_dispatch_send_packet(
        dispatch_dir=dispatch,
        output_dir=tmp_path / "dispatch_send",
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary_row = report.summary.iloc[0]
    assert not report.ready
    assert bool(summary_row["broker_dispatch_manifest_current"])
    assert bool(summary_row["broker_dispatch_lineage_contract_consistent"])
    assert not bool(summary_row["broker_dispatch_non_authorizing"])
    assert "broker_dispatch_non_authorizing" in failed
    assert not report.requests["authorizes_submission"].astype(bool).any()


def test_broker_dispatch_send_rejects_source_output_overlap(tmp_path):
    dispatch = write_dispatch(tmp_path)

    with pytest.raises(ValueError, match="must not overwrite"):
        write_broker_dispatch_send_packet(
            dispatch_dir=dispatch,
            output_dir=dispatch / "send",
        )


def test_cli_broker_dispatch_send_hydrates_legacy_draft_vendor_data_from_manifest_chain(
    tmp_path,
):
    dispatch = write_dispatch(
        tmp_path,
        broker_readiness_config={
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
    )
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    config = json.loads((out_dir / "broker_dispatch_send_config.json").read_text(encoding="utf-8"))
    vendor = config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert (
        summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"]
        == "arrow_money"
    )
    assert int(summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert pd.isna(
        summary.loc[
            0,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        ]
    )
    assert int(
        summary.loc[
            0,
            "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
        ]
    ) == 0
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["unique_mapping_drafts"] == 1
    assert not vendor["mapping_source_mode"]
    assert vendor["mapping_application_count"] == 0
    assert vendor["unique_mapping_applications"] == 0
    assert vendor["target_application_coverage"] == 0.0
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64
    assert vendor["datasets"][1]["mapping_source"] == "vendor_intake_draft"


def test_cli_broker_dispatch_send_blocks_thin_target_vendor_sidecar(tmp_path):
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    dispatch = write_dispatch(
        tmp_path,
        broker_readiness_config={
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
                    "required": True,
                    "matches": True,
                    "current_application_lineage_sha256": lineage_sha256,
                    "broker_application_lineage_sha256": lineage_sha256,
                    "carried_application_lineage_sha256": lineage_sha256,
                },
            },
        },
    )
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_route_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_carried_lineage_sha256_matches",
    } <= failed


def test_cli_broker_dispatch_send_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    dispatch = write_dispatch(
        tmp_path,
        broker_readiness_config={
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
    )
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    config = json.loads((out_dir / "broker_dispatch_send_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    readiness = config["dispatch_broker_vendor_data_readiness"]
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        "dispatch_broker_vendor_data_readiness_ready",
        "dispatch_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary.loc[0, "dispatch_broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "dispatch_broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "dispatch_broker_vendor_data_readiness_failed_checks"]) == 1
    assert readiness["provided"]
    assert not readiness["ready"]
    assert readiness["failed_checks"] == 1
    assert config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"]["ready"]


def test_cli_broker_dispatch_send_fails_when_request_limit_breached(tmp_path):
    dispatch = write_dispatch(tmp_path)
    out_dir = tmp_path / "dispatch_send"
    action_dir = tmp_path / "dispatch_send_action_gate"
    blocked_dir = tmp_path / "dispatch_send_blocked_gate"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--max-requests",
            "1",
            "--fail-on-breach",
        ]
    )
    action_code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(action_dir),
            "--max-requests",
            "1",
            "--fail-on-actions",
        ]
    )
    blocked_code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(blocked_dir),
            "--max-requests",
            "1",
            "--fail-on-blocked-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    action_queue = pd.read_csv(out_dir / "broker_dispatch_send_action_queue.csv")
    config = json.loads((out_dir / "broker_dispatch_send_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert action_code == 2
    assert blocked_code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "request_count_within_limit" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "action_queue_count"]) >= 1
    assert int(summary.loc[0, "blocked_action_count"]) >= 1
    assert summary.loc[0, "next_gate"] == "prepare-broker-dispatch-send"
    assert action_queue.loc[0, "queue_status"] == "blocked"
    assert action_queue.loc[0, "component"] == "broker_dispatch_send"
    assert action_queue.loc[0, "check"] == "request_count_within_limit"
    assert action_queue.loc[0, "next_gate"] == "prepare-broker-dispatch-send"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli prepare-broker-dispatch-send --help"
    assert config["primary_action"]["check"] == "request_count_within_limit"
    assert config["next_actions"][0]["next_gate"] == "prepare-broker-dispatch-send"


def test_cli_broker_dispatch_send_can_require_roundtrip_proof(tmp_path):
    dispatch = write_dispatch(tmp_path, route_roundtrip=False)
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_dispatch_roundtrip_provided" in failed


def test_cli_broker_dispatch_send_can_require_route_readiness(tmp_path):
    dispatch = write_dispatch(tmp_path, route_readiness=False)
    out_dir = tmp_path / "dispatch_send"

    code = main(
        [
            "prepare-broker-dispatch-send",
            "--dispatch",
            str(dispatch),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_readiness_provided" in failed
