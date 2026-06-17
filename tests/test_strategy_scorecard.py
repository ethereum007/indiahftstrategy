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


def complete_ops_launch_rows(strategy="lead_lag_taker", *, market="india_nse_index_derivatives"):
    run_types = [
        ("scaleup_plan", "scaleup_summary.csv"),
        ("runtime_telemetry_snapshot", "runtime_telemetry_summary.csv"),
        ("runtime_guard", "runtime_guard_summary.csv"),
        ("runtime_session_monitor", "runtime_session_summary.csv"),
        ("broker_readiness", "broker_readiness_summary.csv"),
        ("cutover_gate", "cutover_summary.csv"),
        ("route_enable_packet", "route_enable_summary.csv"),
        ("broker_dispatch_plan", "broker_dispatch_summary.csv"),
        ("broker_dispatch_send_packet", "broker_dispatch_send_summary.csv"),
        ("broker_dispatch_ack_reconciliation", "broker_dispatch_ack_summary.csv"),
        ("broker_dispatch_roundtrip", "broker_dispatch_roundtrip_summary.csv"),
    ]
    return [
        row(run_type, summary_file, strategy, market=market, minute=10 + index)
        for index, (run_type, summary_file) in enumerate(run_types)
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
    assert ranked.loc["leadlag", "next_gate"] == "plan-scaleup"
    assert ranked.loc["leadlag", "next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert not bool(ranked.loc["imbalance", "ready"])
    assert ranked.loc["imbalance", "readiness_score"] < 1.0
    assert "imbalance_replay_walkforward" in ranked.loc["imbalance", "missing_required_run_types"]
    assert ranked.loc["imbalance", "next_required_run_type"] == "imbalance_replay_walkforward"
    assert ranked.loc["imbalance", "next_gate"] == "walkforward-imbalance-replay"
    assert report.summary.loc[0, "best_profile"] == "leadlag"
    assert report.summary.loc[0, "best_next_gate"] == "plan-scaleup"
    assert report.summary.loc[0, "best_next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert report.config["best_profile"] == "leadlag"
    assert report.config["next_actions"][0]["next_gate"] == "plan-scaleup"
    assert report.config["next_actions"][0]["next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert report.config["next_actions"][1]["missing_required_run_types"] == [
        "imbalance_replay_walkforward",
        "imbalance_research_pipeline",
        "imbalance_order_plan",
        "imbalance_launch_pipeline",
    ]


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
    assert (out_dir / "strategy_scorecard_next_actions.json").exists()
    assert (out_dir / "manifest.json").exists()
    config = json.loads((out_dir / "strategy_scorecard_next_actions.json").read_text(encoding="utf-8"))
    assert config == report.config
    assert config["next_actions"][0]["profile"] == "leadlag"


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
    assert scorecard.loc[0, "next_gate"] == "walkforward-imbalance-replay"
    assert scorecard.loc[0, "next_gate_help_command"] == "python -m hft_cli walkforward-imbalance-replay --help"
    assert "missing_required_run_type" in set(gaps["gap"])
    next_gate = gaps.loc[gaps["required_run_type"] == "imbalance_replay_walkforward", "next_gate"].iloc[0]
    assert next_gate == "walkforward-imbalance-replay"
    help_command = gaps.loc[
        gaps["required_run_type"] == "imbalance_replay_walkforward",
        "next_gate_help_command",
    ].iloc[0]
    assert help_command == "python -m hft_cli walkforward-imbalance-replay --help"


def test_strategy_scorecard_scores_named_ops_launch_strategy_with_file_inputs():
    catalog = pd.DataFrame(
        complete_ops_launch_rows("lead_lag_taker") + complete_ops_launch_rows("imbalance")
    )

    report = evaluate_strategy_scorecard(
        catalog,
        thresholds=StrategyScorecardThresholds(
            profiles=("ops_launch",),
            expected_market="india_nse_index_derivatives",
            expected_ops_strategy="leadlag",
            require_file_inputs=True,
        ),
    )

    score = report.scorecard.iloc[0]
    assert report.ready
    assert score["profile"] == "ops_launch"
    assert score["strategy"] == "lead_lag_taker"
    assert score["recommendation"] == "ready_for_live_dryrun_route_review"
    assert score["next_gate"] == "review-route-readiness"
    assert score["next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert report.summary.loc[0, "recommendation"] == "promote_ready_route_to_live_dryrun_review"
    assert report.summary.loc[0, "best_next_gate"] == "review-route-readiness"
    assert report.summary.loc[0, "best_next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert report.config["best_next_gate"] == "review-route-readiness"
    assert report.config["best_next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert report.config["next_actions"][0]["next_gate"] == "review-route-readiness"
    assert report.config["next_actions"][0]["next_gate_help_command"] == (
        "python -m hft_cli review-route-readiness --help"
    )
    assert set(report.gaps["total_runs"]) == {1}


def test_cli_strategy_scorecard_ops_launch_fails_closed_on_mixed_strategy_without_filter(tmp_path):
    catalog_path = tmp_path / "experiment_catalog.csv"
    out_dir = tmp_path / "scorecard"
    pd.DataFrame(
        complete_ops_launch_rows("lead_lag_taker") + complete_ops_launch_rows("imbalance")
    ).to_csv(catalog_path, index=False)

    code = main(
        [
            "score-strategy-readiness",
            "--catalog",
            str(catalog_path),
            "--out",
            str(out_dir),
            "--profile",
            "ops_launch",
            "--market",
            "india_nse_index_derivatives",
            "--require-file-inputs",
            "--fail-on-breach",
        ]
    )

    scorecard = pd.read_csv(out_dir / "strategy_scorecard.csv")
    assert code == 2
    assert not bool(scorecard.loc[0, "ready"])
    assert scorecard.loc[0, "recommendation"] == "review_ops_launch_checks"
