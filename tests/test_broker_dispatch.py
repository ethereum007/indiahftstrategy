import json

import pandas as pd

from hft_cli import main
from reports.broker_dispatch import (
    BrokerDispatchThresholds,
    evaluate_broker_dispatch_plan,
    write_broker_dispatch_plan,
)
from reports.catalog import catalog_experiment_runs


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
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
            "recommendation": route_readiness_recommendation,
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
        "comparison": {
            "accepted": comparison_accepted,
            "failed_checks": comparison_failed_checks,
        },
        "datasets": datasets,
    }


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


def write_inputs(root, *, route_ready=True, duplicate=False, dispatch=True, route_readiness=True):
    route = root / "route_enable"
    upload = root / "upload"
    route.mkdir(parents=True)
    upload.mkdir()
    route_summary(
        route_ready,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(
        route / "route_enable_summary.csv",
        index=False,
    )
    (route / "route_enable_config.json").write_text(
        json.dumps(
            route_config(
                route_ready,
                dispatch_provided=dispatch,
                dispatch_ready=dispatch,
                route_readiness_provided=route_readiness,
                route_readiness_ready=route_readiness,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (route / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "route_enable_packet",
                "inputs": {
                    "cutover_manifest": {
                        "path": str(route / "cutover_manifest.json"),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
    assert report.dispatch_orders["route_dispatch_roundtrip_batch_id"].tolist() == ["BDP-0", "BDP-0"]
    assert report.summary.iloc[0]["route_dispatch_roundtrip_ready"]
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
    assert summary["pre_portfolio_max_notional_per_session"] == 25_000.0
    assert portfolio["required"]
    assert portfolio["provided"]
    assert portfolio["ready"]
    assert portfolio["selected_allocation_notional"] == 2_000.0
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
    assert (out_dir / "broker_dispatch_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
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


def test_cli_broker_dispatch_hydrates_broker_vendor_data_from_route_manifest_chain(tmp_path):
    route, upload = write_inputs(tmp_path)
    broker_config = route / "broker_readiness_config.json"
    cutover_manifest = route / "cutover_manifest.json"
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


def test_cli_broker_dispatch_blocks_failed_broker_vendor_data_readiness_sidecar(tmp_path):
    route, upload = write_inputs(tmp_path)
    broker_config = route / "broker_readiness_config.json"
    cutover_manifest = route / "cutover_manifest.json"
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
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "route_enabled" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
