import json

import pandas as pd

from hft_cli import main
from reports.data_readiness import (
    DATA_READINESS_REQUIRED_ARTIFACTS,
    DATA_READINESS_RUN_TYPE,
)
from reports.data_readiness_comparison import (
    DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
    DATA_READINESS_COMPARISON_RUN_TYPE,
    DataReadinessComparisonThresholds,
    compare_data_readiness,
    load_data_readiness_comparison_evidence,
    verify_data_readiness_comparison,
    write_data_readiness_comparison,
)
from reports.market_calendar import write_market_calendar_report
from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)
from tests.data_readiness_helpers import (
    reseal_experiment_manifest,
    write_manifest_bound_data_readiness,
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
    market_calendar_dir=None,
):
    return write_manifest_bound_data_readiness(
        path,
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
            "recommendation": (
                "feed_strategy_research"
                if ready
                else "fix_data_readiness_gaps"
            ),
        },
        source_text=f"source_hash\n{source_hash or path.name}\n",
        market_calendar_dir=market_calendar_dir,
    )


def reseal_comparison_report(path):
    reseal_experiment_manifest(path)


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


def test_compare_data_readiness_requires_one_calendar_source():
    runs = readiness_runs()
    runs["market_calendar_id"] = "nse-fo-test-2026-06"
    runs["market_calendar_sha256"] = "e" * 64
    runs["market_calendar_valid_from"] = "2026-06-01"
    runs["market_calendar_valid_to"] = "2026-06-30"

    accepted = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            require_market_calendar=True,
            require_consistent_market_calendar=True,
        ),
    )
    assert accepted.accepted
    assert accepted.summary.loc[0, "market_calendar_coverage"] == 1.0
    assert accepted.summary.loc[0, "unique_market_calendar_fingerprints"] == 1

    runs.loc[1, "market_calendar_sha256"] = "f" * 64
    rejected = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            require_market_calendar=True,
            require_consistent_market_calendar=True,
        ),
    )
    failed = set(rejected.checks.loc[~rejected.checks["passed"], "check"])
    assert not rejected.accepted
    assert "unique_market_calendar_fingerprints" in failed
    assert rejected.action_queue is not None
    action = rejected.action_queue.set_index("check").loc[
        "unique_market_calendar_fingerprints"
    ]
    assert action["next_gate"] == "market-calendar-report"


def test_compare_data_readiness_rejects_partial_calendar_coverage():
    runs = readiness_runs()
    runs.loc[0, "market_calendar_id"] = "nse-fo-test-2026-06"
    runs.loc[0, "market_calendar_sha256"] = "e" * 64
    runs.loc[0, "market_calendar_valid_from"] = "2026-06-01"
    runs.loc[0, "market_calendar_valid_to"] = "2026-06-30"

    report = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            require_market_calendar=True,
        ),
    )

    assert not report.accepted
    assert report.summary.loc[0, "market_calendar_coverage"] == 0.5
    assert "market_calendar_coverage" in set(
        report.checks.loc[~report.checks["passed"], "check"]
    )


def test_cli_comparison_requires_consistent_calendar(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    calendar_source = tmp_path / "calendar.json"
    calendar_dir = tmp_path / "calendar_report"
    calendar_source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calendar_id": "nse-fo-test-2026-06",
                "market": "india_nse_index_derivatives",
                "timezone": "Asia/Kolkata",
                "valid_from": "2026-06-01",
                "valid_to": "2026-06-30",
                "provenance": {
                    "publisher": "test-exchange",
                    "source_url": "https://example.test/calendar",
                    "published_date": "2026-05-01",
                },
                "sessions": [],
            }
        ),
        encoding="utf-8",
    )
    write_market_calendar_report(
        calendar_source,
        calendar_dir,
        expected_market="india_nse_index_derivatives",
    )
    write_readiness_dir(day1, market_calendar_dir=calendar_dir)
    write_readiness_dir(day2, market_calendar_dir=calendar_dir)

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
            "--require-market-calendar",
            "--require-consistent-market-calendar",
            "--fail-on-breach",
        ]
    )

    assert code == 0
    summary = pd.read_csv(out_dir / "data_readiness_comparison_summary.csv")
    assert summary.loc[0, "market_calendar_coverage"] == 1.0
    assert summary.loc[0, "unique_market_calendar_fingerprints"] == 1


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


def test_compare_data_readiness_requires_distinct_local_observation_dates():
    runs = readiness_runs()
    runs["observation_dates"] = "2026-06-10"

    blocked = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            min_unique_observation_dates=2,
        ),
    )

    blocked_summary = blocked.summary.iloc[0]
    failed = set(
        blocked.checks.loc[
            ~blocked.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not blocked.accepted
    assert blocked_summary["observation_dates"] == "2026-06-10"
    assert int(blocked_summary["unique_observation_dates"]) == 1
    assert int(
        blocked_summary["overlapping_observation_date_memberships"]
    ) == 1
    assert "unique_observation_dates" in failed
    action = blocked.action_queue.set_index("check").loc[
        "unique_observation_dates"
    ]
    assert action["next_gate"] == "pipeline-vendor-market-data-batch"
    assert action["recommendation"] == "collect_additional_vendor_data_days"

    runs.loc[1, "observation_dates"] = "2026-06-11"
    accepted = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            min_unique_observation_dates=2,
        ),
    )

    assert accepted.accepted
    assert accepted.summary.loc[0, "observation_dates"] == (
        "2026-06-10;2026-06-11"
    )
    assert int(accepted.summary.loc[0, "unique_observation_dates"]) == 2


def test_compare_data_readiness_fails_closed_on_missing_or_invalid_dates():
    runs = readiness_runs()
    runs["observation_dates"] = ["2026-06-10", "not-a-date"]

    report = compare_data_readiness(
        runs,
        thresholds=DataReadinessComparisonThresholds(
            min_datasets=2,
            min_unique_observation_dates=2,
        ),
    )

    failed = set(
        report.checks.loc[
            ~report.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert not report.accepted
    assert report.summary.loc[0, "observation_date_coverage"] == 0.5
    assert int(
        report.summary.loc[0, "observation_date_parse_error_count"]
    ) == 1
    assert {
        "observation_date_coverage",
        "observation_date_parse_error_count",
        "unique_observation_dates",
    }.issubset(failed)


def test_cli_comparison_requires_manifest_bound_observation_dates(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(day1, source_hash="a" * 64)
    write_readiness_dir(day2, source_hash="b" * 64)

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
            "--min-unique-observation-dates",
            "2",
            "--fail-on-breach",
        ]
    )

    checks = pd.read_csv(
        out_dir / "data_readiness_comparison_checks.csv"
    )
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert code == 2
    assert {
        "observation_date_coverage",
        "unique_observation_dates",
    }.issubset(failed)


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
    assert report.summary.loc[0, "data_readiness_manifest_coverage"] == 1.0
    assert report.summary.loc[0, "current_data_readiness_manifests"] == 2
    assert bool(report.summary.loc[0, "non_authorizing"])
    assert not bool(report.summary.loc[0, "authorizes_routing"])
    assert not bool(report.summary.loc[0, "authorizes_submission"])
    assert report.dataset_runs["data_readiness_manifest_current"].all()
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
    assert config["non_authorizing"]
    assert not config["authorizes_routing"]
    assert not config["authorizes_submission"]
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 0
    assert config["next_gate"] == ""
    assert config["next_gate_help_command"] == ""
    assert config["primary_action_status"] == ""
    assert config["primary_action"] == {}
    assert config["next_actions"] == []
    assert config["ready_actions"] == []
    assert config["blocked_actions"] == []
    assert config["data_readiness_lineage"]["manifest_required"]
    assert config["data_readiness_lineage"]["current_manifests"] == 2
    assert config["data_readiness_lineage"]["manifest_coverage"] == 1.0
    assert config["data_readiness_lineage"]["dependency_count"] == 2
    assert "# Data Readiness Comparison Runbook" in runbook
    assert "- Accepted: yes" in runbook
    assert "- Non-authorizing: yes" in runbook
    assert "- Authorizes routing: no" in runbook
    assert "- Authorizes submission: no" in runbook
    assert "- Current readiness-manifest coverage: 1" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "data_readiness_comparison_action_queue.csv" in artifact_paths
    assert "data_readiness_comparison_config.json" in artifact_paths
    assert "data_readiness_comparison_runbook.md" in artifact_paths
    assert set(manifest["inputs"]) == {
        "readiness",
        "readiness_dependencies",
        "readiness_manifests",
    }
    assert manifest["extra"] == {
        "accepted": True,
        "non_authorizing": True,
        "authorizes_routing": False,
        "authorizes_submission": False,
    }
    verification = verify_data_readiness_comparison(out_dir)
    evidence = load_data_readiness_comparison_evidence(out_dir)
    assert verification.verified
    assert verification.accepted
    assert verification.manifest_current
    assert verification.inputs_current
    assert verification.artifacts_consistent
    assert verification.non_authorizing
    assert evidence.passed
    assert evidence.semantically_verified
    assert (
        main(
            [
                "verify-data-readiness-comparison",
                "--report",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 0
    )

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


def test_write_data_readiness_comparison_rejects_loose_summary(tmp_path):
    loose = tmp_path / "loose"
    current = tmp_path / "current"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(loose)
    write_readiness_dir(current)
    (loose / "manifest.json").unlink()

    report = write_data_readiness_comparison(
        [loose, current],
        output_dir=out_dir,
        labels=["loose", "current"],
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )

    assert not report.accepted
    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert "data_readiness_manifest_coverage" in failed
    assert report.summary.loc[0, "data_readiness_manifest_coverage"] == 0.5
    loose_row = report.dataset_runs.set_index("dataset").loc["loose"]
    assert loose_row["reported_ready"]
    assert not loose_row["ready"]
    assert not loose_row["data_readiness_manifest_current"]
    assert loose_row["data_readiness_manifest_error"] == "manifest_missing"
    queue = report.action_queue.set_index("check")
    assert (
        queue.loc["data_readiness_manifest_coverage", "next_gate"]
        == "review-data-readiness"
    )
    assert queue.loc[
        "data_readiness_manifest_coverage",
        "recommendation",
    ] == "regenerate_current_manifest_bound_data_readiness"


def test_write_data_readiness_comparison_rejects_stale_readiness_input(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    source1 = write_readiness_dir(day1)
    write_readiness_dir(day2)
    source1.write_text("source_hash\nchanged\n", encoding="utf-8")

    readiness_integrity = verify_experiment_manifest(
        day1 / "manifest.json",
        expected_run_type=DATA_READINESS_RUN_TYPE,
        required_artifacts=DATA_READINESS_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    report = write_data_readiness_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["stale", "current"],
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )

    assert not readiness_integrity.passed
    assert readiness_integrity.error == "input_drift"
    assert not report.accepted
    stale = report.dataset_runs.set_index("dataset").loc["stale"]
    assert stale["reported_ready"]
    assert not stale["ready"]
    assert stale["data_readiness_manifest_error"] == "input_drift"
    assert report.summary.loc[0, "data_readiness_manifest_coverage"] == 0.5


def test_comparison_rejects_resealed_semantic_readiness_tamper(
    tmp_path,
):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(day1)
    write_readiness_dir(day2)
    manifest_path = day1 / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary_path = day1 / "data_readiness_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "recommendation"] = "route_live_orders"
    summary.to_csv(summary_path, index=False)
    write_experiment_manifest(
        day1,
        run_type=manifest["run_type"],
        parameters=manifest["parameters"],
        inputs={
            name: value["path"]
            for name, value in manifest["inputs"].items()
        },
        extra=manifest["extra"],
    )

    integrity = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_RUN_TYPE,
        required_artifacts=DATA_READINESS_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    report = write_data_readiness_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["resealed", "current"],
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )

    assert integrity.passed
    assert not report.accepted
    assert report.summary.loc[0, "data_readiness_manifest_coverage"] == 1.0
    assert (
        report.summary.loc[
            0,
            "data_readiness_report_verification_coverage",
        ]
        == 0.5
    )
    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert "data_readiness_report_verification_coverage" in failed
    resealed = report.dataset_runs.set_index("dataset").loc["resealed"]
    assert resealed["data_readiness_manifest_current"]
    assert not resealed["data_readiness_report_verified"]
    assert not resealed["data_readiness_report_artifacts_consistent"]
    queue = report.action_queue.set_index("check")
    assert (
        queue.loc[
            "data_readiness_report_verification_coverage",
            "recommendation",
        ]
        == "regenerate_semantically_verified_data_readiness"
    )


def test_comparison_verifier_rejects_resealed_authority_widening(
    tmp_path,
):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(day1)
    write_readiness_dir(day2)
    write_data_readiness_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )
    summary_path = out_dir / "data_readiness_comparison_summary.csv"
    summary = pd.read_csv(summary_path)
    summary.loc[0, "authorizes_routing"] = True
    summary.to_csv(summary_path, index=False)
    reseal_comparison_report(out_dir)

    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    verification = verify_data_readiness_comparison(out_dir)
    evidence = load_data_readiness_comparison_evidence(out_dir)
    record = evidence.summary.iloc[0]

    assert integrity.passed
    assert verification.manifest_current
    assert verification.inputs_current
    assert not verification.artifacts_consistent
    assert not verification.non_authorizing
    assert not verification.verified
    assert not evidence.passed
    assert evidence.reason == (
        "data_readiness_comparison_"
        "artifacts_do_not_reconstruct_from_inputs"
    )
    assert bool(record["accepted"])
    assert (
        main(
            [
                "verify-data-readiness-comparison",
                "--report",
                str(out_dir),
                "--fail-on-breach",
            ]
        )
        == 2
    )


def test_comparison_verifier_rejects_resealed_extra_artifact(
    tmp_path,
):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    write_readiness_dir(day1)
    write_readiness_dir(day2)
    write_data_readiness_comparison(
        [day1, day2],
        output_dir=out_dir,
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )
    (out_dir / "unexpected_order_payload.csv").write_text(
        "instrument_id,side,qty\nNIFTY_TEST,BUY,1\n",
        encoding="utf-8",
    )
    reseal_comparison_report(out_dir)

    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    verification = verify_data_readiness_comparison(out_dir)

    assert integrity.passed
    assert integrity.artifact_count == 7
    assert verification.manifest_current
    assert not verification.artifacts_consistent
    assert not verification.verified


def test_comparison_manifest_tracks_transitive_readiness_dependencies(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
    source1 = write_readiness_dir(day1)
    source2 = write_readiness_dir(day2)

    report = write_data_readiness_comparison(
        [day1, day2],
        output_dir=out_dir,
        labels=["day1", "day2"],
        thresholds=DataReadinessComparisonThresholds(min_datasets=2),
    )
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependency_paths = {
        item["path"]
        for item in manifest["inputs"]["readiness_dependencies"]
    }
    current = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )

    assert report.accepted
    assert current.passed
    assert dependency_paths == {
        str(source1.parent.resolve()),
        str(source2.parent.resolve()),
    }
    assert load_data_readiness_comparison_evidence(out_dir).passed

    day1_manifest = day1 / "manifest.json"
    original_manifest = day1_manifest.read_text(encoding="utf-8")
    refreshed_manifest = json.loads(original_manifest)
    refreshed_manifest["generated_at_utc"] = "2099-01-01T00:00:00+00:00"
    day1_manifest.write_text(
        json.dumps(refreshed_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_drift = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    assert not manifest_drift.passed
    assert manifest_drift.error == "input_drift"

    day1_manifest.write_text(original_manifest, encoding="utf-8")
    assert verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    ).passed

    source1.write_text("source_hash\nchanged-after-comparison\n", encoding="utf-8")

    drifted = verify_experiment_manifest(
        manifest_path,
        expected_run_type=DATA_READINESS_COMPARISON_RUN_TYPE,
        required_artifacts=DATA_READINESS_COMPARISON_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    evidence = load_data_readiness_comparison_evidence(out_dir)
    assert not drifted.passed
    assert drifted.error == "input_drift"
    assert not evidence.passed
    assert evidence.reason == "data_readiness_comparison_manifest_input_drift"
