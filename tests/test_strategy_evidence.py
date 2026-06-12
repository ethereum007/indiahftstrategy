import pandas as pd

from hft_cli import main
from reports.evidence import (
    EvidenceThresholds,
    evaluate_strategy_evidence,
    write_strategy_evidence_review,
)


def catalog_rows(*, dirty=False, commit="abc123"):
    return pd.DataFrame(
        [
            {
                "run_dir": "runs/proof",
                "run_type": "proof_report",
                "generated_at_utc": "2026-06-10T09:30:00Z",
                "git_commit": commit,
                "git_dirty": dirty,
                "summary_status": True,
                "summary_file": "proof_summary.csv",
            },
            {
                "run_dir": "runs/stress",
                "run_type": "stress_report",
                "generated_at_utc": "2026-06-10T09:35:00Z",
                "git_commit": commit,
                "git_dirty": dirty,
                "summary_status": True,
                "summary_file": "stress_summary.csv",
            },
            {
                "run_dir": "runs/promotion",
                "run_type": "promotion_report",
                "generated_at_utc": "2026-06-10T09:40:00Z",
                "git_commit": commit,
                "git_dirty": dirty,
                "summary_status": True,
                "summary_file": "promotion_summary.csv",
            },
        ]
    )


def test_strategy_evidence_passes_complete_clean_catalog():
    review = evaluate_strategy_evidence(
        catalog_rows(),
        thresholds=EvidenceThresholds(require_same_git_commit=True),
    )

    assert review.ready
    assert set(review.evidence["required_run_type"]) == {"proof_report", "stress_report", "promotion_report"}
    assert set(review.evidence["passed"]) == {True}
    assert review.summary.iloc[0]["recommendation"] == "eligible_for_shadow_scaleup_review"


def test_strategy_evidence_fails_missing_failed_and_dirty_artifacts():
    catalog = catalog_rows(dirty=True)
    catalog = catalog.loc[catalog["run_type"] != "stress_report"].copy()
    catalog.loc[catalog["run_type"] == "promotion_report", "summary_status"] = False

    review = evaluate_strategy_evidence(catalog)

    assert not review.ready
    failed = set(review.checks.loc[~review.checks["passed"].astype(bool), "check"])
    assert "required_run_type:stress_report" in failed
    assert "required_run_type:promotion_report" in failed
    assert "clean_git_artifacts" in failed


def test_strategy_evidence_can_require_proof_refresh_gate():
    catalog = pd.concat(
        [
            catalog_rows(),
            pd.DataFrame(
                [
                    {
                        "run_dir": "runs/proof_refresh",
                        "run_type": "proof_refresh_gate",
                        "generated_at_utc": "2026-06-10T09:45:00Z",
                        "git_commit": "abc123",
                        "git_dirty": False,
                        "summary_status": True,
                        "summary_file": "proof_refresh_summary.csv",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=("proof_report", "stress_report", "promotion_report", "proof_refresh_gate")
        ),
    )

    assert review.ready
    assert "proof_refresh_gate" in set(review.evidence["required_run_type"])


def test_strategy_evidence_can_require_broker_readiness_gate():
    catalog = pd.concat(
        [
            catalog_rows(),
            pd.DataFrame(
                [
                    {
                        "run_dir": "runs/broker_readiness",
                        "run_type": "broker_readiness",
                        "generated_at_utc": "2026-06-10T09:50:00Z",
                        "git_commit": "abc123",
                        "git_dirty": False,
                        "summary_status": True,
                        "summary_file": "broker_readiness_summary.csv",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    review = evaluate_strategy_evidence(
        catalog,
        thresholds=EvidenceThresholds(
            required_run_types=("proof_report", "stress_report", "promotion_report", "broker_readiness")
        ),
    )

    assert review.ready
    assert "broker_readiness" in set(review.evidence["required_run_type"])


def test_write_strategy_evidence_review_outputs_files_and_manifest(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "evidence"
    catalog_rows().to_csv(catalog_path, index=False)

    review = write_strategy_evidence_review(
        catalog_path,
        output_dir=out_dir,
        thresholds=EvidenceThresholds(required_run_types=("proof_report", "stress_report")),
    )

    assert review.output_dir == out_dir
    assert review.ready
    assert (out_dir / "strategy_evidence_items.csv").exists()
    assert (out_dir / "strategy_evidence_checks.csv").exists()
    assert (out_dir / "strategy_evidence_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_strategy_evidence_can_fail_on_breach(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "evidence"
    catalog_rows().to_csv(catalog_path, index=False)

    code = main(
        [
            "review-strategy-evidence",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--required-run-type",
            "proof_report",
            "--required-run-type",
            "shadow_session_comparison",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "strategy_evidence_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert int(summary.loc[0, "failed_checks"]) == 1
