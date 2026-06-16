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


def test_write_data_readiness_comparison_outputs_artifacts(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
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
    assert (out_dir / "manifest.json").exists()


def test_cli_compare_data_readiness_can_fail_on_bad_dataset(tmp_path):
    day1 = tmp_path / "day1"
    day2 = tmp_path / "day2"
    out_dir = tmp_path / "comparison"
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
    assert code == 2
    assert not bool(summary.loc[0, "accepted"])


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
    assert code == 2
    assert not bool(summary.loc[0, "accepted"])
    assert summary.loc[0, "source_file_fingerprint_coverage"] == 0.5
    assert "source_file_fingerprint_coverage" in set(checks.loc[~checks["passed"].astype(bool), "check"])
