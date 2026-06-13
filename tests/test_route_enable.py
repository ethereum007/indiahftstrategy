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
):
    cutover = root / "cutover"
    upload = root / "upload"
    export = root / "export"
    cutover.mkdir(parents=True)
    upload.mkdir()
    export.mkdir()
    cutover_summary(ready=cutover_ready, dispatch_provided=dispatch, dispatch_ready=dispatch).to_csv(
        cutover / "cutover_summary.csv",
        index=False,
    )
    (cutover / "cutover_config.json").write_text(
        json.dumps(cutover_config(dispatch_provided=dispatch, dispatch_ready=dispatch), indent=2) + "\n",
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
    catalog = catalog_experiment_runs([out_dir])
    assert catalog.catalog.iloc[0]["run_type"] == "route_enable_packet"
    assert catalog.catalog.iloc[0]["summary_file"] == "route_enable_summary.csv"
    assert bool(catalog.catalog.iloc[0]["summary_status"])


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
