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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
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
    broker_schema_status="placeholder_normalized_pending_vendor_schema",
    broker_schema_reviewed=True,
    broker_schema_review_mode="reviewed_vendor_mapping",
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
        "upload": {
            "ready": True,
            "orders": upload_orders,
            "output_file": "broker_upload_orders.csv",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
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


def write_inputs(root, *, route_ready=True, duplicate=False, dispatch=True):
    route = root / "route_enable"
    upload = root / "upload"
    route.mkdir(parents=True)
    upload.mkdir()
    route_summary(route_ready, dispatch_provided=dispatch, dispatch_ready=dispatch).to_csv(
        route / "route_enable_summary.csv",
        index=False,
    )
    (route / "route_enable_config.json").write_text(
        json.dumps(route_config(route_ready, dispatch_provided=dispatch, dispatch_ready=dispatch), indent=2) + "\n",
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
    assert {"route_enable_summary", "route_enable_config", "upload_orders"} <= set(manifest["inputs"])
    assert path_tail(manifest["inputs"]["route_enable_summary"]["path"]).endswith(
        "/route_enable/route_enable_summary.csv"
    )
    assert path_tail(manifest["inputs"]["route_enable_config"]["path"]).endswith(
        "/route_enable/route_enable_config.json"
    )
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "broker_dispatch_plan"
    assert catalog.catalog.iloc[0]["summary_file"] == "broker_dispatch_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


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
