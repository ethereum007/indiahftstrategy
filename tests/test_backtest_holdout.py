import json

import pandas as pd

from hft_cli import main
from reports.backtest_holdout import (
    BacktestHoldoutConfig,
    write_backtest_holdout_audit,
)
from reports.catalog import catalog_experiment_runs
from reports.manifest import write_experiment_manifest
from reports.sweeps import write_sweep_comparison


def test_backtest_holdout_passes_frozen_candidate_without_reselection(tmp_path):
    selection, development = _write_selection(tmp_path)
    holdouts = _write_holdouts(
        tmp_path / "holdouts",
        [
            {"A": 8.0, "B": 100.0, "C": 2.0},
            {"A": 9.0, "B": 110.0, "C": 2.0},
            {"A": 10.0, "B": 120.0, "C": 2.0},
        ],
    )
    output = tmp_path / "holdout_audit"

    report = write_backtest_holdout_audit(
        selection,
        holdouts,
        output_dir=output,
        config=BacktestHoldoutConfig(group_columns=("scenario",)),
    )

    summary = report.summary.iloc[0]
    config = json.loads(
        (output / "backtest_holdout_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert report.action_queue.empty
    assert summary["candidate_scenario"] == "scenario=A"
    assert int(summary["expected_sweeps"]) == 3
    assert int(summary["covered_sweeps"]) == 3
    assert float(summary["proof_pass_rate"]) == 1.0
    assert float(summary["worst_score"]) == 8.0
    assert bool(summary["selection_holdout_disjoint"])
    assert not bool(summary["authorizes_submission"])
    assert set(report.observations["candidate_scenario"]) == {"scenario=A"}
    assert config["resolved_score_column"] == "robust_score"
    assert config["selection_manifest_sha256"]
    assert len(config["development_sweep_paths"]) == len(development)
    assert manifest["run_type"] == "backtest_holdout_audit"
    assert len(manifest["inputs"]["holdout_sweeps"]) == 3
    assert len(manifest["inputs"]["holdout_sweep_manifests"]) == 3
    assert not manifest["extra"]["authorizes_submission"]
    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert catalog["run_type"] == "backtest_holdout_audit"
    assert catalog["summary_file"] == "backtest_holdout_summary.csv"
    assert bool(catalog["summary_status"])
    for name in (
        "backtest_holdout_observations.csv",
        "backtest_holdout_provenance.csv",
        "backtest_holdout_checks.csv",
        "backtest_holdout_summary.csv",
        "backtest_holdout_action_queue.csv",
        "backtest_holdout_config.json",
        "backtest_holdout_runbook.md",
        "manifest.json",
    ):
        assert (output / name).exists()


def test_backtest_holdout_blocks_development_overlap(tmp_path):
    selection, development = _write_selection(tmp_path)
    holdouts = _write_holdouts(
        tmp_path / "holdouts",
        [
            {"A": 8.0, "B": 4.0, "C": 2.0},
            {"A": 9.0, "B": 4.0, "C": 2.0},
        ],
    )

    report = write_backtest_holdout_audit(
        selection,
        [development[0], *holdouts],
        output_dir=tmp_path / "holdout_audit",
        config=BacktestHoldoutConfig(group_columns=("scenario",)),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert "selection_holdout_disjoint" in failed
    assert "reserve_new_sweeps_never_consumed_by_selection" in set(
        report.action_queue["recommendation"]
    )


def test_backtest_holdout_blocks_missing_and_losing_candidate(tmp_path):
    selection, _ = _write_selection(tmp_path)
    holdouts = _write_holdouts(
        tmp_path / "holdouts",
        [
            {"A": 8.0, "B": 4.0, "C": 2.0},
            {"B": 20.0, "C": 2.0},
            {"A": -1.0, "B": 4.0, "C": 2.0},
        ],
    )

    report = write_backtest_holdout_audit(
        selection,
        holdouts,
        output_dir=tmp_path / "holdout_audit",
        config=BacktestHoldoutConfig(group_columns=("scenario",)),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    assert not report.passed
    assert {
        "finite_score_count",
        "candidate_coverage_rate",
        "proof_pass_rate",
        "worst_score",
        "worst_net_pnl",
    }.issubset(failed)
    assert int(report.summary.iloc[0]["covered_sweeps"]) == 2


def test_backtest_holdout_blocks_drifted_holdout_manifest(tmp_path):
    selection, _ = _write_selection(tmp_path)
    holdouts = _write_holdouts(
        tmp_path / "holdouts",
        [
            {"A": 8.0, "B": 4.0, "C": 2.0},
            {"A": 9.0, "B": 4.0, "C": 2.0},
            {"A": 10.0, "B": 4.0, "C": 2.0},
        ],
    )
    target = holdouts[1] / "sweep_runs.csv"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    report = write_backtest_holdout_audit(
        selection,
        holdouts,
        output_dir=tmp_path / "holdout_audit",
        config=BacktestHoldoutConfig(group_columns=("scenario",)),
    )

    failed = set(report.checks.loc[~report.checks["passed"], "check"])
    provenance = report.provenance.set_index("label")
    assert not report.passed
    assert "holdout_manifests_current" in failed
    assert provenance.loc["H02", "error"] == "artifact_drift"


def test_backtest_holdout_cli_fails_closed_on_overlap(tmp_path):
    selection, development = _write_selection(tmp_path)
    holdouts = _write_holdouts(
        tmp_path / "holdouts",
        [
            {"A": 8.0, "B": 4.0, "C": 2.0},
            {"A": 9.0, "B": 4.0, "C": 2.0},
        ],
    )
    output = tmp_path / "holdout_audit"

    status = main(
        [
            "audit-backtest-holdout",
            "--selection",
            str(selection),
            "--holdout-sweeps",
            str(development[0]),
            *[str(path) for path in holdouts],
            "--out",
            str(output),
            "--group-cols",
            "scenario",
            "--fail-on-breach",
        ]
    )

    assert status == 2
    summary = pd.read_csv(output / "backtest_holdout_summary.csv").iloc[0]
    assert not bool(summary["passed"])
    assert not bool(summary["selection_holdout_disjoint"])


def _write_selection(tmp_path):
    development = _write_holdouts(
        tmp_path / "development",
        [
            {"A": 10.0 + period, "B": 5.0, "C": 1.0}
            for period in range(6)
        ],
        prefix="D",
    )
    selection = tmp_path / "selection"
    write_sweep_comparison(
        development,
        output_dir=selection,
        labels=[f"D{index + 1:02d}" for index in range(len(development))],
        group_cols=["scenario"],
        min_sweeps=6,
    )
    return selection, development


def _write_holdouts(root, scores_by_period, *, prefix="H"):
    paths = []
    for index, scores in enumerate(scores_by_period, start=1):
        label = f"{prefix}{index:02d}"
        path = root / label
        path.mkdir(parents=True)
        rows = [_sweep_row(scenario, score) for scenario, score in scores.items()]
        pd.DataFrame(rows).to_csv(path / "sweep_runs.csv", index=False)
        source_dir = root / "_sources"
        source_dir.mkdir(exist_ok=True)
        source = source_dir / f"{label}.csv"
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


def _sweep_row(scenario, score):
    return {
        "run": f"scenario_{scenario}",
        "scenario": scenario,
        "proof_passed": score >= 0.0,
        "net_pnl": score,
        "robust_score": score,
        "max_drawdown": max(0.0, -score),
        "fills": 10,
        "worst_regime_equity_change": score,
        "losing_regimes": int(score < 0.0),
    }
