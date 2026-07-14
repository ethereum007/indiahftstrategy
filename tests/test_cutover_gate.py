import json

import pandas as pd
import pytest

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.cutover import CutoverGateThresholds, evaluate_cutover_gate, write_cutover_gate_report
from reports.manifest import file_sha256, verify_experiment_manifest, write_experiment_manifest
from reports.runtime_guard import RUNTIME_LINEAGE_COLUMNS, SCALEUP_PROVENANCE_COLUMNS


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
    return config


def with_scaleup_broker_vendor_batch_summary(summary, vendor):
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
    if strategy_portfolio:
        row.update(
            {
                "strategy_portfolio_required": True,
                "strategy_portfolio_provided": True,
                "strategy_portfolio_ready": portfolio_ready,
                "strategy_portfolio_deployment_mode": "paper_shadow",
                "strategy_portfolio_allocation_mode": "readiness_weighted",
                "strategy_portfolio_capital_currency": "INR",
                "strategy_portfolio_selected_profile": "leadlag-live-dryrun",
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


def write_inputs(root, *, target_mode="live_dryrun", operator=True, dispatch=True):
    scaleup = root / "scaleup"
    broker = root / "broker"
    runtime = root / "runtime"
    scaleup.mkdir(parents=True)
    broker.mkdir()
    runtime.mkdir()
    scaleup_summary(target_mode=target_mode, dispatch_provided=dispatch, dispatch_ready=dispatch).to_csv(
        scaleup / "scaleup_summary.csv",
        index=False,
    )
    scaleup_checks().to_csv(scaleup / "scaleup_checks.csv", index=False)
    (scaleup / "scaleup_config.json").write_text(
        json.dumps(
            scaleup_config(target_mode=target_mode, dispatch_provided=dispatch, dispatch_ready=dispatch),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    pd.DataFrame([{"ready": True, "target_mode": target_mode}]).to_csv(
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
    runtime_summary = runtime_session_summary(target_mode=target_mode)
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
            **lineage,
            "authorizes_submission": False,
        },
    )
    review_path = root / "operator_review.csv"
    if operator:
        operator_review().to_csv(review_path, index=False)
    return scaleup, broker, runtime, review_path


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
    config["broker_readiness"]["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = target_application_vendor_market_data_batch_config()

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
    summary_datasets = json.loads(summary[f"{prefix}_datasets_json"])
    assert summary_datasets[0]["mapping_application_id"] == "mapping-app-day1"
    assert summary_datasets[1]["applied_mapping_sha256"] == "3" * 64
    vendor = report.config[prefix]
    assert vendor["mapping_source_mode"] == "per_dataset_verified_target_application"
    assert vendor["mapping_application_count"] == 2
    assert vendor["unique_mapping_applications"] == 2
    assert vendor["target_application_coverage"] == 1.0
    assert vendor["datasets"][0]["mapping_application_id"] == "mapping-app-day1"
    assert vendor["datasets"][1]["target_intake_receipt_id"] == "target-intake-day2"
    expected_checks = {
        f"{prefix}_mapping_source_mode",
        f"{prefix}_mapping_application_count",
        f"{prefix}_unique_mapping_applications",
        f"{prefix}_target_application_coverage",
        f"{prefix}_application_lineage_datasets",
    }
    passed = set(report.checks.loc[report.checks["passed"].astype(bool), "check"])
    assert expected_checks <= passed


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
    scaleup, broker, runtime, review_path = write_inputs(tmp_path)
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
    assert (out_dir / "cutover_runbook.md").read_text(encoding="utf-8").startswith("# Cutover Gate Runbook")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {item["path"] for item in manifest["artifacts"]}
    assert "cutover_action_queue.csv" in artifact_paths
    assert "cutover_runbook.md" in artifact_paths
    assert {
        "scaleup_summary",
        "scaleup_config",
        "scaleup_checks",
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
    assert report.summary.iloc[0]["runtime_scaleup_manifest_sha256"] == file_sha256(
        scaleup / "manifest.json"
    )
    assert not bool(report.summary.iloc[0]["authorizes_submission"])
    assert report.config["runtime_lineage"]["runtime_lineage_gate_passed"]
    assert not report.config["authorizes_submission"]
    assert {
        "runtime_session_manifest",
        "runtime_session_artifacts",
        "runtime_session_dependencies",
    } <= set(manifest["inputs"])
    assert manifest["extra"]["runtime_lineage_gate_passed"]
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
    assert {"runtime_session_manifest_current", "runtime_lineage_gate_passed"} <= failed
    assert report.action_queue.iloc[0]["next_gate"] == "monitor-runtime-session"


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


def test_cli_cutover_gate_hydrates_broker_vendor_data_from_sidecar(tmp_path):
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
                    "broker_dispatch_roundtrip_vendor_market_data_batch": (
                        target_application_vendor_market_data_batch_config()
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
    config = json.loads((out_dir / "cutover_config.json").read_text(encoding="utf-8"))
    vendor = config["scaleup_broker_dispatch_roundtrip_vendor_market_data_batch"]
    assert code == 0
    assert bool(summary.loc[0, "ready"])
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
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["unique_mapping_drafts"] == 1
    assert vendor["mapping_source_mode"] == "per_dataset_verified_target_application"
    assert vendor["mapping_application_count"] == 2
    assert vendor["unique_mapping_applications"] == 2
    assert vendor["target_application_coverage"] == 1.0
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64
    assert vendor["datasets"][1]["mapping_application_id"] == "mapping-app-day2"


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
