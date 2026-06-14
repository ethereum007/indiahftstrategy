import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.cutover import CutoverGateThresholds, evaluate_cutover_gate, write_cutover_gate_report


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
                "route_readiness_recommendation": "eligible_for_live_dryrun_route_review"
                if route_readiness_ready
                else "complete_route_readiness_gaps",
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
            "recommendation": "eligible_for_live_dryrun_route_review"
            if route_readiness_ready
            else "complete_route_readiness_gaps",
        },
        "broker_readiness": {
            "adapter_schema_status": broker_schema_status,
            "schema_reviewed": broker_schema_reviewed,
            "schema_review_mode": broker_schema_review_mode,
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
):
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "guard_action": "halt" if halted else "continue",
                "halted": halted,
                "target_mode": target_mode,
                "strategy": strategy,
                "market": market,
                "failed_checks": 1 if halted or not ready else 0,
                "recommendation": "stop_routing_and_execute_halt_response" if halted else "continue_with_controls",
            }
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
    runtime_session_summary(target_mode=target_mode).to_csv(runtime / "runtime_session_summary.csv", index=False)
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
    assert summary["scaleup_shadow_broker_adapter"] == "arrow_money"
    assert summary["scaleup_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["scaleup_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["scaleup_shadow_broker_readiness"]["provided"]
    assert report.config["scaleup_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["scaleup_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["scaleup_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["scaleup_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


def test_cutover_gate_blocks_bad_shadow_broker_readiness_from_scaleup_config():
    config = scaleup_config()
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
    assert report.config["scaleup_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


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
    assert summary["scaleup_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["scaleup_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["scaleup_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["scaleup_broker_shadow_broker_readiness"]["provided"]
    assert report.config["scaleup_broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
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
    assert report.config["scaleup_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2
    assert report.config["scaleup_broker_shadow_broker_readiness"]["dispatch_roundtrip"][
        "max_rejected_orders"
    ] == 1


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
    assert (out_dir / "cutover_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
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


def test_cli_cutover_gate_reads_launch_pipeline_broker_readiness_roots(tmp_path):
    cases = [
        ("leadlag", "06_broker_readiness"),
        ("surface_mm", "05_broker_readiness"),
    ]
    for family, broker_folder in cases:
        case_dir = tmp_path / family
        scaleup, _broker, _runtime, review_path = write_inputs(case_dir)
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
    assert not bool(summary.loc[0, "ready"])
    assert "operator_approved" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
