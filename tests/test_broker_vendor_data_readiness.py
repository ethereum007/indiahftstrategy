import json

import pandas as pd

from hft_cli import main
from reports.broker_vendor_data_readiness import (
    BrokerVendorDataReadinessConfig,
    write_broker_vendor_data_readiness_pipeline,
)
from tests.broker_vendor_data_helpers import assert_broker_vendor_data_proof_forwarded


def vendor_ticks(day: str, *, base: float = 100.0):
    return pd.DataFrame(
        [
            {
                "exchange_ts": f"{day} 09:15:00",
                "best_bid": base,
                "best_ask": base + 0.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": base + 0.05,
                "last_size": 75,
            },
            {
                "exchange_ts": f"{day} 09:15:01",
                "best_bid": base + 0.05,
                "best_ask": base + 0.10,
                "bid_size": 150,
                "ask_size": 75,
                "last_px": base + 0.10,
                "last_size": 75,
            },
        ]
    )


def schema_summary(adapter):
    return pd.DataFrame(
        [
            {
                "adapter": adapter,
                "kind": "orders",
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "missing_required_columns": 0,
                "all_required_present": True,
            }
        ]
    )


def order_export_summary(adapter):
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0,
            }
        ]
    )


def upload_summary(adapter):
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": adapter,
                "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
                "orders": 2,
                "failed_checks": 0,
                "recommendation": "dry_run_or_paper_review",
            }
        ]
    )


def dispatch_roundtrip_summary(adapter):
    return pd.DataFrame(
        [
            {
                "passed": True,
                "adapter": adapter,
                "target_mode": "live_dryrun",
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "scenario_key": "trigger_ticks=2",
                "batch_id": "BDP-1",
                "requests": 2,
                "send_requests": 2,
                "acked_orders": 2,
                "missing_request_acks": 0,
                "rejected_orders": 0,
                "unmatched_acks": 0,
                "failed_checks": 0,
                "route_dispatch_roundtrip_provided": True,
                "route_dispatch_roundtrip_ready": True,
                "route_dispatch_roundtrip_target_mode": "live_dryrun",
                "route_dispatch_roundtrip_strategy": "lead_lag_taker",
                "route_dispatch_roundtrip_market": "india_nse_index_derivatives",
                "route_dispatch_roundtrip_scenario_key": "trigger_ticks=2",
                "route_dispatch_roundtrip_batch_id": "BDP-0",
                "route_dispatch_roundtrip_requests": 2,
                "route_dispatch_roundtrip_acked_orders": 2,
                "route_dispatch_roundtrip_missing_request_acks": 0,
                "route_dispatch_roundtrip_rejected_orders": 0,
                "route_dispatch_roundtrip_unmatched_acks": 0,
                "recommendation": "ready_for_broker_readiness_review",
            }
        ]
    )


def dispatch_roundtrip_config():
    return {
        "route_readiness": {
            "required": True,
            "provided": True,
            "ready": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "route_ready_pairs": 1,
            "gap_pairs": 0,
            "recommendation": "eligible_for_live_dryrun_route_review",
            "ops_launch_controls_ready": True,
            "ops_launch_control_failures": "",
            "ops_broker_roundtrip_portfolio_safe_runs": 1,
            "ops_broker_roundtrip_portfolio_breach_runs": 0,
            "ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
            "ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
        },
        "route_enable_dispatch_roundtrip": {"failed_checks": 0},
    }


def leadlag_scenario_key():
    return (
        "strategy=lead_lag_taker|market=india_nse_index_derivatives|trigger_ticks=10|"
        "delta=1|leader_tick=0.05|laggard_tick=0.05"
    )


def write_leadlag_promotion(path):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": True,
                "candidate_scenario_key": leadlag_scenario_key(),
                "failed_checks": 0,
                "recommendation": "paper_or_shadow_candidate",
            }
        ]
    ).to_csv(path / "promotion_summary.csv", index=False)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "lead_lag_taker",
                "scenario_key": leadlag_scenario_key(),
                "parameters": {
                    "market": "india_nse_index_derivatives",
                    "leader_tick": 0.05,
                    "laggard_tick": 0.05,
                    "delta": 1.0,
                    "trigger_ticks": 10.0,
                    "qty": 75,
                    "flat_after_ns": 200_000,
                    "cooloff_ns": 1000,
                },
                "metrics": {
                    "total_net_pnl": 42.0,
                    "median_markout_mean": 0.15,
                },
                "failed_checks": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_inputs(root, adapter):
    day1 = root / f"{adapter}_ticks_day1.csv"
    day2 = root / f"{adapter}_ticks_day2.csv"
    schema_dir = root / "schema"
    export_dir = root / "export"
    upload_dir = root / "upload"
    roundtrip_dir = root / "roundtrip"
    for path in (schema_dir, export_dir, upload_dir, roundtrip_dir):
        path.mkdir(parents=True)
    vendor_ticks("2026-06-10", base=100.0).to_csv(day1, index=False)
    vendor_ticks("2026-06-11", base=100.5).to_csv(day2, index=False)
    schema_summary(adapter).to_csv(schema_dir / "adapter_schema_summary.csv", index=False)
    order_export_summary(adapter).to_csv(export_dir / "broker_order_summary.csv", index=False)
    upload_summary(adapter).to_csv(upload_dir / "broker_upload_summary.csv", index=False)
    dispatch_roundtrip_summary(adapter).to_csv(roundtrip_dir / "broker_dispatch_roundtrip_summary.csv", index=False)
    (roundtrip_dir / "broker_dispatch_roundtrip_config.json").write_text(
        json.dumps(dispatch_roundtrip_config(), indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "input": [day1, day2],
        "schema": schema_dir,
        "export": export_dir,
        "upload": upload_dir,
        "roundtrip": roundtrip_dir,
    }


def test_broker_vendor_data_readiness_pipeline_runs_arrow_and_irage(tmp_path):
    for adapter in ("arrow_money", "irage"):
        root = tmp_path / adapter
        paths = write_inputs(root, adapter)
        out_dir = root / "proof"

        report = write_broker_vendor_data_readiness_pipeline(
            paths["input"],
            output_dir=out_dir,
            labels=["day1", "day2"],
            schema_audit_dir=paths["schema"],
            order_export_dir=paths["export"],
            upload_pack_dir=paths["upload"],
            dispatch_roundtrip_dir=paths["roundtrip"],
            config=BrokerVendorDataReadinessConfig(
                adapter=adapter,
                kind="ticks",
                timestamp_unit="datetime",
                tick_size=0.05,
                min_rows=2,
            ),
        )

        assert report.ready
        summary = report.summary.iloc[0]
        assert summary["adapter"] == adapter
        assert bool(summary["vendor_batch_ready"])
        assert bool(summary["broker_readiness_ready"])
        assert bool(summary["broker_vendor_data_ready"])
        assert summary["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
        assert not bool(summary["schema_review_required"])
        assert not bool(summary["schema_reviewed"])
        assert summary["schema_review_mode"] == "placeholder_unreviewed"
        assert bool(summary["placeholder_schema_active"])
        assert bool(summary["placeholder_schema_allowed"])
        assert summary["placeholder_schema_warning"] == "placeholder adapter schema allowed for dry-run review only"
        assert int(summary["dataset_count"]) == 2
        assert int(summary["unique_source_files"]) == 2
        assert int(summary["unique_header_fingerprints"]) == 1
        assert summary["source_file_fingerprint_coverage"] == 1.0
        assert summary["min_mapping_coverage"] == 1.0
        assert int(summary["unique_mapping_drafts"]) == 1
        assert summary["mapping_sources"] == "vendor_intake_draft"
        assert bool(summary["comparison_accepted"])
        assert int(summary["failed_checks"]) == 0
        assert int(summary["failed_check_count"]) == 0
        assert summary["failed_check_names"] == ""
        assert summary["first_failed_reason"] == ""
        assert summary["primary_blocker_check"] == ""
        assert bool(report.checks["passed"].all())
        assert (out_dir / "broker_vendor_data_readiness_checks.csv").exists()
        assert (out_dir / "broker_vendor_data_readiness_action_queue.csv").exists()
        assert (out_dir / "broker_vendor_data_readiness_runbook.md").exists()
        assert (out_dir / "01_vendor_market_data_batch" / "vendor_market_data_batch_config.json").exists()
        assert (out_dir / "02_broker_readiness" / "broker_readiness_config.json").exists()
        action_queue = pd.read_csv(out_dir / "broker_vendor_data_readiness_action_queue.csv")
        assert report.action_queue is not None
        assert report.action_queue.empty
        assert action_queue.empty
        assert "next_gate_help_command" in action_queue.columns
        runbook = (out_dir / "broker_vendor_data_readiness_runbook.md").read_text(encoding="utf-8")
        assert "# Broker Vendor Data Readiness Runbook" in runbook
        assert "- Ready: yes" in runbook
        assert "- Placeholder schema allowed: yes" in runbook
        assert "placeholder adapter schema allowed for dry-run review only" in runbook
        assert "broker_data_proof_ready" in runbook
        config = json.loads((out_dir / "broker_vendor_data_readiness_config.json").read_text(encoding="utf-8"))
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        assert config["ready"]
        assert config["adapter"] == adapter
        assert config["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
        assert not config["schema_review_required"]
        assert not config["schema_reviewed"]
        assert config["schema_review_mode"] == "placeholder_unreviewed"
        assert config["placeholder_schema_active"]
        assert config["placeholder_schema_allowed"]
        assert config["placeholder_schema_warning"] == "placeholder adapter schema allowed for dry-run review only"
        assert config["vendor_market_data_batch"]["source_file_fingerprint_coverage"] == 1.0
        assert config["vendor_market_data_batch"]["min_mapping_coverage"] == 1.0
        assert config["vendor_market_data_batch"]["unique_mapping_drafts"] == 1
        assert config["vendor_market_data_batch"]["comparison"]["accepted"]
        assert config["broker_readiness"]["broker_vendor_data_ready"]
        assert config["broker_readiness"]["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
        assert config["broker_readiness"]["placeholder_schema_allowed"]
        assert config["failed_check_count"] == 0
        assert config["failed_checks"] == []
        assert config["first_failed_reason"] == ""
        assert config["primary_blocker"] == {}
        assert config["ready_action_count"] == 0
        assert config["blocked_action_count"] == 0
        assert config["next_gate"] == ""
        assert config["next_gate_help_command"] == ""
        assert config["primary_action_status"] == ""
        assert config["primary_action"] == {}
        assert config["next_actions"] == []
        assert config["ready_actions"] == []
        assert config["blocked_actions"] == []
        component_by_name = {item["component"]: item for item in config["components"]}
        assert component_by_name["vendor_market_data_batch"]["source_file_fingerprint_coverage"] == 1.0
        assert component_by_name["vendor_market_data_batch"]["min_mapping_coverage"] == 1.0
        assert component_by_name["vendor_market_data_batch"]["unique_mapping_drafts"] == 1
        assert component_by_name["broker_readiness"]["adapter_schema_status"] == (
            "placeholder_normalized_pending_vendor_schema"
        )
        assert component_by_name["broker_readiness"]["placeholder_schema_active"]
        assert manifest["run_type"] == "broker_vendor_data_readiness_pipeline"
        assert "vendor_market_data_batch" in manifest["inputs"]
        assert "broker_readiness" in manifest["inputs"]
        artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
        assert "broker_vendor_data_readiness_action_queue.csv" in artifact_paths
        assert "broker_vendor_data_readiness_runbook.md" in artifact_paths


def test_cli_broker_vendor_data_readiness_pipeline(tmp_path):
    paths = write_inputs(tmp_path, "arrow_money")
    out_dir = tmp_path / "proof"

    code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(out_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_vendor_data_readiness_summary.csv")
    components = pd.read_csv(out_dir / "broker_vendor_data_readiness_components.csv")
    checks = pd.read_csv(out_dir / "broker_vendor_data_readiness_checks.csv")
    assert code == 0
    assert bool(summary.loc[0, "ready"])
    assert bool(summary.loc[0, "broker_vendor_data_ready"])
    assert int(summary.loc[0, "failed_checks"]) == 0
    assert int(summary.loc[0, "failed_check_count"]) == 0
    assert pd.isna(summary.loc[0, "primary_blocker_check"])
    assert bool(checks["passed"].all())
    assert summary.loc[0, "source_file_fingerprint_coverage"] == 1.0
    assert summary.loc[0, "min_mapping_coverage"] == 1.0
    assert int(summary.loc[0, "unique_mapping_drafts"]) == 1
    assert set(components["component"]) == {"vendor_market_data_batch", "broker_readiness"}
    vendor_component = components.set_index("component").loc["vendor_market_data_batch"]
    assert vendor_component["source_file_fingerprint_coverage"] == 1.0
    assert vendor_component["min_mapping_coverage"] == 1.0
    assert int(vendor_component["unique_mapping_drafts"]) == 1
    assert summary.loc[0, "adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(summary.loc[0, "placeholder_schema_allowed"])


def test_cli_broker_vendor_data_readiness_blocks_placeholder_schema_without_override(tmp_path):
    paths = write_inputs(tmp_path, "arrow_money")
    out_dir = tmp_path / "proof"
    blocked_dir = tmp_path / "proof_blocked"
    actions_dir = tmp_path / "proof_actions"

    code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(out_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_vendor_data_readiness_summary.csv")
    action_queue = pd.read_csv(out_dir / "broker_vendor_data_readiness_action_queue.csv")
    config = json.loads((out_dir / "broker_vendor_data_readiness_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_vendor_data_readiness_runbook.md").read_text(encoding="utf-8")
    broker_checks = pd.read_csv(out_dir / "02_broker_readiness" / "broker_readiness_checks.csv")
    broker_failed = set(broker_checks.loc[~broker_checks["passed"].astype(bool), "check"])

    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(summary.loc[0, "schema_review_required"])
    assert not bool(summary.loc[0, "schema_reviewed"])
    assert summary.loc[0, "schema_review_mode"] == "placeholder_unreviewed"
    assert bool(summary.loc[0, "placeholder_schema_active"])
    assert not bool(summary.loc[0, "placeholder_schema_allowed"])
    assert summary.loc[0, "placeholder_schema_warning"] == (
        "placeholder adapter schema requires reviewed vendor mapping before broker readiness"
    )
    assert "schema_reviewed" in broker_failed
    assert "broker_readiness_ready" in set(action_queue["check"])
    assert config["schema_review_required"]
    assert config["placeholder_schema_active"]
    assert not config["placeholder_schema_allowed"]
    assert config["broker_readiness"]["schema_review_required"]
    assert config["broker_readiness"]["placeholder_schema_active"]
    assert not config["broker_readiness"]["placeholder_schema_allowed"]
    assert "- Placeholder schema allowed: no" in runbook
    assert "placeholder adapter schema requires reviewed vendor mapping before broker readiness" in runbook

    blocked_code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(blocked_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--require-dispatch-roundtrip",
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(actions_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--require-dispatch-roundtrip",
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


def test_cli_broker_vendor_data_readiness_writes_root_checks_for_bad_vendor_batch(tmp_path):
    paths = write_inputs(tmp_path, "arrow_money")
    out_dir = tmp_path / "proof"
    reused_input = paths["input"][0]

    code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            str(reused_input),
            str(reused_input),
            "--out",
            str(out_dir),
            "--label",
            "day1",
            "--label",
            "day1_copy",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "broker_vendor_data_readiness_summary.csv")
    checks = pd.read_csv(out_dir / "broker_vendor_data_readiness_checks.csv")
    action_queue = pd.read_csv(out_dir / "broker_vendor_data_readiness_action_queue.csv")
    runbook = (out_dir / "broker_vendor_data_readiness_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "broker_vendor_data_readiness_config.json").read_text(encoding="utf-8"))
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_checks"]) == len(failed)
    assert int(summary.loc[0, "failed_check_count"]) == len(failed)
    assert str(summary.loc[0, "failed_check_names"]).split(";")[0] == "vendor_batch_ready"
    assert summary.loc[0, "first_failed_reason"] == "vendor market-data batch is not ready"
    assert summary.loc[0, "primary_blocker_check"] == "vendor_batch_ready"
    assert not bool(summary.loc[0, "primary_blocker_value"])
    assert summary.loc[0, "primary_blocker_operator"] == "is"
    assert bool(summary.loc[0, "primary_blocker_threshold"])
    assert summary.loc[0, "primary_blocker_reason"] == "vendor market-data batch is not ready"
    assert {
        "vendor_batch_ready",
        "broker_readiness_ready",
        "broker_vendor_data_ready",
        "failed_components",
        "unique_source_files",
        "comparison_accepted",
    } <= failed
    assert config["failed_check_count"] == len(failed)
    assert set(config["failed_checks"]) == failed
    assert config["first_failed_reason"] == "vendor market-data batch is not ready"
    assert config["primary_blocker"]["check"] == "vendor_batch_ready"
    assert config["primary_blocker"]["observed"] is False
    assert config["primary_blocker"]["operator"] == "is"
    assert config["primary_blocker"]["expected"] is True
    assert config["primary_blocker"]["message"] == "vendor market-data batch is not ready"
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == len(action_queue)
    assert config["next_gate"] == action_queue.loc[0, "next_gate"]
    assert config["next_gate_help_command"] == action_queue.loc[0, "next_gate_help_command"]
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == action_queue.loc[0, "check"]
    assert config["primary_action"]["next_gate"] == action_queue.loc[0, "next_gate"]
    assert config["ready_actions"] == []
    assert {item["check"] for item in config["next_actions"]} == failed
    assert {item["check"] for item in config["blocked_actions"]} == failed
    assert set(action_queue["check"]) == failed
    assert "pipeline-vendor-market-data-batch" in set(action_queue["next_gate"])
    assert "review-broker-readiness" in set(action_queue["next_gate"])
    assert "pipeline-broker-vendor-readiness" in set(action_queue["next_gate"])
    assert "- Ready: no" in runbook
    assert "pipeline-vendor-market-data-batch" in runbook


def test_cli_broker_vendor_data_readiness_output_feeds_launch_cli(tmp_path):
    paths = write_inputs(tmp_path / "broker_inputs", "arrow_money")
    proof_dir = tmp_path / "broker_vendor_data"

    vendor_code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            *(str(path) for path in paths["input"]),
            "--out",
            str(proof_dir),
            "--label",
            "day1",
            "--label",
            "day2",
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-rows",
            "2",
            "--schema-audit",
            str(paths["schema"]),
            "--order-export",
            str(paths["export"]),
            "--upload-pack",
            str(paths["upload"]),
            "--dispatch-roundtrip",
            str(paths["roundtrip"]),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
        ]
    )

    promotion_dir = tmp_path / "promotion"
    launch_dir = tmp_path / "launch_pipeline"
    write_leadlag_promotion(promotion_dir)
    launch_code = main(
        [
            "pipeline-leadlag-launch",
            "--promotion",
            str(promotion_dir),
            "--out",
            str(launch_dir),
            "--adapter",
            "arrow_money",
            "--route-tag",
            "leadlag_shadow",
            "--laggard-instrument-id",
            "NIFTY_20260610_25000C",
            "--reference-price",
            "10",
            "--max-order-qty",
            "75",
            "--max-notional",
            "10000",
            "--max-orders",
            "2",
            "--broker-vendor-data-readiness",
            str(proof_dir),
            "--allow-placeholder-schema",
            "--fail-on-breach",
        ]
    )

    launch_summary = pd.read_csv(launch_dir / "leadlag_launch_pipeline_summary.csv")
    assert vendor_code == 0
    assert launch_code == 0
    assert bool(launch_summary.loc[0, "ready"])
    assert_broker_vendor_data_proof_forwarded(launch_dir)
