import hashlib
import json

import pandas as pd
import pytest

from hft_cli import main
from reports.broker_dispatch_ack import (
    BrokerDispatchAckThresholds,
    evaluate_broker_dispatch_acknowledgements,
    write_broker_dispatch_acknowledgements,
)
from reports.catalog import catalog_experiment_runs
from reports.operational_lineage import empty_broker_dispatch_send_lineage


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
        "send_carried_application_lineage_sha256": lineage_sha256,
    }


def send_final_target_application_lineage_comparison(vendor, **overrides):
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
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


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
                "failed_checks": 0 if ready else 1,
                "recommendation": "ready_for_broker_dryrun_dispatch"
                if ready
                else "fix_broker_dispatch_plan",
            }
        ]
    )


def dispatch_orders():
    return pd.DataFrame(
        [
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-1",
                "route_dispatch_roundtrip_batch_id": "BDP-0",
                "source_order_id": "ORD-1",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
            {
                "dispatch_batch_id": "BDP-1",
                "dispatch_order_id": "DSP-2",
                "route_dispatch_roundtrip_batch_id": "BDP-0",
                "source_order_id": "ORD-2",
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "adapter": "arrow_money",
                "dry_run_only": True,
            },
        ]
    )


def ack_rows(
    statuses=("accepted", "accepted"),
    *,
    extra=False,
    duplicate=False,
    by_source=False,
    route_roundtrip_batch_id="BDP-0",
):
    rows = []
    for index, status in enumerate(statuses, start=1):
        route_batch_id = _route_batch_id(route_roundtrip_batch_id, index)
        row = {
            "status": status,
            "broker_order_id": f"BRK-{index}",
            "ack_ts_ns": 1_000 + index,
        }
        if route_batch_id is not None:
            row["route_dispatch_roundtrip_batch_id"] = route_batch_id
        if by_source:
            row["source_order_id"] = f"ORD-{index}"
        else:
            row["dispatch_order_id"] = f"DSP-{index}"
            row["source_order_id"] = f"ORD-{index}"
        rows.append(row)
    if duplicate:
        route_batch_id = _route_batch_id(route_roundtrip_batch_id, 1)
        rows.append(
            {
                "dispatch_order_id": "DSP-1",
                "source_order_id": "ORD-1",
                "status": "accepted",
                "broker_order_id": "BRK-1-DUP",
                "ack_ts_ns": 1_099,
                **(
                    {"route_dispatch_roundtrip_batch_id": route_batch_id}
                    if route_batch_id is not None
                    else {}
                ),
            }
        )
    if extra:
        route_batch_id = _route_batch_id(route_roundtrip_batch_id, 999)
        rows.append(
            {
                "dispatch_order_id": "DSP-999",
                "source_order_id": "ORD-999",
                "status": "accepted",
                "broker_order_id": "BRK-999",
                "ack_ts_ns": 9_999,
                **(
                    {"route_dispatch_roundtrip_batch_id": route_batch_id}
                    if route_batch_id is not None
                    else {}
                ),
            }
        )
    return pd.DataFrame(rows)


def _route_batch_id(value, index):
    if isinstance(value, (list, tuple)):
        return value[index - 1] if index <= len(value) else value[-1]
    return value


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


def with_dispatch_broker_vendor_batch_summary(summary, vendor):
    prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
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
        final_lineage = send_final_target_application_lineage_comparison(vendor)
        final_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
        result.loc[
            0,
            "dispatch_broker_vendor_market_data_batch_lineage_match_required",
        ] = lineage["required"]
        result.loc[
            0,
            "dispatch_broker_vendor_market_data_batch_lineage_matches",
        ] = lineage["matches"]
        result.loc[
            0,
            "dispatch_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["current_application_lineage_sha256"]
        result.loc[
            0,
            "dispatch_broker_vendor_market_data_batch_application_lineage_sha256",
        ] = lineage["broker_application_lineage_sha256"]
        for stage in ("scaleup", "cutover", "route", "dispatch", "send"):
            result.loc[
                0,
                f"{stage}_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256",
            ] = lineage[f"{stage}_carried_application_lineage_sha256"]
        result.loc[0, f"{final_prefix}_lineage_match_required"] = final_lineage[
            "required"
        ]
        result.loc[0, f"{final_prefix}_lineage_matches"] = final_lineage["matches"]
        for field, value in final_lineage.items():
            if field not in {"required", "matches", "carried_application_lineage_sha256"}:
                result.loc[0, f"{final_prefix}_{field}"] = value
    return result


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


def broker_vendor_data_readiness_config(*, provided=True, ready=True, failed_checks=0):
    return {
        "provided": provided,
        "ready": ready,
        "failed_checks": failed_checks,
    }


def write_inputs(
    tmp_path,
    *,
    dispatch_ready=True,
    ack_statuses=("accepted", "accepted"),
    route_roundtrip=True,
    route_readiness=True,
):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    dispatch_summary(
        dispatch_ready,
        route_roundtrip_provided=route_roundtrip,
        route_roundtrip_ready=route_roundtrip,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(dispatch / "broker_dispatch_summary.csv", index=False)
    dispatch_orders().to_csv(dispatch / "broker_dispatch_orders.csv", index=False)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(
            dispatch_config(
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
                "inputs": {
                    "route_enable_manifest": {
                        "path": str(dispatch / "route_enable_manifest.json"),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    acks = tmp_path / "broker_dispatch_acks.csv"
    ack_rows(ack_statuses).to_csv(acks, index=False)
    return dispatch, acks


def test_broker_dispatch_ack_accepts_complete_source_id_acks():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(by_source=True),
    )

    assert report.passed
    summary = report.summary.iloc[0]
    assert summary["ack_rate"] == 1.0
    assert summary["recommendation"] == "broker_dispatch_acknowledged"
    assert report.acknowledgements["match_key"].tolist() == ["source_order_id", "source_order_id"]
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
    assert report.acknowledgements["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.acknowledgements["ack_route_dispatch_roundtrip_batch_ids"].tolist() == ["BDP-0", "BDP-0"]
    assert summary["broker_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(summary["broker_schema_reviewed"])
    assert summary["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["broker_readiness"]["schema_reviewed"]
    assert report.config["broker_readiness"]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert int(summary["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert report.config["route_dispatch_roundtrip"]["dispatch_batch_id"] == "BDP-0"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 0
    assert bool(summary["route_readiness_required"])
    assert bool(summary["route_readiness_ready"])
    assert summary["route_readiness_strategy"] == "lead_lag_taker"
    assert report.config["route_readiness"]["required"]
    assert report.config["route_readiness"]["market"] == "india_nse_index_derivatives"
    assert bool(summary["route_readiness_ops_launch_controls_present"])
    assert int(summary["route_readiness_ops_launch_controls_blocked_pairs"]) == 0
    assert int(summary["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) == 0
    assert report.config["route_readiness"]["ops_launch_controls_present"]
    assert report.config["route_readiness"]["ops_broker_roundtrip_portfolio_concentration_breach_pairs"] == 0
    assert bool(summary["route_broker_route_readiness_ready"])
    assert summary["route_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    assert report.config["route_broker_route_readiness"]["ops_launch_controls_ready"]
    assert report.config["route_broker_route_readiness"]["ops_broker_roundtrip_portfolio_concentration_ok_runs"] == 1


def test_broker_dispatch_ack_carries_verified_send_lineage():
    lineage = empty_broker_dispatch_send_lineage(required=True)
    lineage.update(
        {
            "provided": True,
            "manifest_current": True,
            "manifest_run_type": "broker_dispatch_send_packet",
            "manifest_path": "send/manifest.json",
            "manifest_sha256": "a" * 64,
            "contract_consistent": True,
            "non_authorizing": True,
            "broker_dispatch_lineage_gate_passed": True,
            "broker_dispatch_matches_current": True,
            "expected_dispatch_matches_current": True,
            "gate_passed": True,
        }
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(by_source=True),
        broker_dispatch_send_lineage=lineage,
    )

    assert report.passed
    assert report.acknowledgements[
        "broker_dispatch_send_lineage_gate_passed"
    ].astype(bool).all()
    assert not report.acknowledgements["authorizes_submission"].astype(bool).any()
    assert bool(
        report.summary.iloc[0]["broker_dispatch_send_lineage_gate_passed"]
    )
    assert report.config["broker_dispatch_send_lineage"][
        "broker_dispatch_send_lineage_gate_passed"
    ]
    assert not report.config["authorizes_submission"]


def test_broker_dispatch_ack_blocks_missing_required_send_lineage():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(by_source=True),
        thresholds=BrokerDispatchAckThresholds(require_send_packet=True),
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert {
        "broker_dispatch_send_lineage_provided",
        "broker_dispatch_send_manifest_current",
        "broker_dispatch_send_lineage_contract_consistent",
        "broker_dispatch_send_non_authorizing",
        "broker_dispatch_send_broker_dispatch_lineage_gate_passed",
        "broker_dispatch_send_broker_dispatch_matches_current",
        "broker_dispatch_send_expected_dispatch_matches_current",
        "broker_dispatch_send_lineage_gate_passed",
    } <= failed
    assert report.config["next_gate"] == "prepare-broker-dispatch-send"


def test_broker_dispatch_ack_carries_route_broker_resume_gate():
    config = dispatch_config()
    config["route_broker_resume_gate"] = {
        "broker_route_readiness": resume_route_proof(),
        "incident_broker_route_readiness": resume_route_proof(route_ready_pairs=2),
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(by_source=True),
        dispatch_config=config,
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


def test_broker_dispatch_ack_blocks_bad_route_broker_resume_gate():
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

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(by_source=True),
        dispatch_config=config,
    )

    assert not report.passed
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


def test_broker_dispatch_ack_carries_strategy_portfolio_allocation():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=2_000.0,
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=dispatch_config(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=2_000.0,
        ),
    )

    assert report.passed
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


def test_broker_dispatch_ack_blocks_dispatch_above_strategy_portfolio_allocation():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1_200.0,
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=dispatch_config(
            strategy_portfolio_required=True,
            strategy_portfolio_provided=True,
            strategy_portfolio_ready=True,
            strategy_portfolio_selected_eligible=True,
            strategy_portfolio_selected_allocation_notional=1_200.0,
        ),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_notional_within_strategy_portfolio_allocation" in failed
    assert report.config["primary_blocker"]["check"] == "dispatch_notional_within_strategy_portfolio_allocation"
    assert report.config["dispatch_total_notional"] == 1_575.0


def test_broker_dispatch_ack_carries_send_shadow_broker_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
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
    assert report.config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_ack_blocks_bad_send_shadow_broker_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
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

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "send_shadow_broker_readiness_ready",
        "send_shadow_broker_vendor_data_readiness_ready",
        "send_shadow_broker_vendor_data_readiness_failed_checks",
        "send_shadow_broker_adapter_matches",
        "send_shadow_broker_adapter_consistent",
        "send_shadow_broker_route_readiness_ready",
        "send_shadow_broker_route_readiness_strategy_matches",
        "send_shadow_broker_route_readiness_market_matches",
        "send_shadow_broker_route_readiness_gap_pairs",
        "send_shadow_broker_dispatch_roundtrip_ready",
        "send_shadow_broker_dispatch_roundtrip_strategy_matches",
        "send_shadow_broker_dispatch_roundtrip_market_matches",
        "send_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "send_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "send_shadow_broker_dispatch_roundtrip_rejected_orders",
        "send_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "send_shadow_broker_route_dispatch_roundtrip_ready",
        "send_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "send_shadow_broker_route_dispatch_roundtrip_market_matches",
        "send_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_ack_blocks_partial_send_shadow_broker_vendor_data_readiness():
    config = dispatch_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        broker_vendor_data_readiness_sessions=1,
        broker_vendor_data_readiness_provided_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "send_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "send_shadow_broker_vendor_data_readiness_provided",
        "send_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["provided_sessions"] == 1


def test_broker_dispatch_ack_carries_send_broker_shadow_broker_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(),
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
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
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert (
        report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"]
        == 2
    )
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["route_broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["route_broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_dispatch_ack_carries_ack_vendor_market_data_batch():
    config = dispatch_config()
    config["route_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["ack_vendor_market_data_batch"]
    assert report.passed
    assert summary["ack_vendor_market_data_batch_provided"]
    assert summary["ack_vendor_market_data_batch_ready"]
    assert summary["ack_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["ack_vendor_market_data_batch_kind"] == "ticks"
    assert summary["ack_vendor_market_data_batch_manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert int(summary["ack_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["ack_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["ack_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["ack_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["ack_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["ack_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["ack_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_dispatch_ack_blocks_wrong_manifest_vendor_market_data_batch():
    config = dispatch_config()
    config["dispatch_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["ack_vendor_market_data_batch"]
    assert "ack_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["ack_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_ack_carries_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.passed
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
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


def test_broker_dispatch_ack_carries_target_application_vendor_batch_from_dispatch_config():
    vendor_input = target_application_vendor_market_data_batch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config = dispatch_config()
    config[input_prefix] = vendor_input
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor_input)
    )
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = send_final_target_application_lineage_comparison(vendor_input)

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
    prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    lineage_sha256 = target_application_lineage_sha256(vendor_input["datasets"])
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    assert int(summary[f"{prefix}_unique_mapping_applications"]) == 2
    assert summary[f"{prefix}_target_application_coverage"] == 1.0
    assert summary[f"{prefix}_application_lineage_consistency_required"]
    assert summary[f"{prefix}_application_lineage_consistent"]
    assert summary[f"{prefix}_application_lineage_sha256"] == lineage_sha256
    assert summary["ack_broker_vendor_market_data_batch_lineage_match_required"]
    assert summary["ack_broker_vendor_market_data_batch_lineage_matches"]
    assert (
        summary[
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        summary[
            "ack_carried_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
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
        "ack_carried_application_lineage_sha256": lineage_sha256,
    }
    final_lineage = report.config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
        "carried_application_lineage_sha256",
    ):
        assert final_lineage[field] == lineage_sha256
    expected_checks = {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
        f"{prefix}_lineage_consistency_required",
        f"{prefix}_application_lineage_consistent",
        f"{prefix}_lineage_match_required",
        f"{prefix}_lineage_matches",
        f"{prefix}_source_lineage_sha256_matches",
        f"{prefix}_application_lineage_sha256_matches",
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_route_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_send_carried_lineage_sha256_matches",
        f"{prefix}_ack_carried_lineage_sha256_matches",
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
        f"{prefix}_final_send_packet_review_carried_lineage_sha256_matches",
        f"{prefix}_ack_reconciliation_review_carried_lineage_sha256_matches",
    }
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


def test_broker_dispatch_ack_carries_target_application_vendor_batch_from_dispatch_summary():
    vendor = target_application_vendor_market_data_batch_config()
    summary_input = with_dispatch_broker_vendor_batch_summary(dispatch_summary(), vendor)

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=summary_input,
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=dispatch_config(),
    )

    assert report.passed
    prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    assert summary[f"{prefix}_mapping_source_mode"] == "per_dataset_verified_target_application"
    assert int(summary[f"{prefix}_mapping_application_count"]) == 2
    carried = report.config[prefix]
    assert carried["unique_mapping_applications"] == 2
    assert carried["target_application_coverage"] == 1.0
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    assert carried["datasets"][1]["mapping_scope_review_id"] == "scope-review-1"
    final_lineage = report.config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["dispatch_plan_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["send_packet_review_carried_application_lineage_sha256"] == (
        final_lineage["broker_application_lineage_sha256"]
    )
    assert final_lineage["carried_application_lineage_sha256"] == final_lineage[
        "broker_application_lineage_sha256"
    ]


def test_broker_dispatch_ack_uses_dispatch_compatibility_lineage_before_send_final():
    compatibility_sha256 = "a" * 64
    final_sha256 = "b" * 64
    config = dispatch_config()
    config[
        "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
    }
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        "current_application_lineage_sha256": final_sha256,
        "broker_application_lineage_sha256": final_sha256,
        "dispatch_carried_application_lineage_sha256": final_sha256,
        "send_carried_application_lineage_sha256": final_sha256,
        "dispatch_plan_review_carried_application_lineage_sha256": final_sha256,
        "carried_application_lineage_sha256": "c" * 64,
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
    lineage = report.config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["current_application_lineage_sha256"] == compatibility_sha256
    assert lineage["broker_application_lineage_sha256"] == compatibility_sha256
    assert lineage["send_carried_application_lineage_sha256"] == compatibility_sha256


def test_broker_dispatch_ack_ignores_send_complete_final_lineage_until_upgrade():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = send_final_target_application_lineage_comparison(vendor)
    complete_final_sha256 = "f" * 64
    config[
        "send_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
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
                "dispatch_final_review_carried_application_lineage_sha256",
                "carried_application_lineage_sha256",
            )
        },
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
    final_lineage = report.config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert final_lineage["send_packet_review_carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    assert final_lineage["broker_application_lineage_sha256"] != complete_final_sha256


def test_broker_dispatch_ack_blocks_incomplete_target_application_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config(
        mapping_source_mode="legacy_application_mode",
        mapping_application_count=1,
        unique_mapping_applications=1,
        target_application_coverage=0.5,
    )
    vendor["datasets"][1]["mapping_application_sha256"] = ""
    config = dispatch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = send_final_target_application_lineage_comparison(vendor)

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
    } <= failed


def test_broker_dispatch_ack_blocks_target_application_lineage_drift_after_send():
    vendor = target_application_vendor_market_data_batch_config()
    lineage = target_application_lineage_comparison(vendor)
    config = dispatch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = lineage
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = send_final_target_application_lineage_comparison(vendor)
    vendor["datasets"][1]["mapping_application_sha256"] = "9" * 64

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert f"{output_prefix}_ack_carried_lineage_sha256_matches" in failed
    assert f"{output_prefix}_ack_reconciliation_review_carried_lineage_sha256_matches" in failed
    assert {
        f"{output_prefix}_source_lineage_sha256_matches",
        f"{output_prefix}_application_lineage_sha256_matches",
        f"{output_prefix}_scaleup_carried_lineage_sha256_matches",
        f"{output_prefix}_cutover_carried_lineage_sha256_matches",
        f"{output_prefix}_route_carried_lineage_sha256_matches",
        f"{output_prefix}_dispatch_carried_lineage_sha256_matches",
        f"{output_prefix}_send_carried_lineage_sha256_matches",
        f"{output_prefix}_final_send_packet_review_carried_lineage_sha256_matches",
    } <= passed


@pytest.mark.parametrize(
    ("lineage_mutation", "vendor_overrides", "expected_check"),
    [
        (
            {"matches": False},
            {},
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ),
        (
            {"current_application_lineage_sha256": "f" * 64},
            {},
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        ),
        (
            {},
            {"application_lineage_consistent": False},
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_consistent",
        ),
    ],
)
def test_broker_dispatch_ack_blocks_failed_send_target_lineage_decisions(
    lineage_mutation,
    vendor_overrides,
    expected_check,
):
    vendor = target_application_vendor_market_data_batch_config(**vendor_overrides)
    lineage = target_application_lineage_comparison(vendor)
    lineage.update(lineage_mutation)
    config = dispatch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = lineage
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = send_final_target_application_lineage_comparison(vendor)

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert expected_check in failed


def test_broker_dispatch_ack_requires_final_lineage_comparison_for_reconciled_target():
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
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
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches",
        ),
        (
            "readiness_carried_application_lineage_sha256",
            "f" * 64,
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_final_readiness_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_final_send_packet_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_dispatch_ack_blocks_invalid_final_lineage_comparison(
    field,
    value,
    expected_failed_check,
):
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )
    config[
        "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = send_final_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_dispatch_ack_does_not_require_final_comparison_when_consistency_is_absent():
    config = dispatch_config()
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    output_prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    config[input_prefix] = vendor
    config[f"{input_prefix}_lineage_comparison"] = (
        target_application_lineage_comparison(vendor)
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    check_names = set(report.checks["check"])
    final_prefix = f"{output_prefix}_final_"
    assert not any(name.startswith(final_prefix) for name in check_names)
    assert f"{output_prefix}_ack_reconciliation_review_carried_lineage_sha256_matches" not in check_names


def test_broker_dispatch_ack_consumes_sender_target_lineage_handoff():
    vendor = target_application_vendor_market_data_batch_config()
    input_prefix = "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=dispatch_config(),
        send_config={
            input_prefix: vendor,
            f"{input_prefix}_lineage_comparison": (
                target_application_lineage_comparison(vendor)
            ),
            "send_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison": (
                send_final_target_application_lineage_comparison(vendor)
            ),
        },
    )

    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    lineage = report.config[
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert report.passed
    assert lineage["send_carried_application_lineage_sha256"] == lineage_sha256
    assert lineage["ack_carried_application_lineage_sha256"] == lineage_sha256
    final_lineage = report.config[
        "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["send_packet_review_carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert final_lineage["carried_application_lineage_sha256"] == lineage_sha256


def test_broker_dispatch_ack_blocks_failed_broker_vendor_data_readiness():
    config = dispatch_config()
    config["dispatch_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config(
        ready=False,
        failed_checks=1,
    )
    config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    wrapper = report.config["ack_broker_vendor_data_readiness"]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.passed
    assert {
        "ack_broker_vendor_data_readiness_ready",
        "ack_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary["ack_broker_vendor_data_readiness_provided"])
    assert not bool(summary["ack_broker_vendor_data_readiness_ready"])
    assert int(summary["ack_broker_vendor_data_readiness_failed_checks"]) == 1
    assert wrapper["provided"]
    assert not wrapper["ready"]
    assert wrapper["failed_checks"] == 1
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["unique_mapping_drafts"] == 1


def test_broker_dispatch_ack_prefers_ack_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor_market_data_batch_config()
    config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert report.passed
    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == (
        "india_nse_index_derivatives"
    )
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]


def test_broker_dispatch_ack_blocks_wrong_manifest_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["dispatch_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_ack_carries_roundtrip_broker_vendor_market_data_batch():
    config = dispatch_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert report.passed
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_provided"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert int(summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["unique_mapping_drafts"] == 1


def test_broker_dispatch_ack_blocks_wrong_manifest_roundtrip_vendor_market_data_batch():
    config = dispatch_config()
    config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_dispatch_ack_carries_ack_broker_vendor_market_data_batch_when_preferred():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor_market_data_batch_config()

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage",
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage",
        "ack_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_drafts",
    } <= failed
    assert not summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_ready"]
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "irage"
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_market"] == "us_options_regular"
    assert vendor["adapter"] == "irage"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["source_file_fingerprint_coverage"] == 0.0
    assert vendor["min_mapping_coverage"] == 0.0
    assert vendor["unique_mapping_drafts"] == 0
    assert vendor["failed_datasets"] == 1
    assert not vendor["comparison"]["accepted"]


def test_broker_dispatch_ack_blocks_wrong_manifest_ack_broker_vendor_market_data_batch_when_preferred():
    config = dispatch_config()
    config["route_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config(
        manifest_run_type="not_vendor_batch"
    )

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    vendor = report.config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert "ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type" in failed
    assert summary["ack_broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_cli_broker_dispatch_ack_hydrates_legacy_draft_vendor_data_from_manifest_chain(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
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
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    config = json.loads((out_dir / "broker_dispatch_ack_config.json").read_text(encoding="utf-8"))
    vendor = config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 0
    assert bool(summary.loc[0, "passed"])
    assert bool(summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert (
        summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_adapter"]
        == "arrow_money"
    )
    assert int(summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert pd.isna(
        summary.loc[
            0,
            "ack_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        ]
    )
    assert int(
        summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count"]
    ) == 0
    assert int(
        summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications"]
    ) == 0
    assert summary.loc[0, "ack_broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage"] == 0.0
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


def test_cli_broker_dispatch_ack_blocks_thin_target_vendor_sidecar(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
    broker_config = dispatch / "broker_readiness_config.json"
    cutover_manifest = dispatch / "cutover_manifest.json"
    route_manifest = dispatch / "route_enable_manifest.json"
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
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
                        "required": True,
                        "matches": True,
                        "current_application_lineage_sha256": lineage_sha256,
                        "broker_application_lineage_sha256": lineage_sha256,
                        "carried_application_lineage_sha256": lineage_sha256,
                    },
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
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    prefix = "ack_broker_dispatch_roundtrip_vendor_market_data_batch"
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert {
        f"{prefix}_scaleup_carried_lineage_sha256_matches",
        f"{prefix}_cutover_carried_lineage_sha256_matches",
        f"{prefix}_route_carried_lineage_sha256_matches",
        f"{prefix}_dispatch_carried_lineage_sha256_matches",
        f"{prefix}_send_carried_lineage_sha256_matches",
    } <= failed


def test_cli_broker_dispatch_ack_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
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
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    config = json.loads((out_dir / "broker_dispatch_ack_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    wrapper = config["ack_broker_vendor_data_readiness"]
    vendor = config["ack_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert {
        "ack_broker_vendor_data_readiness_ready",
        "ack_broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary.loc[0, "ack_broker_vendor_data_readiness_provided"])
    assert not bool(summary.loc[0, "ack_broker_vendor_data_readiness_ready"])
    assert int(summary.loc[0, "ack_broker_vendor_data_readiness_failed_checks"]) == 1
    assert wrapper["provided"]
    assert not wrapper["ready"]
    assert wrapper["failed_checks"] == 1
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["unique_mapping_drafts"] == 1


def test_broker_dispatch_ack_blocks_bad_send_broker_shadow_broker_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
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

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "send_broker_shadow_broker_readiness_ready",
        "send_broker_shadow_broker_vendor_data_readiness_ready",
        "send_broker_shadow_broker_vendor_data_readiness_failed_checks",
        "send_broker_shadow_broker_adapter_matches",
        "send_broker_shadow_broker_adapter_consistent",
        "send_broker_shadow_broker_route_readiness_ready",
        "send_broker_shadow_broker_route_readiness_strategy_matches",
        "send_broker_shadow_broker_route_readiness_market_matches",
        "send_broker_shadow_broker_route_readiness_gap_pairs",
        "send_broker_shadow_broker_dispatch_roundtrip_ready",
        "send_broker_shadow_broker_dispatch_roundtrip_strategy_matches",
        "send_broker_shadow_broker_dispatch_roundtrip_market_matches",
        "send_broker_shadow_broker_dispatch_roundtrip_scenario_consistent",
        "send_broker_shadow_broker_dispatch_roundtrip_missing_request_acks",
        "send_broker_shadow_broker_dispatch_roundtrip_rejected_orders",
        "send_broker_shadow_broker_dispatch_roundtrip_unmatched_acks",
        "send_broker_shadow_broker_route_dispatch_roundtrip_ready",
        "send_broker_shadow_broker_route_dispatch_roundtrip_strategy_matches",
        "send_broker_shadow_broker_route_dispatch_roundtrip_market_matches",
        "send_broker_shadow_broker_route_dispatch_roundtrip_scenario_consistent",
    } <= failed
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


def test_broker_dispatch_ack_blocks_partial_send_broker_shadow_broker_vendor_data_readiness():
    config = dispatch_config()
    config["route_broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=config,
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "send_broker_shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "send_broker_shadow_broker_vendor_data_readiness_provided",
        "send_broker_shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["route_broker_shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["route_broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_broker_dispatch_ack_requires_route_readiness():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(route_readiness_provided=False, route_readiness_ready=False),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_provided", "route_readiness_ready"} <= failed
    assert report.config["route_readiness"]["required"]
    assert not report.config["route_readiness"]["provided"]


def test_broker_dispatch_ack_blocks_route_readiness_identity_mismatch():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_readiness_strategy_matches", "route_readiness_market_matches"} <= failed
    assert report.summary.iloc[0]["route_readiness_strategy"] == "surface_mm"
    assert report.config["route_readiness"]["market"] == "us_options_regular"


def test_broker_dispatch_ack_blocks_stale_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            route_ops_launch_controls_present=False,
            route_ops_launch_controls_blocked_pairs=1,
            route_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=dispatch_config(
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


def test_broker_dispatch_ack_blocks_stale_route_broker_route_readiness_ops_controls():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(
            broker_route_readiness_ops_launch_controls_ready=False,
            broker_route_readiness_ops_launch_control_failures="concentration breach on BANKNIFTY weekly",
            broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
        dispatch_config=dispatch_config(
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


def test_broker_dispatch_ack_requires_route_roundtrip_proof():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(route_roundtrip_provided=False, route_roundtrip_ready=False),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert report.config["route_dispatch_roundtrip"]["required"]


def test_broker_dispatch_ack_blocks_bad_route_roundtrip_quality():
    report = evaluate_broker_dispatch_acknowledgements(
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
        broker_acks=ack_rows(),
    )

    assert not report.passed
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


def test_broker_dispatch_ack_blocks_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(route_enable_dispatch_roundtrip_failed_checks=1),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert report.config["failed_check_count"] == len(failed)
    assert report.config["primary_blocker"]["check"] in failed
    assert not report.config["primary_blocker"]["passed"]
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.summary.iloc[0]["broker_schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1
    assert report.config["broker_readiness"]["schema_reviewed"]


def test_broker_dispatch_ack_reads_nested_route_enable_dispatch_roundtrip_failed_checks(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
    (dispatch / "broker_dispatch_config.json").write_text(
        json.dumps(dispatch_config(route_enable_dispatch_roundtrip_failed_checks=1), indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_broker_dispatch_acknowledgements(
        dispatch_dir=dispatch,
        acks_path=acks,
        output_dir=tmp_path / "dispatch_acks",
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert report.config["route_enable_dispatch_roundtrip"]["failed_checks"] == 1


def test_broker_dispatch_ack_blocks_route_roundtrip_batch_mismatch():
    orders = dispatch_orders()
    orders.loc[0, "route_dispatch_roundtrip_batch_id"] = "BDP-OLD"

    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=orders,
        broker_acks=ack_rows(route_roundtrip_batch_id="BDP-BAD"),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_order_route_roundtrip_batch_matches",
        "ack_route_roundtrip_batch_matches",
    } <= failed
    assert report.acknowledgements["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-BAD", "BDP-BAD"]
    assert report.acknowledgements["ack_route_dispatch_roundtrip_batch_ids"].tolist() == ["BDP-BAD", "BDP-BAD"]


def test_broker_dispatch_ack_blocks_missing_ack():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(("accepted",)),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "all_dispatch_orders_acked" in failed
    summary = report.summary.iloc[0]
    queue = report.action_queue
    assert int(summary["missing_acks"]) == 1
    assert int(summary["action_queue_count"]) >= 1
    assert summary["primary_blocker_check"] == "all_dispatch_orders_acked"
    assert summary["next_gate"] == "reconcile-broker-dispatch"
    assert summary["next_gate_help_command"] == "python -m hft_cli reconcile-broker-dispatch --help"
    assert queue is not None
    row = queue.set_index("check").loc["all_dispatch_orders_acked"]
    assert row["component"] == "broker_dispatch_ack"
    assert row["next_gate"] == "reconcile-broker-dispatch"
    assert row["next_gate_help_command"] == "python -m hft_cli reconcile-broker-dispatch --help"
    assert row["recommendation"] == (
        "collect_missing_broker_acknowledgements_or_allow_missing_acks_for_diagnostics"
    )
    assert report.config["primary_action"]["check"] == "all_dispatch_orders_acked"
    assert report.config["blocked_actions"][0]["next_gate"] == "reconcile-broker-dispatch"


def test_broker_dispatch_ack_blocks_rejected_duplicate_and_unmatched_acks():
    report = evaluate_broker_dispatch_acknowledgements(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
        broker_acks=ack_rows(("accepted", "rejected"), duplicate=True, extra=True),
    )

    assert not report.passed
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert failed >= {
        "all_dispatch_orders_acked",
        "rejected_orders",
        "duplicate_ack_orders",
        "unmatched_acks",
    }
    summary = report.summary.iloc[0]
    assert int(summary["rejected_orders"]) == 1
    assert int(summary["duplicate_ack_orders"]) == 1
    assert int(summary["unmatched_acks"]) == 1


def test_write_broker_dispatch_ack_outputs_artifacts_and_catalog_entry(tmp_path):
    dispatch, acks = write_inputs(tmp_path)
    out_dir = tmp_path / "dispatch_acks"

    report = write_broker_dispatch_acknowledgements(
        dispatch_dir=dispatch,
        acks_path=acks,
        output_dir=out_dir,
    )

    assert report.passed
    assert (out_dir / "broker_dispatch_acknowledgements.csv").exists()
    assert (out_dir / "broker_dispatch_unmatched_acks.csv").exists()
    assert (out_dir / "broker_dispatch_ack_checks.csv").exists()
    assert (out_dir / "broker_dispatch_ack_summary.csv").exists()
    assert (out_dir / "broker_dispatch_ack_action_queue.csv").exists()
    assert (out_dir / "broker_dispatch_ack_config.json").exists()
    assert (out_dir / "broker_dispatch_ack_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "broker_dispatch_ack_action_queue.csv")
    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    config = json.loads((out_dir / "broker_dispatch_ack_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_dispatch_ack_runbook.md").read_text(encoding="utf-8")
    assert action_queue.empty
    assert int(summary.loc[0, "action_queue_count"]) == 0
    assert int(summary.loc[0, "blocked_action_count"]) == 0
    assert config["action_queue_count"] == 0
    assert config["next_actions"] == []
    assert "# Broker Dispatch Acknowledgement Runbook" in runbook
    assert "No broker dispatch acknowledgement actions." in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
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
    assert path_tail(manifest["inputs"]["broker_acks"]["path"]).endswith("/broker_dispatch_acks.csv")
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "broker_dispatch_ack_action_queue.csv" in artifact_paths
    assert "broker_dispatch_ack_runbook.md" in artifact_paths
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_ack_reconciliation"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_ack_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_ack_fails_on_rejected_ack(tmp_path):
    dispatch, acks = write_inputs(tmp_path, ack_statuses=("accepted", "rejected"))
    out_dir = tmp_path / "dispatch_acks"
    blocked_dir = tmp_path / "dispatch_acks_blocked"
    actions_dir = tmp_path / "dispatch_acks_actions"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    queue = pd.read_csv(out_dir / "broker_dispatch_ack_action_queue.csv")
    config = json.loads((out_dir / "broker_dispatch_ack_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "rejected_orders" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "rejected_orders" in set(queue["check"])
    rejected_row = queue.set_index("check").loc["rejected_orders"]
    assert rejected_row["component"] == "broker_dispatch_ack"
    assert rejected_row["next_gate"] == "reconcile-broker-dispatch"
    assert rejected_row["next_gate_help_command"] == "python -m hft_cli reconcile-broker-dispatch --help"
    assert config["blocked_action_count"] >= 1
    assert config["primary_action_status"] == "blocked"

    blocked_code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(blocked_dir),
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(actions_dir),
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


def test_cli_broker_dispatch_ack_can_require_roundtrip_proof(tmp_path):
    dispatch, acks = write_inputs(tmp_path, route_roundtrip=False)
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "route_dispatch_roundtrip_provided" in failed


def test_cli_broker_dispatch_ack_can_require_route_readiness(tmp_path):
    dispatch, acks = write_inputs(tmp_path, route_readiness=False)
    out_dir = tmp_path / "dispatch_acks"

    code = main(
        [
            "reconcile-broker-dispatch",
            "--dispatch",
            str(dispatch),
            "--acks",
            str(acks),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_dispatch_ack_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_ack_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "route_readiness_provided" in failed
