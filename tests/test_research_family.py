import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import write_experiment_manifest
from reports.research_family import (
    ResearchFamilyConfig,
    write_research_family_audit,
)


def test_research_family_applies_holm_to_scenario_adjusted_studies(tmp_path):
    studies = [
        _write_study(tmp_path, "leadlag", adjusted_pvalue=0.01),
        _write_study(tmp_path, "imbalance", adjusted_pvalue=0.04),
        _write_study(tmp_path, "surface_mm", adjusted_pvalue=0.20),
    ]
    output = tmp_path / "family"

    report = write_research_family_audit(
        studies,
        output_dir=output,
        config=ResearchFamilyConfig(
            family_id="india_index_microstructure_v1",
            declaration_complete_attested=True,
        ),
    )

    rows = report.studies.set_index("study_label")
    summary = report.summary.iloc[0]
    config = json.loads(
        (output / "research_family_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert report.action_queue.empty
    assert float(rows.loc["leadlag", "holm_adjusted_pvalue"]) == 0.03
    assert float(rows.loc["imbalance", "holm_adjusted_pvalue"]) == 0.08
    assert float(rows.loc["surface_mm", "holm_adjusted_pvalue"]) == 0.20
    assert bool(rows.loc["leadlag", "family_passed"])
    assert bool(rows.loc["imbalance", "family_passed"])
    assert not bool(rows.loc["surface_mm", "family_passed"])
    assert int(summary["family_candidate_count"]) == 2
    assert bool(summary["family_wise_error_control_claimed"])
    assert len(config["selected_candidates"]) == 2
    assert len(config["candidate_decisions"]) == 3
    assert manifest["run_type"] == "research_family_audit"
    assert manifest["extra"]["declaration_complete_attested"]
    assert manifest["extra"]["family_wise_error_control_claimed"]
    assert not manifest["extra"]["authorizes_submission"]
    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert catalog["run_type"] == "research_family_audit"
    assert catalog["summary_file"] == "research_family_summary.csv"
    assert bool(catalog["summary_status"])
    for name in (
        "research_family_studies.csv",
        "research_family_checks.csv",
        "research_family_summary.csv",
        "research_family_action_queue.csv",
        "research_family_config.json",
        "research_family_runbook.md",
        "manifest.json",
    ):
        assert (output / name).exists()


def test_research_family_keeps_failed_attempt_in_holm_denominator(tmp_path):
    studies = [
        _write_study(tmp_path, "ready", adjusted_pvalue=0.04),
        _write_study(
            tmp_path,
            "failed",
            adjusted_pvalue=0.50,
            ready=False,
            holdout_passed=False,
        ),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        config=ResearchFamilyConfig(
            family_id="declared_attempts",
            declaration_complete_attested=True,
        ),
    )

    rows = report.studies.set_index("study_label")
    assert report.passed
    assert float(rows.loc["ready", "holm_adjusted_pvalue"]) == 0.08
    assert bool(rows.loc["ready", "family_passed"])
    assert not bool(rows.loc["failed", "source_eligible"])
    assert not bool(rows.loc["failed", "family_passed"])
    assert int(report.summary.iloc[0]["study_count"]) == 2
    assert int(report.summary.iloc[0]["source_ready_count"]) == 1


def test_research_family_requires_complete_declaration_attestation(tmp_path):
    studies = [
        _write_study(tmp_path, "leadlag", adjusted_pvalue=0.01),
        _write_study(tmp_path, "imbalance", adjusted_pvalue=0.02),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        config=ResearchFamilyConfig(family_id="unattested_family"),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert "family_declaration_attested" in failed
    assert report.config["selected_candidates"] == []
    assert not bool(report.summary.iloc[0]["family_wise_error_control_claimed"])


def test_research_family_blocks_duplicate_or_drifted_studies(tmp_path):
    first = _write_study(tmp_path, "leadlag", adjusted_pvalue=0.01)
    second = _write_study(tmp_path, "imbalance", adjusted_pvalue=0.02)
    summary_path = second / "robust_selection_pipeline_summary.csv"
    summary_path.write_text(
        summary_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    report = write_research_family_audit(
        [first, first, second],
        labels=["leadlag", "leadlag_copy", "imbalance"],
        output_dir=tmp_path / "family",
        config=ResearchFamilyConfig(
            family_id="invalid_family",
            declaration_complete_attested=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert "unique_study_paths" in failed
    assert "current_study_manifests" in failed
    drifted = report.studies.set_index("study_label").loc["imbalance"]
    assert not bool(drifted["manifest_current"])
    assert drifted["manifest_error"] == "artifact_drift"


def test_research_family_cli_fails_closed_without_attestation(tmp_path):
    studies = [
        _write_study(tmp_path, "leadlag", adjusted_pvalue=0.01),
        _write_study(tmp_path, "imbalance", adjusted_pvalue=0.02),
    ]
    output = tmp_path / "family"

    status = main(
        [
            "audit-research-family",
            "--studies",
            *[str(path) for path in studies],
            "--out",
            str(output),
            "--family-id",
            "unattested_cli_family",
            "--fail-on-breach",
        ]
    )

    assert status == 2
    summary = pd.read_csv(output / "research_family_summary.csv").iloc[0]
    assert not bool(summary["passed"])
    assert not bool(summary["declaration_complete_attested"])


def test_research_family_blocks_out_of_range_adjusted_pvalue(tmp_path):
    studies = [
        _write_study(tmp_path, "valid", adjusted_pvalue=0.02),
        _write_study(tmp_path, "invalid", adjusted_pvalue=-0.01),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        config=ResearchFamilyConfig(
            family_id="malformed_pvalue_family",
            declaration_complete_attested=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    invalid = report.studies.set_index("study_label").loc["invalid"]
    assert not report.passed
    assert "valid_adjusted_pvalues" in failed
    assert not bool(invalid["family_passed"])
    assert pd.isna(invalid["holm_adjusted_pvalue"])


def _write_study(
    tmp_path,
    label,
    *,
    adjusted_pvalue,
    ready=True,
    holdout_passed=True,
):
    root = tmp_path / label
    significance_dir = root / "02_backtest_significance"
    significance_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "passed": adjusted_pvalue <= 0.1,
                "candidate_scenario": f"scenario={label}",
                "scenario_trial_count": 3,
                "sign_pvalue": adjusted_pvalue / 3.0,
                "adjusted_sign_pvalue": adjusted_pvalue,
            }
        ]
    ).to_csv(
        significance_dir / "backtest_significance_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": label,
                "market": "india_nse_index_derivatives",
                "candidate_scenario_key": f"scenario={label}",
                "overfit_scenario_count": 3,
                "adjusted_sign_pvalue": adjusted_pvalue,
                "backtest_holdout_passed": holdout_passed,
                "next_gate": "stage-orders" if ready else "keep-in-research",
                "authorizes_submission": False,
            }
        ]
    ).to_csv(root / "robust_selection_pipeline_summary.csv", index=False)
    sources = tmp_path / "_sources"
    sources.mkdir(exist_ok=True)
    source = sources / f"{label}.csv"
    pd.DataFrame([{"ts": 1, "score": adjusted_pvalue}]).to_csv(
        source,
        index=False,
    )
    write_experiment_manifest(
        root,
        run_type="robust_selection_pipeline",
        inputs={"market_data": source},
    )
    return root
