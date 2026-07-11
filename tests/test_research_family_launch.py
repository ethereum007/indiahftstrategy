import json
from pathlib import Path

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.manifest import (
    file_sha256,
    verify_experiment_manifest,
    write_experiment_manifest,
)
from reports.research_family import ResearchFamilyConfig, write_research_family_audit
from reports.research_family_launch import (
    load_research_family_launch_matrix,
    write_research_family_launch_matrix,
)
from reports.research_family_registration import write_research_family_registration


def test_research_family_launch_builds_deterministic_pending_contracts(tmp_path):
    registration, registration_dir = _write_registration(tmp_path)

    first = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
    )
    second = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches_copy",
    )

    summary = first.summary.iloc[0]
    assert registration.passed
    assert not first.passed
    assert int(summary["valid_contract_count"]) == 2
    assert int(summary["contract_ready_count"]) == 2
    assert int(summary["never_launched_count"]) == 2
    assert int(summary["closure_covered_count"]) == 0
    assert summary["next_gate"] == "run-research-family-study"
    assert first.launches["contract_valid"].astype(bool).all()
    assert first.launches["sweep_inputs_current"].astype(bool).all()
    assert first.launches["contract_id"].tolist() == second.launches[
        "contract_id"
    ].tolist()
    for row in first.launches.itertuples(index=False):
        argv = json.loads(row.launch_argv_json)
        assert "--require-research-registration" in argv
        assert "--registered-study-label" in argv
        assert "--research-launch-matrix" in argv
        assert "--research-launch-contract-id" in argv
        assert "--require-research-launch-contract" in argv
        assert "--fail-on-breach" in argv
        assert not bool(row.authorizes_submission)
        contract = json.loads(
            Path(row.contract_path).read_text(encoding="utf-8")
        )
        assert contract["contract_id"] == row.contract_id
        assert not contract["authorizes_submission"]


def test_research_family_launch_executes_and_binds_exact_contract(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    contract = pending.launches.set_index("study_label").loc["leadlag"]

    status = main(
        [
            "run-research-family-study",
            "--launch-matrix",
            str(launch_dir),
            "--contract-id",
            str(contract["contract_id"]),
        ]
    )

    result_root = tmp_path / "results" / "leadlag"
    summary = pd.read_csv(
        result_root / "robust_selection_pipeline_summary.csv"
    ).iloc[0]
    binding = pd.read_csv(
        result_root / "robust_selection_pipeline_research_launch_contract.csv"
    ).iloc[0]
    manifest = json.loads((result_root / "manifest.json").read_text(encoding="utf-8"))
    assert status == 0
    assert bool(summary["ready"])
    assert bool(summary["research_launch_contract_passed"])
    assert summary["research_launch_contract_id"] == contract["contract_id"]
    assert bool(binding["passed"])
    assert bool(binding["sweep_paths_match"])
    assert bool(binding["group_columns_match"])
    assert manifest["inputs"]["research_family_launch_contract"]["sha256"] == (
        file_sha256(Path(str(contract["contract_path"])))
    )
    refreshed = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    refreshed_leadlag = refreshed.launches.set_index("study_label").loc[
        "leadlag"
    ]
    root_integrity = verify_experiment_manifest(
        result_root / "manifest.json",
        expected_run_type="robust_selection_pipeline",
        require_input_fingerprints=True,
    )
    assert refreshed_leadlag["study_status"] == "completed_ready"
    assert bool(refreshed_leadlag["result_launch_contract_bound"])
    assert root_integrity.passed
    result_summary_path = result_root / "robust_selection_pipeline_summary.csv"
    result_summary_path.write_text(
        result_summary_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    drifted_matrix = load_research_family_launch_matrix(launch_dir)
    assert not drifted_matrix.manifest_current
    assert drifted_matrix.manifest_error == "input_drift"


def test_research_family_launch_blocks_contract_argument_drift(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    launch_dir = tmp_path / "launches"
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=launch_dir,
    )
    contract = pending.launches.set_index("study_label").loc["leadlag"]
    argv = json.loads(contract["launch_argv_json"])
    first_sweep = argv.index("--sweeps") + 1
    argv[first_sweep], argv[first_sweep + 1] = (
        argv[first_sweep + 1],
        argv[first_sweep],
    )

    status = main(argv[3:])

    result_root = tmp_path / "results" / "leadlag"
    summary = pd.read_csv(
        result_root / "robust_selection_pipeline_summary.csv"
    ).iloc[0]
    binding = pd.read_csv(
        result_root / "robust_selection_pipeline_research_launch_contract.csv"
    ).iloc[0]
    assert status == 2
    assert not bool(summary["ready"])
    assert summary["next_gate"] == "plan-research-family-launches"
    assert not bool(binding["passed"])
    assert not bool(binding["sweep_paths_match"])
    assert "sweep_paths_match" in binding["failed_check_names"]


def test_research_family_launch_covers_bound_result_and_attested_abandonment(
    tmp_path,
):
    registration, registration_dir = _write_registration(tmp_path)
    registration_id = str(registration.summary.iloc[0]["registration_id"])
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
    )
    leadlag_contract = pending.launches.set_index("study_label").loc["leadlag"]
    _write_bound_result(
        tmp_path / "results" / "leadlag",
        registration_dir=registration_dir,
        registration_id=registration_id,
        study_label="leadlag",
        launch_contract_id=str(leadlag_contract["contract_id"]),
        launch_contract_path=Path(str(leadlag_contract["contract_path"])),
    )
    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)

    report = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
        abandonment_path=abandonments,
        attest_abandonments=True,
    )

    rows = report.launches.set_index("study_label")
    summary = report.summary.iloc[0]
    manifest = json.loads(
        (tmp_path / "launches" / "manifest.json").read_text(encoding="utf-8")
    )
    assert report.passed
    assert report.action_queue.empty
    assert rows.loc["leadlag", "study_status"] == "completed_ready"
    assert bool(rows.loc["leadlag", "result_manifest_current"])
    assert bool(rows.loc["leadlag", "result_registration_bound"])
    assert bool(rows.loc["leadlag", "result_launch_contract_bound"])
    assert rows.loc["imbalance", "study_status"] == "abandoned"
    assert bool(rows.loc["imbalance", "abandonment_valid"])
    assert rows["closure_covered"].astype(bool).all()
    assert int(summary["closure_covered_count"]) == 2
    assert summary["next_gate"] == "audit-research-family"
    assert manifest["run_type"] == "research_family_launch_matrix"
    assert manifest["inputs"]["research_family_abandonments"]["kind"] == "file"
    assert len(manifest["inputs"]["robust_study_manifests"]) == 1
    assert not manifest["extra"]["authorizes_submission"]
    family = write_research_family_audit(
        [tmp_path / "results" / "leadlag"],
        labels=["leadlag"],
        output_dir=tmp_path / "family",
        registration_path=registration_dir,
        launch_matrix_path=tmp_path / "launches",
        config=ResearchFamilyConfig(
            family_id="launch_matrix_family",
            declaration_complete_attested=True,
            require_prospective_registration=True,
            require_launch_coverage=True,
        ),
    )
    family_rows = family.studies.set_index("study_label")
    assert family.passed
    assert family_rows.loc["imbalance", "study_disposition"] == "abandoned"
    assert float(
        family_rows.loc["imbalance", "within_study_adjusted_pvalue"]
    ) == 1.0
    assert not bool(family_rows.loc["imbalance", "family_passed"])
    assert int(family.summary.iloc[0]["abandoned_study_count"]) == 1
    assert bool(family.summary.iloc[0]["launch_coverage_passed"])
    family_cli_status = main(
        [
            "audit-research-family",
            "--studies",
            str(tmp_path / "results" / "leadlag"),
            "--label",
            "leadlag",
            "--out",
            str(tmp_path / "family_cli"),
            "--family-id",
            "launch_matrix_family",
            "--registration",
            str(registration_dir),
            "--require-prospective-registration",
            "--launch-matrix",
            str(tmp_path / "launches"),
            "--require-launch-coverage",
            "--attest-complete-family",
            "--fail-on-breach",
        ]
    )
    assert family_cli_status == 0
    catalog = catalog_experiment_runs([tmp_path / "launches"]).catalog.iloc[0]
    assert catalog["run_type"] == "research_family_launch_matrix"
    assert catalog["summary_file"] == "research_family_launch_summary.csv"
    assert bool(catalog["summary_status"])


def test_research_family_launch_cli_blocks_unattested_abandonment(tmp_path):
    _, registration_dir = _write_registration(tmp_path)
    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)
    output = tmp_path / "launches"

    status = main(
        [
            "plan-research-family-launches",
            "--registration",
            str(registration_dir),
            "--abandonments",
            str(abandonments),
            "--out",
            str(output),
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(output / "research_family_launch_summary.csv").iloc[0]
    rows = pd.read_csv(output / "research_family_launch_matrix.csv").set_index(
        "study_label"
    )
    failed = set(
        pd.read_csv(output / "research_family_launch_checks.csv")
        .loc[lambda frame: ~frame["passed"].astype(bool), "check"]
    )
    assert status == 2
    assert not bool(summary["passed"])
    assert rows.loc["imbalance", "study_status"] == "never_launched"
    assert not bool(rows.loc["imbalance", "abandonment_valid"])
    assert "abandonments_attested" in failed


def test_research_family_launch_blocks_result_bound_to_different_registration(
    tmp_path,
):
    _, registration_dir = _write_registration(tmp_path)
    pending = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
    )
    leadlag_contract = pending.launches.set_index("study_label").loc["leadlag"]
    _write_bound_result(
        tmp_path / "results" / "leadlag",
        registration_dir=registration_dir,
        registration_id="0" * 64,
        study_label="leadlag",
        launch_contract_id=str(leadlag_contract["contract_id"]),
        launch_contract_path=Path(str(leadlag_contract["contract_path"])),
    )
    abandonments = tmp_path / "abandonments.csv"
    pd.DataFrame(
        [{"study_label": "imbalance", "reason": "feed history was unavailable"}]
    ).to_csv(abandonments, index=False)

    report = write_research_family_launch_matrix(
        registration_dir,
        output_dir=tmp_path / "launches",
        abandonment_path=abandonments,
        attest_abandonments=True,
    )

    leadlag = report.launches.set_index("study_label").loc["leadlag"]
    assert not report.passed
    assert bool(leadlag["result_exists"])
    assert bool(leadlag["result_manifest_current"])
    assert not bool(leadlag["result_registration_bound"])
    assert not bool(leadlag["closure_covered"])
    assert "leadlag" in set(report.action_queue["component"])


def _write_registration(tmp_path):
    sweeps = _write_sweeps(tmp_path / "sweeps")
    plan_path = tmp_path / "plan.csv"
    pd.DataFrame(
        [
            {
                "study_label": label,
                "strategy": label,
                "market": "india_nse_index_derivatives",
                "hypothesis": f"{label} remains positive after costs",
                "planned_study_path": f"results/{label}",
                "primary_metric": "robust_score",
                "max_scenarios": 3,
                "development_sweeps": 6,
                "holdout_sweeps": 3,
                "sweep_paths_json": json.dumps([str(path) for path in sweeps]),
                "group_cols_json": json.dumps(["scenario"]),
                "sweep_labels_json": json.dumps(
                    [f"period_{index + 1}" for index in range(9)]
                ),
            }
            for label in ("leadlag", "imbalance")
        ]
    ).to_csv(plan_path, index=False)
    registration_dir = tmp_path / "registration"
    report = write_research_family_registration(
        plan_path,
        output_dir=registration_dir,
        family_id="launch_matrix_family",
    )
    return report, registration_dir


def _write_sweeps(root):
    paths = []
    source_dir = root / "_sources"
    source_dir.mkdir(parents=True)
    for index in range(9):
        path = root / f"period_{index + 1}"
        path.mkdir()
        pd.DataFrame(
            [
                {
                    "run": f"scenario_{scenario}",
                    "scenario": scenario,
                    "robust_score": score,
                    "net_pnl": score,
                    "proof_passed": True,
                    "max_drawdown": 0.0,
                    "fills": 10,
                    "worst_regime_equity_change": score,
                    "losing_regimes": 0,
                }
                for scenario, score in (("A", 10.0), ("B", 5.0), ("C", 1.0))
            ]
        ).to_csv(path / "sweep_runs.csv", index=False)
        source = source_dir / f"period_{index + 1}.csv"
        pd.DataFrame([{"ts": index, "bid": 100.0, "ask": 100.05}]).to_csv(
            source,
            index=False,
        )
        write_experiment_manifest(
            path,
            run_type="test_sweep",
            inputs={"market_data": source},
        )
        paths.append(path)
    return paths


def _write_bound_result(
    root,
    *,
    registration_dir,
    registration_id,
    study_label,
    launch_contract_id,
    launch_contract_path,
):
    root.mkdir(parents=True)
    significance_dir = root / "02_backtest_significance"
    overfit_dir = root / "02_backtest_overfit"
    significance_dir.mkdir()
    overfit_dir.mkdir()
    manifest_sha = file_sha256(registration_dir / "manifest.json")
    launch_contract_sha = file_sha256(launch_contract_path)
    pd.DataFrame(
        [
            {
                "ready": True,
                "strategy": study_label,
                "market": "india_nse_index_derivatives",
                "candidate_scenario_key": f"scenario={study_label}",
                "overfit_scenario_count": 3,
                "development_sweep_count": 6,
                "holdout_sweep_count": 3,
                "adjusted_sign_pvalue": 0.01,
                "backtest_holdout_passed": True,
                "next_gate": "stage-orders",
                "research_registration_provided": True,
                "research_registration_passed": True,
                "research_registration_id": registration_id,
                "research_registration_manifest_sha256": manifest_sha,
                "registered_study_label": study_label,
                "research_launch_contract_provided": True,
                "research_launch_contract_passed": True,
                "research_launch_contract_id": launch_contract_id,
                "research_launch_contract_sha256": launch_contract_sha,
                "authorizes_submission": False,
            }
        ]
    ).to_csv(root / "robust_selection_pipeline_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "passed": True,
                "registration_id": registration_id,
                "registered_study_label": study_label,
            }
        ]
    ).to_csv(
        root / "robust_selection_pipeline_research_registration.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "passed": True,
                "contract_id": launch_contract_id,
                "contract_sha256": launch_contract_sha,
            }
        ]
    ).to_csv(
        root / "robust_selection_pipeline_research_launch_contract.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                "passed": True,
                "candidate_scenario": f"scenario={study_label}",
                "scenario_trial_count": 3,
                "sign_pvalue": 0.003,
                "adjusted_sign_pvalue": 0.01,
            }
        ]
    ).to_csv(
        significance_dir / "backtest_significance_summary.csv",
        index=False,
    )
    pd.DataFrame(
        [{"passed": True, "score_column": "robust_score", "scenario_count": 3}]
    ).to_csv(overfit_dir / "backtest_overfit_summary.csv", index=False)
    write_experiment_manifest(
        root,
        run_type="robust_selection_pipeline",
        inputs={
            "research_family_registration": registration_dir,
            "research_family_registration_manifest": registration_dir
            / "manifest.json",
            "research_family_launch_contract": launch_contract_path,
        },
    )
