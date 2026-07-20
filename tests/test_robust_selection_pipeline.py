import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.promotion import PromotionThresholds
from reports.research_family_registration import (
    write_research_family_registration,
)
from reports.robust_selection_pipeline import write_robust_selection_pipeline
from reports.robust_selection_semantics import (
    build_robust_selection_semantics,
    semantic_digest,
)
from reports.walkforward_split_audit import write_walk_forward_split_audit


def test_robust_selection_semantics_bind_walkforward_audit_identity():
    common = {
        "sweep_paths": ["sweep"],
        "labels": ["period"],
        "group_cols": ["scenario"],
        "strategy": "surface_mm",
        "market": "india_nse_index_derivatives",
        "selection": {},
        "overfit_config": {},
        "overfit_thresholds": {},
        "significance_config": {},
        "significance_thresholds": {},
        "holdout_sweeps": 1,
        "holdout_config": {},
        "holdout_thresholds": {},
        "promotion_thresholds": {},
    }
    unbound = build_robust_selection_semantics(**common)
    bound = build_robust_selection_semantics(
        **common,
        walkforward_split_audit={
            "path": "audit",
            "required": True,
            "manifest_sha256": "a" * 64,
        },
    )
    changed_proof = build_robust_selection_semantics(
        **common,
        walkforward_split_audit={
            "path": "audit",
            "required": True,
            "manifest_sha256": "b" * 64,
        },
    )

    assert "walkforward_split_audit" not in unbound
    assert bound["walkforward_split_audit"]["required"]
    assert semantic_digest(unbound) != semantic_digest(bound)
    assert semantic_digest(bound) != semantic_digest(changed_proof)


def test_robust_selection_pipeline_promotes_stable_multi_period_candidate(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
        strategy="surface_mm",
    )

    summary = report.summary.iloc[0]
    config = json.loads((output / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report.ready
    assert report.action_queue.empty
    assert set(report.stages["stage"]) == {
        "research_launch_execution_receipt",
        "research_launch_contract",
        "research_registration",
        "walkforward_split_audit",
        "sweep_provenance",
        "selection",
        "backtest_overfit",
        "backtest_significance",
        "backtest_holdout",
        "promotion",
    }
    assert report.stages["status"].astype(bool).all()
    assert summary["candidate_scenario_key"] == "scenario=A"
    assert float(summary["probability_overfit"]) == 0.0
    assert float(summary["selection_candidate_rate"]) == 1.0
    assert summary["next_gate"] == "stage-orders"
    assert bool(summary["sweep_provenance_passed"])
    assert not bool(summary["research_registration_provided"])
    assert bool(summary["research_registration_passed"])
    assert not bool(summary["research_launch_contract_provided"])
    assert bool(summary["research_launch_contract_passed"])
    assert not bool(summary["research_launch_execution_receipt_provided"])
    assert bool(summary["research_launch_execution_receipt_passed"])
    assert not bool(summary["walkforward_split_audit_provided"])
    assert bool(summary["walkforward_split_audit_passed"])
    registration_stage = report.stages.set_index("stage").loc[
        "research_registration"
    ]
    assert bool(registration_stage["status"])
    assert bool(registration_stage["skipped"])
    assert int(summary["sweep_manifest_current_count"]) == 9
    assert int(summary["development_sweep_count"]) == 6
    assert int(summary["holdout_sweep_count"]) == 3
    assert bool(summary["backtest_holdout_passed"])
    assert float(summary["holdout_candidate_coverage_rate"]) == 1.0
    assert not bool(summary["authorizes_submission"])
    assert config["ready"]
    assert config["source_run_type"] == "robust_selection_pipeline"
    assert config["backtest_overfit"]["passed"]
    assert config["backtest_overfit"]["selection_matches"]
    assert config["backtest_significance"]["passed"]
    assert config["backtest_significance"]["selection_matches"]
    assert config["backtest_holdout"]["passed"]
    assert config["backtest_holdout"]["selection_matches"]
    assert config["backtest_holdout"]["candidate_matches"]
    assert config["upstream_integrity"]["passed"]
    assert not config["pipeline"]["research_registration_provided"]
    assert config["pipeline"]["research_registration_passed"]
    assert not config["pipeline"]["walkforward_split_audit_provided"]
    assert config["pipeline"]["walkforward_split_audit_passed"]
    assert not config["authorizes_submission"]
    assert manifest["run_type"] == "robust_selection_pipeline"
    assert not manifest["extra"]["authorizes_submission"]
    assert len(manifest["inputs"]["development_sweeps"]) == 6
    assert len(manifest["inputs"]["holdout_sweeps"]) == 3
    assert len(manifest["inputs"]["sweep_manifests"]) == 9
    assert manifest["inputs"]["backtest_overfit_manifest"]["kind"] == "file"
    assert manifest["inputs"]["backtest_significance_manifest"]["kind"] == "file"
    assert manifest["inputs"]["backtest_holdout_manifest"]["kind"] == "file"
    scenario_runs = pd.read_csv(output / "01_selection" / "scenario_runs.csv")
    assert scenario_runs["sweep"].nunique() == 6
    assert set(report.sweep_provenance["study_role"]) == {"development", "holdout"}
    promotion_manifest = json.loads(
        (output / "03_promotion" / "manifest.json").read_text(encoding="utf-8")
    )
    assert promotion_manifest["inputs"]["upstream_integrity"]["kind"] == "file"
    assert promotion_manifest["inputs"]["backtest_holdout_audit_manifest"]["kind"] == "file"
    for name in (
        "01_selection/selection_summary.csv",
        "02_backtest_overfit/backtest_overfit_summary.csv",
        "02_backtest_significance/backtest_significance_summary.csv",
        "02_backtest_holdout/backtest_holdout_summary.csv",
        "03_promotion/promotion_summary.csv",
        "robust_selection_pipeline_research_registration.csv",
        "robust_selection_pipeline_research_launch_contract.csv",
        "robust_selection_pipeline_research_launch_execution_receipt.csv",
        "robust_selection_pipeline_walkforward_split_audit.csv",
        "robust_selection_pipeline_preflight.csv",
        "robust_selection_pipeline_sweep_provenance.csv",
        "robust_selection_pipeline_stages.csv",
        "robust_selection_pipeline_summary.csv",
        "robust_selection_pipeline_action_queue.csv",
        "robust_selection_pipeline_runbook.md",
        "candidate_config.json",
        "manifest.json",
    ):
        assert (output / name).exists()
    catalog = catalog_experiment_runs([output]).catalog
    pipeline = catalog.loc[catalog["run_type"] == "robust_selection_pipeline"].iloc[0]
    assert pipeline["summary_file"] == "robust_selection_pipeline_summary.csv"
    assert bool(pipeline["summary_status"])
    assert pipeline["summary_strategy"] == "surface_mm"


def test_robust_selection_pipeline_binds_registered_study_row(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"
    registration, registration_dir = _write_pipeline_registration(
        tmp_path,
        output,
    )

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
        strategy="surface_mm",
        research_registration_path=registration_dir,
        registered_study_label="surface_mm_study",
        require_research_registration=True,
    )

    summary = report.summary.iloc[0]
    binding = report.research_registration.iloc[0]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((output / "candidate_config.json").read_text(encoding="utf-8"))
    registration_id = str(registration.summary.iloc[0]["registration_id"])
    registration_manifest = registration_dir / "manifest.json"
    assert report.ready
    assert bool(binding["passed"])
    assert bool(binding["contract_matches"])
    assert binding["registered_study_label"] == "surface_mm_study"
    assert binding["registration_id"] == registration_id
    assert bool(summary["research_registration_provided"])
    assert bool(summary["research_registration_passed"])
    assert summary["research_registration_id"] == registration_id
    assert summary["research_registration_manifest_sha256"] == file_sha256(
        registration_manifest
    )
    assert report.preflight["passed"].astype(bool).all()
    assert config["pipeline"]["research_registration_id"] == registration_id
    assert config["pipeline"]["registered_study_label"] == "surface_mm_study"
    assert manifest["inputs"]["research_family_registration"]["kind"] == "directory"
    assert manifest["inputs"]["research_family_registration_manifest"][
        "sha256"
    ] == file_sha256(registration_manifest)
    assert manifest["extra"]["research_registration_passed"]
    assert manifest["extra"]["research_registration_manifest_sha256"] == file_sha256(
        registration_manifest
    )
    assert not manifest["extra"]["authorizes_submission"]


def test_robust_selection_pipeline_binds_current_walkforward_split_audit(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    audit_dir, labels_path = _write_walkforward_split_audit(tmp_path)
    output = tmp_path / "robust_selection"

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
        walkforward_split_audit_path=audit_dir,
        require_walkforward_split_audit=True,
    )

    binding = report.walkforward_split_audit.iloc[0]
    summary = report.summary.iloc[0]
    config = json.loads((output / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    stage = report.stages.set_index("stage").loc["walkforward_split_audit"]
    preflight = report.preflight.set_index("component").loc[
        "walkforward_split_audit"
    ]
    assert report.ready
    assert bool(binding["provided"])
    assert bool(binding["required"])
    assert bool(binding["passed"])
    assert bool(binding["manifest_current"])
    assert bool(binding["checks_passed"])
    assert bool(binding["folds_passed"])
    assert bool(binding["non_authorizing"])
    assert int(binding["future_training_rows"]) == 0
    assert int(binding["overlapping_training_labels"]) == 0
    assert int(binding["embargo_breach_rows"]) == 0
    assert bool(summary["walkforward_split_audit_provided"])
    assert bool(summary["walkforward_split_audit_passed"])
    assert summary["walkforward_split_audit_manifest_sha256"] == file_sha256(
        audit_dir / "manifest.json"
    )
    assert bool(stage["status"])
    assert not bool(stage["skipped"])
    assert bool(preflight["passed"])
    assert config["pipeline"]["walkforward_split_audit_required"]
    assert config["pipeline"]["walkforward_split_fold_count"] == 3
    assert manifest["inputs"]["walkforward_split_audit"]["kind"] == "directory"
    assert manifest["inputs"]["walkforward_split_audit_manifest"]["kind"] == "file"
    dependencies = manifest["inputs"]["walkforward_split_audit_dependencies"]
    assert len(dependencies) == 1
    assert dependencies[0]["path"] == str(labels_path.resolve())
    assert verify_experiment_manifest(output / "manifest.json").passed

    labels_path.write_text(
        labels_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    integrity = verify_experiment_manifest(output / "manifest.json")
    assert not integrity.passed
    assert integrity.error == "input_drift"


def test_robust_selection_pipeline_cli_blocks_missing_required_split_audit(
    tmp_path,
):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"
    args = [
        "pipeline-robust-selection",
        "--sweeps",
        *[str(path) for path in sweeps],
        "--out",
        str(output),
        "--group-cols",
        "scenario",
        "--require-walkforward-split-audit",
        "--fail-on-breach",
    ]
    for label in labels:
        args.extend(["--label", label])

    status = main(args)

    binding = pd.read_csv(
        output / "robust_selection_pipeline_walkforward_split_audit.csv"
    ).iloc[0]
    summary = pd.read_csv(output / "robust_selection_pipeline_summary.csv").iloc[0]
    stages = pd.read_csv(output / "robust_selection_pipeline_stages.csv").set_index(
        "stage"
    )
    assert status == 2
    assert not bool(binding["provided"])
    assert bool(binding["required"])
    assert not bool(binding["passed"])
    assert binding["failed_check_names"] == "audit_provided"
    assert not bool(summary["ready"])
    assert summary["next_gate"] == "audit-walkforward-splits"
    assert not bool(stages.loc["walkforward_split_audit", "status"])
    assert not bool(stages.loc["promotion", "status"])


def test_robust_selection_pipeline_blocks_drifted_supplied_split_audit(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    audit_dir, labels_path = _write_walkforward_split_audit(tmp_path)
    labels_path.write_text(
        labels_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "robust_selection"

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
        walkforward_split_audit_path=audit_dir,
    )

    binding = report.walkforward_split_audit.iloc[0]
    assert not report.ready
    assert bool(binding["provided"])
    assert not bool(binding["required"])
    assert not bool(binding["passed"])
    assert not bool(binding["manifest_current"])
    assert binding["manifest_error"] == "input_drift"
    assert "manifest_current" in binding["failed_check_names"]
    assert report.summary.iloc[0]["next_gate"] == "audit-walkforward-splits"
    assert set(report.action_queue["component"]) == {
        "walkforward_split_audit",
        "promotion",
    }
    assert report.candidate_config["failed_checks"] == [
        "walkforward_split_audit",
        "promotion",
    ]


def test_robust_selection_pipeline_cli_blocks_registered_search_breadth_breach(
    tmp_path,
):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"
    _, registration_dir = _write_pipeline_registration(
        tmp_path,
        output,
        max_scenarios=2,
    )
    args = [
        "pipeline-robust-selection",
        "--sweeps",
        *[str(path) for path in sweeps],
        "--out",
        str(output),
        "--group-cols",
        "scenario",
        "--strategy",
        "surface_mm",
        "--research-registration",
        str(registration_dir),
        "--registered-study-label",
        "surface_mm_study",
        "--require-research-registration",
        "--fail-on-breach",
    ]
    for label in labels:
        args.extend(["--label", label])

    status = main(args)

    binding = pd.read_csv(
        output / "robust_selection_pipeline_research_registration.csv"
    ).iloc[0]
    summary = pd.read_csv(output / "robust_selection_pipeline_summary.csv").iloc[0]
    stages = pd.read_csv(output / "robust_selection_pipeline_stages.csv").set_index(
        "stage"
    )
    assert status == 2
    assert not bool(binding["passed"])
    assert not bool(binding["search_breadth_within_plan"])
    assert "search_breadth_within_plan" in binding["failed_check_names"]
    assert not bool(summary["ready"])
    assert summary["next_gate"] == "register-research-family"
    assert not bool(stages.loc["research_registration", "status"])
    assert not bool(stages.loc["promotion", "status"])


def test_robust_selection_pipeline_blocks_missing_required_registration(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
        require_research_registration=True,
    )

    binding = report.research_registration.iloc[0]
    assert not report.ready
    assert not bool(binding["provided"])
    assert not bool(binding["passed"])
    assert binding["failed_check_names"] == "registration_provided"
    assert report.summary.iloc[0]["next_gate"] == "register-research-family"
    assert set(report.action_queue["component"]) == {
        "research_registration",
        "promotion",
    }


def test_robust_selection_pipeline_cli_blocks_partition_memorization(tmp_path):
    sweeps, labels = _write_memorized_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"
    args = [
        "pipeline-robust-selection",
        "--sweeps",
        *[str(path) for path in sweeps],
        "--out",
        str(output),
        "--group-cols",
        "scenario",
        "--min-selection-median-net-pnl",
        "-20",
        "--min-promotion-median-net-pnl",
        "-20",
    ]
    for label in labels:
        args.extend(["--label", label])
    args.append("--fail-on-breach")

    status = main(args)

    summary = pd.read_csv(output / "robust_selection_pipeline_summary.csv").iloc[0]
    stages = pd.read_csv(output / "robust_selection_pipeline_stages.csv").set_index("stage")
    actions = pd.read_csv(output / "robust_selection_pipeline_action_queue.csv")
    promotion_checks = pd.read_csv(output / "03_promotion" / "promotion_checks.csv")
    assert status == 2
    assert not bool(summary["ready"])
    assert bool(stages.loc["selection", "status"])
    assert not bool(stages.loc["backtest_overfit", "status"])
    assert not bool(stages.loc["backtest_significance", "status"])
    assert bool(stages.loc["backtest_holdout", "status"])
    assert not bool(stages.loc["promotion", "status"])
    assert float(summary["probability_overfit"]) == 1.0
    assert summary["next_gate"] == "audit-backtest-overfit"
    assert set(actions["component"]) == {
        "backtest_overfit",
        "backtest_significance",
        "promotion",
    }
    failed = set(
        promotion_checks.loc[
            ~promotion_checks["passed"].astype(bool), "check"
        ]
    )
    assert "overfit_audit_passed" in failed
    assert "significance_audit_passed" in failed


def test_robust_selection_pipeline_blocks_underpowered_period_count(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps", periods=6)
    output = tmp_path / "robust_selection"

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
        promotion_thresholds=PromotionThresholds(min_sweeps=3),
    )

    assert not report.ready
    failed = set(
        report.overfit.checks.loc[
            ~report.overfit.checks["passed"].astype(bool), "check"
        ]
    )
    assert "split_count" in failed
    assert "partition_count" in failed
    assert report.summary.iloc[0]["next_gate"] == "audit-backtest-overfit"
    assert set(report.action_queue["component"]) == {
        "backtest_overfit",
        "backtest_significance",
        "promotion",
    }
    assert set(report.action_queue["queue_status"]) == {"blocked"}


def test_robust_selection_pipeline_blocks_missing_or_drifted_sweep_manifest(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps")
    output = tmp_path / "robust_selection"
    runs_path = sweeps[0] / "sweep_runs.csv"
    runs_path.write_text(runs_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    (sweeps[1] / "manifest.json").unlink()

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
    )

    provenance = report.sweep_provenance.set_index("label")
    assert not report.ready
    assert not bool(provenance.loc[labels[0], "passed"])
    assert provenance.loc[labels[0], "error"] == "artifact_drift"
    assert provenance.loc[labels[1], "error"] == "manifest_missing"
    assert bool(provenance.loc[labels[2], "passed"])
    assert not bool(report.summary.iloc[0]["sweep_provenance_passed"])
    assert report.summary.iloc[0]["next_gate"] == "pipeline-robust-selection"
    assert set(report.action_queue["component"]) == {
        "sweep_provenance",
        "promotion",
    }
    promotion_checks = report.promotion.checks.set_index("check")
    assert not report.promotion.ready
    assert not bool(promotion_checks.loc["upstream_integrity_passed", "passed"])
    assert not report.candidate_config["ready"]
    assert report.candidate_config["upstream_integrity"]["provided"]
    assert not report.candidate_config["upstream_integrity"]["passed"]
    assert report.candidate_config["failed_checks"] == [
        "sweep_provenance",
        "promotion",
    ]


def test_robust_selection_pipeline_blocks_losing_reserved_holdout(tmp_path):
    sweeps, labels = _write_stable_sweeps(
        tmp_path / "sweeps",
        losing_holdout=True,
    )
    output = tmp_path / "robust_selection"

    report = write_robust_selection_pipeline(
        sweeps,
        output_dir=output,
        labels=labels,
        group_cols=["scenario"],
    )

    stages = report.stages.set_index("stage")
    failed_holdout = set(
        report.holdout.checks.loc[~report.holdout.checks["passed"], "check"]
    )
    promotion_checks = report.promotion.checks.set_index("check")
    assert not report.ready
    assert bool(stages.loc["selection", "status"])
    assert bool(stages.loc["backtest_overfit", "status"])
    assert bool(stages.loc["backtest_significance", "status"])
    assert not bool(stages.loc["backtest_holdout", "status"])
    assert not bool(stages.loc["promotion", "status"])
    assert {"worst_score", "worst_net_pnl"}.issubset(failed_holdout)
    assert report.summary.iloc[0]["next_gate"] == "audit-backtest-holdout"
    assert set(report.action_queue["component"]) == {
        "backtest_holdout",
        "promotion",
    }
    assert not bool(promotion_checks.loc["holdout_audit_passed", "passed"])
    assert not report.candidate_config["backtest_holdout"]["passed"]


def _write_pipeline_registration(tmp_path, output, *, max_scenarios=3):
    plan_path = tmp_path / "research_family_plan.csv"
    pd.DataFrame(
        [
            {
                "study_label": "surface_mm_study",
                "strategy": "surface_mm",
                "market": "india_nse_index_derivatives",
                "hypothesis": "surface quotes retain edge after costs",
                "planned_study_path": str(output),
                "primary_metric": "robust_score",
                "max_scenarios": max_scenarios,
                "development_sweeps": 6,
                "holdout_sweeps": 3,
            },
            {
                "study_label": "future_study",
                "strategy": "surface_mm",
                "market": "india_nse_index_derivatives",
                "hypothesis": "a second declared study will be evaluated later",
                "planned_study_path": str(output.parent / "future_study"),
                "primary_metric": "robust_score",
                "max_scenarios": 3,
                "development_sweeps": 6,
                "holdout_sweeps": 3,
            },
        ]
    ).to_csv(plan_path, index=False)
    registration_dir = tmp_path / "registration"
    report = write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="pipeline_binding_family",
    )
    assert report.passed
    return report, registration_dir


def _write_walkforward_split_audit(tmp_path):
    labels_path = tmp_path / "walkforward_labels.csv"
    pd.DataFrame(
        {
            "ts": list(range(1, 17)),
            "label_end_ts": list(range(1, 17)),
        }
    ).to_csv(labels_path, index=False)
    audit_dir = tmp_path / "walkforward_split_audit"
    report = write_walk_forward_split_audit(
        labels_path,
        output_dir=audit_dir,
    )
    assert report.passed
    return audit_dir, labels_path


def _write_stable_sweeps(root, *, periods=9, losing_holdout=False):
    labels = [f"2026-06-{period + 1:02d}" for period in range(periods)]
    paths = []
    for period, label in enumerate(labels):
        path = root / label
        path.mkdir(parents=True)
        rows = []
        for scenario, base in (("A", 10.0), ("B", 5.0), ("C", 1.0)):
            score = base + period * 0.1
            if losing_holdout and period == periods - 1 and scenario == "A":
                score = -1.0
            rows.append(_sweep_row(scenario, score))
        pd.DataFrame(rows).to_csv(path / "sweep_runs.csv", index=False)
        _write_sweep_manifest(path, label)
        paths.append(path)
    return paths, labels


def _write_memorized_sweeps(root):
    scenarios = [f"S{index}" for index in range(6)]
    labels = [f"2026-06-{period + 1:02d}" for period in range(9)]
    paths = []
    for period, label in enumerate(labels):
        path = root / label
        path.mkdir(parents=True)
        rows = []
        for index, scenario in enumerate(scenarios):
            if period < 6:
                score = 10.0 if index == period else -10.0
            else:
                score = 5.0 if scenario == "S0" else 1.0
            rows.append(_sweep_row(scenario, score))
        pd.DataFrame(rows).to_csv(path / "sweep_runs.csv", index=False)
        _write_sweep_manifest(path, label)
        paths.append(path)
    return paths, labels


def _sweep_row(scenario, score):
    return {
        "run": f"scenario_{scenario}",
        "scenario": scenario,
        "proof_passed": True,
        "net_pnl": score,
        "robust_score": score,
        "max_drawdown": 0.0,
        "fills": 10,
        "worst_regime_equity_change": score,
        "losing_regimes": int(score < 0.0),
    }


def _write_sweep_manifest(path, label):
    source_dir = path.parent / "_sources"
    source_dir.mkdir(exist_ok=True)
    source = source_dir / f"{label}.csv"
    pd.DataFrame([{"ts": 1, "bid": 100.0, "ask": 100.05}]).to_csv(
        source,
        index=False,
    )
    write_experiment_manifest(
        path,
        run_type="test_sweep",
        inputs={"market_data": source},
    )
