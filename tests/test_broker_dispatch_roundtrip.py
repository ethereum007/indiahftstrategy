import json

import pandas as pd

from hft_cli import main
from reports.broker_dispatch_roundtrip import (
    evaluate_broker_dispatch_roundtrip,
    write_broker_dispatch_roundtrip,
)
from reports.catalog import catalog_experiment_runs


def path_tail(value):
    return str(value).replace("\\", "/")


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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
                "dispatch_batch_id": "BDP-1",
                "dry_run_only": True,
                "route_readiness_required": route_readiness_required,
                "route_readiness_provided": route_readiness_provided,
                "route_readiness_ready": route_readiness_ready,
                "route_readiness_strategy": route_readiness_strategy,
                "route_readiness_market": route_readiness_market,
                "route_readiness_route_ready_pairs": route_readiness_route_ready_pairs,
                "route_readiness_gap_pairs": route_readiness_gap_pairs,
                "route_readiness_recommendation": route_readiness_recommendation,
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
            "recommendation": route_readiness_recommendation,
        },
        "route_enable_dispatch_roundtrip": {
            "failed_checks": route_enable_dispatch_roundtrip_failed_checks,
        }
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
    assert report.summary.iloc[0]["recommendation"] == "broker_dry_run_roundtrip_proved"
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
    assert summary["shadow_broker_adapter"] == "arrow_money"
    assert summary["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["shadow_broker_readiness"]["provided"]
    assert report.config["shadow_broker_readiness"]["adapter"] == "arrow_money"
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
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


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
    assert summary["broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["broker_shadow_broker_readiness"]["provided"]
    assert report.config["broker_shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert report.config["broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 0
    assert report.config["broker_shadow_broker_readiness"]["dispatch_roundtrip"]["sessions"] == 2
    assert report.config["broker_shadow_broker_readiness"]["route_dispatch_roundtrip"]["market"] == (
        "india_nse_index_derivatives"
    )


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
    assert report.config["broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


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
    assert (out_dir / "broker_dispatch_roundtrip_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    expected_inputs = {
        "dispatch_summary": "/broker_dispatch_summary.csv",
        "dispatch_orders": "/broker_dispatch_orders.csv",
        "dispatch_config": "/broker_dispatch_config.json",
        "send_summary": "/broker_dispatch_send_summary.csv",
        "send_requests": "/broker_dispatch_send_requests.csv",
        "send_config": "/broker_dispatch_send_config.json",
        "ack_summary": "/broker_dispatch_ack_summary.csv",
        "acknowledgements": "/broker_dispatch_acknowledgements.csv",
        "ack_config": "/broker_dispatch_ack_config.json",
    }
    for name, suffix in expected_inputs.items():
        assert path_tail(manifest["inputs"][name]["path"]).endswith(suffix)
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_roundtrip"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_roundtrip_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_roundtrip_fails_on_missing_ack(tmp_path):
    dispatch, send, ack = write_inputs(tmp_path, missing_ack=True)
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
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert "missing_request_acks" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
