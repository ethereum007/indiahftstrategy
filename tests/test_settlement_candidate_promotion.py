import json

import pandas as pd

from hft_cli import main
from reports.settlement_candidate_promotion import (
    SettlementCandidatePromotionThresholds,
    evaluate_settlement_candidate_promotion,
    write_settlement_candidate_promotion,
)


def walkforward_summary(passed=True):
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": 0 if passed else 1,
                "fold_count": 2,
                "passed_folds": 2 if passed else 1,
                "pass_rate": 1.0 if passed else 0.5,
                "total_opportunities": 4,
                "total_net_edge": 450.0,
                "median_best_net_edge": 125.0,
                "best_net_edge": 150.0,
                "median_known_fraction": 0.6,
                "best_fold": "day1",
                "best_ts": 200,
                "best_expiry": "2026-06-10",
                "best_strike": 100.0,
                "best_option_type": "C",
                "best_direction": "buy_underpriced",
            }
        ]
    )


def candidate_config(ready=True):
    return {
        "schema_version": 1,
        "ready": ready,
        "strategy": "settlement_convergence",
        "source_run_type": "settlement_convergence_walkforward",
        "failed_checks": [] if ready else ["pass_rate"],
        "research_defaults": {
            "min_known_fraction": 0.5,
            "min_gross_edge_ticks": 10.0,
            "min_net_edge": 100.0,
            "qty": 75,
            "depth_fraction": 1.0,
        },
        "best_fold": {
            "fold": "day1",
            "ts": 200,
            "expiry": "2026-06-10",
            "strike": 100.0,
            "option_type": "C",
            "direction": "buy_underpriced",
            "best_net_edge": 150.0,
        },
    }


def write_walkforward(path, *, passed=True, ready=True):
    path.mkdir(parents=True, exist_ok=True)
    walkforward_summary(passed=passed).to_csv(
        path / "settlement_convergence_walkforward_summary.csv",
        index=False,
    )
    (path / "candidate_config.json").write_text(
        json.dumps(candidate_config(ready=ready), indent=2) + "\n",
        encoding="utf-8",
    )


def test_settlement_candidate_promotion_passes_ready_walkforward():
    report = evaluate_settlement_candidate_promotion(
        walkforward_summary(),
        candidate_config(),
        thresholds=SettlementCandidatePromotionThresholds(
            min_pass_rate=1.0,
            min_total_opportunities=2,
            min_total_net_edge=400.0,
            min_median_best_net_edge=100.0,
            min_median_known_fraction=0.5,
        ),
    )

    config = report.candidate_config
    assert report.ready
    assert report.summary.loc[0, "recommendation"] == "paper_or_shadow_candidate"
    assert config["ready"]
    assert config["strategy"] == "settlement_convergence"
    assert "strategy=settlement_convergence" in config["scenario_key"]
    assert config["parameters"]["best_direction"] == "buy_underpriced"
    assert config["metrics"]["total_net_edge"] == 450.0


def test_write_settlement_candidate_promotion_outputs_launch_compatible_files(tmp_path):
    walkforward_dir = tmp_path / "walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir)

    report = write_settlement_candidate_promotion(
        walkforward_dir,
        output_dir=out_dir,
        thresholds=SettlementCandidatePromotionThresholds(min_total_net_edge=400.0),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.ready
    assert config["ready"]
    assert (out_dir / "promotion_candidate.csv").exists()
    assert (out_dir / "promotion_checks.csv").exists()
    assert (out_dir / "promotion_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_settlement_candidate_promotion_fails_closed_on_weak_walkforward(tmp_path):
    walkforward_dir = tmp_path / "walkforward"
    out_dir = tmp_path / "promotion"
    write_walkforward(walkforward_dir, passed=False, ready=False)

    code = main(
        [
            "promote-settlement-candidate",
            "--walkforward",
            str(walkforward_dir),
            "--out",
            str(out_dir),
            "--min-pass-rate",
            "1",
            "--min-total-opportunities",
            "4",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "promotion_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert not config["ready"]
    assert "walkforward_passed" in config["failed_checks"]
