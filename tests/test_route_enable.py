import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.route_enable import (
    RouteEnableThresholds,
    evaluate_route_enable_packet,
    write_route_enable_packet,
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
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
                "adapter": adapter,
                "max_orders_per_session": max_orders,
                "max_notional_per_session": max_notional,
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
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
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "complete_route_readiness_gaps"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
        "scaleup_route_readiness": {
            "required": route_readiness_required,
            "provided": route_readiness_provided,
            "ready": route_readiness_ready,
            "strategy": route_readiness_strategy,
            "market": route_readiness_market,
            "route_ready_pairs": route_readiness_route_ready_pairs,
            "gap_pairs": route_readiness_gap_pairs,
            "recommendation": route_readiness_recommendation,
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
        "mapping_sources": mapping_sources,
        "comparison": {
            "accepted": comparison_accepted,
            "failed_checks": comparison_failed_checks,
        },
        "datasets": datasets,
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
    cutover_summary(
        ready=cutover_ready,
        dispatch_provided=dispatch,
        dispatch_ready=dispatch,
        route_readiness_provided=route_readiness,
        route_readiness_ready=route_readiness,
    ).to_csv(
        cutover / "cutover_summary.csv",
        index=False,
    )
    (cutover / "cutover_config.json").write_text(
        json.dumps(
            cutover_config(
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
    (cutover / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "cutover_gate",
                "inputs": {
                    "broker_readiness_config": {
                        "path": str(cutover / "broker_readiness_config.json"),
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
    assert report.config["route_enabled"]
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


def test_route_enable_blocks_bad_cutover_shadow_broker_readiness():
    config = cutover_config()
    config["scaleup_shadow_broker_readiness"] = shadow_broker_config(
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

    report = evaluate_route_enable_packet(
        cutover_summary=cutover_summary(),
        cutover_config=config,
        upload_summary=upload_summary(),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {
        "cutover_shadow_broker_readiness_ready",
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
    assert report.config["shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2


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
    assert summary["cutover_broker_shadow_broker_adapter"] == "arrow_money"
    assert summary["cutover_broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert summary["cutover_broker_shadow_broker_dispatch_roundtrip_scenario_count"] == 1
    assert report.config["cutover_broker_shadow_broker_readiness"]["provided"]
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
    assert summary["cutover_vendor_market_data_batch_mapping_sources"] == "vendor_intake_draft"
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
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
    assert summary["cutover_broker_dispatch_roundtrip_vendor_market_data_batch_mapping_sources"] == (
        "vendor_intake_draft"
    )
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"
    assert vendor["comparison"]["accepted"]
    assert len(vendor["datasets"]) == 2
    assert vendor["datasets"][0]["source_file_sha256"] == "a" * 64


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
    assert vendor["adapter"] == "arrow_money"
    assert vendor["manifest_run_type"] == "vendor_market_data_batch_pipeline"


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
    assert report.config["cutover_broker_shadow_broker_readiness"]["adapter"] == "irage"
    assert report.config["cutover_broker_shadow_broker_readiness"]["route_readiness"]["max_gap_pairs"] == 2
    assert report.config["cutover_broker_shadow_broker_readiness"]["dispatch_roundtrip"][
        "max_rejected_orders"
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
    assert (out_dir / "route_enable_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
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
    assert vendor["provided"]
    assert vendor["ready"]
    assert vendor["comparison"]["accepted"]
    assert vendor["datasets"][1]["source_file_sha256"] == "d" * 64


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
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "cutover_ready" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
