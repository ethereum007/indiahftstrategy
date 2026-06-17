import json

import pandas as pd

from hft_cli import main
from reports.strategy_scorecard import (
    StrategyScorecardThresholds,
    evaluate_strategy_scorecard,
    write_strategy_scorecard,
)


def row(run_type, summary_file, strategy, *, market="india_nse_index_derivatives", status=True, minute=30):
    return {
        "run_dir": f"runs/{strategy}/{run_type}",
        "run_type": run_type,
        "generated_at_utc": f"2026-06-10T09:{minute:02d}:00Z",
        "git_commit": "abc123",
        "git_dirty": False,
        "summary_status": status,
        "summary_file": summary_file,
        "summary_strategy": strategy,
        "summary_market": market,
        "summary_candidate_scenario_key": f"strategy={strategy}|market={market}|scenario=base",
        "parameters_json": json.dumps({"strategy": strategy, "market": market}),
        "input_count": 1,
        "input_file_count": 1,
        "input_directory_count": 0,
        "input_other_count": 0,
        "input_unfingerprinted_count": 0,
        "input_hashed_count": 1,
    }


def complete_leadlag_rows():
    return [
        row("leadlag_edge_audit", "leadlag_edge_summary.csv", "lead_lag_taker", minute=25),
        row("leadlag_replay_walkforward", "leadlag_replay_walkforward_summary.csv", "lead_lag_taker", minute=30),
        row("stress_report", "stress_summary.csv", "lead_lag_taker", minute=35),
        row("promotion_report", "promotion_summary.csv", "lead_lag_taker", minute=40),
        row("leadlag_order_plan", "leadlag_order_summary.csv", "lead_lag_taker", minute=45),
        row("leadlag_launch_pipeline", "leadlag_launch_pipeline_summary.csv", "lead_lag_taker", minute=50),
    ]


def incomplete_imbalance_rows():
    return [
        row("imbalance_edge_walkforward", "imbalance_edge_walkforward_summary.csv", "imbalance", minute=31),
        row("promotion_report", "promotion_summary.csv", "imbalance", minute=41),
    ]


def test_strategy_scorecard_ranks_ready_profile_and_keeps_mixed_promotions_separate():
    catalog = pd.DataFrame(complete_leadlag_rows() + incomplete_imbalance_rows())

    report = evaluate_strategy_scorecard(
        catalog,
        thresholds=StrategyScorecardThresholds(
            profiles=("leadlag", "imbalance"),
            expected_market="india_nse_index_derivatives",
        ),
    )

    ranked = report.scorecard.set_index("profile")
    assert report.ready
    assert ranked.loc["leadlag", "rank"] == 1
    assert bool(ranked.loc["leadlag", "ready"])
    assert ranked.loc["leadlag", "readiness_score"] == 1.0
    assert not bool(ranked.loc["imbalance", "ready"])
    assert ranked.loc["imbalance", "readiness_score"] < 1.0
    assert "imbalance_replay_walkforward" in ranked.loc["imbalance", "missing_required_run_types"]
    assert report.summary.loc[0, "best_profile"] == "leadlag"


def test_write_strategy_scorecard_outputs_files_and_manifest(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "scorecard"
    pd.DataFrame(complete_leadlag_rows()).to_csv(catalog_path, index=False)

    report = write_strategy_scorecard(
        catalog_path,
        output_dir=out_dir,
        thresholds=StrategyScorecardThresholds(
            profiles=("leadlag",),
            expected_market="india_nse_index_derivatives",
            require_file_inputs=True,
        ),
    )

    assert report.output_dir == out_dir
    assert report.ready
    assert (out_dir / "strategy_scorecard.csv").exists()
    assert (out_dir / "strategy_scorecard_gaps.csv").exists()
    assert (out_dir / "strategy_scorecard_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_strategy_scorecard_returns_breach_when_no_profile_is_ready(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "scorecard"
    pd.DataFrame(incomplete_imbalance_rows()).to_csv(catalog_path, index=False)

    code = main(
        [
            "score-strategy-readiness",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "imbalance",
            "--market",
            "india_nse_index_derivatives",
            "--fail-on-breach",
        ]
    )

    scorecard = pd.read_csv(out_dir / "strategy_scorecard.csv")
    gaps = pd.read_csv(out_dir / "strategy_scorecard_gaps.csv")
    assert code == 2
    assert not bool(scorecard.loc[0, "ready"])
    assert "missing_required_run_type" in set(gaps["gap"])
