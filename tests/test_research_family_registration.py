import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.research_family_registration import (
    write_research_family_registration,
)


def test_research_family_registration_locks_normalized_plan_deterministically(tmp_path):
    plan_path = _write_plan(tmp_path)
    first_output = tmp_path / "registration"
    second_output = tmp_path / "registration_copy"

    first = write_research_family_registration(
        plan_path,
        output_dir=first_output,
        family_id="india_index_microstructure_v1",
    )
    second = write_research_family_registration(
        plan_path,
        output_dir=second_output,
        family_id="india_index_microstructure_v1",
    )

    summary = first.summary.iloc[0]
    lock = json.loads(
        (first_output / "registration.lock.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (first_output / "manifest.json").read_text(encoding="utf-8")
    )
    assert first.passed
    assert first.action_queue.empty
    assert summary["registration_id"] == second.summary.iloc[0]["registration_id"]
    assert len(str(summary["registration_id"])) == 64
    assert int(summary["study_count"]) == 3
    assert int(summary["min_planned_development_sweeps"]) == 6
    assert int(summary["min_planned_holdout_sweeps"]) == 3
    assert set(first.studies["study_label"]) == {
        "leadlag",
        "imbalance",
        "surface_mm",
    }
    assert all(
        path.startswith(str(tmp_path.resolve()))
        for path in first.studies["planned_study_path"]
    )
    assert lock["registration_id"] == summary["registration_id"]
    assert lock["passed"]
    assert not lock["closed"]
    assert not lock["authorizes_submission"]
    assert manifest["run_type"] == "research_family_registration"
    assert manifest["extra"]["registration_id"] == summary["registration_id"]
    assert not manifest["extra"]["authorizes_submission"]
    catalog = catalog_experiment_runs([first_output]).catalog.iloc[0]
    assert catalog["run_type"] == "research_family_registration"
    assert catalog["summary_file"] == "research_family_registration_summary.csv"
    assert bool(catalog["summary_status"])
    for name in (
        "research_family_registration_studies.csv",
        "research_family_registration_checks.csv",
        "research_family_registration_summary.csv",
        "research_family_registration_action_queue.csv",
        "research_family_registration_config.json",
        "research_family_registration_runbook.md",
        "registration.lock.json",
        "manifest.json",
    ):
        assert (first_output / name).exists()


def test_research_family_registration_blocks_duplicate_and_weak_plan(tmp_path):
    plan = _plan_rows(tmp_path)
    plan[1]["study_label"] = plan[0]["study_label"]
    plan[1]["planned_study_path"] = plan[0]["planned_study_path"]
    plan[1]["hypothesis"] = ""
    plan[1]["max_scenarios"] = 0
    plan[1]["development_sweeps"] = 5
    plan[1]["holdout_sweeps"] = 2
    plan_path = tmp_path / "plan.csv"
    pd.DataFrame(plan).to_csv(plan_path, index=False)

    report = write_research_family_registration(
        plan_path,
        output_dir=tmp_path / "registration",
        family_id="invalid_family",
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert {
        "unique_study_labels",
        "unique_study_paths",
        "complete_text_fields",
        "valid_max_scenarios",
        "development_sweep_plan",
        "holdout_sweep_plan",
    }.issubset(failed)
    assert not bool(report.summary.iloc[0]["closed"])


def test_research_family_registration_cli_fails_closed_for_weak_plan(tmp_path):
    rows = _plan_rows(tmp_path)[:1]
    plan_path = tmp_path / "plan.csv"
    pd.DataFrame(rows).to_csv(plan_path, index=False)
    output = tmp_path / "registration"

    status = main(
        [
            "register-research-family",
            "--plan",
            str(plan_path),
            "--out",
            str(output),
            "--family-id",
            "underpowered_registration",
            "--fail-on-breach",
        ]
    )

    assert status == 2
    summary = pd.read_csv(
        output / "research_family_registration_summary.csv"
    ).iloc[0]
    assert not bool(summary["passed"])
    assert int(summary["study_count"]) == 1


def _write_plan(tmp_path):
    plan_path = tmp_path / "plan.csv"
    pd.DataFrame(_plan_rows(tmp_path)).to_csv(plan_path, index=False)
    return plan_path


def _plan_rows(tmp_path):
    return [
        {
            "study_label": label,
            "strategy": label,
            "market": "india_nse_index_derivatives",
            "hypothesis": f"{label} edge persists net of costs",
            "planned_study_path": f"results/{label}",
            "primary_metric": "robust_score",
            "max_scenarios": scenarios,
            "development_sweeps": 6,
            "holdout_sweeps": 3,
        }
        for label, scenarios in (
            ("leadlag", 24),
            ("imbalance", 36),
            ("surface_mm", 48),
        )
    ]
