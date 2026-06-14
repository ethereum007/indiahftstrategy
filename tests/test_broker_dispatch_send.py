import json

import pandas as pd

from hft_cli import main
from reports.broker_dispatch_send import (
    evaluate_broker_dispatch_send_packet,
    write_broker_dispatch_send_packet,
)
from reports.catalog import catalog_experiment_runs


def path_tail(value):
    return str(value).replace("\\", "/")


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
                "dispatch_batch_id": "BDP-1",
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


def vendor_market_data_batch_config():
    return {
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


def write_dispatch(tmp_path, *, ready=True, state="armed_dry_run", route_roundtrip=True, route_readiness=True):
    dispatch = tmp_path / "dispatch"
    dispatch.mkdir()
    dispatch_summary(
        ready=ready,
        state=state,
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
    return dispatch


def test_broker_dispatch_send_packet_prepares_non_submitting_requests():
    report = evaluate_broker_dispatch_send_packet(
        dispatch_summary=dispatch_summary(),
        dispatch_orders=dispatch_orders(),
    )

    assert report.ready
    assert report.summary.iloc[0]["request_state"] == "dry_run_send_packet_ready"
    assert report.summary.iloc[0]["recommendation"] == "ready_for_non_submitting_broker_sender_review"
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


def test_broker_dispatch_send_blocks_bad_dispatch_shadow_broker_readiness():
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
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


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
    assert summary["route_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["route_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["route_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["route_broker_shadow_broker_readiness"]["provided"]
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
    assert int(summary["dispatch_vendor_market_data_batch_dataset_count"]) == 2
    assert int(summary["dispatch_vendor_market_data_batch_unique_source_files"]) == 2
    assert int(summary["dispatch_vendor_market_data_batch_unique_header_fingerprints"]) == 1
    assert summary["dispatch_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


def test_broker_dispatch_send_blocks_bad_route_broker_shadow_broker_readiness():
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
    assert report.config["route_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["route_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


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
    assert (out_dir / "broker_dispatch_send_config.json").exists()
    assert (out_dir / "manifest.json").exists()
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
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_send_packet"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_send_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


def test_cli_broker_dispatch_send_fails_when_request_limit_breached(tmp_path):
    dispatch = write_dispatch(tmp_path)
    out_dir = tmp_path / "dispatch_send"

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

    summary = pd.read_csv(out_dir / "broker_dispatch_send_summary.csv")
    checks = pd.read_csv(out_dir / "broker_dispatch_send_checks.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "request_count_within_limit" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
