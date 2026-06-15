import json

import pandas as pd

from hft_cli import main
from reports.scaleup import ScaleUpThresholds, evaluate_scaleup_plan, write_scaleup_plan


def path_tail(value):
    return str(value).replace("\\", "/")


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
    shadow_broker_readiness_provided=False,
    shadow_broker_readiness_sessions=0,
    shadow_broker_readiness_ready_sessions=None,
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
    dispatch_roundtrip_vendor_market_data_batch_market="",
    dispatch_roundtrip_vendor_market_data_batch_dataset_count=0,
    dispatch_roundtrip_vendor_market_data_batch_ready_datasets=0,
    dispatch_roundtrip_vendor_market_data_batch_failed_datasets=0,
    dispatch_roundtrip_vendor_market_data_batch_ready_rate=0.0,
    dispatch_roundtrip_vendor_market_data_batch_unique_source_files=0,
    dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints=0,
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
                "shadow_broker_readiness_provided": shadow_broker_readiness_provided,
                "shadow_broker_readiness_sessions": shadow_broker_readiness_sessions,
                "shadow_broker_readiness_ready_sessions": shadow_broker_readiness_ready_sessions,
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


def with_broker_dispatch_roundtrip_vendor_batch(summary, **overrides):
    values = {
        "provided": True,
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
        "mapping_sources": "vendor_intake_draft",
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
    prefix = "broker_dispatch_roundtrip_vendor_market_data_batch"
    for suffix, value in values.items():
        result.loc[0, f"{prefix}_{suffix}"] = value
    return result


def data_readiness_comparison_summary(accepted=True):
    return pd.DataFrame(
        [
            {
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


def route_readiness_summary(
    ready=True,
    strategy="lead_lag_taker",
    market="india_nse_index_derivatives",
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


def write_settlement_pipeline(root, *, launch_ready=True, broker_ready=True):
    pipeline = root / "settlement_pipeline"
    launch = pipeline / "03_launch"
    broker = pipeline / "06_broker_readiness"
    launch.mkdir(parents=True, exist_ok=True)
    broker.mkdir(parents=True, exist_ok=True)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    broker_readiness_summary(broker_ready).to_csv(broker / "broker_readiness_summary.csv", index=False)
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
    broker.mkdir(parents=True, exist_ok=True)
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
    broker_readiness_summary(broker_ready).to_csv(broker / "broker_readiness_summary.csv", index=False)
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
):
    pipeline = root / f"{family}_launch_pipeline"
    launch = pipeline / "03_launch"
    broker = pipeline / "06_broker_readiness"
    launch.mkdir(parents=True, exist_ok=True)
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
            }
        ]
    ).to_csv(pipeline / summary_file, index=False)
    launch_summary(launch_ready).to_csv(launch / "launch_summary.csv", index=False)
    broker_readiness_summary(broker_ready).to_csv(broker / "broker_readiness_summary.csv", index=False)
    (broker / "broker_readiness_config.json").write_text(
        json.dumps(
            {
                "ready": broker_ready,
                "adapter": "arrow_money",
                "dispatch_roundtrip": {"ready": broker_ready},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return pipeline


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
    assert report.summary.iloc[0]["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert report.summary.iloc[0]["shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["shadow_broker_readiness"]["sessions"] == 2
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
            dispatch_roundtrip_vendor_market_data_batch_market="india_nse_index_derivatives",
            dispatch_roundtrip_vendor_market_data_batch_dataset_count=2,
            dispatch_roundtrip_vendor_market_data_batch_ready_datasets=2,
            dispatch_roundtrip_vendor_market_data_batch_ready_rate=1.0,
            dispatch_roundtrip_vendor_market_data_batch_unique_source_files=2,
            dispatch_roundtrip_vendor_market_data_batch_unique_header_fingerprints=1,
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
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_unique_source_files"]) == 2
    assert summary["broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


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
        "broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_failed_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_source_files",
        "broker_dispatch_roundtrip_vendor_market_data_batch_header_fingerprints",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed


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
    assert int(summary["broker_dispatch_roundtrip_vendor_market_data_batch_dataset_count"]) == 2
    vendor = report.config["broker_readiness"]["dispatch_roundtrip"]["vendor_market_data_batch"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["comparison"]["accepted"]


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
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_accepted",
        "broker_dispatch_roundtrip_vendor_market_data_batch_comparison_failed_checks",
    } <= failed


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
    assert summary["broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["broker_shadow_broker_dispatch_roundtrip_scenario_count"]) == 1
    assert int(summary["broker_shadow_broker_route_dispatch_roundtrip_sessions"]) == 2
    shadow_proof = report.config["broker_readiness"]["shadow_broker_readiness"]
    assert shadow_proof["provided"]
    assert shadow_proof["adapter"] == "arrow_money"
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
    assert int(summary["broker_shadow_broker_route_readiness_gap_pairs"]) == 2
    shadow_proof = report.config["broker_readiness"]["shadow_broker_readiness"]
    assert shadow_proof["adapter"] == "irage"
    assert shadow_proof["dispatch_roundtrip"]["max_rejected_orders"] == 1


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
    assert report.summary.iloc[0]["data_readiness_comparison_dataset_count"] == 2
    assert report.config["data_readiness_comparison"]["required"]
    assert report.config["data_readiness_comparison"]["accepted"]
    assert report.config["data_readiness_comparison"]["ready_rate"] == 1.0


def test_write_scaleup_plan_carries_vendor_market_data_batch_config(tmp_path):
    evidence, shadow, launch, _ = write_inputs(tmp_path)
    vendor_batch = tmp_path / "vendor_batch"
    comparison = vendor_batch / "comparison"
    comparison.mkdir(parents=True)
    data_readiness_comparison_summary(True).to_csv(
        comparison / "data_readiness_comparison_summary.csv",
        index=False,
    )
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
    vendor = config["data_readiness_comparison"]["vendor_market_data_batch"]
    assert report.ready
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["adapter"] == "arrow_money"
    assert vendor["dataset_count"] == 2
    assert vendor["unique_source_files"] == 2
    assert vendor["unique_header_fingerprints"] == 1
    assert vendor["mapping_sources"] == "vendor_intake_draft"
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64
    assert path_tail(manifest["inputs"]["vendor_market_data_batch_config"]["path"]).endswith(
        "/vendor_batch/vendor_market_data_batch_config.json"
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
