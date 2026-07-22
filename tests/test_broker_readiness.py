import hashlib
import json
import warnings

import pandas as pd
import pytest

from adapters.broker_readiness import (
    BrokerReadinessThresholds,
    evaluate_broker_readiness,
    write_broker_readiness_report,
)
from hft_cli import main
from reports.broker_dispatch_roundtrip import (
    BrokerDispatchRoundTripThresholds,
    write_broker_dispatch_roundtrip,
)
from reports.operational_lineage import load_broker_readiness_lineage
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
)
from tests.broker_vendor_data_helpers import write_broker_vendor_data_proof
from tests.test_broker_dispatch_send import (
    _refresh_manifest as refresh_dispatch_manifest,
    _write_verified_ack_chain,
)


def broker_vendor_ticks(day: str, *, base: float = 100.0, session_open: str = "09:15"):
    return pd.DataFrame(
        [
            {
                "exchange_ts": f"{day} {session_open}:00",
                "best_bid": base,
                "best_ask": base + 0.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": base + 0.05,
                "last_size": 75,
            },
            {
                "exchange_ts": f"{day} {session_open}:01",
                "best_bid": base + 0.05,
                "best_ask": base + 0.10,
                "bid_size": 150,
                "ask_size": 75,
                "last_px": base + 0.10,
                "last_size": 75,
            },
        ]
    )


def schema_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "kind": "orders",
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "missing_required_columns": 0 if ready else 1,
                "all_required_present": ready,
            }
        ]
    )


def schema_review_checklist():
    return pd.DataFrame(
        [
            {
                "check_name": "required_columns_present",
                "passed": True,
                "status": "pass",
                "detail": "all required source columns are present",
            },
            {
                "check_name": "vendor_schema_reviewed",
                "passed": False,
                "status": "blocked",
                "detail": "adapter is still using normalized placeholders",
            },
            {
                "check_name": "extra_columns_classified",
                "passed": False,
                "status": "review",
                "detail": "1 extra vendor column needs classification",
            },
        ]
    )


def order_export_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0 if ready else 1,
            }
        ]
    )


def upload_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0 if ready else 1,
                "recommendation": "internal_upload_ready" if adapter == "normalized" else "dry_run_or_paper_review",
            }
        ]
    )


def mapping_draft_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "vendor_columns": 8,
                "required_columns": 8,
                "mapped_columns": 8 if ready else 7,
                "mapped_required_columns": 8 if ready else 7,
                "unmapped_required_columns": 0 if ready else 1,
            }
        ]
    )


def mapped_order_summary(adapter="normalized", ready=True):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "adapter_schema_status": "native_normalized"
                if adapter == "normalized"
                else "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "target_columns": 8,
                "mapped_columns": 8 if ready else 7,
                "failed_mappings": 0 if ready else 1,
            }
        ]
    )


def runtime_session_summary(adapter="normalized", ready=True, halted=False):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "target_mode": "shadow",
                "strategy": "surface_mm",
                "market": "india_nse_index_derivatives",
                "guard_action": "halt" if halted else "continue",
                "halted": halted,
                "failed_checks": 1 if halted else 0,
                "recommendation": "stop_routing_and_execute_halt_response" if halted else "continue_with_controls",
            }
        ]
    )


def resume_summary(
    adapter="normalized",
    ready=True,
    route_ready=True,
    route_strategy="surface_mm",
    route_market="india_nse_index_derivatives",
    route_gap_pairs=0,
    route_ops_launch_controls_ready=True,
    route_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    incident_route_ready=True,
    incident_route_strategy="surface_mm",
    incident_route_market="india_nse_index_derivatives",
    incident_route_gap_pairs=0,
    incident_route_ops_launch_controls_ready=True,
    incident_route_ops_broker_roundtrip_portfolio_safe_runs=1,
    incident_route_ops_broker_roundtrip_portfolio_breach_runs=0,
    incident_route_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    incident_route_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "adapter": adapter,
                "strategy": "surface_mm",
                "market": "india_nse_index_derivatives",
                "incident_strategy": "surface_mm",
                "incident_market": "india_nse_index_derivatives",
                "proof_refresh_ready": ready,
                "proof_refresh_strategy": "surface_mm",
                "proof_refresh_market": "india_nse_index_derivatives",
                "incident_proof_refresh_strategy": "surface_mm",
                "incident_proof_refresh_market": "india_nse_index_derivatives",
                "broker_route_readiness_required": True,
                "broker_route_readiness_provided": True,
                "broker_route_readiness_ready": route_ready,
                "broker_route_readiness_strategy": route_strategy,
                "broker_route_readiness_market": route_market,
                "broker_route_readiness_route_ready_pairs": 1,
                "broker_route_readiness_gap_pairs": route_gap_pairs,
                "broker_route_readiness_recommendation": (
                    "route_ready" if route_ready and route_gap_pairs == 0 else "complete_route_readiness_gaps"
                ),
                "broker_route_readiness_ops_launch_controls_ready": route_ops_launch_controls_ready,
                "broker_route_readiness_ops_launch_control_failures": (
                    "" if route_ops_launch_controls_ready else "launch controls stale"
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    route_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    route_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "incident_broker_route_readiness_required": True,
                "incident_broker_route_readiness_provided": True,
                "incident_broker_route_readiness_ready": incident_route_ready,
                "incident_broker_route_readiness_strategy": incident_route_strategy,
                "incident_broker_route_readiness_market": incident_route_market,
                "incident_broker_route_readiness_route_ready_pairs": 1,
                "incident_broker_route_readiness_gap_pairs": incident_route_gap_pairs,
                "incident_broker_route_readiness_recommendation": (
                    "route_ready"
                    if incident_route_ready and incident_route_gap_pairs == 0
                    else "complete_route_readiness_gaps"
                ),
                "incident_broker_route_readiness_ops_launch_controls_ready": (
                    incident_route_ops_launch_controls_ready
                ),
                "incident_broker_route_readiness_ops_launch_control_failures": (
                    "" if incident_route_ops_launch_controls_ready else "incident launch controls stale"
                ),
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    incident_route_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    incident_route_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    incident_route_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    incident_route_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "failed_checks": 0 if ready else 1,
                "recommendation": "resume_with_scaleup_controls" if ready else "keep_trading_disabled",
            }
        ]
    )


def dispatch_roundtrip_summary(
    adapter="normalized",
    passed=True,
    failed_checks=None,
    route_provided=True,
    route_ready=True,
    route_target_mode="live_dryrun",
    route_strategy="lead_lag_taker",
    route_market="india_nse_index_derivatives",
    route_scenario_key="trigger_ticks=2",
    route_batch_id="BDP-0",
    route_requests=2,
    route_acked_orders=2,
    route_missing_request_acks=0,
    route_rejected_orders=0,
    route_unmatched_acks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    route_readiness_ops_launch_controls_present=True,
    route_readiness_ops_launch_controls_blocked_pairs=0,
    route_readiness_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    route_readiness_ops_launch_controls_ready=True,
    route_readiness_ops_launch_control_failures="",
    route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    route_broker_route_readiness_required=True,
    route_broker_route_readiness_provided=True,
    route_broker_route_readiness_ready=True,
    route_broker_route_readiness_strategy="lead_lag_taker",
    route_broker_route_readiness_market="india_nse_index_derivatives",
    route_broker_route_readiness_route_ready_pairs=1,
    route_broker_route_readiness_gap_pairs=0,
    route_broker_route_readiness_recommendation=None,
    route_broker_route_readiness_ops_launch_controls_ready=True,
    route_broker_route_readiness_ops_launch_control_failures="",
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    route_enable_dispatch_roundtrip_failed_checks=0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "route_readiness_inputs_missing"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
    )
    route_broker_route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_broker_route_readiness_recommendation is None and route_broker_route_readiness_ready
        else "route_readiness_inputs_missing"
        if route_broker_route_readiness_recommendation is None
        else route_broker_route_readiness_recommendation
    )
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "adapter": adapter,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "dispatch_batch_id": "BDP-1",
                "dispatch_orders": 2,
                "send_requests": 2,
                "acked_orders": 2 if passed else 1,
                "missing_request_acks": 0 if passed else 1,
                "rejected_orders": 0,
                "duplicate_ack_orders": 0,
                "unmatched_acks": 0,
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
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
                "route_readiness_ops_launch_controls_present": route_readiness_ops_launch_controls_present,
                "route_readiness_ops_launch_controls_blocked_pairs": (
                    route_readiness_ops_launch_controls_blocked_pairs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_breach_pairs": (
                    route_readiness_ops_broker_roundtrip_portfolio_breach_pairs
                ),
                "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs
                ),
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
                "route_broker_route_readiness_required": route_broker_route_readiness_required,
                "route_broker_route_readiness_provided": route_broker_route_readiness_provided,
                "route_broker_route_readiness_ready": route_broker_route_readiness_ready,
                "route_broker_route_readiness_strategy": route_broker_route_readiness_strategy,
                "route_broker_route_readiness_market": route_broker_route_readiness_market,
                "route_broker_route_readiness_route_ready_pairs": route_broker_route_readiness_route_ready_pairs,
                "route_broker_route_readiness_gap_pairs": route_broker_route_readiness_gap_pairs,
                "route_broker_route_readiness_recommendation": route_broker_route_readiness_recommendation,
                "route_broker_route_readiness_ops_launch_controls_ready": (
                    route_broker_route_readiness_ops_launch_controls_ready
                ),
                "route_broker_route_readiness_ops_launch_control_failures": (
                    route_broker_route_readiness_ops_launch_control_failures
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": (
                    route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": (
                    route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                    route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
                ),
                "route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                    route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
                ),
                "route_enable_dispatch_roundtrip_failed_checks": route_enable_dispatch_roundtrip_failed_checks,
                "failed_checks": (0 if passed else 1) if failed_checks is None else failed_checks,
                "recommendation": "broker_dry_run_roundtrip_proved"
                if passed
                else "investigate_broker_dry_run_roundtrip",
            }
        ]
    )


def dispatch_roundtrip_config(
    route_enable_dispatch_roundtrip_failed_checks=0,
    route_readiness_required=True,
    route_readiness_provided=True,
    route_readiness_ready=True,
    route_readiness_strategy="lead_lag_taker",
    route_readiness_market="india_nse_index_derivatives",
    route_readiness_route_ready_pairs=1,
    route_readiness_gap_pairs=0,
    route_readiness_recommendation=None,
    route_readiness_ops_launch_controls_present=True,
    route_readiness_ops_launch_controls_blocked_pairs=0,
    route_readiness_ops_broker_roundtrip_portfolio_breach_pairs=0,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs=0,
    route_readiness_ops_launch_controls_ready=True,
    route_readiness_ops_launch_control_failures="",
    route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
    route_broker_route_readiness_required=True,
    route_broker_route_readiness_provided=True,
    route_broker_route_readiness_ready=True,
    route_broker_route_readiness_strategy="lead_lag_taker",
    route_broker_route_readiness_market="india_nse_index_derivatives",
    route_broker_route_readiness_route_ready_pairs=1,
    route_broker_route_readiness_gap_pairs=0,
    route_broker_route_readiness_recommendation=None,
    route_broker_route_readiness_ops_launch_controls_ready=True,
    route_broker_route_readiness_ops_launch_control_failures="",
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=1,
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=0,
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=1,
    route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "route_readiness_inputs_missing"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
    )
    route_broker_route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_broker_route_readiness_recommendation is None and route_broker_route_readiness_ready
        else "route_readiness_inputs_missing"
        if route_broker_route_readiness_recommendation is None
        else route_broker_route_readiness_recommendation
    )
    return {
        "route_readiness": {
            "required": route_readiness_required,
            "provided": route_readiness_provided,
            "ready": route_readiness_ready,
            "strategy": route_readiness_strategy,
            "market": route_readiness_market,
            "route_ready_pairs": route_readiness_route_ready_pairs,
            "gap_pairs": route_readiness_gap_pairs,
            "recommendation": route_readiness_recommendation,
            "ops_launch_controls_present": route_readiness_ops_launch_controls_present,
            "ops_launch_controls_blocked_pairs": route_readiness_ops_launch_controls_blocked_pairs,
            "ops_broker_roundtrip_portfolio_breach_pairs": (
                route_readiness_ops_broker_roundtrip_portfolio_breach_pairs
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_pairs": (
                route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs
            ),
            "ops_launch_controls_ready": route_readiness_ops_launch_controls_ready,
            "ops_launch_control_failures": route_readiness_ops_launch_control_failures,
            "ops_broker_roundtrip_portfolio_safe_runs": (
                route_readiness_ops_broker_roundtrip_portfolio_safe_runs
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": (
                route_readiness_ops_broker_roundtrip_portfolio_breach_runs
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
            ),
        },
        "route_broker_route_readiness": {
            "required": route_broker_route_readiness_required,
            "provided": route_broker_route_readiness_provided,
            "ready": route_broker_route_readiness_ready,
            "strategy": route_broker_route_readiness_strategy,
            "market": route_broker_route_readiness_market,
            "route_ready_pairs": route_broker_route_readiness_route_ready_pairs,
            "gap_pairs": route_broker_route_readiness_gap_pairs,
            "recommendation": route_broker_route_readiness_recommendation,
            "ops_launch_controls_ready": route_broker_route_readiness_ops_launch_controls_ready,
            "ops_launch_control_failures": route_broker_route_readiness_ops_launch_control_failures,
            "ops_broker_roundtrip_portfolio_safe_runs": (
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs
            ),
            "ops_broker_roundtrip_portfolio_breach_runs": (
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs
            ),
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": (
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs
            ),
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": (
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs
            ),
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
        }
    }


def shadow_broker_config(
    sessions=2,
    ready_sessions=2,
    adapter="normalized",
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
        "provided": sessions > 0,
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


def vendor_market_data_batch_config():
    return {
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
        "source_file_fingerprint_coverage": 1.0,
        "min_mapping_coverage": 1.0,
        "unique_header_fingerprints": 1,
        "unique_mapping_drafts": 1,
        "mapping_sources": "vendor_intake_draft",
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
            "application_lineage_consistency_required": True,
            "application_lineage_consistent": True,
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
    vendor.setdefault(
        "application_lineage_sha256",
        target_application_lineage_sha256(vendor["datasets"]),
    )
    return vendor


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
        {field: str(dataset[field]).strip() for field in identity_fields}
        for dataset in datasets
    ]
    lineage_json = json.dumps(
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
    return hashlib.sha256(lineage_json.encode("utf-8")).hexdigest()


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
    }
    comparison.update(overrides)
    return comparison


def roundtrip_final_target_application_lineage_comparison(vendor, **overrides):
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
        "ack_reconciliation_review_carried_application_lineage_sha256": lineage_sha256,
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def roundtrip_complete_final_target_application_lineage_comparison(
    vendor,
    **overrides,
):
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
        "ack_reconciliation_review_carried_application_lineage_sha256": lineage_sha256,
        "roundtrip_final_review_carried_application_lineage_sha256": lineage_sha256,
        "broker_readiness_review_carried_application_lineage_sha256": lineage_sha256,
        "scaleup_final_review_carried_application_lineage_sha256": lineage_sha256,
        "cutover_final_review_carried_application_lineage_sha256": lineage_sha256,
        "route_final_review_carried_application_lineage_sha256": lineage_sha256,
        "dispatch_final_review_carried_application_lineage_sha256": lineage_sha256,
        "send_final_review_carried_application_lineage_sha256": lineage_sha256,
        "ack_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        "carried_application_lineage_sha256": lineage_sha256,
    }
    comparison.update(overrides)
    return comparison


def roundtrip_view_33_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = roundtrip_complete_final_target_application_lineage_comparison(
        vendor
    )
    for field in tuple(comparison):
        if field.endswith("_sha256"):
            comparison[field] = lineage_sha256
    comparison.update(
        {
            "roundtrip_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def roundtrip_view_41_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = roundtrip_view_33_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def roundtrip_view_49_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = roundtrip_view_41_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def roundtrip_view_57_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = roundtrip_view_49_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    for compatibility_only_field in (
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    ):
        comparison.pop(compatibility_only_field, None)
    comparison.update(
        {
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
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
    comparison = roundtrip_view_57_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def roundtrip_view_65_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = roundtrip_view_57_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.pop(
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
        None,
    )
    comparison.update(
        {
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def roundtrip_view_73_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    comparison = roundtrip_view_65_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "scaleup_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "cutover_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "route_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "dispatch_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "send_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def broker_readiness_view_74_target_application_lineage_comparison(
    vendor,
    *,
    lineage_sha256=None,
    broker_readiness_lineage_sha256=None,
    **overrides,
):
    lineage_sha256 = lineage_sha256 or target_application_lineage_sha256(
        vendor["datasets"]
    )
    broker_readiness_lineage_sha256 = (
        broker_readiness_lineage_sha256 or lineage_sha256
    )
    comparison = roundtrip_view_73_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": broker_readiness_lineage_sha256,
            "carried_application_lineage_sha256": broker_readiness_lineage_sha256,
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
    comparison = roundtrip_view_65_target_application_lineage_comparison(
        vendor,
        lineage_sha256=lineage_sha256,
    )
    comparison.update(
        {
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256": lineage_sha256,
            "carried_application_lineage_sha256": lineage_sha256,
        }
    )
    comparison.update(overrides)
    return comparison


def add_roundtrip_complete_final_target_application_lineage(
    config,
    vendor,
    **overrides,
):
    config[
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_complete_final_target_application_lineage_comparison(
        vendor,
        **overrides,
    )
    config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_33_target_application_lineage_comparison(vendor)
    config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_41_target_application_lineage_comparison(vendor)
    config[
        "roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_49_target_application_lineage_comparison(vendor)
    config[
        "roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_57_target_application_lineage_comparison(vendor)
    config[
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_65_target_application_lineage_comparison(vendor)
    config[
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_73_target_application_lineage_comparison(vendor)


def with_broker_vendor_batch_summary(
    summary,
    vendor,
    *,
    include_lineage_comparison=True,
):
    result = summary.copy()
    prefix = "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"
    for key, value in vendor.items():
        if key == "comparison":
            result.loc[0, f"{prefix}_comparison_accepted"] = value["accepted"]
            result.loc[0, f"{prefix}_comparison_failed_checks"] = value["failed_checks"]
        elif key == "datasets":
            result.loc[0, f"{prefix}_datasets_json"] = json.dumps(value, sort_keys=True)
        else:
            result.loc[0, f"{prefix}_{key}"] = value
    if include_lineage_comparison and vendor.get("application_lineage_sha256"):
        comparison = target_application_lineage_comparison(vendor)
        final_comparison = roundtrip_final_target_application_lineage_comparison(
            vendor
        )
        complete_final_comparison = (
            roundtrip_complete_final_target_application_lineage_comparison(vendor)
        )
        extended_complete_final_comparison = (
            roundtrip_view_33_target_application_lineage_comparison(vendor)
        )
        latest_extended_complete_final_comparison = (
            roundtrip_view_41_target_application_lineage_comparison(vendor)
        )
        current_latest_extended_complete_final_comparison = (
            roundtrip_view_49_target_application_lineage_comparison(vendor)
        )
        reconciled_current_latest_extended_complete_final_comparison = (
            roundtrip_view_57_target_application_lineage_comparison(vendor)
        )
        verified_reconciled_current_latest_extended_complete_final_comparison = (
            roundtrip_view_65_target_application_lineage_comparison(vendor)
        )
        confirmed_verified_reconciled_current_latest_extended_complete_final_comparison = (
            roundtrip_view_73_target_application_lineage_comparison(vendor)
        )
        final_prefix = "ack_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        complete_final_prefix = (
            "ack_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        extended_complete_final_prefix = (
            "ack_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        latest_extended_complete_final_prefix = (
            "ack_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        current_latest_extended_complete_final_prefix = (
            "ack_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        reconciled_current_latest_extended_complete_final_prefix = (
            "ack_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        verified_reconciled_current_latest_extended_complete_final_prefix = (
            "ack_verified_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        confirmed_verified_reconciled_current_latest_extended_complete_final_prefix = (
            "ack_confirmed_verified_reconciled_current_latest_extended_complete_final_"
            "broker_dispatch_roundtrip_vendor_market_data_batch"
        )
        result.loc[
            0,
            "roundtrip_broker_vendor_market_data_batch_lineage_match_required",
        ] = comparison["required"]
        result.loc[
            0,
            "roundtrip_broker_vendor_market_data_batch_lineage_matches",
        ] = comparison["matches"]
        summary_fields = {
            "current_application_lineage_sha256": (
                "roundtrip_ack_vendor_market_data_batch_application_lineage_sha256"
            ),
            "broker_application_lineage_sha256": (
                "roundtrip_ack_broker_vendor_market_data_batch_application_lineage_sha256"
            ),
            "scaleup_carried_application_lineage_sha256": (
                "scaleup_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
            "cutover_carried_application_lineage_sha256": (
                "cutover_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
            "route_carried_application_lineage_sha256": (
                "route_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
            "dispatch_carried_application_lineage_sha256": (
                "dispatch_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
            "send_carried_application_lineage_sha256": (
                "send_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
            "ack_carried_application_lineage_sha256": (
                "ack_carried_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
            "roundtrip_carried_application_lineage_sha256": (
                "roundtrip_carried_broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_sha256"
            ),
        }
        for field, summary_field in summary_fields.items():
            result.loc[0, summary_field] = comparison[field]
        result.loc[0, f"{final_prefix}_lineage_match_required"] = final_comparison[
            "required"
        ]
        result.loc[0, f"{final_prefix}_lineage_matches"] = final_comparison["matches"]
        for field, value in final_comparison.items():
            if field not in {"required", "matches", "carried_application_lineage_sha256"}:
                result.loc[0, f"{final_prefix}_{field}"] = value
        result.loc[0, f"{complete_final_prefix}_lineage_match_required"] = (
            complete_final_comparison["required"]
        )
        result.loc[0, f"{complete_final_prefix}_lineage_matches"] = (
            complete_final_comparison["matches"]
        )
        for field, value in complete_final_comparison.items():
            if field not in {
                "required",
                "matches",
                "carried_application_lineage_sha256",
            }:
                result.loc[0, f"{complete_final_prefix}_{field}"] = value
        result.loc[0, f"{extended_complete_final_prefix}_lineage_match_required"] = (
            extended_complete_final_comparison["required"]
        )
        result.loc[0, f"{extended_complete_final_prefix}_lineage_matches"] = (
            extended_complete_final_comparison["matches"]
        )
        for field, value in extended_complete_final_comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "roundtrip_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[0, f"{extended_complete_final_prefix}_{field}"] = value
        result.loc[
            0,
            f"{latest_extended_complete_final_prefix}_lineage_match_required",
        ] = latest_extended_complete_final_comparison["required"]
        result.loc[
            0,
            f"{latest_extended_complete_final_prefix}_lineage_matches",
        ] = latest_extended_complete_final_comparison["matches"]
        for field, value in latest_extended_complete_final_comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "roundtrip_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[0, f"{latest_extended_complete_final_prefix}_{field}"] = (
                value
            )
        result.loc[
            0,
            f"{current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = current_latest_extended_complete_final_comparison["required"]
        result.loc[
            0,
            f"{current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = current_latest_extended_complete_final_comparison["matches"]
        for field, value in current_latest_extended_complete_final_comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "roundtrip_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[
                0,
                f"{current_latest_extended_complete_final_prefix}_{field}",
            ] = value
        result.loc[
            0,
            f"{reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = reconciled_current_latest_extended_complete_final_comparison["required"]
        result.loc[
            0,
            f"{reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = reconciled_current_latest_extended_complete_final_comparison["matches"]
        for field, value in reconciled_current_latest_extended_complete_final_comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "roundtrip_reconciled_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[
                0,
                f"{reconciled_current_latest_extended_complete_final_prefix}_{field}",
            ] = value
        result.loc[
            0,
            f"{verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = verified_reconciled_current_latest_extended_complete_final_comparison[
            "required"
        ]
        result.loc[
            0,
            f"{verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = verified_reconciled_current_latest_extended_complete_final_comparison[
            "matches"
        ]
        for field, value in verified_reconciled_current_latest_extended_complete_final_comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[
                0,
                f"{verified_reconciled_current_latest_extended_complete_final_prefix}_{field}",
            ] = value
        result.loc[
            0,
            f"{confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_match_required",
        ] = confirmed_verified_reconciled_current_latest_extended_complete_final_comparison[
            "required"
        ]
        result.loc[
            0,
            f"{confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_lineage_matches",
        ] = confirmed_verified_reconciled_current_latest_extended_complete_final_comparison[
            "matches"
        ]
        for field, value in confirmed_verified_reconciled_current_latest_extended_complete_final_comparison.items():
            if field in {"required", "matches"}:
                continue
            if field == "carried_application_lineage_sha256":
                field = (
                    "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_"
                    "carried_application_lineage_sha256"
                )
            result.loc[
                0,
                f"{confirmed_verified_reconciled_current_latest_extended_complete_final_prefix}_{field}",
            ] = value
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
            "unique_source_files": 0,
            "source_file_fingerprint_coverage": 0.0,
            "min_mapping_coverage": 0.0,
            "unique_header_fingerprints": 0,
            "unique_mapping_drafts": 0,
            "mapping_sources": "",
            "comparison": {"accepted": False, "failed_checks": 1},
        }
    )
    return vendor


def broker_vendor_data_readiness_config(*, provided=True, ready=True, failed_checks=0):
    return {
        "provided": provided,
        "ready": ready,
        "failed_checks": failed_checks,
    }


def path_tail(value):
    return str(value).replace("\\", "/")


def write_broker_readiness_input_dirs(
    root,
    adapter,
    *,
    verified_roundtrip=False,
    canonical_leadlag=False,
):
    schema_dir = root / "schema"
    export_dir = root / "export"
    upload_dir = root / "upload"
    roundtrip_dir = root / "roundtrip"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir(parents=True)
    schema_summary(adapter, True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary(adapter, True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary(adapter, True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    if verified_roundtrip:
        dispatch, send, ack = _write_verified_ack_chain(
            root,
            adapter=adapter,
            canonical_leadlag=canonical_leadlag,
        )
        roundtrip_report = write_broker_dispatch_roundtrip(
            dispatch_dir=dispatch,
            send_dir=send,
            ack_dir=ack,
            output_dir=roundtrip_dir,
            thresholds=BrokerDispatchRoundTripThresholds(
                require_ack_lineage=True,
            ),
        )
        assert roundtrip_report.passed
    else:
        roundtrip_dir.mkdir()
        dispatch_roundtrip_summary(adapter, True).to_csv(
            roundtrip_dir / "broker_dispatch_roundtrip_summary.csv",
            index=False,
        )
        (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
            json.dumps(dispatch_roundtrip_config(), indent=2) + "\n",
            encoding="utf-8",
        )
    return schema_dir, export_dir, upload_dir, roundtrip_dir


def write_vendor_market_data_batch(root, adapter, *, market="india_nse_index_derivatives"):
    day1 = root / f"{adapter}_ticks_day1.csv"
    day2 = root / f"{adapter}_ticks_day2.csv"
    out_dir = root / "vendor_batch"
    session_open = "09:30" if market.startswith("us_") else "09:15"
    broker_vendor_ticks("2026-06-10", base=100.0, session_open=session_open).to_csv(day1, index=False)
    broker_vendor_ticks("2026-06-11", base=100.5, session_open=session_open).to_csv(day2, index=False)
    filter_session = not market.startswith("us_")
    report = write_vendor_market_data_batch_pipeline(
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        config=VendorMarketDataPipelineConfig(
            adapter=adapter,
            kind="ticks",
            market=market,
            timestamp_unit="datetime",
            filter_session=filter_session,
            tick_size=0.05,
            min_rows=2,
            max_out_of_session_rows=0 if filter_session else 2,
        ),
    )
    assert report.ready
    return out_dir


def test_broker_readiness_accepts_ready_normalized_artifacts():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized"),
    )

    assert report.ready
    assert report.summary.iloc[0]["recommendation"] == "broker_integration_ready"
    assert set(report.checks["passed"]) == {True}


def test_broker_readiness_accepts_required_runtime_session():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        runtime_session_summary=runtime_session_summary("normalized", ready=True, halted=False),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_runtime_session=True),
    )

    assert report.ready
    runtime_item = report.items.loc[report.items["component"] == "runtime_session"].iloc[0]
    assert bool(runtime_item["ready"])
    assert runtime_item["runtime_guard_action"] == "continue"
    assert runtime_item["runtime_target_mode"] == "shadow"
    assert runtime_item["runtime_strategy"] == "surface_mm"
    assert runtime_item["runtime_market"] == "india_nse_index_derivatives"
    summary = report.summary.iloc[0]
    assert bool(summary["runtime_session_provided"])
    assert bool(summary["runtime_session_ready"])
    assert summary["runtime_guard_action"] == "continue"
    assert not bool(summary["runtime_guard_halted"])
    assert summary["runtime_target_mode"] == "shadow"
    assert summary["runtime_strategy"] == "surface_mm"
    assert summary["runtime_market"] == "india_nse_index_derivatives"


def test_broker_readiness_accepts_required_resume_gate():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        resume_summary=resume_summary("normalized", ready=True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_resume_gate=True),
    )

    assert report.ready
    resume_item = report.items.loc[report.items["component"] == "resume_gate"].iloc[0]
    assert bool(resume_item["ready"])
    assert resume_item["resume_strategy"] == "surface_mm"
    assert resume_item["resume_proof_refresh_strategy"] == "surface_mm"
    assert bool(resume_item["resume_broker_route_readiness_ready"])
    assert resume_item["resume_broker_route_readiness_strategy"] == "surface_mm"
    assert int(resume_item["resume_broker_route_readiness_gap_pairs"]) == 0
    assert int(resume_item["resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
    summary = report.summary.iloc[0]
    assert bool(summary["resume_gate_provided"])
    assert bool(summary["resume_gate_ready"])
    assert bool(summary["resume_proof_refresh_ready"])
    assert summary["resume_strategy"] == "surface_mm"
    assert summary["resume_incident_market"] == "india_nse_index_derivatives"
    assert summary["resume_proof_refresh_market"] == "india_nse_index_derivatives"
    assert bool(summary["resume_broker_route_readiness_ready"])
    assert summary["resume_broker_route_readiness_market"] == "india_nse_index_derivatives"
    assert bool(summary["resume_incident_broker_route_readiness_ready"])
    assert int(summary["resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"]) == 1
    assert report.config["resume_gate"]["broker_route_readiness"]["ready"]
    assert report.config["resume_gate"]["broker_route_readiness"]["strategy"] == "surface_mm"
    assert report.config["resume_gate"]["incident_broker_route_readiness"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_broker_readiness_blocks_dirty_resume_route_readiness_proof():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        resume_summary=resume_summary(
            "normalized",
            ready=True,
            route_ready=False,
            route_strategy="lead_lag_taker",
            route_market="us_options_regular",
            route_gap_pairs=2,
            route_ops_launch_controls_ready=False,
            route_ops_broker_roundtrip_portfolio_safe_runs=0,
            route_ops_broker_roundtrip_portfolio_breach_runs=1,
            route_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            route_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
            incident_route_ready=False,
            incident_route_gap_pairs=1,
            incident_route_ops_launch_controls_ready=False,
            incident_route_ops_broker_roundtrip_portfolio_safe_runs=0,
            incident_route_ops_broker_roundtrip_portfolio_breach_runs=1,
            incident_route_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            incident_route_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_resume_gate=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "resume_broker_route_readiness_ready",
        "resume_broker_route_readiness_strategy_matches",
        "resume_broker_route_readiness_market_matches",
        "resume_broker_route_readiness_gap_pairs",
        "resume_broker_route_readiness_ops_launch_controls_ready",
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "resume_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
        "resume_incident_broker_route_readiness_ready",
        "resume_incident_broker_route_readiness_gap_pairs",
        "resume_incident_broker_route_readiness_ops_launch_controls_ready",
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs",
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    route_actions = report.action_queue.loc[
        report.action_queue["check"].str.startswith("resume_broker_route_readiness")
        | report.action_queue["check"].str.startswith("resume_incident_broker_route_readiness")
    ]
    assert not route_actions.empty
    assert set(route_actions["component"]) == {"route_readiness"}
    assert set(route_actions["next_gate"]) == {"review-route-readiness"}
    summary = report.summary.iloc[0]
    assert not bool(summary["resume_broker_route_readiness_ready"])
    assert int(summary["resume_broker_route_readiness_gap_pairs"]) == 2
    assert report.config["resume_gate"]["broker_route_readiness"]["gap_pairs"] == 2
    assert not report.config["resume_gate"]["incident_broker_route_readiness"]["ops_launch_controls_ready"]


def test_broker_readiness_accepts_required_dispatch_roundtrip():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert bool(item["ready"])
    assert item["dispatch_roundtrip_target_mode"] == "live_dryrun"
    assert item["dispatch_roundtrip_strategy"] == "lead_lag_taker"
    assert int(item["dispatch_roundtrip_acked_orders"]) == 2
    summary = report.summary.iloc[0]
    assert bool(summary["dispatch_roundtrip_provided"])
    assert bool(summary["dispatch_roundtrip_ready"])
    assert summary["dispatch_roundtrip_batch_id"] == "BDP-1"
    assert int(summary["dispatch_roundtrip_requests"]) == 2
    assert int(summary["dispatch_roundtrip_missing_request_acks"]) == 0
    assert int(summary["dispatch_roundtrip_failed_checks"]) == 0
    assert int(summary["route_enable_dispatch_roundtrip_failed_checks"]) == 0
    assert bool(summary["route_readiness_provided"])
    assert bool(summary["route_readiness_ready"])
    assert summary["route_readiness_strategy"] == "lead_lag_taker"
    assert summary["route_readiness_market"] == "india_nse_index_derivatives"
    assert int(summary["route_readiness_gap_pairs"]) == 0
    assert bool(summary["route_dispatch_roundtrip_provided"])
    assert bool(summary["route_dispatch_roundtrip_ready"])
    assert summary["route_dispatch_roundtrip_batch_id"] == "BDP-0"
    assert int(summary["route_dispatch_roundtrip_requests"]) == 2


def test_broker_readiness_carries_dispatch_roundtrip_shadow_broker_readiness():
    config = dispatch_roundtrip_config()
    config["shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert bool(item["shadow_broker_readiness_provided"])
    assert int(item["shadow_broker_readiness_sessions"]) == 2
    assert int(item["shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert item["shadow_broker_adapter"] == "normalized"
    summary = report.summary.iloc[0]
    assert bool(summary["shadow_broker_readiness_provided"])
    assert int(summary["shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["shadow_broker_adapter"] == "normalized"
    assert summary["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["shadow_broker_dispatch_roundtrip_scenario_count"]) == 1
    assert int(summary["shadow_broker_route_dispatch_roundtrip_sessions"]) == 2
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2


def test_broker_readiness_blocks_dirty_dispatch_roundtrip_shadow_broker_readiness():
    config = dispatch_roundtrip_config()
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

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_broker_readiness_ready",
        "shadow_broker_vendor_data_readiness_ready",
        "shadow_broker_vendor_data_readiness_failed_checks",
        "shadow_broker_adapter_matches",
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
    summary = report.summary.iloc[0]
    assert summary["shadow_broker_adapter"] == "irage"
    assert int(summary["shadow_broker_vendor_data_readiness_failed_checks"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert int(summary["shadow_broker_route_readiness_gap_pairs"]) == 2


def test_broker_readiness_blocks_partial_dispatch_roundtrip_shadow_broker_vendor_data_readiness():
    config = dispatch_roundtrip_config()
    config["shadow_broker_readiness"] = shadow_broker_config(
        broker_vendor_data_readiness_sessions=1,
        broker_vendor_data_readiness_provided_sessions=1,
        broker_vendor_data_readiness_ready_sessions=1,
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "shadow_broker_vendor_data_readiness_present_for_broker_sessions",
        "shadow_broker_vendor_data_readiness_provided",
        "shadow_broker_vendor_data_readiness_ready",
    } <= failed
    summary = report.summary.iloc[0]
    assert int(summary["shadow_broker_vendor_data_readiness_sessions"]) == 1
    assert report.config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["provided_sessions"] == 1


def test_broker_readiness_carries_dispatch_roundtrip_broker_shadow_broker_readiness():
    config = dispatch_roundtrip_config()
    config["broker_shadow_broker_readiness"] = shadow_broker_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert bool(item["broker_shadow_broker_readiness_provided"])
    assert int(item["broker_shadow_broker_readiness_sessions"]) == 2
    assert int(item["broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert item["broker_shadow_broker_adapter"] == "normalized"
    summary = report.summary.iloc[0]
    assert bool(summary["broker_shadow_broker_readiness_provided"])
    assert int(summary["broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_ready_sessions"]) == 2
    assert int(summary["broker_shadow_broker_vendor_data_readiness_failed_checks"]) == 0
    assert summary["broker_shadow_broker_adapter"] == "normalized"
    assert summary["broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["broker_shadow_broker_dispatch_roundtrip_scenario_count"]) == 1
    assert int(summary["broker_shadow_broker_route_dispatch_roundtrip_sessions"]) == 2
    assert report.config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2


def test_broker_readiness_carries_dispatch_roundtrip_vendor_market_data_batch():
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert bool(item["dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert item["dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert int(item["dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    summary = report.summary.iloc[0]
    assert bool(summary["dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary["dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary["dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert int(summary["dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary["dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert int(summary["dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    vendor = report.config["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_readiness_blocks_dirty_dispatch_roundtrip_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    vendor.update(
        {
            "ready": False,
            "adapter": "irage",
            "market": "us_options_regular",
            "dataset_count": 0,
            "ready_datasets": 0,
            "failed_datasets": 1,
            "unique_source_files": 0,
            "source_file_fingerprint_coverage": 0.0,
            "min_mapping_coverage": 0.0,
            "unique_header_fingerprints": 0,
            "unique_mapping_drafts": 0,
            "mapping_sources": "",
            "comparison": {"accepted": False, "failed_checks": 1},
        }
    )
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_ready",
        "dispatch_roundtrip_vendor_market_data_batch_adapter_matches",
        "dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "dispatch_roundtrip_vendor_market_data_batch_source_files",
        "dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed


def test_broker_readiness_carries_broker_dispatch_roundtrip_vendor_market_data_batch():
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert bool(item["broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert item["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert int(item["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    summary = report.summary.iloc[0]
    assert bool(summary["broker_dispatch_roundtrip_vendor_market_data_batch_provided"])
    assert bool(summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "ticks"
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_source_file_fingerprint_coverage"] == 1.0
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_min_mapping_coverage"] == 1.0
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_drafts"]) == 1
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    vendor = report.config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["source_file_fingerprint_coverage"] == 1.0
    assert vendor["min_mapping_coverage"] == 1.0
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_readiness_carries_final_target_application_lineage_consistency():
    vendor = target_application_vendor_market_data_batch_config()
    final_lineage = target_application_lineage_comparison(vendor)
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = final_lineage
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    field_prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    summary = report.summary.iloc[0]
    carried = report.config["dispatch_roundtrip"][field_prefix]
    assert bool(item[f"{field_prefix}_application_lineage_consistency_required"])
    assert bool(item[f"{field_prefix}_application_lineage_consistent"])
    assert bool(summary[f"{field_prefix}_application_lineage_consistency_required"])
    assert bool(summary[f"{field_prefix}_application_lineage_consistent"])
    assert carried["application_lineage_consistency_required"]
    assert carried["application_lineage_consistent"]
    assert carried["application_lineage_sha256"] == vendor["application_lineage_sha256"]
    assert carried["datasets"][1]["mapping_application_id"] == "mapping-app-day2"
    assert bool(summary["broker_vendor_market_data_batch_lineage_match_required"])
    assert bool(summary["broker_vendor_market_data_batch_lineage_matches"])
    assert len(summary["vendor_market_data_batch_application_lineage_sha256"]) == 64
    assert summary["vendor_market_data_batch_application_lineage_sha256"] == (
        summary["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    lineage_config = report.config["dispatch_roundtrip"][
        "vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage_config["required"]
    assert lineage_config["matches"]
    assert lineage_config["current_application_lineage_sha256"] == (
        lineage_config["broker_application_lineage_sha256"]
    )
    final_lineage_config = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage_config["required"]
    assert final_lineage_config["matches"]
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
        assert final_lineage_config[field] == vendor["application_lineage_sha256"]
    readiness_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_final_lineage["required"]
    assert readiness_final_lineage["matches"]
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
        "carried_application_lineage_sha256",
    ):
        assert readiness_final_lineage[field] == vendor["application_lineage_sha256"]
    readiness_complete_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_complete_final_lineage["required"]
    assert readiness_complete_final_lineage["matches"]
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
        "carried_application_lineage_sha256",
    ):
        assert (
            readiness_complete_final_lineage[field]
            == vendor["application_lineage_sha256"]
        )
    complete_summary_prefix = (
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    assert bool(summary[f"{complete_summary_prefix}_lineage_match_required"])
    assert bool(summary[f"{complete_summary_prefix}_lineage_matches"])
    for field in (
        "ack_complete_final_review_carried_application_lineage_sha256",
        "roundtrip_complete_final_review_carried_application_lineage_sha256",
        "broker_readiness_complete_final_review_carried_application_lineage_sha256",
    ):
        assert (
            summary[f"{complete_summary_prefix}_{field}"]
            == vendor["application_lineage_sha256"]
        )
    extended_summary_prefix = (
        "roundtrip_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    extended_source = roundtrip_view_33_target_application_lineage_comparison(
        vendor
    )
    assert bool(summary[f"{extended_summary_prefix}_lineage_match_required"])
    assert bool(summary[f"{extended_summary_prefix}_lineage_matches"])
    for field, value in extended_source.items():
        if not field.endswith("_sha256"):
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "roundtrip_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        assert summary[f"{extended_summary_prefix}_{field}"] == value
    assert (
        summary[
            f"{extended_summary_prefix}_broker_readiness_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    readiness_extended_complete_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_extended_complete_final_lineage["required"]
    assert readiness_extended_complete_final_lineage["matches"]
    for field, value in readiness_extended_complete_final_lineage.items():
        if field.endswith("_sha256"):
            assert value == vendor["application_lineage_sha256"]
    latest_extended_summary_prefix = (
        "roundtrip_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    latest_extended_source = (
        roundtrip_view_41_target_application_lineage_comparison(vendor)
    )
    assert bool(
        summary[f"{latest_extended_summary_prefix}_lineage_match_required"]
    )
    assert bool(summary[f"{latest_extended_summary_prefix}_lineage_matches"])
    for field, value in latest_extended_source.items():
        if not field.endswith("_sha256"):
            continue
        if field == "carried_application_lineage_sha256":
            field = (
                "roundtrip_latest_extended_complete_final_review_"
                "carried_application_lineage_sha256"
            )
        assert summary[f"{latest_extended_summary_prefix}_{field}"] == value
    assert (
        summary[
            f"{latest_extended_summary_prefix}_broker_readiness_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    readiness_latest_extended_complete_final_lineage = report.config[
        "dispatch_roundtrip"
    ][
        "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_latest_extended_complete_final_lineage["required"]
    assert readiness_latest_extended_complete_final_lineage["matches"]
    for field, value in readiness_latest_extended_complete_final_lineage.items():
        if field.endswith("_sha256"):
            assert value == vendor["application_lineage_sha256"]
    current_latest_summary_prefix = (
        "roundtrip_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    current_latest_source = roundtrip_view_49_target_application_lineage_comparison(
        vendor
    )
    assert bool(
        summary[f"{current_latest_summary_prefix}_lineage_match_required"]
    )
    assert bool(summary[f"{current_latest_summary_prefix}_lineage_matches"])
    compatibility_only_fields = {
        "broker_readiness_extended_complete_final_review_carried_application_lineage_sha256",
        "scaleup_extended_complete_final_review_carried_application_lineage_sha256",
        "cutover_extended_complete_final_review_carried_application_lineage_sha256",
    }
    for field, value in current_latest_source.items():
        if field in {"required", "matches", *compatibility_only_fields}:
            continue
        summary_field = (
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            if field == "carried_application_lineage_sha256"
            else field
        )
        assert summary[f"{current_latest_summary_prefix}_{summary_field}"] == value
    assert (
        summary[
            f"{current_latest_summary_prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    readiness_current_latest_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_current_latest_lineage["required"]
    assert readiness_current_latest_lineage["matches"]
    for field, value in current_latest_source.items():
        if field in {
            "required",
            "matches",
            "carried_application_lineage_sha256",
            *compatibility_only_fields,
        }:
            continue
        assert readiness_current_latest_lineage[field] == value
    assert (
        readiness_current_latest_lineage[
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    assert readiness_current_latest_lineage[
        "carried_application_lineage_sha256"
    ] == vendor["application_lineage_sha256"]
    reconciled_current_latest_summary_prefix = (
        "roundtrip_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    reconciled_current_latest_source = (
        roundtrip_view_57_target_application_lineage_comparison(vendor)
    )
    assert len(reconciled_current_latest_source) == 56
    assert bool(
        summary[
            f"{reconciled_current_latest_summary_prefix}_lineage_match_required"
        ]
    )
    assert bool(
        summary[f"{reconciled_current_latest_summary_prefix}_lineage_matches"]
    )
    for field, value in reconciled_current_latest_source.items():
        if field in {"required", "matches"}:
            continue
        summary_field = (
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
            if field == "carried_application_lineage_sha256"
            else field
        )
        assert (
            summary[
                f"{reconciled_current_latest_summary_prefix}_{summary_field}"
            ]
            == value
        )
    assert (
        summary[
            f"{reconciled_current_latest_summary_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    readiness_reconciled_current_latest_lineage = report.config[
        "dispatch_roundtrip"
    ][
        "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_reconciled_current_latest_lineage = (
        broker_readiness_view_58_target_application_lineage_comparison(vendor)
    )
    assert len(expected_reconciled_current_latest_lineage) == 57
    assert set(readiness_reconciled_current_latest_lineage) == set(
        expected_reconciled_current_latest_lineage
    )
    assert readiness_reconciled_current_latest_lineage == (
        expected_reconciled_current_latest_lineage
    )
    verified_reconciled_summary_prefix = (
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    verified_reconciled_source = (
        roundtrip_view_65_target_application_lineage_comparison(vendor)
    )
    assert len(verified_reconciled_source) == 64
    assert bool(summary[f"{verified_reconciled_summary_prefix}_lineage_match_required"])
    assert bool(summary[f"{verified_reconciled_summary_prefix}_lineage_matches"])
    for field, value in verified_reconciled_source.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{verified_reconciled_summary_prefix}_{field}"] == value
    assert (
        summary[
            f"{verified_reconciled_summary_prefix}_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    readiness_verified_reconciled_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_verified_reconciled_lineage = (
        broker_readiness_view_66_target_application_lineage_comparison(vendor)
    )
    assert len(readiness_verified_reconciled_lineage) == 65
    assert readiness_verified_reconciled_lineage == (
        expected_verified_reconciled_lineage
    )
    confirmed_verified_reconciled_summary_prefix = (
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    confirmed_verified_reconciled_source = (
        roundtrip_view_73_target_application_lineage_comparison(vendor)
    )
    assert len(confirmed_verified_reconciled_source) == 72
    assert bool(
        summary[f"{confirmed_verified_reconciled_summary_prefix}_lineage_match_required"]
    )
    assert bool(
        summary[f"{confirmed_verified_reconciled_summary_prefix}_lineage_matches"]
    )
    for field, value in confirmed_verified_reconciled_source.items():
        if field in {"required", "matches", "carried_application_lineage_sha256"}:
            continue
        assert summary[f"{confirmed_verified_reconciled_summary_prefix}_{field}"] == value
    assert (
        summary[
            f"{confirmed_verified_reconciled_summary_prefix}_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    readiness_confirmed_verified_reconciled_lineage = report.config[
        "dispatch_roundtrip"
    ][
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_confirmed_verified_reconciled_lineage = (
        broker_readiness_view_74_target_application_lineage_comparison(vendor)
    )
    assert len(readiness_confirmed_verified_reconciled_lineage) == 73
    assert readiness_confirmed_verified_reconciled_lineage == (
        expected_confirmed_verified_reconciled_lineage
    )
    expected_checks = {
        f"{field_prefix}_mapping_source_mode",
        f"{field_prefix}_mapping_application_count",
        f"{field_prefix}_unique_mapping_applications",
        f"{field_prefix}_target_application_coverage",
        f"{field_prefix}_application_lineage_datasets",
        f"{field_prefix}_application_lineage_consistent",
        f"{field_prefix}_lineage_match_required",
        f"{field_prefix}_lineage_matches",
        f"{field_prefix}_source_lineage_sha256_matches",
        f"{field_prefix}_application_lineage_sha256_matches",
        f"{field_prefix}_scaleup_carried_lineage_sha256_matches",
        f"{field_prefix}_cutover_carried_lineage_sha256_matches",
        f"{field_prefix}_route_carried_lineage_sha256_matches",
        f"{field_prefix}_dispatch_carried_lineage_sha256_matches",
        f"{field_prefix}_send_carried_lineage_sha256_matches",
        f"{field_prefix}_ack_carried_lineage_sha256_matches",
        f"{field_prefix}_roundtrip_carried_lineage_sha256_matches",
        f"{field_prefix}_readiness_carried_lineage_sha256_matches",
        f"{field_prefix}_matches_current_vendor_lineage",
        f"{field_prefix}_final_lineage_match_required",
        f"{field_prefix}_final_lineage_matches",
        f"{field_prefix}_final_source_lineage_sha256_matches",
        f"{field_prefix}_final_broker_lineage_sha256_matches",
        f"{field_prefix}_final_application_lineage_sha256_matches",
        f"{field_prefix}_final_prior_scaleup_carried_lineage_sha256_matches",
        f"{field_prefix}_final_prior_cutover_carried_lineage_sha256_matches",
        f"{field_prefix}_final_route_carried_lineage_sha256_matches",
        f"{field_prefix}_final_dispatch_carried_lineage_sha256_matches",
        f"{field_prefix}_final_send_carried_lineage_sha256_matches",
        f"{field_prefix}_final_ack_carried_lineage_sha256_matches",
        f"{field_prefix}_final_roundtrip_carried_lineage_sha256_matches",
        f"{field_prefix}_final_readiness_carried_lineage_sha256_matches",
        f"{field_prefix}_final_scaleup_review_carried_lineage_sha256_matches",
        f"{field_prefix}_final_cutover_review_carried_lineage_sha256_matches",
        f"{field_prefix}_final_route_enable_review_carried_lineage_sha256_matches",
        f"{field_prefix}_final_dispatch_plan_review_carried_lineage_sha256_matches",
        f"{field_prefix}_final_send_packet_review_carried_lineage_sha256_matches",
        f"{field_prefix}_final_ack_reconciliation_review_carried_lineage_sha256_matches",
        f"{field_prefix}_final_roundtrip_review_carried_lineage_sha256_matches",
        f"{field_prefix}_broker_readiness_final_review_carried_lineage_sha256_matches",
    }
    complete_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final"
    )
    expected_checks.update(
        {
            f"{complete_check_prefix}_lineage_match_required",
            f"{complete_check_prefix}_lineage_matches",
            f"{complete_check_prefix}_source_lineage_sha256_matches",
            f"{complete_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{complete_check_prefix}_compatibility_roundtrip_final_review_carried_lineage_sha256_matches",
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
            f"{complete_check_prefix}_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{extended_check_prefix}_lineage_match_required",
            f"{extended_check_prefix}_lineage_matches",
            f"{extended_check_prefix}_source_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{extended_check_prefix}_compatibility_roundtrip_complete_final_review_carried_lineage_sha256_matches",
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
    ):
        expected_checks.add(
            f"{extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    latest_extended_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{latest_extended_check_prefix}_lineage_match_required",
            f"{latest_extended_check_prefix}_lineage_matches",
            f"{latest_extended_check_prefix}_source_lineage_sha256_matches",
            f"{latest_extended_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{latest_extended_check_prefix}_compatibility_roundtrip_extended_complete_final_review_carried_lineage_sha256_matches",
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
        "broker_readiness_latest_extended_complete_final_review",
    ):
        expected_checks.add(
            f"{latest_extended_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    current_latest_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{current_latest_check_prefix}_lineage_match_required",
            f"{current_latest_check_prefix}_lineage_matches",
            f"{current_latest_check_prefix}_source_lineage_sha256_matches",
            f"{current_latest_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{current_latest_check_prefix}_compatibility_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_scaleup_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_cutover_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_route_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_dispatch_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_send_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_ack_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_roundtrip_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{current_latest_check_prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
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
            f"{current_latest_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    reconciled_current_latest_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_reconciled_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{reconciled_current_latest_check_prefix}_lineage_match_required",
            f"{reconciled_current_latest_check_prefix}_lineage_matches",
            f"{reconciled_current_latest_check_prefix}_source_lineage_sha256_matches",
            f"{reconciled_current_latest_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{reconciled_current_latest_check_prefix}_compatibility_broker_readiness_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{reconciled_current_latest_check_prefix}_roundtrip_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{reconciled_current_latest_check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
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
        "broker_readiness_latest_extended_complete_final_review",
        "scaleup_latest_extended_complete_final_review",
        "cutover_latest_extended_complete_final_review",
        "route_latest_extended_complete_final_review",
        "dispatch_latest_extended_complete_final_review",
        "send_latest_extended_complete_final_review",
        "ack_current_latest_extended_complete_final_review",
        "roundtrip_current_latest_extended_complete_final_review",
        "broker_readiness_current_latest_extended_complete_final_review",
        "scaleup_current_latest_extended_complete_final_review",
        "cutover_current_latest_extended_complete_final_review",
        "route_current_latest_extended_complete_final_review",
        "dispatch_current_latest_extended_complete_final_review",
        "send_current_latest_extended_complete_final_review",
        "ack_reconciled_current_latest_extended_complete_final_review",
        "roundtrip_reconciled_current_latest_extended_complete_final_review",
    ):
        expected_checks.add(
            f"{reconciled_current_latest_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    verified_reconciled_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{verified_reconciled_check_prefix}_lineage_match_required",
            f"{verified_reconciled_check_prefix}_lineage_matches",
            f"{verified_reconciled_check_prefix}_source_lineage_sha256_matches",
            f"{verified_reconciled_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{verified_reconciled_check_prefix}_compatibility_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{verified_reconciled_check_prefix}_roundtrip_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{verified_reconciled_check_prefix}_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    source_view_65_fields = set(verified_reconciled_source) - {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }
    for field in source_view_65_fields:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_checks.add(
            f"{verified_reconciled_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    confirmed_verified_reconciled_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    expected_checks.update(
        {
            f"{confirmed_verified_reconciled_check_prefix}_lineage_match_required",
            f"{confirmed_verified_reconciled_check_prefix}_lineage_matches",
            f"{confirmed_verified_reconciled_check_prefix}_source_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_check_prefix}_compatibility_broker_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_check_prefix}_compatibility_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_check_prefix}_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
            f"{confirmed_verified_reconciled_check_prefix}_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        }
    )
    source_view_73_fields = set(confirmed_verified_reconciled_source) - {
        "required",
        "matches",
        "current_application_lineage_sha256",
        "broker_application_lineage_sha256",
        "carried_application_lineage_sha256",
    }
    for field in source_view_73_fields:
        stage = field.removesuffix("_carried_application_lineage_sha256")
        if stage == "scaleup":
            stage = "prior_scaleup"
        elif stage == "cutover":
            stage = "prior_cutover"
        expected_checks.add(
            f"{confirmed_verified_reconciled_check_prefix}_{stage}_carried_lineage_sha256_matches"
        )
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


def test_broker_readiness_blocks_roundtrip_view_33_drift_while_preserving_view_26():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_33_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_roundtrip_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_broker_readiness_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    complete_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert complete_final_lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert (
        complete_final_lineage[
            "roundtrip_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert complete_final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    assert complete_final_lineage["broker_application_lineage_sha256"] != "f" * 64
    extended_complete_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        extended_complete_final_lineage["broker_application_lineage_sha256"]
        == "f" * 64
    )
    assert (
        extended_complete_final_lineage[
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        extended_complete_final_lineage["carried_application_lineage_sha256"]
        == lineage_sha256
    )


def test_broker_readiness_blocks_roundtrip_view_41_drift_while_preserving_view_34():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_41_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_roundtrip_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    broker_readiness_view_34 = report.config["dispatch_roundtrip"][
        "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        broker_readiness_view_34["broker_application_lineage_sha256"]
        == lineage_sha256
    )
    assert (
        broker_readiness_view_34[
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        broker_readiness_view_34["carried_application_lineage_sha256"]
        == lineage_sha256
    )
    assert broker_readiness_view_34["broker_application_lineage_sha256"] != (
        "f" * 64
    )
    broker_readiness_view_42 = report.config["dispatch_roundtrip"][
        "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_42["broker_application_lineage_sha256"] == "f" * 64
    assert (
        broker_readiness_view_42[
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        broker_readiness_view_42[
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        broker_readiness_view_42["carried_application_lineage_sha256"]
        == lineage_sha256
    )


def test_broker_readiness_blocks_roundtrip_view_49_drift_while_preserving_view_42():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config[
        "roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_49_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_broker_readiness_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    broker_readiness_view_42 = report.config["dispatch_roundtrip"][
        "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_42["broker_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert (
        broker_readiness_view_42[
            "roundtrip_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert broker_readiness_view_42["carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert broker_readiness_view_42["broker_application_lineage_sha256"] != (
        "f" * 64
    )
    broker_readiness_view_50 = report.config["dispatch_roundtrip"][
        "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_50["broker_application_lineage_sha256"] == (
        "f" * 64
    )
    assert (
        broker_readiness_view_50[
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        broker_readiness_view_50[
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert broker_readiness_view_50["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_broker_readiness_blocks_roundtrip_view_57_drift_while_preserving_view_50():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config[
        "roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_57_target_application_lineage_comparison(
        vendor,
        lineage_sha256="f" * 64,
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    broker_readiness_view_50 = report.config["dispatch_roundtrip"][
        "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_50["required"]
    assert broker_readiness_view_50["matches"]
    assert broker_readiness_view_50["broker_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert (
        broker_readiness_view_50[
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert (
        broker_readiness_view_50[
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert broker_readiness_view_50["carried_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert broker_readiness_view_50["broker_application_lineage_sha256"] != (
        "f" * 64
    )
    broker_readiness_view_58 = report.config["dispatch_roundtrip"][
        "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_58["broker_application_lineage_sha256"] == (
        "f" * 64
    )
    assert (
        broker_readiness_view_58[
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == "f" * 64
    )
    assert (
        broker_readiness_view_58[
            "broker_readiness_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert broker_readiness_view_58["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_broker_readiness_blocks_roundtrip_view_65_drift_while_preserving_view_58():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    drifted_view_65 = roundtrip_view_65_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_65) == 64
    config[
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = drifted_view_65
    summary = with_broker_vendor_batch_summary(
        dispatch_roundtrip_summary("arrow_money", True),
        vendor,
    )
    summary_prefix = (
        "ack_verified_reconciled_current_latest_extended_complete_final_"
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    )
    for field, value in drifted_view_65.items():
        if field == "required":
            summary.loc[0, f"{summary_prefix}_lineage_match_required"] = value
        elif field == "matches":
            summary.loc[0, f"{summary_prefix}_lineage_matches"] = value
        elif field == "carried_application_lineage_sha256":
            summary.loc[
                0,
                f"{summary_prefix}_roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            ] = value
        else:
            summary.loc[0, f"{summary_prefix}_{field}"] = value

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=summary,
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    broker_readiness_view_58 = report.config["dispatch_roundtrip"][
        "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_58 == (
        broker_readiness_view_58_target_application_lineage_comparison(vendor)
    )
    assert broker_readiness_view_58["broker_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert broker_readiness_view_58["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    broker_readiness_view_66 = report.config["dispatch_roundtrip"][
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_66["broker_application_lineage_sha256"] == (
        drifted_lineage_sha256
    )
    assert (
        broker_readiness_view_66[
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == drifted_lineage_sha256
    )
    assert (
        broker_readiness_view_66[
            "broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == lineage_sha256
    )
    assert broker_readiness_view_66["carried_application_lineage_sha256"] == (
        lineage_sha256
    )


def test_broker_readiness_blocks_roundtrip_view_73_drift_while_preserving_view_66():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = target_application_lineage_sha256(vendor["datasets"])
    drifted_lineage_sha256 = "f" * 64
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    drifted_view_73 = roundtrip_view_73_target_application_lineage_comparison(
        vendor,
        lineage_sha256=drifted_lineage_sha256,
    )
    assert len(drifted_view_73) == 72
    config[
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = drifted_view_73

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{check_prefix}_compatibility_broker_readiness_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        f"{check_prefix}_broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    broker_readiness_view_66 = report.config["dispatch_roundtrip"][
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_66 == (
        broker_readiness_view_66_target_application_lineage_comparison(vendor)
    )
    assert broker_readiness_view_66["broker_application_lineage_sha256"] == (
        lineage_sha256
    )
    assert broker_readiness_view_66["broker_application_lineage_sha256"] != (
        drifted_lineage_sha256
    )
    broker_readiness_view_74 = report.config["dispatch_roundtrip"][
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert broker_readiness_view_74 == (
        broker_readiness_view_74_target_application_lineage_comparison(
            vendor,
            lineage_sha256=drifted_lineage_sha256,
            broker_readiness_lineage_sha256=lineage_sha256,
        )
    )


def test_broker_readiness_requires_roundtrip_view_73_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    broker_readiness_view_74 = report.config["dispatch_roundtrip"][
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not broker_readiness_view_74["required"]
    assert not broker_readiness_view_74["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_view_73_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    roundtrip_view_73 = config[
        "roundtrip_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    roundtrip_view_73[field] = value

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_readiness_requires_roundtrip_view_65_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_verified_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_verified_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_verified_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_verified_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_verified_reconciled_current_latest_extended_complete_final_roundtrip_verified_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_verified_reconciled_current_latest_extended_complete_final_roundtrip_verified_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_view_65_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    comparison = config[
        "roundtrip_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    comparison[field] = value

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_readiness_requires_roundtrip_view_57_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_reconciled_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_reconciled_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_reconciled_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_reconciled_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_reconciled_current_latest_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_reconciled_current_latest_extended_complete_final_roundtrip_reconciled_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_reconciled_current_latest_extended_complete_final_roundtrip_reconciled_current_latest_extended_complete_final_review_generic_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_view_57_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    comparison = config[
        "roundtrip_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    comparison[field] = value

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_readiness_requires_roundtrip_view_49_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_current_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_current_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_current_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_current_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_current_latest_extended_complete_final_send_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_current_latest_extended_complete_final_roundtrip_current_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_view_49_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    comparison = config[
        "roundtrip_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    comparison[field] = value

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_readiness_blocks_roundtrip_complete_final_lineage_drift():
    vendor = target_application_vendor_market_data_batch_config()
    lineage_sha256 = vendor["application_lineage_sha256"]
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    complete_final_sha256 = "f" * 64
    complete_final_fields = (
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
        "carried_application_lineage_sha256",
    )
    config[
        "roundtrip_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = {
        "required": True,
        "matches": True,
        **{field: complete_final_sha256 for field in complete_final_fields},
    }
    config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_33_target_application_lineage_comparison(vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    complete_check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{complete_check_prefix}_compatibility_broker_lineage_sha256_matches",
        f"{complete_check_prefix}_compatibility_roundtrip_final_review_carried_lineage_sha256_matches",
        f"{complete_check_prefix}_broker_readiness_complete_final_review_carried_lineage_sha256_matches",
    } <= failed
    readiness_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_final_lineage["broker_application_lineage_sha256"] == lineage_sha256
    assert readiness_final_lineage["carried_application_lineage_sha256"] == lineage_sha256
    assert readiness_final_lineage["broker_application_lineage_sha256"] != complete_final_sha256
    readiness_complete_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert (
        readiness_complete_final_lineage["broker_application_lineage_sha256"]
        == complete_final_sha256
    )
    assert (
        readiness_complete_final_lineage["carried_application_lineage_sha256"]
        == lineage_sha256
    )


def test_broker_readiness_blocks_roundtrip_final_lineage_drift_when_compatibility_matches():
    vendor = target_application_vendor_market_data_batch_config()
    compatibility_sha256 = vendor["application_lineage_sha256"]
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(
        vendor,
        current_application_lineage_sha256="f" * 64,
    )
    add_roundtrip_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert (
        "broker_dispatch_roundtrip_vendor_market_data_batch_final_source_lineage_sha256_matches"
        in failed
    )
    lineage = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert lineage["current_application_lineage_sha256"] == compatibility_sha256
    assert lineage["broker_application_lineage_sha256"] == compatibility_sha256
    assert lineage["roundtrip_carried_application_lineage_sha256"] == (
        compatibility_sha256
    )


def test_broker_readiness_blocks_final_target_lineage_drift_from_current_vendor_batch():
    vendor = target_application_vendor_market_data_batch_config()
    final_vendor = json.loads(json.dumps(vendor))
    final_vendor["datasets"][1]["mapping_application_id"] = "mapping-app-replaced"
    final_vendor["application_lineage_sha256"] = target_application_lineage_sha256(
        final_vendor["datasets"]
    )
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = final_vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(final_vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(final_vendor)
    add_roundtrip_complete_final_target_application_lineage(config, final_vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_name = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "matches_current_vendor_lineage"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    lineage_config = report.config["dispatch_roundtrip"][
        "vendor_market_data_batch_lineage_comparison"
    ]
    assert check_name in failed
    assert bool(summary["broker_vendor_market_data_batch_lineage_match_required"])
    assert not bool(summary["broker_vendor_market_data_batch_lineage_matches"])
    assert summary["vendor_market_data_batch_application_lineage_sha256"] != (
        summary["broker_vendor_market_data_batch_application_lineage_sha256"]
    )
    assert lineage_config["required"]
    assert not lineage_config["matches"]


def test_broker_readiness_carries_flattened_final_target_application_lineage_consistency():
    vendor = target_application_vendor_market_data_batch_config()
    summary_input = with_broker_vendor_batch_summary(
        dispatch_roundtrip_summary("arrow_money", True),
        vendor,
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=summary_input,
        dispatch_roundtrip_config=dispatch_roundtrip_config(),
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    field_prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    summary = report.summary.iloc[0]
    carried = report.config["dispatch_roundtrip"][field_prefix]
    assert bool(summary[f"{field_prefix}_application_lineage_consistency_required"])
    assert bool(summary[f"{field_prefix}_application_lineage_consistent"])
    assert carried["application_lineage_consistency_required"]
    assert carried["application_lineage_consistent"]
    assert carried["application_lineage_sha256"] == vendor["application_lineage_sha256"]
    assert carried["datasets"][0]["mapping_application_sha256"] == "1" * 64
    final_lineage = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert final_lineage["required"]
    assert final_lineage["matches"]
    assert final_lineage["readiness_carried_application_lineage_sha256"] == (
        vendor["application_lineage_sha256"]
    )
    readiness_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_final_lineage["required"]
    assert readiness_final_lineage["matches"]
    assert readiness_final_lineage[
        "roundtrip_final_review_carried_application_lineage_sha256"
    ] == vendor["application_lineage_sha256"]
    assert readiness_final_lineage["carried_application_lineage_sha256"] == vendor[
        "application_lineage_sha256"
    ]
    readiness_complete_final_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_complete_final_lineage["required"]
    assert readiness_complete_final_lineage["matches"]
    assert readiness_complete_final_lineage[
        "ack_complete_final_review_carried_application_lineage_sha256"
    ] == vendor["application_lineage_sha256"]
    assert readiness_complete_final_lineage[
        "roundtrip_complete_final_review_carried_application_lineage_sha256"
    ] == vendor["application_lineage_sha256"]
    assert readiness_complete_final_lineage[
        "carried_application_lineage_sha256"
    ] == vendor["application_lineage_sha256"]
    readiness_current_latest_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert readiness_current_latest_lineage["required"]
    assert readiness_current_latest_lineage["matches"]
    assert (
        readiness_current_latest_lineage[
            "roundtrip_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    assert (
        readiness_current_latest_lineage[
            "broker_readiness_current_latest_extended_complete_final_review_carried_application_lineage_sha256"
        ]
        == vendor["application_lineage_sha256"]
    )
    assert readiness_current_latest_lineage[
        "carried_application_lineage_sha256"
    ] == vendor["application_lineage_sha256"]
    readiness_reconciled_current_latest_lineage = report.config[
        "dispatch_roundtrip"
    ][
        "broker_readiness_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    expected_reconciled_current_latest_lineage = (
        broker_readiness_view_58_target_application_lineage_comparison(vendor)
    )
    assert len(readiness_reconciled_current_latest_lineage) == 57
    assert readiness_reconciled_current_latest_lineage == (
        expected_reconciled_current_latest_lineage
    )
    readiness_verified_reconciled_lineage = report.config["dispatch_roundtrip"][
        "broker_readiness_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert len(readiness_verified_reconciled_lineage) == 65
    assert readiness_verified_reconciled_lineage == (
        broker_readiness_view_66_target_application_lineage_comparison(vendor)
    )
    readiness_confirmed_verified_reconciled_lineage = report.config[
        "dispatch_roundtrip"
    ][
        "broker_readiness_confirmed_verified_reconciled_current_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert len(readiness_confirmed_verified_reconciled_lineage) == 73
    assert readiness_confirmed_verified_reconciled_lineage == (
        broker_readiness_view_74_target_application_lineage_comparison(vendor)
    )


def test_broker_readiness_blocks_inconsistent_final_target_application_lineage():
    vendor = target_application_vendor_market_data_batch_config(
        application_lineage_consistency_required=False,
        application_lineage_consistent=False,
    )
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_name = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "application_lineage_consistent"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    carried = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ]
    assert check_name in failed
    assert bool(
        summary[
            "broker_dispatch_roundtrip_vendor_market_data_batch_"
            "application_lineage_consistency_required"
        ]
    )
    assert not bool(
        summary[
            "broker_dispatch_roundtrip_vendor_market_data_batch_"
            "application_lineage_consistent"
        ]
    )
    assert carried["application_lineage_consistency_required"]
    assert not carried["application_lineage_consistent"]


def test_broker_readiness_requires_final_target_application_lineage_comparison():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert f"{prefix}_lineage_match_required" in failed
    assert f"{prefix}_lineage_matches" in failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


def test_broker_readiness_requires_roundtrip_final_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{prefix}_final_lineage_match_required",
        f"{prefix}_final_lineage_matches",
    } <= failed


def test_broker_readiness_requires_roundtrip_complete_final_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_readiness_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


def test_broker_readiness_requires_roundtrip_view_33_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_readiness_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


def test_broker_readiness_requires_roundtrip_view_41_lineage_for_reconciled_target():
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config.pop(
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    check_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_latest_extended_complete_final"
    )
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        f"{check_prefix}_lineage_match_required",
        f"{check_prefix}_lineage_matches",
    } <= failed
    comparison = report.config["dispatch_roundtrip"][
        "broker_readiness_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert not comparison["required"]
    assert not comparison["matches"]


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
            "broker_dispatch_roundtrip_vendor_market_data_batch_final_roundtrip_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_final_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )
    add_roundtrip_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final_source_lineage_sha256_matches",
        ),
        (
            "route_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final_route_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_complete_final_roundtrip_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_complete_final_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(
        config,
        vendor,
        **{field: value},
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "send_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_extended_complete_final_send_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_extended_complete_final_roundtrip_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_view_33_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config[
        "roundtrip_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_33_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


@pytest.mark.parametrize(
    ("field", "value", "expected_failed_check"),
    [
        (
            "required",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_latest_extended_complete_final_lineage_match_required",
        ),
        (
            "matches",
            False,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_latest_extended_complete_final_lineage_matches",
        ),
        (
            "current_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_latest_extended_complete_final_source_lineage_sha256_matches",
        ),
        (
            "roundtrip_extended_complete_final_review_carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_latest_extended_complete_final_roundtrip_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
        (
            "carried_application_lineage_sha256",
            "f" * 64,
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_latest_extended_complete_final_roundtrip_latest_extended_complete_final_review_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_roundtrip_view_41_lineage(
    field,
    value,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)
    config[
        "roundtrip_latest_extended_complete_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_view_41_target_application_lineage_comparison(
        vendor,
        **{field: value},
    )

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_readiness_recomputes_final_target_application_lineage():
    vendor = target_application_vendor_market_data_batch_config()
    tampered_vendor = json.loads(json.dumps(vendor))
    tampered_vendor["datasets"][1]["mapping_application_id"] = "mapping-app-tampered"
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = tampered_vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = tampered_vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    check_name = f"{prefix}_readiness_carried_lineage_sha256_matches"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert check_name in failed
    assert (
        f"{prefix}_broker_readiness_final_review_carried_lineage_sha256_matches"
        in failed
    )
    assert f"{prefix}_matches_current_vendor_lineage" in passed
    comparison = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ]
    assert comparison["readiness_carried_application_lineage_sha256"] == (
        target_application_lineage_sha256(tampered_vendor["datasets"])
    )
    assert comparison["readiness_carried_application_lineage_sha256"] != (
        comparison["broker_application_lineage_sha256"]
    )


@pytest.mark.parametrize(
    ("comparison_overrides", "expected_failed_check"),
    [
        (
            {"required": False},
            "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_match_required",
        ),
        (
            {"matches": False},
            "broker_dispatch_roundtrip_vendor_market_data_batch_lineage_matches",
        ),
        (
            {"current_application_lineage_sha256": "f" * 64},
            "broker_dispatch_roundtrip_vendor_market_data_batch_source_lineage_sha256_matches",
        ),
        (
            {"roundtrip_carried_application_lineage_sha256": "f" * 64},
            "broker_dispatch_roundtrip_vendor_market_data_batch_roundtrip_carried_lineage_sha256_matches",
        ),
    ],
)
def test_broker_readiness_blocks_invalid_final_target_lineage_decisions(
    comparison_overrides,
    expected_failed_check,
):
    vendor = target_application_vendor_market_data_batch_config()
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor
    config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(vendor, **comparison_overrides)
    config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(vendor)
    add_roundtrip_complete_final_target_application_lineage(config, vendor)

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert expected_failed_check in failed


def test_broker_readiness_keeps_generic_target_application_batch_compatible():
    vendor = target_application_vendor_market_data_batch_config()
    vendor.pop("application_lineage_consistency_required")
    vendor.pop("application_lineage_consistent")
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    check_name = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "application_lineage_consistent"
    )
    checks = set(report.checks["check"])
    carried = report.config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ]
    assert check_name not in checks
    extended_prefix = (
        "broker_dispatch_roundtrip_vendor_market_data_batch_"
        "roundtrip_extended_complete_final_"
    )
    assert not any(name.startswith(extended_prefix) for name in checks)
    assert not carried["application_lineage_consistency_required"]
    assert not carried["application_lineage_consistent"]


def test_broker_readiness_carries_roundtrip_broker_vendor_data_readiness():
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    summary = report.summary.iloc[0]
    wrapper = report.config["dispatch_roundtrip"]["broker_vendor_data_readiness"]
    assert bool(item["broker_vendor_data_readiness_provided"])
    assert bool(item["broker_vendor_data_readiness_ready"])
    assert int(item["broker_vendor_data_readiness_failed_checks"]) == 0
    assert bool(summary["broker_vendor_data_readiness_provided"])
    assert bool(summary["broker_vendor_data_readiness_ready"])
    assert int(summary["broker_vendor_data_readiness_failed_checks"]) == 0
    assert wrapper["provided"]
    assert wrapper["ready"]
    assert wrapper["failed_checks"] == 0


def test_broker_readiness_blocks_failed_roundtrip_broker_vendor_data_readiness():
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config(
        ready=False,
        failed_checks=1,
    )
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    wrapper = report.config["dispatch_roundtrip"]["broker_vendor_data_readiness"]
    vendor = report.config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert {
        "broker_vendor_data_readiness_ready",
        "broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert bool(summary["broker_vendor_data_readiness_provided"])
    assert not bool(summary["broker_vendor_data_readiness_ready"])
    assert int(summary["broker_vendor_data_readiness_failed_checks"]) == 1
    assert wrapper["provided"]
    assert not wrapper["ready"]
    assert wrapper["failed_checks"] == 1
    assert vendor["provided"]
    assert vendor["ready"]


def test_broker_readiness_carries_broker_vendor_market_data_batch_from_generic_roundtrip_proof():
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "vendor_market_data_batch_pipeline"
    )
    vendor = report.config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["comparison"]["accepted"]


def test_broker_readiness_blocks_wrong_manifest_generic_roundtrip_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    vendor["manifest_run_type"] = "not_vendor_batch"
    config = dispatch_roundtrip_config()
    config["roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    summary = report.summary.iloc[0]
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
        "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
    } <= failed
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"
    vendor = report.config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["manifest_run_type"] == "not_vendor_batch"


def test_broker_readiness_blocks_dirty_broker_dispatch_roundtrip_vendor_market_data_batch():
    vendor = vendor_market_data_batch_config()
    vendor.update(
        {
            "ready": False,
            "adapter": "irage",
            "market": "us_options_regular",
            "dataset_count": 0,
            "ready_datasets": 0,
            "failed_datasets": 1,
            "unique_source_files": 0,
            "source_file_fingerprint_coverage": 0.0,
            "min_mapping_coverage": 0.0,
            "unique_header_fingerprints": 0,
            "unique_mapping_drafts": 0,
            "mapping_sources": "",
            "comparison": {"accepted": False, "failed_checks": 1},
        }
    )
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
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
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed


def test_broker_readiness_prefers_broker_dispatch_roundtrip_vendor_market_data_batch():
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor_market_data_batch_config()
    config["broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "arrow_money"
    vendor = report.config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert vendor["ready"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["comparison"]["accepted"]


def test_broker_readiness_blocks_dirty_preferred_broker_dispatch_roundtrip_vendor_market_data_batch():
    config = dispatch_roundtrip_config()
    config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    config["broker_dispatch_roundtrip_vendor_market_data_batch"] = dirty_vendor_market_data_batch_config()

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("arrow_money", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
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
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed
    summary = report.summary.iloc[0]
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == "irage"
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets"]) == 1


def test_broker_readiness_blocks_dirty_dispatch_roundtrip_broker_shadow_broker_readiness():
    config = dispatch_roundtrip_config()
    config["broker_shadow_broker_readiness"] = shadow_broker_config(
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

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
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
    assert report.config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert int(summary["broker_shadow_broker_route_readiness_gap_pairs"]) == 2


def test_broker_readiness_blocks_partial_dispatch_roundtrip_broker_shadow_broker_vendor_data_readiness():
    config = dispatch_roundtrip_config()
    config["broker_shadow_broker_readiness"] = {
        "provided": True,
        **shadow_broker_config(
            broker_vendor_data_readiness_sessions=1,
            broker_vendor_data_readiness_provided_sessions=1,
            broker_vendor_data_readiness_ready_sessions=1,
        ),
    }

    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True),
        dispatch_roundtrip_config=config,
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
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
    assert report.config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"][
        "provided_sessions"
    ] == 1


def test_broker_readiness_fails_for_missing_route_dispatch_roundtrip_proof():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_provided=False,
            route_ready=False,
        ),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"route_dispatch_roundtrip_provided", "route_dispatch_roundtrip_ready"} <= failed
    assert not bool(report.summary.iloc[0]["route_dispatch_roundtrip_provided"])


def test_broker_readiness_fails_for_dirty_route_dispatch_roundtrip_proof():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_ready=False,
            route_target_mode="shadow",
            route_strategy="surface_mm",
            route_market="us_options_regular",
            route_scenario_key="wrong-scenario",
            route_requests=1,
            route_acked_orders=1,
            route_missing_request_acks=1,
            route_rejected_orders=1,
            route_unmatched_acks=1,
        ),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_dispatch_roundtrip_ready",
        "route_dispatch_roundtrip_target_mode_matches",
        "route_dispatch_roundtrip_strategy_matches",
        "route_dispatch_roundtrip_market_matches",
        "route_dispatch_roundtrip_scenario_matches",
        "route_dispatch_roundtrip_request_count_matches",
        "route_dispatch_roundtrip_missing_request_acks",
        "route_dispatch_roundtrip_rejected_orders",
        "route_dispatch_roundtrip_unmatched_acks",
    } <= failed
    assert int(report.summary.iloc[0]["route_dispatch_roundtrip_missing_request_acks"]) == 1


def test_broker_readiness_fails_for_dirty_route_readiness_proof():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_readiness_ready=False,
            route_readiness_strategy="surface_mm",
            route_readiness_market="us_options_regular",
            route_readiness_gap_pairs=2,
        ),
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_route_readiness=True,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_ready",
        "route_readiness_strategy_matches",
        "route_readiness_market_matches",
        "route_readiness_gap_pairs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["route_readiness_ready"])
    assert summary["route_readiness_strategy"] == "surface_mm"
    assert summary["route_readiness_market"] == "us_options_regular"
    assert int(summary["route_readiness_gap_pairs"]) == 2


def test_broker_readiness_fails_for_stale_route_readiness_ops_controls():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_readiness_ops_launch_controls_ready=False,
            route_readiness_ops_launch_control_failures=(
                "broker_roundtrip_portfolio_concentration_ok_runs;"
                "broker_roundtrip_portfolio_concentration_breach_runs"
            ),
            route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_route_readiness=True,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_ops_launch_controls_ready",
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs",
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs",
    } <= failed
    summary = report.summary.iloc[0]
    assert not bool(summary["route_readiness_ops_launch_controls_ready"])
    assert (
        "broker_roundtrip_portfolio_concentration_breach_runs"
        in summary["route_readiness_ops_launch_control_failures"]
    )
    assert int(summary["route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs"]) == 1
    assert not report.config["dispatch_roundtrip"]["route_readiness"]["ops_launch_controls_ready"]


def test_broker_readiness_fails_for_stale_final_route_ops_controls():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_readiness_ops_launch_controls_present=False,
            route_readiness_ops_launch_controls_blocked_pairs=1,
            route_readiness_ops_broker_roundtrip_portfolio_breach_pairs=1,
            route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
        ),
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_route_readiness=True,
            require_dispatch_roundtrip=True,
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
    route_proof = report.config["dispatch_roundtrip"]["route_readiness"]
    assert not route_proof["ops_launch_controls_present"]
    assert route_proof["ops_broker_roundtrip_portfolio_breach_pairs"] == 1
    assert route_proof["ops_broker_roundtrip_portfolio_concentration_breach_pairs"] == 1


def test_broker_readiness_fails_for_stale_route_broker_route_readiness_controls():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_broker_route_readiness_ops_launch_controls_ready=False,
            route_broker_route_readiness_ops_launch_control_failures=(
                "broker_roundtrip_portfolio_safe_runs;"
                "broker_roundtrip_portfolio_concentration_ok_runs"
            ),
            route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
            route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
            route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
            route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
        ),
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_route_readiness=True,
            require_dispatch_roundtrip=True,
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
    route_proof = report.config["dispatch_roundtrip"]["route_broker_route_readiness"]
    assert not route_proof["ops_launch_controls_ready"]
    assert route_proof["ops_broker_roundtrip_portfolio_safe_runs"] == 0
    assert route_proof["ops_broker_roundtrip_portfolio_concentration_breach_runs"] == 1


def test_broker_readiness_blocks_halted_runtime_session():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        runtime_session_summary=runtime_session_summary("normalized", ready=False, halted=True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_runtime_session=True),
    )

    assert not report.ready
    runtime_item = report.items.loc[report.items["component"] == "runtime_session"].iloc[0]
    assert bool(runtime_item["runtime_guard_halted"])
    summary = report.summary.iloc[0]
    assert bool(summary["runtime_session_provided"])
    assert not bool(summary["runtime_session_ready"])
    assert summary["runtime_guard_action"] == "halt"
    assert bool(summary["runtime_guard_halted"])
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_session_ready" in failed


def test_broker_readiness_fails_when_required_dispatch_roundtrip_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_roundtrip_provided" in failed


def test_broker_readiness_fails_for_failed_dispatch_roundtrip():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", False),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert not bool(item["ready"])
    assert int(item["dispatch_roundtrip_missing_request_acks"]) == 1
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_roundtrip_ready" in failed


def test_broker_readiness_fails_for_inconsistent_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary("normalized", True, failed_checks=1),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert not bool(item["ready"])
    assert int(report.summary.iloc[0]["dispatch_roundtrip_failed_checks"]) == 1
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "dispatch_roundtrip_ready" in failed


def test_broker_readiness_fails_for_route_enable_dispatch_roundtrip_failed_checks():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        dispatch_roundtrip_summary=dispatch_roundtrip_summary(
            "normalized",
            True,
            route_enable_dispatch_roundtrip_failed_checks=1,
        ),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_dispatch_roundtrip=True),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert int(item["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed


def test_broker_readiness_reads_dispatch_roundtrip_config_route_enable_failed_checks(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    dispatch_roundtrip_summary("normalized", True).to_csv(
        roundtrip_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(
            dispatch_roundtrip_config(route_enable_dispatch_roundtrip_failed_checks=1),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert int(item["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    assert int(report.summary.iloc[0]["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "route_enable_dispatch_roundtrip_failed_checks" in failed


def test_broker_readiness_reads_dispatch_roundtrip_config_route_readiness(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    dispatch_roundtrip_summary("normalized", True).to_csv(
        roundtrip_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(
            dispatch_roundtrip_config(
                route_readiness_ready=False,
                route_readiness_strategy="surface_mm",
                route_readiness_market="us_options_regular",
                route_readiness_gap_pairs=3,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_route_readiness=True,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    item = report.items.loc[report.items["component"] == "dispatch_roundtrip"].iloc[0]
    assert item["route_readiness_strategy"] == "surface_mm"
    assert int(item["route_readiness_gap_pairs"]) == 3
    summary = report.summary.iloc[0]
    assert not bool(summary["route_readiness_ready"])
    assert summary["route_readiness_market"] == "us_options_regular"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_ready",
        "route_readiness_strategy_matches",
        "route_readiness_market_matches",
        "route_readiness_gap_pairs",
    } <= failed


def test_broker_readiness_reads_dispatch_roundtrip_config_final_route_ops_controls(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    dispatch_roundtrip_summary("normalized", True).to_csv(
        roundtrip_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(
            dispatch_roundtrip_config(
                route_readiness_ops_launch_controls_present=False,
                route_readiness_ops_launch_controls_blocked_pairs=1,
                route_readiness_ops_broker_roundtrip_portfolio_breach_pairs=1,
                route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs=1,
                route_broker_route_readiness_ops_launch_controls_ready=False,
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs=0,
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs=1,
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs=0,
                route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs=1,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_route_readiness=True,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    summary = report.summary.iloc[0]
    assert not bool(summary["route_readiness_ops_launch_controls_present"])
    assert int(summary["route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) == 1
    assert not bool(summary["route_broker_route_readiness_ops_launch_controls_ready"])
    assert int(summary["route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 0
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "route_readiness_ops_launch_controls_present",
        "route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_pairs",
        "route_broker_route_readiness_ops_launch_controls_ready",
        "route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs",
    } <= failed
    route_proof = report.config["dispatch_roundtrip"]["route_readiness"]
    broker_route_proof = report.config["dispatch_roundtrip"]["route_broker_route_readiness"]
    assert route_proof["ops_launch_controls_blocked_pairs"] == 1
    assert broker_route_proof["ops_broker_roundtrip_portfolio_concentration_breach_runs"] == 1


def test_broker_readiness_fails_closed_for_placeholder_broker_schema():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        thresholds=BrokerReadinessThresholds(adapter="arrow_money"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "schema_reviewed" in failed
    assert not bool(report.summary.iloc[0]["schema_reviewed"])
    assert report.summary.iloc[0]["schema_review_mode"] == "placeholder_unreviewed"
    assert report.summary.iloc[0]["recommendation"] == "obtain_vendor_schema_samples"


def test_broker_readiness_carries_schema_review_checklist_counts():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        schema_review_checklist=schema_review_checklist(),
        order_export_summary=order_export_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
        ),
    )

    summary = report.summary.iloc[0]
    schema_item = report.items.loc[report.items["component"] == "schema_audit"].iloc[0]
    assert report.ready
    assert bool(summary["schema_review_checklist_present"])
    assert int(summary["schema_review_check_count"]) == 3
    assert int(summary["schema_review_blocked_checks"]) == 1
    assert int(summary["schema_review_review_checks"]) == 1
    assert summary["schema_review_blocked_check_names"] == "vendor_schema_reviewed"
    assert summary["schema_review_review_check_names"] == "extra_columns_classified"
    assert bool(schema_item["schema_review_checklist_present"])
    assert report.config["schema_review_checklist"] == {
        "provided": True,
        "check_count": 3,
        "blocked_checks": 1,
        "review_checks": 1,
        "blocked_check_names": ["vendor_schema_reviewed"],
        "review_check_names": ["extra_columns_classified"],
    }


def test_broker_readiness_accepts_reviewed_vendor_mapping_for_placeholder_adapter():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        mapping_draft_summary=mapping_draft_summary("arrow_money", True),
        mapped_order_summary=mapped_order_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        thresholds=BrokerReadinessThresholds(adapter="arrow_money"),
    )

    assert report.ready
    assert bool(report.summary.iloc[0]["schema_reviewed"])
    assert report.summary.iloc[0]["schema_review_mode"] == "reviewed_vendor_mapping"
    assert report.summary.iloc[0]["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert report.summary.iloc[0]["recommendation"] == "broker_integration_ready"
    assert set(report.checks["passed"]) == {True}


def test_broker_readiness_blocks_incomplete_reviewed_vendor_mapping():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        mapping_draft_summary=mapping_draft_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        thresholds=BrokerReadinessThresholds(adapter="arrow_money"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "schema_reviewed" in failed
    assert not bool(report.summary.iloc[0]["schema_reviewed"])
    assert report.summary.iloc[0]["schema_review_mode"] == "placeholder_unreviewed"


def test_broker_readiness_blocks_mixed_vendor_mapping_adapter():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("arrow_money", True),
        order_export_summary=order_export_summary("arrow_money", True),
        mapping_draft_summary=mapping_draft_summary("irage", True),
        mapped_order_summary=mapped_order_summary("arrow_money", True),
        upload_pack_summary=upload_summary("arrow_money", True),
        thresholds=BrokerReadinessThresholds(adapter="arrow_money"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"schema_reviewed", "mapping_draft_adapter_match"} <= failed
    assert not bool(report.summary.iloc[0]["schema_reviewed"])
    assert report.summary.iloc[0]["schema_review_mode"] == "placeholder_unreviewed"


def test_broker_readiness_fails_when_required_upload_pack_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized"),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "upload_pack_provided" in failed


def test_broker_readiness_fails_when_required_runtime_session_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_runtime_session=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "runtime_session_provided" in failed


def test_broker_readiness_fails_when_required_resume_gate_is_missing():
    report = evaluate_broker_readiness(
        schema_audit_summary=schema_summary("normalized", True),
        order_export_summary=order_export_summary("normalized", True),
        upload_pack_summary=upload_summary("normalized", True),
        thresholds=BrokerReadinessThresholds(adapter="normalized", require_resume_gate=True),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "resume_gate_provided" in failed


def test_write_broker_readiness_outputs_artifacts(tmp_path):
    schema_dir, export_dir, upload_dir, roundtrip_dir = (
        write_broker_readiness_input_dirs(
            tmp_path,
            "arrow_money",
            verified_roundtrip=True,
            canonical_leadlag=True,
        )
    )
    resume_dir = tmp_path / "resume"
    out_dir = tmp_path / "readiness"
    resume_dir.mkdir()
    schema_review_checklist().to_csv(schema_dir / "adapter_schema_review_checklist.csv", index=False)
    resume_summary("arrow_money", True).to_csv(resume_dir / "resume_summary.csv", index=False)
    roundtrip_config_path = roundtrip_dir / "broker_dispatch_roundtrip_config.json"
    roundtrip_config = json.loads(roundtrip_config_path.read_text(encoding="utf-8"))
    roundtrip_config["shadow_broker_readiness"] = shadow_broker_config(adapter="arrow_money")
    roundtrip_config["broker_shadow_broker_readiness"] = shadow_broker_config(adapter="arrow_money")
    roundtrip_config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    roundtrip_config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = (
        vendor_market_data_batch_config()
    )
    roundtrip_config["roundtrip_broker_vendor_data_readiness"] = broker_vendor_data_readiness_config()
    roundtrip_config_path.write_text(
        json.dumps(roundtrip_config, indent=2) + "\n",
        encoding="utf-8",
    )
    refresh_dispatch_manifest(roundtrip_dir / "manifest.json")

    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.PerformanceWarning)
        report = write_broker_readiness_report(
            output_dir=out_dir,
            schema_audit_dir=schema_dir,
            order_export_dir=export_dir,
            upload_pack_dir=upload_dir,
            resume_dir=resume_dir,
            dispatch_roundtrip_dir=roundtrip_dir,
            thresholds=BrokerReadinessThresholds(
                adapter="arrow_money",
                require_reviewed_schema=False,
                require_resume_gate=True,
                require_dispatch_roundtrip=True,
            ),
        )

    assert report.ready
    assert report.output_dir == out_dir
    assert report.summary.iloc[0]["recommendation"] == "dry_run_only_until_vendor_schema_review"
    assert report.summary.iloc[0]["resume_strategy"] == "surface_mm"
    assert bool(report.summary.iloc[0]["schema_review_checklist_present"])
    assert int(report.summary.iloc[0]["schema_review_blocked_checks"]) == 1
    assert report.summary.iloc[0]["schema_review_blocked_check_names"] == "vendor_schema_reviewed"
    assert bool(report.summary.iloc[0]["resume_gate_ready"])
    assert bool(report.summary.iloc[0]["dispatch_roundtrip_ready"])
    assert bool(report.summary.iloc[0]["broker_dispatch_roundtrip_lineage_required"])
    assert bool(report.summary.iloc[0]["broker_dispatch_roundtrip_manifest_current"])
    assert bool(report.summary.iloc[0]["broker_dispatch_roundtrip_lineage_contract_consistent"])
    assert bool(report.summary.iloc[0]["broker_dispatch_roundtrip_lineage_gate_passed"])
    assert bool(
        report.summary.iloc[0][
            "broker_dispatch_roundtrip_strategy_portfolio_"
            "leadlag_edge_lineage_required"
        ]
    )
    assert report.summary.iloc[0][
        "broker_dispatch_roundtrip_strategy_portfolio_"
        "leadlag_edge_lineage_contract_sha256"
    ] == "c" * 64
    assert bool(
        report.summary.iloc[0][
            "broker_dispatch_roundtrip_strategy_portfolio_"
            "leadlag_ack_contract_consistent"
        ]
    )
    assert (out_dir / "broker_readiness_items.csv").exists()
    assert (out_dir / "broker_readiness_checks.csv").exists()
    assert (out_dir / "broker_readiness_summary.csv").exists()
    assert (out_dir / "broker_readiness_action_queue.csv").exists()
    assert (out_dir / "broker_readiness_config.json").exists()
    assert (out_dir / "broker_readiness_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "broker_readiness_action_queue.csv")
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    runbook = (out_dir / "broker_readiness_runbook.md").read_text(encoding="utf-8")
    assert "# Broker Readiness Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "- Terminal round-trip source binding passed: yes" in runbook
    assert "dry_run_only_until_vendor_schema_review" in runbook
    assert "## Components" in runbook
    assert "## Blocked Actions" in runbook
    config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
    assert config == report.config
    assert config["ready"]
    assert config["adapter"] == "arrow_money"
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert config["schema_review_checklist"]["provided"]
    assert config["schema_review_checklist"]["blocked_check_names"] == ["vendor_schema_reviewed"]
    assert config["schema_review_checklist"]["review_check_names"] == ["extra_columns_classified"]
    assert config["components"]["dispatch_roundtrip"]["ready"]
    assert config["dispatch_roundtrip"]["lineage"]["lineage_required"]
    assert config["dispatch_roundtrip"]["lineage"]["manifest_current"]
    assert config["dispatch_roundtrip"]["lineage"]["lineage_gate_passed"]
    assert config["dispatch_roundtrip"]["lineage"][
        "strategy_portfolio_leadlag_edge_lineage_contract_sha256"
    ] == "c" * 64
    assert config["dispatch_roundtrip"]["lineage"][
        "strategy_portfolio_leadlag_ack_contract_consistent"
    ]
    assert config["resume_gate"]["proof_refresh"]["strategy"] == "surface_mm"
    assert config["dispatch_roundtrip"]["route_readiness"]["gap_pairs"] == 0
    assert config["dispatch_roundtrip"]["route_readiness"]["ops_launch_controls_present"]
    assert config["dispatch_roundtrip"]["route_readiness"]["ops_broker_roundtrip_portfolio_breach_pairs"] == 0
    assert config["dispatch_roundtrip"]["route_broker_route_readiness"]["ops_launch_controls_ready"]
    assert config["dispatch_roundtrip"]["route_broker_route_readiness"][
        "ops_broker_roundtrip_portfolio_concentration_ok_runs"
    ] == 1
    assert config["dispatch_roundtrip"]["route_dispatch_roundtrip"]["batch_id"] == "BDP-0"
    assert config["dispatch_roundtrip"]["vendor_market_data_batch"]["adapter"] == "arrow_money"
    assert config["dispatch_roundtrip"]["vendor_market_data_batch"]["dataset_count"] == 2
    assert config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]["adapter"] == (
        "arrow_money"
    )
    assert config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]["dataset_count"] == 2
    assert config["dispatch_roundtrip"]["broker_vendor_data_readiness"]["provided"]
    assert config["dispatch_roundtrip"]["broker_vendor_data_readiness"]["ready"]
    assert config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert config["shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert config["shadow_broker_readiness"]["dispatch_roundtrip"]["scenario_count"] == 1
    assert config["broker_shadow_broker_readiness"]["provided"]
    assert config["broker_shadow_broker_readiness"]["broker_vendor_data_readiness"]["ready_sessions"] == 2
    assert config["broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["sessions"] == 2
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(manifest["inputs"]["dispatch_roundtrip"]["path"]).endswith(
        "/roundtrip/broker_dispatch_roundtrip_summary.csv"
    )
    assert path_tail(manifest["inputs"]["dispatch_roundtrip_config"]["path"]).endswith(
        "/roundtrip/broker_dispatch_roundtrip_config.json"
    )
    assert path_tail(manifest["inputs"]["dispatch_roundtrip_manifest"]["path"]).endswith(
        "/roundtrip/manifest.json"
    )
    assert len(manifest["inputs"]["broker_dispatch_roundtrip_artifacts"]) == 6
    assert manifest["inputs"]["broker_dispatch_roundtrip_dependencies"]
    assert manifest["extra"]["broker_dispatch_roundtrip_lineage_gate_passed"]
    assert manifest["extra"][
        "broker_dispatch_roundtrip_strategy_portfolio_"
        "leadlag_edge_lineage_contract_sha256"
    ] == "c" * 64
    assert path_tail(manifest["inputs"]["schema_review_checklist"]["path"]).endswith(
        "/schema/adapter_schema_review_checklist.csv"
    )
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "broker_readiness_action_queue.csv" in artifact_paths
    assert "broker_readiness_runbook.md" in artifact_paths
    lineage = load_broker_readiness_lineage(
        out_dir / "broker_readiness_config.json"
    )
    assert lineage["manifest_current"]
    assert lineage["contract_consistent"], lineage["contract_error"]
    assert lineage["roundtrip_lineage_gate_passed"]
    assert lineage["roundtrip_matches_current"]
    assert lineage["gate_passed"]


def test_broker_readiness_blocks_remanifested_terminal_roundtrip_tamper(
    tmp_path,
):
    schema_dir, export_dir, upload_dir, roundtrip_dir = (
        write_broker_readiness_input_dirs(
            tmp_path,
            "arrow_money",
            verified_roundtrip=True,
        )
    )
    orders_path = roundtrip_dir / "broker_dispatch_roundtrip_orders.csv"
    orders = pd.read_csv(orders_path)
    orders.loc[0, "broker_dispatch_ack_lineage_required"] = False
    orders.to_csv(orders_path, index=False)
    refresh_dispatch_manifest(roundtrip_dir / "manifest.json")
    out_dir = tmp_path / "readiness"

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["broker_dispatch_roundtrip_manifest_current"])
    assert not bool(
        summary["broker_dispatch_roundtrip_lineage_contract_consistent"]
    )
    assert not bool(summary["broker_dispatch_roundtrip_lineage_gate_passed"])
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert {
        "dispatch_roundtrip_lineage_contract_consistent",
        "dispatch_roundtrip_lineage_gate_passed",
    } <= failed
    action = report.action_queue.loc[
        report.action_queue["check"].eq(
            "dispatch_roundtrip_lineage_contract_consistent"
        )
    ].iloc[0]
    assert action["component"] == "dispatch_roundtrip"
    assert action["next_gate"] == "review-broker-dispatch-roundtrip"
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["inputs"]["broker_dispatch_roundtrip_dependencies"]
    assert not manifest["extra"][
        "broker_dispatch_roundtrip_lineage_gate_passed"
    ]


def test_broker_readiness_rejects_loose_roundtrip_summary_and_config(
    tmp_path,
):
    schema_dir, export_dir, upload_dir, roundtrip_dir = (
        write_broker_readiness_input_dirs(tmp_path, "arrow_money")
    )

    report = write_broker_readiness_report(
        output_dir=tmp_path / "readiness",
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["broker_dispatch_roundtrip_lineage_required"])
    assert bool(summary["broker_dispatch_roundtrip_lineage_provided"])
    assert not bool(summary["broker_dispatch_roundtrip_manifest_current"])
    assert not bool(summary["broker_dispatch_roundtrip_lineage_gate_passed"])
    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert {
        "dispatch_roundtrip_lineage_manifest_current",
        "dispatch_roundtrip_lineage_gate_passed",
    } <= failed


def test_broker_readiness_reads_vendor_market_data_batch_artifact(tmp_path):
    for adapter in ("arrow_money", "irage"):
        root = tmp_path / adapter
        schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(
            root,
            adapter,
            verified_roundtrip=True,
        )
        vendor_batch_dir = write_vendor_market_data_batch(root, adapter)
        out_dir = root / "readiness"

        report = write_broker_readiness_report(
            output_dir=out_dir,
            schema_audit_dir=schema_dir,
            order_export_dir=export_dir,
            upload_pack_dir=upload_dir,
            dispatch_roundtrip_dir=roundtrip_dir,
            vendor_market_data_batch_dir=vendor_batch_dir,
            thresholds=BrokerReadinessThresholds(
                adapter=adapter,
                require_reviewed_schema=False,
                require_dispatch_roundtrip=True,
            ),
        )

        assert report.ready
        summary = report.summary.iloc[0]
        assert bool(summary["dispatch_roundtrip_vendor_market_data_batch_ready"])
        assert bool(summary["broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
        assert summary["dispatch_roundtrip_vendor_market_data_batch_adapter"] == adapter
        assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_adapter"] == adapter
        assert int(summary["dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
        assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
        config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
        generic_vendor = config["dispatch_roundtrip"]["vendor_market_data_batch"]
        broker_vendor = config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]
        assert generic_vendor["adapter"] == adapter
        assert broker_vendor["adapter"] == adapter
        assert generic_vendor["comparison"]["accepted"]
        assert broker_vendor["dataset_count"] == 2
        assert broker_vendor["datasets"][0]["data_readiness_manifest_path"].endswith("manifest.json")
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert path_tail(manifest["inputs"]["vendor_market_data_batch_config"]["path"]).endswith(
            "/vendor_batch/vendor_market_data_batch_config.json"
        )
        assert path_tail(manifest["inputs"]["vendor_market_data_batch_manifest"]["path"]).endswith(
            "/vendor_batch/manifest.json"
        )


def test_broker_readiness_preserves_stronger_roundtrip_vendor_proof_with_vendor_artifact(
    tmp_path,
):
    schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(
        tmp_path,
        "arrow_money",
        verified_roundtrip=True,
    )
    roundtrip_config_path = roundtrip_dir / "broker_dispatch_roundtrip_config.json"
    roundtrip_config = json.loads(roundtrip_config_path.read_text(encoding="utf-8"))
    final_vendor = vendor_market_data_batch_config()
    final_vendor["mapping_sources"] = "final_roundtrip_mapping"
    roundtrip_config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = final_vendor
    roundtrip_config_path.write_text(
        json.dumps(roundtrip_config, indent=2) + "\n",
        encoding="utf-8",
    )
    refresh_dispatch_manifest(roundtrip_dir / "manifest.json")
    vendor_batch_dir = write_vendor_market_data_batch(tmp_path, "arrow_money")
    out_dir = tmp_path / "readiness"

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_dir,
        vendor_market_data_batch_dir=vendor_batch_dir,
        thresholds=BrokerReadinessThresholds(
            adapter="arrow_money",
            require_reviewed_schema=False,
            require_dispatch_roundtrip=True,
        ),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    config = report.config["dispatch_roundtrip"]
    assert summary["dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
        "vendor_intake_draft"
    )
    assert summary[
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"
    ] == "final_roundtrip_mapping"
    assert config["vendor_market_data_batch"]["mapping_sources"] == "vendor_intake_draft"
    assert config["broker_dispatch_roundtrip_vendor_market_data_batch"][
        "mapping_sources"
    ] == "final_roundtrip_mapping"


def test_cli_broker_readiness_accepts_vendor_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(
        tmp_path,
        "arrow_money",
        verified_roundtrip=True,
    )
    vendor_batch_dir = write_vendor_market_data_batch(tmp_path, "arrow_money")
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--dispatch-roundtrip",
            str(roundtrip_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]["adapter"] == (
        "arrow_money"
    )


def test_cli_broker_readiness_accepts_vendor_only_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, _roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
    vendor_batch_dir = write_vendor_market_data_batch(tmp_path, "arrow_money")
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--expected-market",
            "india_nse_index_derivatives",
            "--expected-vendor-data-kind",
            "ticks",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert bool(summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert "dispatch_roundtrip_ready" not in set(checks["check"])
    assert config["dispatch_roundtrip"]["vendor_market_data_batch"]["adapter"] == "arrow_money"
    assert config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]["dataset_count"] == 2


def test_cli_broker_readiness_blocks_failed_broker_vendor_data_readiness_root(tmp_path):
    schema_dir, export_dir, upload_dir, _roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
    vendor_batch_dir = write_broker_vendor_data_proof(tmp_path / "broker_vendor_data")
    (vendor_batch_dir / "broker_vendor_data_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": False,
                "adapter": "arrow_money",
                "failed_check_count": 1,
                "failed_checks": ["unique_source_files"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--expected-market",
            "india_nse_index_derivatives",
            "--expected-vendor-data-kind",
            "ticks",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_ready"])
    assert {
        "broker_vendor_data_readiness_ready",
        "broker_vendor_data_readiness_failed_checks",
    } <= failed
    assert config["dispatch_roundtrip"]["broker_vendor_data_readiness"]["provided"]
    assert not config["dispatch_roundtrip"]["broker_vendor_data_readiness"]["ready"]
    assert config["dispatch_roundtrip"]["broker_vendor_data_readiness"]["failed_checks"] == 1
    assert path_tail(manifest["inputs"]["broker_vendor_data_readiness_config"]["path"]).endswith(
        "/broker_vendor_data/broker_vendor_data_readiness_config.json"
    )


def test_cli_broker_readiness_blocks_wrong_kind_vendor_only_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, _roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
    vendor_batch_dir = write_broker_vendor_data_proof(tmp_path / "broker_vendor_data", kind="chain")
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--expected-market",
            "india_nse_index_derivatives",
            "--expected-vendor-data-kind",
            "ticks",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "dispatch_roundtrip_ready" not in failed
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_kind_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_kind_matches",
    } <= failed
    assert summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_kind"] == "chain"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_kind"] == "chain"


def test_cli_broker_readiness_blocks_wrong_manifest_vendor_only_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, _roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
    vendor_batch_dir = write_broker_vendor_data_proof(
        tmp_path / "broker_vendor_data",
        manifest_run_type="not_vendor_batch",
    )
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--expected-market",
            "india_nse_index_derivatives",
            "--expected-vendor-data-kind",
            "ticks",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "dispatch_roundtrip_ready" not in failed
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
        "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type",
    } <= failed
    assert summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == "not_vendor_batch"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_manifest_run_type"] == (
        "not_vendor_batch"
    )


def test_cli_broker_readiness_blocks_wrong_market_vendor_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(
        tmp_path,
        "arrow_money",
        verified_roundtrip=True,
    )
    vendor_batch_dir = write_vendor_market_data_batch(tmp_path, "arrow_money", market="us_options_regular")
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--expected-market",
            "india_nse_index_derivatives",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--dispatch-roundtrip",
            str(roundtrip_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
    } <= failed
    assert summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_market"] == "us_options_regular"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_market"] == "us_options_regular"


def test_cli_broker_readiness_blocks_wrong_market_vendor_only_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, _roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
    vendor_batch_dir = write_vendor_market_data_batch(tmp_path, "arrow_money", market="us_options_regular")
    out_dir = tmp_path / "readiness"

    code = main(
        [
            "review-broker-readiness",
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--expected-market",
            "india_nse_index_derivatives",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--vendor-market-data-batch",
            str(vendor_batch_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "dispatch_roundtrip_ready" not in failed
    assert {
        "dispatch_roundtrip_vendor_market_data_batch_market_matches",
        "broker_dispatch_roundtrip_vendor_market_data_batch_market_matches",
    } <= failed
    assert summary.loc[0, "dispatch_roundtrip_vendor_market_data_batch_market"] == "us_options_regular"
    assert summary.loc[0, "broker_dispatch_roundtrip_vendor_market_data_batch_market"] == "us_options_regular"


def test_broker_readiness_reads_roundtrip_config_next_to_summary_file(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    roundtrip_summary_path = roundtrip_dir / "broker_dispatch_roundtrip_summary.csv"
    dispatch_roundtrip_summary("normalized", True).to_csv(roundtrip_summary_path, index=False)
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(dispatch_roundtrip_config(route_enable_dispatch_roundtrip_failed_checks=1), indent=2) + "\n",
        encoding="utf-8",
    )

    report = write_broker_readiness_report(
        output_dir=out_dir,
        schema_audit_dir=schema_dir,
        order_export_dir=export_dir,
        upload_pack_dir=upload_dir,
        dispatch_roundtrip_dir=roundtrip_summary_path,
        thresholds=BrokerReadinessThresholds(
            adapter="normalized",
            require_dispatch_roundtrip=True,
        ),
    )

    assert not report.ready
    summary = report.summary.iloc[0]
    assert int(summary["route_enable_dispatch_roundtrip_failed_checks"]) == 1
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert path_tail(manifest["inputs"]["dispatch_roundtrip"]["path"]).endswith(
        "/roundtrip/broker_dispatch_roundtrip_summary.csv"
    )
    assert path_tail(manifest["inputs"]["dispatch_roundtrip_config"]["path"]).endswith(
        "/roundtrip/broker_dispatch_roundtrip_config.json"
    )


def test_cli_broker_readiness_can_fail_on_placeholder_schema(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    blocked_dir = tmp_path / "readiness_blocked"
    actions_dir = tmp_path / "readiness_actions"
    schema_dir.mkdir()
    export_dir.mkdir()
    upload_dir.mkdir()
    schema_summary("arrow_money", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("arrow_money", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("arrow_money", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "arrow_money",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    action_queue = pd.read_csv(out_dir / "broker_readiness_action_queue.csv")
    runbook = (out_dir / "broker_readiness_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "schema_reviewed" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == len(action_queue)
    assert config["next_gate"] == action_queue.loc[0, "next_gate"]
    assert config["next_gate_help_command"] == action_queue.loc[0, "next_gate_help_command"]
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "schema_reviewed"
    assert config["primary_action"]["component"] == "schema_audit"
    assert config["primary_action"]["next_gate"] == "audit-adapter-schema"
    assert config["ready_actions"] == []
    assert {item["check"] for item in config["next_actions"]} == set(action_queue["check"])
    assert {item["check"] for item in config["blocked_actions"]} == set(action_queue["check"])
    assert action_queue.loc[0, "check"] == "schema_reviewed"
    assert action_queue.loc[0, "component"] == "schema_audit"
    assert action_queue.loc[0, "next_gate"] == "audit-adapter-schema"
    assert action_queue.loc[0, "next_gate_help_command"] == "python -m hft_cli audit-adapter-schema --help"
    assert "- Ready: no" in runbook
    assert "audit-adapter-schema" in runbook

    blocked_code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "arrow_money",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(blocked_dir),
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "arrow_money",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(actions_dir),
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


def test_cli_broker_readiness_accepts_reviewed_vendor_mapping_without_placeholder_override(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    mapping_dir = tmp_path / "mapping"
    mapped_dir = tmp_path / "mapped"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, mapping_dir, mapped_dir, upload_dir):
        path.mkdir()
    schema_summary("arrow_money", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("arrow_money", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    mapping_draft_summary("arrow_money", True).to_csv(mapping_dir / "order_mapping_draft_summary.csv", index=False)
    mapped_order_summary("arrow_money", True).to_csv(mapped_dir / "mapped_order_summary.csv", index=False)
    upload_summary("arrow_money", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "arrow_money",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--mapping-draft",
            str(mapping_dir),
            "--mapped-orders",
            str(mapped_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-mapping-draft",
            "--require-mapped-orders",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "schema_reviewed"])
    assert summary.loc[0, "schema_review_mode"] == "reviewed_vendor_mapping"
    assert summary.loc[0, "recommendation"] == "broker_integration_ready"
    assert set(checks["passed"]) == {True}


def test_cli_broker_readiness_reads_launch_pipeline_export_and_upload_roots(tmp_path):
    cases = [
        ("leadlag", "04_export", "05_upload_pack"),
        ("imbalance", "04_export", "05_upload_pack"),
        ("parity", "04_export", "05_upload_pack"),
        ("surface_mm", "03_export", "04_upload_pack"),
    ]
    for family, export_folder, upload_folder in cases:
        case_dir = tmp_path / family
        schema_dir = case_dir / "schema"
        pipeline = case_dir / f"{family}_launch_pipeline"
        export_dir = pipeline / export_folder
        upload_dir = pipeline / upload_folder
        out_dir = case_dir / "readiness"
        schema_dir.mkdir(parents=True)
        export_dir.mkdir(parents=True)
        upload_dir.mkdir(parents=True)
        schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
        order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
        upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

        code = main(
            [
                "review-broker-readiness",
                "--adapter",
                "normalized",
                "--schema-audit",
                str(schema_dir),
                "--order-export",
                str(pipeline),
                "--upload-pack",
                str(pipeline),
                "--out",
                str(out_dir),
                "--fail-on-breach",
            ]
        )

        summary = pd.read_csv(out_dir / "broker_readiness_summary.csv")
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert code == 0
        assert bool(summary.loc[0, "ready"])
        assert path_tail(manifest["inputs"]["order_export"]["path"]).endswith(
            f"/{family}_launch_pipeline/{export_folder}/broker_order_summary.csv"
        )
        assert path_tail(manifest["inputs"]["upload_pack"]["path"]).endswith(
            f"/{family}_launch_pipeline/{upload_folder}/broker_upload_summary.csv"
        )


def test_cli_broker_readiness_can_require_runtime_session(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-runtime-session",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "runtime_session_provided" in failed


def test_cli_broker_readiness_can_require_resume_gate(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-resume-gate",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "resume_gate_provided" in failed


def test_cli_broker_readiness_can_require_dispatch_roundtrip(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--out",
            str(out_dir),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert "dispatch_roundtrip_provided" in failed


def test_cli_broker_readiness_can_require_route_readiness(tmp_path):
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir()
    schema_summary("normalized", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("normalized", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("normalized", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    dispatch_roundtrip_summary(
        "normalized",
        True,
        route_readiness_provided=False,
        route_readiness_ready=False,
    ).to_csv(roundtrip_dir / "broker_dispatch_roundtrip_summary.csv", index=False)

    code = main(
        [
            "review-broker-readiness",
            "--adapter",
            "normalized",
            "--schema-audit",
            str(schema_dir),
            "--order-export",
            str(export_dir),
            "--upload-pack",
            str(upload_dir),
            "--dispatch-roundtrip",
            str(roundtrip_dir),
            "--out",
            str(out_dir),
            "--require-route-readiness",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(out_dir / "broker_readiness_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert {"route_readiness_provided", "route_readiness_ready"} <= failed
