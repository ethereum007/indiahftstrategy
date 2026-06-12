import json

import pandas as pd

from hft_cli import main
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
