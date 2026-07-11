import json

import pandas as pd

from hft_cli import main
from reports.backtest_overfit import (
    BacktestOverfitConfig,
    BacktestOverfitThresholds,
    evaluate_backtest_overfit,
    write_backtest_overfit_audit,
)
from reports.catalog import catalog_experiment_runs
from reports.manifest import write_experiment_manifest


def test_backtest_overfit_audit_passes_stable_edge():
    runs, scores = _stable_panel()

    report = evaluate_backtest_overfit(
        runs,
        scenario_scores=scores,
        thresholds=BacktestOverfitThresholds(
            max_probability_overfit=0.0,
            min_median_oos_score=5.0,
            min_oos_positive_rate=1.0,
            min_median_rank_correlation=0.9,
        ),
    )

    summary = report.summary.iloc[0]
    assert report.passed
    assert int(summary["partition_count"]) == 6
    assert int(summary["scenario_count"]) == 3
    assert int(summary["combination_count"]) == 20
    assert float(summary["probability_overfit"]) == 0.0
    assert float(summary["oos_positive_rate"]) == 1.0
    assert float(summary["median_rank_correlation"]) == 1.0
    assert summary["most_selected_scenario"] == "scenario=A"
    assert summary["selection_candidate_scenario"] == "scenario=A"
    assert float(summary["selection_candidate_rate"]) == 1.0
    assert float(summary["selection_candidate_overfit_rate"]) == 0.0
    assert float(summary["selection_candidate_oos_positive_rate"]) == 1.0
    assert set(report.combinations["selected_scenario"]) == {"scenario=A"}
    assert report.action_queue.empty


def test_backtest_overfit_audit_detects_partition_memorization():
    runs, scores = _memorized_panel()

    report = evaluate_backtest_overfit(
        runs,
        scenario_scores=scores,
        thresholds=BacktestOverfitThresholds(
            max_probability_overfit=0.25,
            min_median_oos_score=0.0,
            min_oos_positive_rate=0.5,
            min_median_rank_correlation=0.0,
        ),
    )

    summary = report.summary.iloc[0]
    assert not report.passed
    assert float(summary["probability_overfit"]) == 1.0
    assert float(summary["median_selected_oos_score"]) == -10.0
    assert float(summary["oos_positive_rate"]) == 0.0
    assert summary["selection_candidate_scenario"] == "scenario=S0"
    assert float(summary["selection_candidate_overfit_rate"]) == 1.0
    assert float(summary["selection_candidate_oos_positive_rate"]) == 0.0
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "probability_overfit" in failed
    assert "median_selected_oos_score" in failed
    assert "oos_positive_rate" in failed
    assert "selection_candidate_overfit_rate" in failed
    assert "selection_candidate_oos_positive_rate" in failed
    assert not report.action_queue.empty
    assert set(report.action_queue["next_gate"]) == {"compare-sweeps"}


def test_backtest_overfit_groups_odd_period_count_without_dropping_periods():
    runs, scores = _stable_panel(periods=7)

    report = evaluate_backtest_overfit(
        runs,
        scenario_scores=scores,
        config=BacktestOverfitConfig(max_partitions=6),
    )

    assert report.passed
    assert report.partition_map["split"].nunique() == 7
    assert report.partition_map["partition"].nunique() == 6
    assert len(report.combinations) == 20


def test_backtest_overfit_fails_when_rank_one_candidate_is_absent_from_runs():
    runs, scores = _stable_panel()
    scores["rank"] = scores["rank"] + 1
    scores = pd.concat(
        [
            pd.DataFrame(
                [{"rank": 1, "scenario": "Z", "scenario_key": "scenario=Z"}]
            ),
            scores,
        ],
        ignore_index=True,
    )

    report = evaluate_backtest_overfit(runs, scenario_scores=scores)

    assert not report.passed
    assert report.summary.iloc[0]["selection_candidate_scenario"] == "scenario=Z"
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "selection_candidate_audited" in failed
    assert "selection_candidate_rate" in failed


def test_write_backtest_overfit_audit_binds_selection_manifest(tmp_path):
    selection = tmp_path / "selection"
    output = tmp_path / "audit"
    runs, scores = _stable_panel()
    _write_selection(selection, runs, scores)

    report = write_backtest_overfit_audit(selection, output_dir=output)

    assert report.passed
    assert report.output_dir == output
    for name in (
        "backtest_overfit_combinations.csv",
        "backtest_overfit_scenario_stability.csv",
        "backtest_overfit_partition_scores.csv",
        "backtest_overfit_partition_map.csv",
        "backtest_overfit_checks.csv",
        "backtest_overfit_summary.csv",
        "backtest_overfit_action_queue.csv",
        "backtest_overfit_config.json",
        "backtest_overfit_runbook.md",
        "manifest.json",
    ):
        assert (output / name).exists()
    config = json.loads((output / "backtest_overfit_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert config["selection_path"] == str(selection.resolve())
    assert len(config["selection_manifest_sha256"]) == 64
    assert config["resolved_score_column"] == "robust_score"
    assert config["resolved_scenario_columns"] == ["scenario"]
    assert manifest["run_type"] == "backtest_overfit_audit"
    assert manifest["inputs"]["selection_manifest"]["sha256"] == config["selection_manifest_sha256"]
    catalog = catalog_experiment_runs([output]).catalog.iloc[0]
    assert catalog["run_type"] == "backtest_overfit_audit"
    assert bool(catalog["summary_status"])
    assert float(catalog["summary_probability_overfit"]) == 0.0


def test_backtest_overfit_cli_fails_closed_for_memorized_grid(tmp_path):
    selection = tmp_path / "selection"
    output = tmp_path / "audit"
    runs, scores = _memorized_panel()
    _write_selection(selection, runs, scores)

    status = main(
        [
            "audit-backtest-overfit",
            "--selection",
            str(selection),
            "--out",
            str(output),
            "--max-probability-overfit",
            "0.25",
            "--fail-on-breach",
        ]
    )

    assert status == 2
    summary = pd.read_csv(output / "backtest_overfit_summary.csv").iloc[0]
    assert not bool(summary["passed"])
    assert float(summary["probability_overfit"]) == 1.0


def _stable_panel(periods: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for period in range(periods):
        for scenario, base in (("A", 10.0), ("B", 5.0), ("C", -1.0)):
            rows.append(
                {
                    "sweep": f"2026-06-{period + 1:02d}",
                    "scenario": scenario,
                    "run": f"scenario_{scenario}",
                    "robust_score": base + period * 0.1,
                    "net_pnl": base + period * 0.2,
                }
            )
    scores = pd.DataFrame(
        [
            {"rank": index + 1, "scenario": scenario, "scenario_key": f"scenario={scenario}"}
            for index, scenario in enumerate(("A", "B", "C"))
        ]
    )
    return pd.DataFrame(rows), scores


def _memorized_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    scenarios = [f"S{index}" for index in range(6)]
    rows = []
    for period in range(6):
        for index, scenario in enumerate(scenarios):
            score = 50.0 if index == period else -10.0
            rows.append(
                {
                    "sweep": f"day{period + 1}",
                    "scenario": scenario,
                    "run": f"scenario_{scenario}",
                    "robust_score": score,
                    "net_pnl": score,
                }
            )
    scores = pd.DataFrame(
        [
            {"rank": index + 1, "scenario": scenario, "scenario_key": f"scenario={scenario}"}
            for index, scenario in enumerate(scenarios)
        ]
    )
    return pd.DataFrame(rows), scores


def _write_selection(path, runs: pd.DataFrame, scores: pd.DataFrame) -> None:
    path.mkdir(parents=True)
    runs.to_csv(path / "scenario_runs.csv", index=False)
    scores.to_csv(path / "scenario_scores.csv", index=False)
    write_experiment_manifest(
        path,
        run_type="sweep_comparison",
        parameters={"group_cols": ["scenario"]},
    )
