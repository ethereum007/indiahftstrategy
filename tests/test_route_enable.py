import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.route_enable import (
    RouteEnableThresholds,
    evaluate_route_enable_packet,
    write_route_enable_packet,
)


def cutover_summary(ready=True, max_orders=10, max_notional=100_000.0, adapter="arrow_money"):
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
                "broker_resume_gate_ready": False,
                "broker_resume_proof_refresh_ready": False,
                "failed_checks": 0 if ready else 1,
                "recommendation": "allow_live_dryrun_cutover" if ready else "keep_cutover_disabled",
            }
        ]
    )


def cutover_config(max_orders=10, max_notional=100_000.0, adapter="arrow_money"):
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
            "resume_gate": {
                "provided": False,
                "ready": False,
                "proof_refresh_ready": False,
            }
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


def write_inputs(root, *, cutover_ready=True, upload_ready=True, upload_orders=2, export_notional=25_000.0):
    cutover = root / "cutover"
    upload = root / "upload"
    export = root / "export"
    cutover.mkdir(parents=True)
    upload.mkdir()
    export.mkdir()
    cutover_summary(ready=cutover_ready).to_csv(cutover / "cutover_summary.csv", index=False)
    (cutover / "cutover_config.json").write_text(
        json.dumps(cutover_config(), indent=2) + "\n",
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
