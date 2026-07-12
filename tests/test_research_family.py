import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.research_family import (
    ResearchFamilyConfig,
    write_research_family_audit,
)
from reports.research_family_registration import (
    write_research_family_registration,
)
from reports.strategy_scorecard import (
    StrategyScorecardThresholds,
    write_strategy_scorecard,
)
from reports.strategy_portfolio import (
    StrategyPortfolioConfig,
    write_strategy_portfolio_allocations,
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
    assert not config[
        "operational_retries_count_as_additional_hypotheses"
    ]
    assert int(summary["launch_attempt_count"]) == 0
    assert int(summary["launch_additional_retry_hypothesis_count"]) == 0
    assert pd.read_csv(
        output / "research_family_launch_attempt_census.csv"
    ).empty
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
        "research_family_launch_attempt_census.csv",
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


def test_research_family_closes_matching_prospective_registration(tmp_path):
    plan_path = _write_registration_plan(tmp_path, ["leadlag", "imbalance"])
    registration_dir = tmp_path / "registration"
    registration = write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="prospective_family",
    )
    studies = [
        _write_study(
            tmp_path,
            "leadlag",
            adjusted_pvalue=0.01,
            registration_dir=registration_dir,
        ),
        _write_study(
            tmp_path,
            "imbalance",
            adjusted_pvalue=0.02,
            registration_dir=registration_dir,
        ),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        config=ResearchFamilyConfig(
            family_id="prospective_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
        ),
    )

    summary = report.summary.iloc[0]
    manifest = json.loads(
        (tmp_path / "family" / "manifest.json").read_text(encoding="utf-8")
    )
    assert registration.passed
    assert report.passed
    assert bool(summary["prospective_registration_passed"])
    assert bool(summary["registration_closed"])
    assert summary["registration_id"] == registration.summary.iloc[0][
        "registration_id"
    ]
    assert report.config["prospective_registration"]["paths_match"]
    assert report.config["prospective_registration"]["prospective"]
    assert report.config["prospective_registration"][
        "source_registration_bindings"
    ]
    assert report.config["prospective_registration"][
        "source_registration_manifest_fingerprints"
    ]
    assert manifest["inputs"]["research_family_registration"]["kind"] == "directory"
    assert manifest["extra"]["registration_closed"]

    catalog_path = tmp_path / "experiment_catalog.csv"
    required = (
        ("leadlag_edge_audit", "leadlag_edge_summary.csv"),
        ("leadlag_replay_walkforward", "leadlag_replay_walkforward_summary.csv"),
        ("stress_report", "stress_summary.csv"),
        ("promotion_report", "promotion_summary.csv"),
        ("leadlag_order_plan", "leadlag_order_summary.csv"),
        ("leadlag_launch_pipeline", "leadlag_launch_pipeline_summary.csv"),
    )
    pd.DataFrame(
        [
            {
                "run_dir": f"runs/leadlag/{run_type}",
                "run_type": run_type,
                "generated_at_utc": f"2026-06-10T09:{index + 10:02d}:00Z",
                "git_commit": "abc123",
                "git_dirty": False,
                "summary_status": True,
                "summary_file": summary_file,
                "summary_strategy": "leadlag",
                "summary_market": "india_nse_index_derivatives",
                "summary_candidate_scenario_key": "scenario=leadlag",
                "parameters_json": "{}",
                "input_count": 1,
                "input_file_count": 1,
                "input_directory_count": 0,
                "input_other_count": 0,
                "input_unfingerprinted_count": 0,
                "input_hashed_count": 1,
            }
            for index, (run_type, summary_file) in enumerate(required)
        ]
    ).to_csv(catalog_path, index=False)
    scorecard = write_strategy_scorecard(
        catalog_path,
        output_dir=tmp_path / "scorecard",
        research_family_path=tmp_path / "family",
        thresholds=StrategyScorecardThresholds(
            profiles=("leadlag",),
            expected_market="india_nse_index_derivatives",
            require_research_family=True,
        ),
    )
    score = scorecard.scorecard.iloc[0]
    assert scorecard.ready
    assert bool(score["research_family_gate_passed"])
    assert score["research_family_id"] == "prospective_family"
    assert score["research_family_matched_study_label"] == "leadlag"
    portfolio = write_strategy_portfolio_allocations(
        tmp_path / "scorecard",
        output_dir=tmp_path / "portfolio",
        config=StrategyPortfolioConfig(max_profile_weight=1.0),
    )
    allocation = portfolio.allocations.iloc[0]
    assert portfolio.ready
    assert allocation["allocation_weight"] == 0.90
    assert bool(allocation["scorecard_manifest_current"])
    assert bool(allocation["scorecard_contract_consistent"])
    assert bool(allocation["research_family_provenance_current"])
    assert allocation["research_family_id"] == "prospective_family"
    assert allocation["research_family_matched_study_label"] == "leadlag"
    assert not bool(allocation["authorizes_submission"])
    assert verify_experiment_manifest(
        tmp_path / "portfolio" / "manifest.json",
        expected_run_type="strategy_portfolio_allocation",
        require_input_fingerprints=True,
    ).passed


def test_research_family_blocks_post_hoc_registration(tmp_path):
    studies = [
        _write_study(tmp_path, "leadlag", adjusted_pvalue=0.01),
        _write_study(tmp_path, "imbalance", adjusted_pvalue=0.02),
    ]
    plan_path = _write_registration_plan(tmp_path, ["leadlag", "imbalance"])
    registration_dir = tmp_path / "registration"
    write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="post_hoc_family",
    )

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        config=ResearchFamilyConfig(
            family_id="post_hoc_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert "prospective" in failed
    assert not bool(report.summary.iloc[0]["registration_closed"])
    assert report.config["selected_candidates"] == []


def test_research_family_blocks_when_required_registration_is_missing(tmp_path):
    studies = [
        _write_study(tmp_path, "leadlag", adjusted_pvalue=0.01),
        _write_study(tmp_path, "imbalance", adjusted_pvalue=0.02),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        config=ResearchFamilyConfig(
            family_id="missing_registration",
            declaration_complete_attested=True,
            require_prospective_registration=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert "prospective_registration_provided" in failed
    assert not bool(report.summary.iloc[0]["registration_closed"])


def test_research_family_blocks_registered_search_breadth_breach(tmp_path):
    plan_path = _write_registration_plan(tmp_path, ["leadlag", "imbalance"])
    plan = pd.read_csv(plan_path)
    plan["max_scenarios"] = 2
    plan.to_csv(plan_path, index=False)
    registration_dir = tmp_path / "registration"
    write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="narrow_search_family",
    )
    studies = [
        _write_study(
            tmp_path,
            "leadlag",
            adjusted_pvalue=0.01,
            registration_dir=registration_dir,
        ),
        _write_study(
            tmp_path,
            "imbalance",
            adjusted_pvalue=0.02,
            registration_dir=registration_dir,
        ),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        config=ResearchFamilyConfig(
            family_id="narrow_search_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert "search_breadth_within_plan" in failed
    assert not report.config["prospective_registration"][
        "search_breadth_within_plan"
    ]


def test_research_family_blocks_mismatched_source_registration_binding(tmp_path):
    plan_path = _write_registration_plan(tmp_path, ["leadlag", "imbalance"])
    registration_dir = tmp_path / "registration"
    write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="binding_mismatch_family",
    )
    studies = [
        _write_study(
            tmp_path,
            "leadlag",
            adjusted_pvalue=0.01,
            registration_dir=registration_dir,
            bound_registration_id="0" * 64,
        ),
        _write_study(
            tmp_path,
            "imbalance",
            adjusted_pvalue=0.02,
            registration_dir=registration_dir,
        ),
    ]

    report = write_research_family_audit(
        studies,
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        config=ResearchFamilyConfig(
            family_id="binding_mismatch_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
        ),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    registration = report.config["prospective_registration"]
    assert not report.passed
    assert "source_registration_bindings" in failed
    assert "source_registration_manifest_fingerprints" not in failed
    assert int(registration["source_registration_binding_count"]) == 1
    assert int(registration["source_registration_manifest_match_count"]) == 2


def _write_study(
    tmp_path,
    label,
    *,
    adjusted_pvalue,
    ready=True,
    holdout_passed=True,
    registration_dir=None,
    bound_registration_id=None,
):
    root = tmp_path / label
    significance_dir = root / "02_backtest_significance"
    overfit_dir = root / "02_backtest_overfit"
    significance_dir.mkdir(parents=True)
    overfit_dir.mkdir(parents=True)
    registration_id = ""
    registration_manifest_sha256 = ""
    if registration_dir is not None:
        registration_summary = pd.read_csv(
            registration_dir / "research_family_registration_summary.csv"
        ).iloc[0]
        registration_id = str(
            bound_registration_id
            if bound_registration_id is not None
            else registration_summary["registration_id"]
        )
        registration_manifest_sha256 = file_sha256(
            registration_dir / "manifest.json"
        )
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
                "passed": True,
                "score_column": "robust_score",
                "scenario_count": 3,
            }
        ]
    ).to_csv(overfit_dir / "backtest_overfit_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "ready": ready,
                "strategy": label,
                "market": "india_nse_index_derivatives",
                "candidate_scenario_key": f"scenario={label}",
                "overfit_scenario_count": 3,
                "development_sweep_count": 6,
                "holdout_sweep_count": 3,
                "research_registration_provided": registration_dir is not None,
                "research_registration_passed": registration_dir is not None,
                "research_registration_id": registration_id,
                "research_registration_manifest_sha256": (
                    registration_manifest_sha256
                ),
                "registered_study_label": label if registration_dir is not None else "",
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
    inputs = {"market_data": source}
    if registration_dir is not None:
        inputs["research_family_registration"] = registration_dir
        inputs["research_family_registration_manifest"] = (
            registration_dir / "manifest.json"
        )
    write_experiment_manifest(
        root,
        run_type="robust_selection_pipeline",
        inputs=inputs,
    )
    return root


def _write_registration_plan(tmp_path, labels):
    plan_path = tmp_path / "family_plan.csv"
    pd.DataFrame(
        [
            {
                "study_label": label,
                "strategy": label,
                "market": "india_nse_index_derivatives",
                "hypothesis": f"{label} remains positive after costs",
                "planned_study_path": label,
                "primary_metric": "robust_score",
                "max_scenarios": 12,
                "development_sweeps": 6,
                "holdout_sweeps": 3,
            }
            for label in labels
        ]
    ).to_csv(plan_path, index=False)
    return plan_path
