import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.promotion import PromotionThresholds
from reports.robust_selection_pipeline import write_robust_selection_pipeline


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
        "selection",
        "backtest_overfit",
        "promotion",
    }
    assert report.stages["status"].astype(bool).all()
    assert summary["candidate_scenario_key"] == "scenario=A"
    assert float(summary["probability_overfit"]) == 0.0
    assert float(summary["selection_candidate_rate"]) == 1.0
    assert summary["next_gate"] == "stage-orders"
    assert not bool(summary["authorizes_submission"])
    assert config["ready"]
    assert config["source_run_type"] == "robust_selection_pipeline"
    assert config["backtest_overfit"]["passed"]
    assert config["backtest_overfit"]["selection_matches"]
    assert not config["authorizes_submission"]
    assert manifest["run_type"] == "robust_selection_pipeline"
    assert not manifest["extra"]["authorizes_submission"]
    assert len(manifest["inputs"]["sweeps"]) == 6
    assert manifest["inputs"]["backtest_overfit_manifest"]["kind"] == "file"
    for name in (
        "01_selection/selection_summary.csv",
        "02_backtest_overfit/backtest_overfit_summary.csv",
        "03_promotion/promotion_summary.csv",
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
    assert not bool(stages.loc["promotion", "status"])
    assert float(summary["probability_overfit"]) == 1.0
    assert summary["next_gate"] == "audit-backtest-overfit"
    assert set(actions["component"]) == {"backtest_overfit", "promotion"}
    failed = set(
        promotion_checks.loc[
            ~promotion_checks["passed"].astype(bool), "check"
        ]
    )
    assert "overfit_audit_passed" in failed


def test_robust_selection_pipeline_blocks_underpowered_period_count(tmp_path):
    sweeps, labels = _write_stable_sweeps(tmp_path / "sweeps", periods=3)
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
        "promotion",
    }
    assert set(report.action_queue["queue_status"]) == {"blocked"}


def _write_stable_sweeps(root, *, periods=6):
    labels = [f"2026-06-{period + 1:02d}" for period in range(periods)]
    paths = []
    for period, label in enumerate(labels):
        path = root / label
        path.mkdir(parents=True)
        rows = []
        for scenario, base in (("A", 10.0), ("B", 5.0), ("C", 1.0)):
            score = base + period * 0.1
            rows.append(_sweep_row(scenario, score))
        pd.DataFrame(rows).to_csv(path / "sweep_runs.csv", index=False)
        paths.append(path)
    return paths, labels


def _write_memorized_sweeps(root):
    scenarios = [f"S{index}" for index in range(6)]
    labels = [f"2026-06-{period + 1:02d}" for period in range(6)]
    paths = []
    for period, label in enumerate(labels):
        path = root / label
        path.mkdir(parents=True)
        rows = [
            _sweep_row(scenario, 10.0 if index == period else -10.0)
            for index, scenario in enumerate(scenarios)
        ]
        pd.DataFrame(rows).to_csv(path / "sweep_runs.csv", index=False)
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
