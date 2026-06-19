import json

import pandas as pd

from hft_cli import main
from reports.data_readiness_comparison import (
    DataReadinessComparisonThresholds,
    compare_data_readiness,
    write_data_readiness_comparison,
)


def readiness_runs():
    return pd.DataFrame(
        [
            {
                "dataset": "2026-06-10",
                "ready": True,
                "components": 6,
                "required_components": 3,
                "provided_components": 6,
                "ready_components": 6,
                "failed_checks": 0,
                "recommendation": "feed_strategy_research",
            },
            {
                "dataset": "2026-06-11",
                "ready": True,
                "components": 6,
                "required_components": 3,
                "provided_components": 6,
                "ready_components": 6,
                "failed_checks": 0,
                "recommendation": "feed_strategy_research",
            },
        ]
    )


def write_readiness_dir(
    path,
    *,
    ready=True,
    failed_checks=0,
    source_hash="",
    header_hash="",
    mapping_hash="",
    mapping_coverage=1.0,
):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "ready": ready,
                "components": 6,
                "required_components": 3,
                "provided_components": 6,
                "ready_components": 6 if ready else 5,
                "failed_checks": failed_checks,
                "vendor_intake_source_file_sha256": source_hash,
                "vendor_intake_source_header_sha256": header_hash,
                "vendor_intake_mapping_draft_sha256": mapping_hash,
                "vendor_intake_mapping_coverage": mapping_coverage,
                "recommendation": "feed_strategy_research" if ready else "fix_data_readiness_gaps",
            }
        ]
    ).to_csv(path / "data_readiness_summary.csv", index=False)


def test_compare_data_readiness_accepts_multiple_clean_datasets():
    report = compare_data_readiness(
        readiness_runs(),
        thresholds=DataReadinessComparisonThresholds(min_datasets=2, min_ready_rate=1.0),
    )

    assert report.accepted
    row = report.summary.iloc[0]
    assert row["dataset_count"] == 2
    assert row["ready_rate"] == 1.0
    assert row["recommendation"] == "feed_walkforward_research"


def test_compare_data_readiness_can_require_unique_vendor_sources():
    runs = readiness_runs()
    runs["source_file_sha256"] = "a" * 64

    report = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            min_ready_rate=1.0,
            min_unique_source_files=2,
        ),
    )

    row = report.summary.iloc[0]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert row["unique_source_files"] == 1
    assert row["source_file_fingerprint_coverage"] == 1.0
    assert "unique_source_files" in failed
    assert report.action_queue is not None
    queue = report.action_queue.set_index("check")
    assert queue.loc["unique_source_files", "next_gate"] == "pipeline-vendor-market-data-batch"
    assert queue.loc["unique_source_files", "next_gate_help_command"] == (
        "python -m hft_cli pipeline-vendor-market-data-batch --help"
    )


def test_compare_data_readiness_can_require_source_fingerprint_coverage():
    runs = readiness_runs()
    runs.loc[0, "source_file_sha256"] = "a" * 64
    runs.loc[1, "source_file_sha256"] = ""

    report = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            min_ready_rate=1.0,
            min_source_file_fingerprint_coverage=1.0,
        ),
    )

    row = report.summary.iloc[0]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert row["source_file_fingerprint_coverage"] == 0.5
    assert "source_file_fingerprint_coverage" in failed


def test_compare_data_readiness_can_require_min_mapping_coverage():
    runs = readiness_runs()
    runs.loc[0, "mapping_coverage"] = 1.0
    runs.loc[1, "mapping_coverage"] = 0.8

    report = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            min_ready_rate=1.0,
            min_mapping_coverage=0.95,
        ),
    )

    row = report.summary.iloc[0]
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert not report.accepted
    assert row["min_mapping_coverage"] == 0.8
    assert "min_mapping_coverage" in failed


def test_compare_data_readiness_fails_on_missing_ready_dataset():
    runs = readiness_runs()
    runs.loc[1, "ready"] = False
    runs.loc[1, "failed_checks"] = 1

    report = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(min_datasets=2, min_ready_rate=1.0),
    )

    assert not report.accepted
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert {"ready_datasets", "ready_rate", "total_failed_checks"} <= failed
    assert report.action_queue is not None
    queue = report.action_queue.set_index("check")
    assert queue.loc["ready_datasets", "next_gate"] == "review-data-readiness"
    assert report.summary.loc[0, "next_gate"] == "review-data-readiness"


def test_write_data_readiness_comparison_outputs_artifacts(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    blocked_gate_dir = tmp_path / "comparison_blocked_gate"
    action_gate_dir = tmp_path / "comparison_action_gate"
    write_readiness_dir(day1, source_hash="a" * 64, header_hash="b" * 64, mapping_hash="c" * 64)
    write_readiness_dir(day2, source_hash="d" * 64, header_hash="b" * 64, mapping_hash="c" * 64)

    report = write_data_readiness_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["2026-06-10", "2026-06-11"],
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )

    assert report.accepted
    assert report.output_dir == out_dir
    assert report.dataset_runs.loc[0, "source_file_sha256"] == "a" * 64
    assert report.summary.loc[0, "unique_source_files"] == 2
    assert report.summary.loc[0, "source_file_fingerprint_coverage"] == 1.0
    assert report.summary.loc[0, "unique_header_fingerprints"] == 1
    assert report.summary.loc[0, "unique_mapping_drafts"] == 1
    assert (out_dir / "data_readiness_runs.csv").exists()
    assert (out_dir / "data_readiness_comparison_checks.csv").exists()
    assert (out_dir / "data_readiness_comparison_summary.csv").exists()
    assert (out_dir / "data_readiness_comparison_action_queue.csv").exists()
    assert (out_dir / "data_readiness_comparison_config.json").exists()
    assert (out_dir / "data_readiness_comparison_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "data_readiness_comparison_action_queue.csv")
    config = json.loads((out_dir / "data_readiness_comparison_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "data_readiness_comparison_runbook.md").read_text(encoding="utf-8")
    assert action_queue.empty
    assert "next_gate_help_command" in action_queue.columns
    assert config["accepted"]
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert "# Data Readiness Comparison Runbook" in runbook
    assert "- Accepted: yes" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "data_readiness_comparison_action_queue.csv" in artifact_paths
    assert "data_readiness_comparison_config.json" in artifact_paths
    assert "data_readiness_comparison_runbook.md" in artifact_paths

    blocked_gate_code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(blocked_gate_dir),
            "--min-datasets",
            "2",
            "--fail-on-blocked-actions",
        ]
    )
    action_gate_code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(action_gate_dir),
            "--min-datasets",
            "2",
            "--fail-on-actions",
        ]
    )
    assert blocked_gate_code == 0
    assert action_gate_code == 0


def test_cli_compare_data_readiness_can_fail_on_bad_dataset(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    blocked_gate_dir = tmp_path / "comparison_blocked_gate"
    action_gate_dir = tmp_path / "comparison_action_gate"
    write_readiness_dir(day1)
    write_readiness_dir(day2, ready=False, failed_checks=1)

    code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(out_dir),
            "--min-datasets",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_comparison_summary.csv")
    queue = pd.read_csv(out_dir / "data_readiness_comparison_action_queue.csv")
    config = json.loads((out_dir / "data_readiness_comparison_config.json").read_text(encoding="utf-8"))
    runbook = (out_dir / "data_readiness_comparison_runbook.md").read_text(encoding="utf-8")
    assert code == 2
    assert not bool(summary.loc[0, "accepted"])
    assert summary.loc[0, "next_gate"] == "review-data-readiness"
    assert not config["accepted"]
    assert config["blocked_action_count"] == len(queue)
    assert config["ready_action_count"] == 0
    assert config["next_gate"] == queue.loc[0, "next_gate"]
    assert config["next_gate_help_command"] == queue.loc[0, "next_gate_help_command"]
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["check"] == queue.loc[0, "check"]
    assert config["primary_action"]["next_gate"] == "review-data-readiness"
    assert config["ready_actions"] == []
    assert {item["check"] for item in config["next_actions"]} == set(queue["check"])
    assert {item["check"] for item in config["blocked_actions"]} == set(queue["check"])
    assert "review-data-readiness" in set(queue["next_gate"])
    assert "`review-data-readiness`" in runbook

    blocked_gate_code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(blocked_gate_dir),
            "--min-datasets",
            "2",
            "--fail-on-blocked-actions",
        ]
    )
    action_gate_code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(action_gate_dir),
            "--min-datasets",
            "2",
            "--fail-on-actions",
        ]
    )
    assert blocked_gate_code == 2
    assert action_gate_code == 2


def test_cli_compare_data_readiness_can_fail_on_missing_source_fingerprint(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(day1, source_hash="a" * 64)
    write_readiness_dir(day2)

    code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(out_dir),
            "--min-datasets",
            "2",
            "--min-source-file-fingerprint-coverage",
            "1.0",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_comparison_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_comparison_checks.csv")
    queue = pd.read_csv(out_dir / "data_readiness_comparison_action_queue.csv")
    assert code == 2
    assert not bool(summary.loc[0, "accepted"])
    assert summary.loc[0, "source_file_fingerprint_coverage"] == 0.5
    assert "source_file_fingerprint_coverage" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert queue.loc[0, "next_gate"] == "pipeline-vendor-market-data-batch"


def test_cli_compare_data_readiness_can_fail_on_low_mapping_coverage(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(day1, source_hash="a" * 64, mapping_coverage=1.0)
    write_readiness_dir(day2, source_hash="d" * 64, mapping_coverage=0.8)

    code = main(
        [
            "compare-data-readiness",
            "--readiness",
            str(day1),
            str(day2),
            "--out",
            str(out_dir),
            "--min-datasets",
            "2",
            "--min-mapping-coverage",
            "0.95",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "data_readiness_comparison_summary.csv")
    checks = pd.read_csv(out_dir / "data_readiness_comparison_checks.csv")
    queue = pd.read_csv(out_dir / "data_readiness_comparison_action_queue.csv")
    assert code == 2
    assert not bool(summary.loc[0, "accepted"])
    assert summary.loc[0, "min_mapping_coverage"] == 0.8
    assert "min_mapping_coverage" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert queue.loc[0, "recommendation"] == "improve_vendor_mapping_coverage"
