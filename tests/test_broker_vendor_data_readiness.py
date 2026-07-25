import json

import pandas as pd
import pytest

from hft_cli import main
from reports.broker_vendor_data_readiness import (
    BrokerVendorDataReadinessConfig,
    write_broker_vendor_data_readiness_pipeline,
)
from reports.manifest import file_sha256
from tests.broker_vendor_data_helpers import assert_broker_vendor_data_proof_forwarded
from tests.test_broker_dispatch_send import _refresh_manifest as refresh_dispatch_manifest
from tests.test_broker_readiness import (
    add_roundtrip_complete_final_target_application_lineage,
    roundtrip_final_target_application_lineage_comparison,
    target_application_lineage_comparison,
    write_broker_readiness_input_dirs,
)
from tests.test_leadlag_launch_pipeline import (
    write_promotion as write_leadlag_promotion,
)
from tests.test_vendor_data_onboarding import target_mapping_application_batch


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


def resume_summary(adapter):
    return pd.DataFrame(
        [
            {
                "ready": True,
                "adapter": adapter,
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "incident_strategy": "lead_lag_taker",
                "incident_market": "india_nse_index_derivatives",
                "proof_refresh_ready": True,
                "proof_refresh_strategy": "lead_lag_taker",
                "proof_refresh_market": "india_nse_index_derivatives",
                "incident_proof_refresh_strategy": "lead_lag_taker",
                "incident_proof_refresh_market": "india_nse_index_derivatives",
                "broker_route_readiness_required": True,
                "broker_route_readiness_provided": True,
                "broker_route_readiness_ready": True,
                "broker_route_readiness_strategy": "lead_lag_taker",
                "broker_route_readiness_market": "india_nse_index_derivatives",
                "broker_route_readiness_route_ready_pairs": 1,
                "broker_route_readiness_gap_pairs": 0,
                "broker_route_readiness_recommendation": "route_ready",
                "broker_route_readiness_ops_launch_controls_ready": True,
                "broker_route_readiness_ops_launch_control_failures": "",
                "broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": 1,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": 0,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
                "broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
                "incident_broker_route_readiness_required": True,
                "incident_broker_route_readiness_provided": True,
                "incident_broker_route_readiness_ready": True,
                "incident_broker_route_readiness_strategy": "lead_lag_taker",
                "incident_broker_route_readiness_market": "india_nse_index_derivatives",
                "incident_broker_route_readiness_route_ready_pairs": 1,
                "incident_broker_route_readiness_gap_pairs": 0,
                "incident_broker_route_readiness_recommendation": "route_ready",
                "incident_broker_route_readiness_ops_launch_controls_ready": True,
                "incident_broker_route_readiness_ops_launch_control_failures": "",
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs": 1,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_breach_runs": 0,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs": 1,
                "incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0,
                "failed_checks": 0,
                "recommendation": "resume_with_scaleup_controls",
            }
        ]
    )


def write_inputs(root, adapter):
    root.mkdir(parents=True, exist_ok=True)
    day1 = root / f"{adapter}_ticks_day1.csv"
    day2 = root / f"{adapter}_ticks_day2.csv"
    resume_dir = root / "resume"
    schema_dir, export_dir, upload_dir, roundtrip_dir = (
        write_broker_readiness_input_dirs(
            root,
            adapter,
            verified_roundtrip=True,
        )
    )
    resume_dir.mkdir()
    vendor_ticks("2026-06-10", base=100.0).to_csv(day1, index=False)
    vendor_ticks("2026-06-11", base=100.5).to_csv(day2, index=False)
    resume_summary(adapter).to_csv(resume_dir / "resume_summary.csv", index=False)
    return {
        "input": [day1, day2],
        "schema": schema_dir,
        "export": export_dir,
        "upload": upload_dir,
        "resume": resume_dir,
        "roundtrip": roundtrip_dir,
    }


def write_market_calendar(root):
    path = root / "market_calendar.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calendar_id": "nse-fo-broker-proof-2026-06",
                "market": "india_nse_index_derivatives",
                "timezone": "Asia/Kolkata",
                "valid_from": "2026-06-01",
                "valid_to": "2026-06-30",
                "provenance": {
                    "publisher": "test-fixture",
                    "source_url": "https://example.test/nse-calendar",
                    "published_date": "2026-05-31",
                },
                "sessions": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_broker_vendor_data_readiness_pipeline_runs_arrow_and_irage(tmp_path):
    for adapter in ("arrow_money", "irage"):
        root = tmp_path / adapter
        paths = write_inputs(root, adapter)
        calendar_path = write_market_calendar(root)
        out_dir = root / "proof"

        report = write_broker_vendor_data_readiness_pipeline(
            paths["input"],
            output_dir=out_dir,
            labels=["day1", "day2"],
            schema_audit_dir=paths["schema"],
            order_export_dir=paths["export"],
            upload_pack_dir=paths["upload"],
            resume_dir=paths["resume"],
            dispatch_roundtrip_dir=paths["roundtrip"],
            config=BrokerVendorDataReadinessConfig(
                adapter=adapter,
                kind="ticks",
                timestamp_unit="datetime",
                tick_size=0.05,
                max_off_tick_price_rows=0,
                min_rows=2,
                market_calendar_path=str(calendar_path),
            ),
        )

        assert report.ready
        summary = report.summary.iloc[0]
        assert summary["adapter"] == adapter
        assert bool(summary["vendor_batch_ready"])
        assert bool(summary["broker_readiness_ready"])
        assert bool(summary["broker_vendor_data_ready"])
        assert bool(summary["broker_readiness_route_readiness_ops_launch_controls_present"])
        assert int(summary["broker_readiness_route_readiness_ops_launch_controls_blocked_pairs"]) == 0
        assert int(summary["broker_readiness_route_readiness_ops_broker_roundtrip_portfolio_breach_pairs"]) == 0
        assert bool(summary["broker_readiness_route_broker_route_readiness_ops_launch_controls_ready"])
        assert int(summary["broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
        assert (
            int(
                summary[
                    "broker_readiness_route_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                ]
            )
            == 1
        )
        assert bool(summary["broker_readiness_resume_broker_route_readiness_ready"])
        assert summary["broker_readiness_resume_broker_route_readiness_strategy"] == "lead_lag_taker"
        assert int(summary["broker_readiness_resume_broker_route_readiness_gap_pairs"]) == 0
        assert bool(summary["broker_readiness_resume_broker_route_readiness_ops_launch_controls_ready"])
        assert int(summary["broker_readiness_resume_broker_route_readiness_ops_broker_roundtrip_portfolio_safe_runs"]) == 1
        assert bool(summary["broker_readiness_resume_incident_broker_route_readiness_ready"])
        assert summary["broker_readiness_resume_incident_broker_route_readiness_market"] == (
            "india_nse_index_derivatives"
        )
        assert (
            int(
                summary[
                    "broker_readiness_resume_incident_broker_route_readiness_ops_broker_roundtrip_portfolio_concentration_ok_runs"
                ]
            )
            == 1
        )
        assert summary["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
        assert not bool(summary["schema_review_required"])
        assert not bool(summary["schema_reviewed"])
        assert summary["schema_review_mode"] == "placeholder_unreviewed"
        assert bool(summary["placeholder_schema_active"])
        assert bool(summary["placeholder_schema_allowed"])
        assert summary["placeholder_schema_warning"] == "placeholder adapter schema allowed for dry-run review only"
        assert int(summary["dataset_count"]) == 2
        assert int(summary["dropped_null_rows"]) == 0
        assert int(summary["dropped_nonfinite_rows"]) == 0
        assert int(summary["dropped_nonintegral_rows"]) == 0
        assert int(summary["dropped_duplicate_rows"]) == 0
        assert int(summary["dropped_integer_overflow_rows"]) == 0
        assert int(summary["dropped_nonmonotonic_rows"]) == 0
        assert int(summary["dropped_nonpositive_strike_rows"]) == 0
        assert int(summary["dropped_negative_depth_rows"]) == 0
        assert int(summary["dropped_invalid_trade_rows"]) == 0
        assert bool(summary["price_grid_validation_enabled"])
        assert summary["price_grid_tick_size"] == pytest.approx(0.05)
        assert int(summary["off_tick_price_rows"]) == 0
        assert int(summary["unique_source_files"]) == 2
        assert int(summary["unique_header_fingerprints"]) == 1
        assert summary["source_file_fingerprint_coverage"] == 1.0
        assert summary["min_mapping_coverage"] == 1.0
        assert int(summary["unique_mapping_drafts"]) == 1
        assert summary["mapping_sources"] == "vendor_intake_draft"
        assert bool(summary["comparison_accepted"])
        assert int(summary["failed_checks"]) == 0
        assert summary["market_calendar_id"] == "nse-fo-broker-proof-2026-06"
        assert summary["market_calendar_sha256"] == file_sha256(calendar_path)
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
        assert "- Null required-field rows: 0" in runbook
        assert "- Non-finite numeric rows: 0" in runbook
        assert "- Non-integral integer-field rows: 0" in runbook
        assert "- Duplicate tick packets: 0" in runbook
        assert "- Integer-overflow rows: 0" in runbook
        assert "- Nonmonotonic tick packets: 0" in runbook
        assert "- Nonpositive depth rows: 0" in runbook
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
        assert config["market_calendar"]["provided"]
        assert config["market_calendar"]["sha256"] == file_sha256(calendar_path)
        assert config["vendor_market_data_batch"]["source_file_fingerprint_coverage"] == 1.0
        assert config["vendor_market_data_batch"]["dropped_null_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_nonfinite_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_nonintegral_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_duplicate_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_integer_overflow_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_nonmonotonic_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_nonpositive_strike_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_negative_depth_rows"] == 0
        assert config["vendor_market_data_batch"]["dropped_invalid_trade_rows"] == 0
        assert config["vendor_market_data_batch"]["price_grid_validation_enabled"]
        assert config["vendor_market_data_batch"]["price_grid_tick_size"] == pytest.approx(0.05)
        assert config["vendor_market_data_batch"]["off_tick_price_rows"] == 0
        assert config["vendor_market_data_batch"]["min_mapping_coverage"] == 1.0
        assert config["vendor_market_data_batch"]["unique_mapping_drafts"] == 1
        assert config["vendor_market_data_batch"]["comparison"]["accepted"]
        assert config["broker_readiness"]["broker_vendor_data_ready"]
        assert config["broker_readiness"]["adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
        assert config["broker_readiness"]["placeholder_schema_allowed"]
        broker_dispatch = config["broker_readiness"]["dispatch_roundtrip"]
        assert broker_dispatch["route_readiness"]["ops_launch_controls_present"]
        assert broker_dispatch["route_readiness"]["ops_broker_roundtrip_portfolio_breach_pairs"] == 0
        assert broker_dispatch["route_broker_route_readiness"]["ops_launch_controls_ready"]
        assert broker_dispatch["route_broker_route_readiness"]["ops_broker_roundtrip_portfolio_safe_runs"] == 1
        assert (
            broker_dispatch["route_broker_route_readiness"][
                "ops_broker_roundtrip_portfolio_concentration_ok_runs"
            ]
            == 1
        )
        broker_resume = config["broker_readiness"]["resume_gate"]
        assert broker_resume["broker_route_readiness"]["ready"]
        assert broker_resume["broker_route_readiness"]["strategy"] == "lead_lag_taker"
        assert broker_resume["broker_route_readiness"]["ops_broker_roundtrip_portfolio_safe_runs"] == 1
        assert broker_resume["incident_broker_route_readiness"]["ready"]
        assert broker_resume["incident_broker_route_readiness"]["market"] == "india_nse_index_derivatives"
        assert (
            broker_resume["incident_broker_route_readiness"][
                "ops_broker_roundtrip_portfolio_concentration_ok_runs"
            ]
            == 1
        )
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
        assert manifest["inputs"]["market_calendar"]["sha256"] == file_sha256(
            calendar_path
        )
        artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
        assert "broker_vendor_data_readiness_action_queue.csv" in artifact_paths
        assert "broker_vendor_data_readiness_runbook.md" in artifact_paths


def test_broker_vendor_data_readiness_preserves_target_application_batch(
    tmp_path,
):
    evidence = write_inputs(tmp_path / "broker_evidence", "arrow_money")
    application_dirs, source_paths, _ = target_mapping_application_batch(
        tmp_path,
        "broker_vendor_target",
        ["2026-07-15", "2026-07-16"],
    )
    out_dir = tmp_path / "broker_vendor_target_proof"

    report = write_broker_vendor_data_readiness_pipeline(
        source_paths,
        output_dir=out_dir,
        labels=["day1", "day2"],
        mapping_application_dirs=application_dirs,
        schema_audit_dir=evidence["schema"],
        order_export_dir=evidence["export"],
        upload_pack_dir=evidence["upload"],
        resume_dir=evidence["resume"],
        dispatch_roundtrip_dir=evidence["roundtrip"],
        config=BrokerVendorDataReadinessConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=1,
        ),
    )

    summary = report.summary.iloc[0]
    broker_summary = report.broker_readiness.summary.iloc[0]
    config = json.loads(
        (out_dir / "broker_vendor_data_readiness_config.json").read_text(
            encoding="utf-8"
        )
    )
    broker_config = json.loads(
        (
            out_dir
            / "02_broker_readiness"
            / "broker_readiness_config.json"
        ).read_text(encoding="utf-8")
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "broker_vendor_data_readiness_runbook.md").read_text(
        encoding="utf-8"
    )

    assert report.ready
    assert summary["mapping_source_mode"] == (
        "per_dataset_verified_target_application"
    )
    assert int(summary["mapping_application_count"]) == 2
    assert int(summary["unique_mapping_applications"]) == 2
    assert summary["target_application_coverage"] == 1.0
    assert summary["broker_vendor_mapping_source_mode"] == (
        "per_dataset_verified_target_application"
    )
    assert int(summary["broker_vendor_mapping_application_count"]) == 2
    assert int(summary["broker_vendor_unique_mapping_applications"]) == 2
    assert summary["broker_vendor_target_application_coverage"] == 1.0
    assert not bool(summary["broker_vendor_application_lineage_consistency_required"])
    assert not bool(summary["broker_vendor_application_lineage_consistent"])
    assert bool(summary["broker_vendor_lineage_match_required"])
    assert bool(summary["broker_vendor_lineage_matches"])
    assert len(summary["vendor_application_lineage_sha256"]) == 64
    assert summary["vendor_application_lineage_sha256"] == (
        summary["broker_vendor_application_lineage_sha256"]
    )
    assert broker_summary[
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode"
    ] == "per_dataset_verified_target_application"
    assert int(
        broker_summary[
            "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count"
        ]
    ) == 2
    assert broker_summary[
        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage"
    ] == 1.0
    assert bool(report.checks["passed"].all())
    assert {
        "mapping_application_count",
        "unique_mapping_applications",
        "target_application_coverage",
        "broker_vendor_mapping_application_count",
        "broker_vendor_unique_mapping_applications",
        "broker_vendor_target_application_coverage",
        "broker_vendor_lineage_matches_current_batch",
    }.issubset(set(report.checks["check"]))
    assert {
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_source_mode",
        "broker_dispatch_roundtrip_vendor_market_data_batch_mapping_application_count",
        "broker_dispatch_roundtrip_vendor_market_data_batch_unique_mapping_applications",
        "broker_dispatch_roundtrip_vendor_market_data_batch_target_application_coverage",
        "broker_dispatch_roundtrip_vendor_market_data_batch_application_lineage_datasets",
        "broker_dispatch_roundtrip_vendor_market_data_batch_matches_current_vendor_lineage",
    }.issubset(set(report.broker_readiness.checks["check"]))
    vendor_config = config["vendor_market_data_batch"]
    assert vendor_config["mapping_application_count"] == 2
    assert vendor_config["unique_mapping_applications"] == 2
    assert vendor_config["target_application_coverage"] == 1.0
    assert len(vendor_config["application_lineage_sha256"]) == 64
    broker_vendor_config = config["broker_readiness"]["vendor_market_data_batch"]
    assert broker_vendor_config["mapping_application_count"] == 2
    assert broker_vendor_config["mapping_source_mode"] == (
        "per_dataset_verified_target_application"
    )
    assert broker_vendor_config["target_application_coverage"] == 1.0
    assert broker_vendor_config["unique_mapping_applications"] == 2
    assert not broker_vendor_config["application_lineage_consistency_required"]
    assert not broker_vendor_config["application_lineage_consistent"]
    assert broker_vendor_config["current_vendor_lineage_match_required"]
    assert broker_vendor_config["matches_current_vendor_lineage"]
    assert broker_vendor_config["application_lineage_sha256"] == (
        vendor_config["application_lineage_sha256"]
    )
    nested_vendor_config = broker_config["dispatch_roundtrip"][
        "broker_dispatch_roundtrip_vendor_market_data_batch"
    ]
    assert nested_vendor_config["mapping_application_count"] == 2
    assert nested_vendor_config["unique_mapping_applications"] == 2
    assert nested_vendor_config["target_application_coverage"] == 1.0
    assert len(nested_vendor_config["datasets"]) == 2
    assert all(
        dataset["mapping_application_id"]
        and dataset["mapping_scope_review_id"]
        and dataset["target_intake_receipt_id"]
        and dataset["applied_mapping_sha256"]
        for dataset in nested_vendor_config["datasets"]
    )
    assert len(manifest["inputs"]["mapping_applications"]) == 2
    assert len(manifest["inputs"]["mapping_application_manifests"]) == 2
    assert len(manifest["inputs"]["mapping_application_receipts"]) == 2
    assert manifest["inputs"]["vendor_market_data_batch_manifest"]["path"].endswith(
        "01_vendor_market_data_batch\\manifest.json"
    )
    assert manifest["parameters"]["mapping_source"] == (
        "per_dataset_verified_target_application"
    )
    assert manifest["parameters"]["mapping_application_count"] == 2
    assert "- Mapping applications: 2" in runbook
    assert "- Target-application coverage: 1.000" in runbook
    assert "- Broker target-application coverage: 1.000" in runbook
    assert "- Final target-lineage consistency required: no" in runbook
    assert "- Current/final target lineage matches: yes" in runbook

    final_vendor_config = json.loads(json.dumps(nested_vendor_config))
    final_vendor_config["application_lineage_consistency_required"] = True
    final_vendor_config["application_lineage_consistent"] = True
    final_lineage_sha256 = str(summary["vendor_application_lineage_sha256"])
    final_vendor_config["application_lineage_sha256"] = final_lineage_sha256
    roundtrip_config_path = (
        evidence["roundtrip"] / "broker_dispatch_roundtrip_config.json"
    )
    final_roundtrip_config = json.loads(
        roundtrip_config_path.read_text(encoding="utf-8")
    )
    final_roundtrip_config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch"
    ] = final_vendor_config
    final_roundtrip_config[
        "roundtrip_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = target_application_lineage_comparison(final_vendor_config)
    final_roundtrip_config[
        "roundtrip_final_broker_dispatch_roundtrip_vendor_market_data_batch_lineage_comparison"
    ] = roundtrip_final_target_application_lineage_comparison(
        final_vendor_config
    )
    add_roundtrip_complete_final_target_application_lineage(
        final_roundtrip_config,
        final_vendor_config,
    )
    roundtrip_config_path.write_text(
        json.dumps(final_roundtrip_config, indent=2) + "\n",
        encoding="utf-8",
    )
    refresh_dispatch_manifest(evidence["roundtrip"] / "manifest.json")

    cli_out = tmp_path / "broker_vendor_target_cli"
    cli_args = [
        "pipeline-broker-vendor-readiness",
        "--input",
        *(str(path) for path in source_paths),
        "--label",
        "cli_day1",
        "--label",
        "cli_day2",
        "--out",
        str(cli_out),
    ]
    for application_dir in application_dirs:
        cli_args.extend(["--mapping-application", str(application_dir)])
    cli_args.extend(
        [
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--schema-audit",
            str(evidence["schema"]),
            "--order-export",
            str(evidence["export"]),
            "--upload-pack",
            str(evidence["upload"]),
            "--dispatch-roundtrip",
            str(evidence["roundtrip"]),
            "--allow-placeholder-schema",
            "--require-dispatch-roundtrip",
            "--fail-on-breach",
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert main(cli_args) == 0
    cli_summary = pd.read_csv(
        cli_out / "broker_vendor_data_readiness_summary.csv"
    ).iloc[0]
    cli_checks = pd.read_csv(
        cli_out / "broker_vendor_data_readiness_checks.csv"
    )
    cli_config = json.loads(
        (cli_out / "broker_vendor_data_readiness_config.json").read_text(
            encoding="utf-8"
        )
    )
    assert int(cli_summary["mapping_application_count"]) == 2
    assert int(cli_summary["broker_vendor_mapping_application_count"]) == 2
    assert bool(cli_summary["broker_vendor_application_lineage_consistency_required"])
    assert bool(cli_summary["broker_vendor_application_lineage_consistent"])
    assert bool(cli_summary["broker_vendor_lineage_match_required"])
    assert bool(cli_summary["broker_vendor_lineage_matches"])
    assert cli_summary["vendor_application_lineage_sha256"] == (
        cli_summary["broker_vendor_application_lineage_sha256"]
    )
    assert {
        "broker_vendor_application_lineage_consistent",
        "broker_vendor_lineage_matches_current_batch",
    }.issubset(set(cli_checks["check"]))
    cli_broker_vendor = cli_config["broker_readiness"]["vendor_market_data_batch"]
    assert cli_broker_vendor["application_lineage_consistency_required"]
    assert cli_broker_vendor["application_lineage_consistent"]
    assert cli_broker_vendor["current_vendor_lineage_match_required"]
    assert cli_broker_vendor["matches_current_vendor_lineage"]


def test_broker_vendor_data_readiness_rejects_bad_application_alignment_before_root(
    tmp_path,
):
    application_dirs, source_paths, _ = target_mapping_application_batch(
        tmp_path,
        "broker_vendor_binding",
        ["2026-07-15", "2026-07-16"],
    )

    count_out = tmp_path / "broker_vendor_count_out"
    with pytest.raises(ValueError, match="one for one"):
        write_broker_vendor_data_readiness_pipeline(
            source_paths,
            output_dir=count_out,
            mapping_application_dirs=application_dirs[:1],
        )
    assert not count_out.exists()

    swapped_out = tmp_path / "broker_vendor_swapped_out"
    with pytest.raises(ValueError, match="exact target source"):
        write_broker_vendor_data_readiness_pipeline(
            source_paths,
            output_dir=swapped_out,
            mapping_application_dirs=list(reversed(application_dirs)),
        )
    assert not swapped_out.exists()


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
            "--max-null-rows",
            "2",
            "--max-nonfinite-rows",
            "3",
            "--max-nonintegral-rows",
            "4",
            "--max-duplicate-tick-rows",
            "5",
            "--max-integer-overflow-rows",
            "6",
            "--max-nonmonotonic-rows",
            "7",
            "--max-nonpositive-strike-rows",
            "8",
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
    vendor_config = json.loads(
        (
            out_dir
            / "01_vendor_market_data_batch"
            / "vendor_market_data_batch_config.json"
        ).read_text(encoding="utf-8")
    )
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
    assert vendor_config["data_readiness_thresholds"]["max_null_rows"] == 2
    assert vendor_config["data_readiness_thresholds"]["max_nonfinite_rows"] == 3
    assert vendor_config["data_readiness_thresholds"]["max_nonintegral_rows"] == 4
    assert vendor_config["data_readiness_thresholds"]["max_duplicate_tick_rows"] == 5
    assert vendor_config["data_readiness_thresholds"]["max_integer_overflow_rows"] == 6
    assert vendor_config["data_readiness_thresholds"]["max_nonmonotonic_rows"] == 7
    assert vendor_config["data_readiness_thresholds"][
        "max_nonpositive_strike_rows"
    ] == 8
    assert summary.loc[0, "adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(summary.loc[0, "placeholder_schema_allowed"])


def test_cli_broker_vendor_data_readiness_carries_chain_strike_grid(tmp_path):
    raw_path = tmp_path / "irage_chain.csv"
    pd.DataFrame(
        [
            {
                "exchange_ts": f"2026-06-10 09:15:0{offset}",
                "expiry_date": "2026-06-25",
                "strike_price": strike,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
            for offset, strike in enumerate((22500.0, 22525.0))
        ]
    ).to_csv(raw_path, index=False)
    out_dir = tmp_path / "chain_proof"

    code = main(
        [
            "pipeline-broker-vendor-readiness",
            "--input",
            str(raw_path),
            "--out",
            str(out_dir),
            "--adapter",
            "irage",
            "--kind",
            "chain",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--max-quote-spread-ticks",
            "10",
            "--max-wide-spread-rows",
            "0",
            "--max-unchanged-bbo-ns",
            "5000000000",
            "--max-stale-bbo-rows",
            "0",
            "--min-daily-observation-span-ns",
            "1000000000",
            "--strike-step",
            "50",
            "--max-off-grid-strike-rows",
            "1",
            "--allow-placeholder-schema",
            "--skip-schema-audit",
            "--skip-order-export",
            "--skip-upload-pack",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(
        out_dir / "broker_vendor_data_readiness_summary.csv"
    )
    config = json.loads(
        (out_dir / "broker_vendor_data_readiness_config.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert code == 0
    assert bool(summary.loc[0, "strike_grid_validation_enabled"])
    assert summary.loc[0, "strike_grid_step"] == 50.0
    assert int(summary.loc[0, "off_grid_strike_rows"]) == 1
    assert bool(summary.loc[0, "quote_spread_validation_enabled"])
    assert summary.loc[0, "max_quote_spread_ticks"] == 10.0
    assert int(summary.loc[0, "wide_spread_rows"]) == 0
    assert bool(summary.loc[0, "bbo_staleness_validation_enabled"])
    assert int(summary.loc[0, "max_unchanged_bbo_ns"]) == 5_000_000_000
    assert int(summary.loc[0, "stale_bbo_rows"]) == 0
    assert int(summary.loc[0, "observation_days"]) == 1
    assert (
        int(summary.loc[0, "min_daily_observation_span_ns"])
        == 1_000_000_000
    )
    assert config["vendor_market_data_batch"][
        "strike_grid_validation_enabled"
    ]
    assert config["vendor_market_data_batch"]["off_grid_strike_rows"] == 1
    assert config["vendor_market_data_batch"][
        "quote_spread_validation_enabled"
    ]
    assert config["vendor_market_data_batch"]["wide_spread_rows"] == 0
    assert config["vendor_market_data_batch"][
        "bbo_staleness_validation_enabled"
    ]
    assert (
        config["vendor_market_data_batch"]["max_unchanged_bbo_ns"]
        == 5_000_000_000
    )
    assert config["vendor_market_data_batch"]["stale_bbo_rows"] == 0
    assert (
        config["vendor_market_data_batch"][
            "min_daily_observation_span_ns"
        ]
        == 1_000_000_000
    )
    assert manifest["parameters"]["config"]["strike_step"] == 50.0
    assert manifest["parameters"]["config"]["max_quote_spread_ticks"] == 10.0
    assert manifest["parameters"]["config"]["max_wide_spread_rows"] == 0
    assert (
        manifest["parameters"]["config"]["max_unchanged_bbo_ns"]
        == 5_000_000_000
    )
    assert manifest["parameters"]["config"]["max_stale_bbo_rows"] == 0
    assert (
        manifest["parameters"]["config"][
            "min_daily_observation_span_ns"
        ]
        == 1_000_000_000
    )
    assert (
        manifest["parameters"]["config"]["max_off_grid_strike_rows"] == 1
    )


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
