import json

import pandas as pd

from hft_cli import main
from reports.vendor_data_onboarding import (
    VendorMarketDataPipelineConfig,
    write_vendor_market_data_batch_pipeline,
    write_vendor_market_data_pipeline,
)


def vendor_ticks(day: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "exchange_ts": f"{day} 09:15:00",
                "best_bid": 100.0,
                "best_ask": 100.05,
                "bid_size": 75,
                "ask_size": 150,
                "last_px": 100.05,
                "last_size": 75,
            },
            {
                "exchange_ts": f"{day} 09:15:01",
                "best_bid": 100.05,
                "best_ask": 100.10,
                "bid_size": 150,
                "ask_size": 75,
                "last_px": 100.10,
                "last_size": 75,
            },
        ]
    )


def test_vendor_market_data_pipeline_onboards_tick_file(tmp_path):
    raw = vendor_ticks("2026-06-10")
    raw_path = tmp_path / "arrow_ticks.csv"
    out_dir = tmp_path / "pipeline"
    raw.to_csv(raw_path, index=False)

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    components = report.components.set_index("component")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "vendor_market_data_pipeline_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "vendor_market_data_pipeline_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_pipeline_runbook.md").read_text(encoding="utf-8")
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert report.ready
    assert summary["normalized_rows"] == 2
    assert summary["mapping_coverage"] == 1.0
    assert summary["mapping_source"] == "vendor_intake_draft"
    assert summary["market"] == "india_nse_index_derivatives"
    assert summary["blocked_action_count"] == 0
    assert summary["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert "# Vendor Market Data Pipeline Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook
    assert summary["source_file_sha256"] == manifest["inputs"]["input"]["sha256"]
    assert len(summary["source_header_sha256"]) == 64
    assert len(summary["mapping_draft_sha256"]) == 64
    assert "vendor_intake_manifest" in manifest["inputs"]
    assert "vendor_intake_source_profile" in manifest["inputs"]
    assert "mapped_data_manifest" in manifest["inputs"]
    assert "data_readiness_manifest" in manifest["inputs"]
    assert config["ready"]
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert config["source"]["file_sha256"] == summary["source_file_sha256"]
    assert config["source"]["header_sha256"] == summary["source_header_sha256"]
    assert config["mapping"]["source"] == "vendor_intake_draft"
    assert config["mapping"]["draft_sha256"] == summary["mapping_draft_sha256"]
    assert config["data_readiness"]["ready"]
    assert config["data_readiness"]["thresholds"]["min_tick_rows"] == 2
    assert config["data_readiness"]["thresholds"]["expected_adapter"] == "arrow_money"
    assert config["data_readiness"]["thresholds"]["expected_vendor_data_kind"] == "ticks"
    assert config["component_manifests"]["vendor_intake"].endswith("manifest.json")
    assert components.loc["vendor_intake", "ready"]
    assert components.loc["data_readiness", "ready"]
    assert (out_dir / "01_vendor_intake" / "vendor_mapping_draft.csv").exists()
    assert (out_dir / "02_normalized" / "normalized_ticks.csv").exists()
    assert (out_dir / "03_diagnostics" / "diagnostic_summary.csv").exists()
    assert (out_dir / "04_data_readiness" / "data_readiness_summary.csv").exists()
    assert "vendor_market_data_pipeline_action_queue.csv" in artifact_paths
    assert "vendor_market_data_pipeline_runbook.md" in artifact_paths
    assert manifest["run_type"] == "vendor_market_data_pipeline"

    ready_code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(tmp_path / "pipeline_cli_ready"),
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
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert ready_code == 0


def test_vendor_market_data_batch_pipeline_compares_clean_tick_days(tmp_path):
    day1 = tmp_path / "arrow_ticks_day1.csv"
    day2 = tmp_path / "arrow_ticks_day2.csv"
    out_dir = tmp_path / "batch"
    vendor_ticks("2026-06-10").to_csv(day1, index=False)
    vendor_ticks("2026-06-11").to_csv(day2, index=False)

    report = write_vendor_market_data_batch_pipeline(
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    summary = report.summary.iloc[0]
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((out_dir / "vendor_market_data_batch_config.json").read_text(encoding="utf-8"))
    action_queue = pd.read_csv(out_dir / "vendor_market_data_batch_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(encoding="utf-8")
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert report.ready
    assert summary["dataset_count"] == 2
    assert summary["unique_source_files"] == 2
    assert summary["source_file_fingerprint_coverage"] == 1.0
    assert summary["min_mapping_coverage"] == 1.0
    assert summary["unique_header_fingerprints"] == 1
    assert summary["unique_mapping_drafts"] == 1
    assert summary["mapping_sources"] == "vendor_intake_draft"
    assert summary["comparison_accepted"]
    assert summary["market"] == "india_nse_index_derivatives"
    assert summary["blocked_action_count"] == 0
    assert summary["next_gate"] == ""
    assert report.action_queue is not None
    assert report.action_queue.empty
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert "# Vendor Market Data Batch Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook
    assert set(report.datasets["dataset"]) == {"day1", "day2"}
    assert report.datasets["source_file_sha256"].nunique() == 2
    assert report.datasets["source_header_sha256"].nunique() == 1
    assert "dataset_manifests" in manifest["inputs"]
    assert len(manifest["inputs"]["dataset_manifests"]) == 2
    assert "comparison_manifest" in manifest["inputs"]
    assert config["ready"]
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert config["dataset_count"] == 2
    assert config["unique_source_files"] == 2
    assert config["source_file_fingerprint_coverage"] == 1.0
    assert config["min_mapping_coverage"] == 1.0
    assert config["unique_header_fingerprints"] == 1
    assert config["unique_mapping_drafts"] == 1
    assert config["comparison"]["accepted"]
    assert config["comparison"]["thresholds"]["min_datasets"] == 2
    assert config["comparison"]["thresholds"]["min_source_file_fingerprint_coverage"] == 1.0
    assert config["comparison"]["thresholds"]["min_mapping_coverage"] == 1.0
    assert len(config["datasets"]) == 2
    assert config["datasets"][0]["data_readiness_manifest_path"].endswith("manifest.json")
    assert (out_dir / "datasets" / "day1" / "vendor_market_data_pipeline_summary.csv").exists()
    assert (out_dir / "comparison" / "data_readiness_comparison_summary.csv").exists()
    assert "vendor_market_data_batch_action_queue.csv" in artifact_paths
    assert "vendor_market_data_batch_runbook.md" in artifact_paths
    assert manifest["run_type"] == "vendor_market_data_batch_pipeline"

    ready_code = main(
        [
            "pipeline-vendor-market-data-batch",
            "--input",
            str(day1),
            str(day2),
            "--label",
            "cli_day1",
            "--label",
            "cli_day2",
            "--out",
            str(tmp_path / "batch_cli_ready"),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-datasets",
            "2",
            "--fail-on-blocked-actions",
            "--fail-on-actions",
        ]
    )
    assert ready_code == 0


def test_vendor_market_data_batch_fails_when_inputs_reuse_same_source_file(tmp_path):
    day1 = tmp_path / "arrow_ticks_day1.csv"
    out_dir = tmp_path / "batch"
    vendor_ticks("2026-06-10").to_csv(day1, index=False)

    report = write_vendor_market_data_batch_pipeline(
        [day1, day1],
        output_dir=out_dir,
        labels=["day1", "day1_copy"],
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="ticks",
            timestamp_unit="datetime",
            tick_size=0.05,
            min_rows=2,
        ),
    )

    checks = pd.read_csv(out_dir / "comparison" / "data_readiness_comparison_checks.csv")
    action_queue = pd.read_csv(out_dir / "vendor_market_data_batch_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "vendor_market_data_batch_config.json").read_text(encoding="utf-8"))
    summary = report.summary.iloc[0]
    assert not report.ready
    assert summary["ready_datasets"] == 2
    assert summary["unique_source_files"] == 1
    assert not summary["comparison_accepted"]
    assert summary["blocked_action_count"] > 0
    assert summary["next_gate"] == "pipeline-vendor-market-data-batch"
    assert summary["next_gate_help_command"] == "python -m hft_cli pipeline-vendor-market-data-batch --help"
    assert "unique_source_files" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "unique_source_files" in set(action_queue["check"])
    assert "pipeline-vendor-market-data-batch" in set(action_queue["next_gate"])
    assert config["blocked_action_count"] == len(action_queue)
    assert config["ready_action_count"] == 0
    assert config["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["next_gate_help_command"] == "python -m hft_cli pipeline-vendor-market-data-batch --help"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "unique_source_files"
    assert config["primary_action"]["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["ready_actions"] == []
    assert config["blocked_actions"][0]["check"] == "unique_source_files"
    assert config["blocked_actions"][0]["source"] == "comparison"
    assert config["blocked_actions"][0]["next_gate"] == "pipeline-vendor-market-data-batch"
    assert "# Vendor Market Data Batch Runbook" in runbook
    assert "- Ready: no" in runbook


def test_vendor_market_data_pipeline_onboards_option_chain_file(tmp_path):
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "expiry_date": "2026-06-25",
                "strike_price": 22500,
                "ce_bid": 100.0,
                "ce_ask": 100.5,
                "ce_bid_qty": 75,
                "ce_ask_qty": 150,
                "pe_bid": 90.0,
                "pe_ask": 90.5,
                "pe_bid_qty": 75,
                "pe_ask_qty": 150,
            }
        ]
    )
    raw_path = tmp_path / "arrow_chain.csv"
    out_dir = tmp_path / "pipeline"
    raw.to_csv(raw_path, index=False)

    report = write_vendor_market_data_pipeline(
        raw_path,
        output_dir=out_dir,
        config=VendorMarketDataPipelineConfig(
            adapter="arrow_money",
            kind="chain",
            timestamp_unit="datetime",
            tick_size=0.05,
        ),
    )

    diagnostics = pd.read_csv(out_dir / "03_diagnostics" / "diagnostic_summary.csv")
    assert report.ready
    assert report.summary.loc[0, "kind"] == "chain"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert set(diagnostics["scope"]) == {"overall", "expiry"}
    assert bool(pd.read_csv(out_dir / "04_data_readiness" / "data_readiness_summary.csv").loc[0, "ready"])


def test_cli_vendor_market_data_pipeline_fails_closed_on_incomplete_mapping(tmp_path):
    raw = pd.DataFrame(
        [
            {
                "exchange_ts": "2026-06-10 09:15:00",
                "best_bid": 100.0,
            }
        ]
    )
    raw_path = tmp_path / "partial_ticks.csv"
    out_dir = tmp_path / "pipeline"
    raw.to_csv(raw_path, index=False)

    code = main(
        [
            "pipeline-vendor-market-data",
            "--input",
            str(raw_path),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "vendor_market_data_pipeline_summary.csv")
    components = pd.read_csv(out_dir / "vendor_market_data_pipeline_components.csv")
    action_queue = pd.read_csv(out_dir / "vendor_market_data_pipeline_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_pipeline_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "vendor_market_data_pipeline_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "blocked_action_count"] > 0
    assert str(summary.loc[0, "next_gate"])
    assert str(summary.loc[0, "next_gate_help_command"]).startswith("python -m hft_cli ")
    assert "not_ready" in set(components["status"])
    assert not action_queue.empty
    assert str(action_queue.loc[0, "next_gate_help_command"]).startswith("python -m hft_cli ")
    assert config["blocked_action_count"] == len(action_queue)
    assert config["ready_action_count"] == 0
    assert config["next_gate"] == summary.loc[0, "next_gate"]
    assert config["next_gate_help_command"] == summary.loc[0, "next_gate_help_command"]
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["next_gate"] == summary.loc[0, "next_gate"]
    assert config["primary_action"]["next_gate_help_command"] == summary.loc[0, "next_gate_help_command"]
    assert config["ready_actions"] == []
    assert config["blocked_actions"][0]["next_gate"] == summary.loc[0, "next_gate"]
    assert config["blocked_actions"][0]["next_gate_help_command"] == summary.loc[0, "next_gate_help_command"]
    assert "# Vendor Market Data Pipeline Runbook" in runbook
    assert "- Ready: no" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook
    assert (out_dir / "04_data_readiness" / "data_readiness_summary.csv").exists()

    for flag, folder_name in [
        ("--fail-on-blocked-actions", "pipeline_blocked_action_gate"),
        ("--fail-on-actions", "pipeline_any_action_gate"),
    ]:
        gated_code = main(
            [
                "pipeline-vendor-market-data",
                "--input",
                str(raw_path),
                "--out",
                str(tmp_path / folder_name),
                "--adapter",
                "arrow_money",
                "--kind",
                "ticks",
                "--timestamp-unit",
                "datetime",
                flag,
            ]
        )
        assert gated_code == 2


def test_cli_vendor_market_data_batch_fails_closed_when_comparison_threshold_misses(tmp_path):
    day1 = tmp_path / "arrow_ticks_day1.csv"
    out_dir = tmp_path / "batch"
    vendor_ticks("2026-06-10").to_csv(day1, index=False)

    code = main(
        [
            "pipeline-vendor-market-data-batch",
            "--input",
            str(day1),
            "--out",
            str(out_dir),
            "--adapter",
            "arrow_money",
            "--kind",
            "ticks",
            "--timestamp-unit",
            "datetime",
            "--tick-size",
            "0.05",
            "--min-datasets",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "vendor_market_data_batch_summary.csv")
    checks = pd.read_csv(out_dir / "comparison" / "data_readiness_comparison_checks.csv")
    action_queue = pd.read_csv(out_dir / "vendor_market_data_batch_action_queue.csv")
    runbook = (out_dir / "vendor_market_data_batch_runbook.md").read_text(encoding="utf-8")
    config = json.loads((out_dir / "vendor_market_data_batch_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert summary.loc[0, "blocked_action_count"] > 0
    assert summary.loc[0, "next_gate"] == "pipeline-vendor-market-data-batch"
    assert summary.loc[0, "next_gate_help_command"] == "python -m hft_cli pipeline-vendor-market-data-batch --help"
    assert "dataset_count" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "dataset_count" in set(action_queue["check"])
    assert config["blocked_action_count"] == len(action_queue)
    assert config["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == "dataset_count"
    assert config["primary_action"]["next_gate"] == "pipeline-vendor-market-data-batch"
    assert config["blocked_actions"][0]["check"] == "dataset_count"
    assert config["blocked_actions"][0]["next_gate_help_command"] == (
        "python -m hft_cli pipeline-vendor-market-data-batch --help"
    )
    assert "# Vendor Market Data Batch Runbook" in runbook
    assert "- Ready: no" in runbook
    assert "- Market: india_nse_index_derivatives" in runbook

    for flag, folder_name in [
        ("--fail-on-blocked-actions", "batch_blocked_action_gate"),
        ("--fail-on-actions", "batch_any_action_gate"),
    ]:
        gated_code = main(
            [
                "pipeline-vendor-market-data-batch",
                "--input",
                str(day1),
                "--out",
                str(tmp_path / folder_name),
                "--adapter",
                "arrow_money",
                "--kind",
                "ticks",
                "--timestamp-unit",
                "datetime",
                "--tick-size",
                "0.05",
                "--min-datasets",
                "2",
                flag,
            ]
        )
        assert gated_code == 2
