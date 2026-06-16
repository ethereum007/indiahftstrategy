import json

import pandas as pd

from adapters.broker_readiness import (
    BrokerReadinessThresholds,
    evaluate_broker_readiness,
    write_broker_readiness_report,
)
from hft_cli import main
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
)
from tests.broker_vendor_data_helpers import write_broker_vendor_data_proof


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


def resume_summary(adapter="normalized", ready=True):
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
    route_enable_dispatch_roundtrip_failed_checks=0,
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "route_readiness_inputs_missing"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
):
    route_readiness_recommendation = (
        "eligible_for_live_dryrun_route_review"
        if route_readiness_recommendation is None and route_readiness_ready
        else "route_readiness_inputs_missing"
        if route_readiness_recommendation is None
        else route_readiness_recommendation
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
):
    return {
        "provided": sessions > 0,
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


def path_tail(value):
    return str(value).replace("\\", "/")


def write_broker_readiness_input_dirs(root, adapter):
    schema_dir = root / "schema"
    export_dir = root / "export"
    upload_dir = root / "upload"
    roundtrip_dir = root / "roundtrip"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir(parents=True)
    schema_summary(adapter, True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary(adapter, True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary(adapter, True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
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
    summary = report.summary.iloc[0]
    assert bool(summary["resume_gate_provided"])
    assert bool(summary["resume_gate_ready"])
    assert bool(summary["resume_proof_refresh_ready"])
    assert summary["resume_strategy"] == "surface_mm"
    assert summary["resume_incident_market"] == "india_nse_index_derivatives"
    assert summary["resume_proof_refresh_market"] == "india_nse_index_derivatives"


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
    assert item["shadow_broker_adapter"] == "normalized"
    summary = report.summary.iloc[0]
    assert bool(summary["shadow_broker_readiness_provided"])
    assert int(summary["shadow_broker_readiness_ready_sessions"]) == 2
    assert summary["shadow_broker_adapter"] == "normalized"
    assert summary["shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["shadow_broker_dispatch_roundtrip_scenario_count"]) == 1
    assert int(summary["shadow_broker_route_dispatch_roundtrip_sessions"]) == 2


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
    assert int(summary["shadow_broker_route_readiness_gap_pairs"]) == 2


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
    assert item["broker_shadow_broker_adapter"] == "normalized"
    summary = report.summary.iloc[0]
    assert bool(summary["broker_shadow_broker_readiness_provided"])
    assert int(summary["broker_shadow_broker_readiness_ready_sessions"]) == 2
    assert summary["broker_shadow_broker_adapter"] == "normalized"
    assert summary["broker_shadow_broker_route_readiness_strategy"] == "lead_lag_taker"
    assert int(summary["broker_shadow_broker_dispatch_roundtrip_scenario_count"]) == 1
    assert int(summary["broker_shadow_broker_route_dispatch_roundtrip_sessions"]) == 2


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
    schema_dir = tmp_path / "schema"
    export_dir = tmp_path / "export"
    upload_dir = tmp_path / "upload"
    resume_dir = tmp_path / "resume"
    roundtrip_dir = tmp_path / "roundtrip"
    out_dir = tmp_path / "readiness"
    schema_dir.mkdir()
    export_dir.mkdir()
    upload_dir.mkdir()
    resume_dir.mkdir()
    roundtrip_dir.mkdir()
    schema_summary("arrow_money", True).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary("arrow_money", True).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary("arrow_money", True).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    resume_summary("arrow_money", True).to_csv(resume_dir / "resume_summary.csv", index=False)
    dispatch_roundtrip_summary("arrow_money", True).to_csv(
        roundtrip_dir / "broker_dispatch_roundtrip_summary.csv",
        index=False,
    )
    roundtrip_config = dispatch_roundtrip_config()
    roundtrip_config["shadow_broker_readiness"] = shadow_broker_config(adapter="arrow_money")
    roundtrip_config["broker_shadow_broker_readiness"] = shadow_broker_config(adapter="arrow_money")
    roundtrip_config["roundtrip_vendor_market_data_batch"] = vendor_market_data_batch_config()
    roundtrip_config["roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"] = (
        vendor_market_data_batch_config()
    )
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(roundtrip_config, indent=2) + "\n",
        encoding="utf-8",
    )
    (roundtrip_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_type": "broker_dispatch_roundtrip",
                "inputs": {
                    "dispatch_manifest": {"path": "dispatch.json"},
                    "send_manifest": {"path": "send.json"},
                    "ack_manifest": {"path": "ack.json"},
                },
            },
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
    assert bool(report.summary.iloc[0]["resume_gate_ready"])
    assert bool(report.summary.iloc[0]["dispatch_roundtrip_ready"])
    assert (out_dir / "broker_readiness_items.csv").exists()
    assert (out_dir / "broker_readiness_checks.csv").exists()
    assert (out_dir / "broker_readiness_summary.csv").exists()
    assert (out_dir / "broker_readiness_config.json").exists()
    assert (out_dir / "manifest.json").exists()
    config = json.loads((out_dir / "broker_readiness_config.json").read_text(encoding="utf-8"))
    assert config == report.config
    assert config["ready"]
    assert config["adapter"] == "arrow_money"
    assert config["components"]["dispatch_roundtrip"]["ready"]
    assert config["resume_gate"]["proof_refresh"]["strategy"] == "surface_mm"
    assert config["dispatch_roundtrip"]["route_readiness"]["gap_pairs"] == 0
    assert config["dispatch_roundtrip"]["route_dispatch_roundtrip"]["batch_id"] == "BDP-0"
    assert config["dispatch_roundtrip"]["vendor_market_data_batch"]["adapter"] == "arrow_money"
    assert config["dispatch_roundtrip"]["vendor_market_data_batch"]["dataset_count"] == 2
    assert config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]["adapter"] == (
        "arrow_money"
    )
    assert config["dispatch_roundtrip"]["broker_dispatch_roundtrip_vendor_market_data_batch"]["dataset_count"] == 2
    assert config["shadow_broker_readiness"]["adapter"] == "arrow_money"
    assert config["shadow_broker_readiness"]["dispatch_roundtrip"]["scenario_count"] == 1
    assert config["broker_shadow_broker_readiness"]["provided"]
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


def test_broker_readiness_reads_vendor_market_data_batch_artifact(tmp_path):
    for adapter in ("arrow_money", "irage"):
        root = tmp_path / adapter
        schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(root, adapter)
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


def test_cli_broker_readiness_accepts_vendor_market_data_batch_artifact(tmp_path):
    schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
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
    schema_dir, export_dir, upload_dir, roundtrip_dir = write_broker_readiness_input_dirs(tmp_path, "arrow_money")
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
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert "schema_reviewed" in set(checks.loc[~checks["passed"].astype(bool), "check"])


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
