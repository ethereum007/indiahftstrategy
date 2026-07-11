import json

import pandas as pd

from hft_cli import main
from reports.backtest_significance import (
    BacktestSignificanceConfig,
    evaluate_backtest_significance,
    write_backtest_significance_audit,
)
from reports.catalog import catalog_experiment_runs
from reports.manifest import file_sha256, write_experiment_manifest


def test_backtest_significance_passes_stable_candidate_and_is_deterministic(tmp_path):
    overfit = _write_overfit_audit(
        tmp_path / "overfit",
        candidate_scores=[10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
    )
    output = tmp_path / "significance"

    report = write_backtest_significance_audit(overfit, output_dir=output)
    repeated = evaluate_backtest_significance(
        pd.read_csv(overfit / "backtest_overfit_partition_scores.csv"),
        pd.read_csv(overfit / "backtest_overfit_summary.csv"),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (output / "backtest_significance_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert int(summary["observation_count"]) == 6
    assert int(summary["positive_count"]) == 6
    assert float(summary["sign_pvalue"]) == 0.015625
    assert float(summary["adjusted_sign_pvalue"]) == 0.046875
    assert float(summary["bootstrap_probability_positive"]) == 1.0
    assert float(summary["bootstrap_mean_lower"]) > 0.0
    assert summary["next_gate"] == "promote-scenario"
    assert not bool(summary["authorizes_submission"])
    pd.testing.assert_frame_equal(
        report.bootstrap_quantiles,
        repeated.bootstrap_quantiles,
    )
    assert config["overfit_manifest_integrity"]["passed"]
    assert len(config["overfit_manifest_sha256"]) == 64
    assert len(config["selection_manifest_sha256"]) == 64
    assert manifest["run_type"] == "backtest_significance_audit"
    assert not manifest["extra"]["authorizes_submission"]
    assert manifest["inputs"]["backtest_overfit_manifest"]["kind"] == "file"
    for name in (
        "backtest_significance_observations.csv",
        "backtest_significance_bootstrap_quantiles.csv",
        "backtest_significance_checks.csv",
        "backtest_significance_summary.csv",
        "backtest_significance_action_queue.csv",
        "backtest_significance_config.json",
        "backtest_significance_runbook.md",
        "manifest.json",
    ):
        assert (output / name).exists()
    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert catalog["run_type"] == "backtest_significance_audit"
    assert catalog["summary_file"] == "backtest_significance_summary.csv"
    assert bool(catalog["summary_status"])


def test_backtest_significance_blocks_weak_underpowered_candidate():
    scores = pd.DataFrame(
        {
            "partition": [0, 1, 2, 3],
            "scenario=A": [1.0, -1.0, 1.0, -1.0],
            "scenario=B": [0.5, 0.5, -0.5, -0.5],
            "scenario=C": [-1.0, -1.0, -1.0, -1.0],
        }
    )
    overfit_summary = pd.DataFrame(
        [
            {
                "passed": True,
                "selection_candidate_scenario": "scenario=A",
                "scenario_count": 3,
            }
        ]
    )

    report = evaluate_backtest_significance(
        scores,
        overfit_summary,
        config=BacktestSignificanceConfig(bootstrap_samples=1_000),
    )

    assert not report.passed
    summary = report.summary.iloc[0]
    assert float(summary["adjusted_sign_pvalue"]) == 1.0
    assert float(summary["bootstrap_probability_positive"]) < 0.95
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "observation_count" in failed
    assert "nonzero_observation_count" in failed
    assert "adjusted_sign_pvalue" in failed
    assert "bootstrap_probability_positive" in failed
    assert not report.action_queue.empty


def test_backtest_significance_blocks_drifted_overfit_manifest(tmp_path):
    overfit = _write_overfit_audit(
        tmp_path / "overfit",
        candidate_scores=[10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
    )
    scores_path = overfit / "backtest_overfit_partition_scores.csv"
    scores_path.write_text(
        scores_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    report = write_backtest_significance_audit(
        overfit,
        output_dir=tmp_path / "significance",
    )

    assert not report.passed
    integrity = report.checks.loc[
        report.checks["check"] == "overfit_manifest_current"
    ].iloc[0]
    assert not bool(integrity["passed"])
    assert report.config["overfit_manifest_integrity"]["error"] == "artifact_drift"


def test_backtest_significance_cli_fails_closed_for_too_few_periods(tmp_path):
    overfit = _write_overfit_audit(
        tmp_path / "overfit",
        candidate_scores=[10.0, 10.1, 10.2],
    )
    output = tmp_path / "significance"

    status = main(
        [
            "audit-backtest-significance",
            "--overfit-audit",
            str(overfit),
            "--out",
            str(output),
            "--bootstrap-samples",
            "1000",
            "--fail-on-breach",
        ]
    )

    assert status == 2
    summary = pd.read_csv(output / "backtest_significance_summary.csv").iloc[0]
    assert not bool(summary["passed"])
    assert int(summary["observation_count"]) == 3


def _write_overfit_audit(path, *, candidate_scores):
    path.mkdir(parents=True)
    selection = path.parent / f"{path.name}_selection"
    selection.mkdir()
    source = path.parent / f"{path.name}_source.csv"
    source.write_text("ts,bid,ask\n1,100,100.05\n", encoding="utf-8")
    pd.DataFrame([{"run": "scenario_A", "robust_score": 10.0}]).to_csv(
        selection / "scenario_runs.csv",
        index=False,
    )
    selection_manifest = write_experiment_manifest(
        selection,
        run_type="sweep_comparison",
        inputs={"market_data": source},
    )
    pd.DataFrame(
        [
            {
                "passed": True,
                "selection_candidate_scenario": "scenario=A",
                "scenario_count": 3,
                "partition_count": len(candidate_scores),
                "combination_count": 20,
                "score_column": "robust_score",
            }
        ]
    ).to_csv(path / "backtest_overfit_summary.csv", index=False)
    pd.DataFrame(
        {
            "partition": list(range(len(candidate_scores))),
            "scenario=A": candidate_scores,
            "scenario=B": [5.0] * len(candidate_scores),
            "scenario=C": [1.0] * len(candidate_scores),
        }
    ).to_csv(path / "backtest_overfit_partition_scores.csv", index=False)
    (path / "backtest_overfit_config.json").write_text(
        json.dumps(
            {
                "selection_path": str(selection.resolve()),
                "selection_manifest_sha256": file_sha256(selection_manifest),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        path,
        run_type="backtest_overfit_audit",
        inputs={
            "selection": selection,
            "selection_manifest": selection_manifest,
        },
    )
    return path
