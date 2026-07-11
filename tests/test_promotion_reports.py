import json

import pandas as pd

from hft_cli import main
from reports.manifest import file_sha256, write_experiment_manifest
from reports.promotion import PromotionThresholds, evaluate_promotion, write_promotion_report


def selection_scores():
    return pd.DataFrame(
        [
            {
                "rank": 1,
                "trigger_ticks": 2.0,
                "order_latency_us": 100.0,
                "scenario_key": "trigger_ticks=2|order_latency_us=100",
                "sweeps_seen": 2,
                "scenario_runs": 2,
                "passed_runs": 2,
                "pass_rate": 1.0,
                "median_net_pnl": 12.0,
                "min_net_pnl": 10.0,
                "median_robust_score": 9.0,
                "min_robust_score": 8.0,
                "worst_drawdown": 2.0,
                "median_fills": 15.0,
                "min_fills": 14.0,
                "worst_regime_equity_change": 1.0,
                "runs_with_losing_regimes": 0,
                "selection_passed": True,
            },
            {
                "rank": 2,
                "trigger_ticks": 3.0,
                "order_latency_us": 100.0,
                "scenario_key": "trigger_ticks=3|order_latency_us=100",
                "sweeps_seen": 2,
                "scenario_runs": 2,
                "passed_runs": 1,
                "pass_rate": 0.5,
                "median_net_pnl": 8.0,
                "min_net_pnl": -1.0,
                "median_robust_score": 4.0,
                "min_robust_score": -2.0,
                "worst_drawdown": 6.0,
                "median_fills": 9.0,
                "min_fills": 0.0,
                "worst_regime_equity_change": -1.0,
                "runs_with_losing_regimes": 1,
                "selection_passed": False,
            },
        ]
    )


def selection_runs():
    return pd.DataFrame(
        [
            {
                "sweep": "day1",
                "run": "a",
                "trigger_ticks": 2.0,
                "order_latency_us": 100.0,
                "net_pnl": 10.0,
                "fills": 14,
                "order_to_trade_ratio": 4.0,
                "maker_share": 1.0,
                "markout_mean": 0.5,
                "proof_passed": True,
            },
            {
                "sweep": "day2",
                "run": "a",
                "trigger_ticks": 2.0,
                "order_latency_us": 100.0,
                "net_pnl": 14.0,
                "fills": 16,
                "order_to_trade_ratio": 5.0,
                "maker_share": 1.0,
                "markout_mean": 0.4,
                "proof_passed": True,
            },
        ]
    )


def write_selection(path, scores=None):
    path.mkdir(parents=True, exist_ok=True)
    (selection_scores() if scores is None else scores).to_csv(path / "scenario_scores.csv", index=False)
    selection_runs().to_csv(path / "scenario_runs.csv", index=False)
    write_experiment_manifest(path, run_type="sweep_comparison")


def test_evaluate_promotion_ready_for_selectable_scenario():
    report = evaluate_promotion(
        selection_scores(),
        selection_runs(),
        thresholds=PromotionThresholds(
            min_pass_rate=1.0,
            min_sweeps=2,
            min_median_net_pnl=10.0,
            min_min_net_pnl=0.0,
            max_worst_drawdown=3.0,
            min_median_fills=10.0,
            max_otr=10.0,
            min_maker_share=1.0,
            min_markout_mean=0.3,
        ),
    )

    assert report.ready
    assert report.candidate.iloc[0]["scenario_key"] == "trigger_ticks=2|order_latency_us=100"
    assert set(report.checks["passed"]) == {True}
    assert report.summary.iloc[0]["recommendation"] == "paper_or_shadow_candidate"


def test_write_promotion_report_outputs_candidate_config_and_manifest(tmp_path):
    selection_dir = tmp_path / "selection"
    out_dir = tmp_path / "promotion"
    write_selection(selection_dir)

    report = write_promotion_report(
        selection_dir,
        output_dir=out_dir,
        thresholds=PromotionThresholds(min_sweeps=2, min_median_net_pnl=10.0),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert config["parameters"] == {"trigger_ticks": 2.0, "order_latency_us": 100.0}
    assert (out_dir / "promotion_candidate.csv").exists()
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "promotion_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_promote_scenario_can_fail_closed(tmp_path):
    selection_dir = tmp_path / "selection"
    out_dir = tmp_path / "cli_promotion"
    scores = selection_scores()
    scores["selection_passed"] = False
    write_selection(selection_dir, scores=scores)

    code = main(
        [
            "promote-scenario",
            "--selection",
            str(selection_dir),
            "--out",
            str(out_dir),
            "--min-sweeps",
            "2",
            "--min-median-net-pnl",
            "10",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "candidate_config.json").exists()


def test_promotion_can_require_backtest_overfit_audit():
    report = evaluate_promotion(
        selection_scores(),
        selection_runs(),
        thresholds=PromotionThresholds(
            min_sweeps=2,
            min_median_net_pnl=10.0,
            require_overfit_audit=True,
        ),
    )

    assert not report.ready
    check = report.checks.loc[report.checks["check"] == "overfit_audit_provided"].iloc[0]
    assert not bool(check["passed"])


def test_promotion_can_require_backtest_significance_audit():
    report = evaluate_promotion(
        selection_scores(),
        selection_runs(),
        thresholds=PromotionThresholds(
            min_sweeps=2,
            min_median_net_pnl=10.0,
            require_significance_audit=True,
        ),
    )

    assert not report.ready
    check = report.checks.loc[
        report.checks["check"] == "significance_audit_provided"
    ].iloc[0]
    assert not bool(check["passed"])


def test_promotion_accepts_matching_passed_backtest_overfit_audit(tmp_path):
    selection_dir = tmp_path / "selection"
    overfit_dir = tmp_path / "overfit"
    output_dir = tmp_path / "promotion"
    write_selection(selection_dir)
    write_overfit_audit(overfit_dir, selection_dir, passed=True)

    report = write_promotion_report(
        selection_dir,
        output_dir=output_dir,
        overfit_audit_path=overfit_dir,
        thresholds=PromotionThresholds(
            min_sweeps=2,
            min_median_net_pnl=10.0,
            require_overfit_audit=True,
        ),
    )

    assert report.ready
    summary = report.summary.iloc[0]
    assert bool(summary["overfit_audit_provided"])
    assert bool(summary["overfit_audit_passed"])
    assert bool(summary["overfit_selection_matches"])
    assert float(summary["probability_overfit"]) == 0.1
    config = json.loads((output_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert config["backtest_overfit"]["passed"]
    assert config["backtest_overfit"]["selection_matches"]
    assert len(config["backtest_overfit"]["audit_manifest_sha256"]) == 64
    assert manifest["inputs"]["backtest_overfit_audit"]["kind"] == "directory"
    assert manifest["inputs"]["backtest_overfit_audit_manifest"]["kind"] == "file"


def test_promotion_blocks_failed_or_unrelated_backtest_overfit_audit(tmp_path):
    selection_dir = tmp_path / "selection"
    other_selection = tmp_path / "other_selection"
    overfit_dir = tmp_path / "overfit"
    output_dir = tmp_path / "promotion"
    write_selection(selection_dir)
    write_selection(other_selection)
    write_overfit_audit(overfit_dir, other_selection, passed=False)
    runs_path = other_selection / "scenario_runs.csv"
    runs_path.write_text(runs_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    code = main(
        [
            "promote-scenario",
            "--selection",
            str(selection_dir),
            "--out",
            str(output_dir),
            "--overfit-audit",
            str(overfit_dir),
            "--require-overfit-audit",
            "--min-sweeps",
            "2",
            "--min-median-net-pnl",
            "10",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    checks = pd.read_csv(output_dir / "promotion_checks.csv")
    failed = set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert "overfit_audit_passed" in failed
    assert "overfit_selection_matches" in failed
    assert "overfit_audit_manifest_current" in failed


def test_promotion_blocks_drifted_backtest_significance_audit(tmp_path):
    selection_dir = tmp_path / "selection"
    significance_dir = tmp_path / "significance"
    output_dir = tmp_path / "promotion"
    write_selection(selection_dir)
    write_significance_audit(significance_dir, selection_dir, passed=True)
    summary_path = significance_dir / "backtest_significance_summary.csv"
    summary_path.write_text(
        summary_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    report = write_promotion_report(
        selection_dir,
        output_dir=output_dir,
        significance_audit_path=significance_dir,
        thresholds=PromotionThresholds(
            min_sweeps=2,
            min_median_net_pnl=10.0,
            require_significance_audit=True,
        ),
    )

    assert not report.ready
    failed = set(report.checks.loc[~report.checks["passed"].astype(bool), "check"])
    assert "significance_audit_manifest_current" in failed


def write_overfit_audit(path, selection, *, passed):
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "passed": passed,
                "ready": passed,
                "probability_overfit": 0.1 if passed else 0.8,
                "partition_count": 6,
                "scenario_count": 3,
                "combination_count": 20,
                "score_column": "robust_score",
            }
        ]
    ).to_csv(path / "backtest_overfit_summary.csv", index=False)
    (path / "backtest_overfit_config.json").write_text(
        json.dumps(
            {
                "selection_path": str(selection.resolve()),
                "selection_manifest_sha256": file_sha256(selection / "manifest.json"),
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
            "selection_manifest": selection / "manifest.json",
        },
    )


def write_significance_audit(path, selection, *, passed):
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "passed": passed,
                "candidate_scenario": "lookback=10|threshold=1.0",
                "observation_count": 6,
                "adjusted_sign_pvalue": 0.05 if passed else 0.5,
                "bootstrap_mean_lower": 1.0 if passed else -1.0,
                "bootstrap_probability_positive": 0.99 if passed else 0.5,
            }
        ]
    ).to_csv(path / "backtest_significance_summary.csv", index=False)
    (path / "backtest_significance_config.json").write_text(
        json.dumps(
            {
                "selection_path": str(selection.resolve()),
                "selection_manifest_sha256": file_sha256(selection / "manifest.json"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        path,
        run_type="backtest_significance_audit",
        inputs={
            "selection": selection,
            "selection_manifest": selection / "manifest.json",
        },
    )
