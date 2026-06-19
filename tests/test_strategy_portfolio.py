import json

import pandas as pd

from hft_cli import main
from reports.strategy_portfolio import (
    StrategyPortfolioConfig,
    evaluate_strategy_portfolio,
    write_strategy_portfolio_allocations,
)


def scorecard_row(
    rank,
    profile,
    strategy,
    *,
    ready=True,
    readiness_score=1.0,
    market="india_nse_index_derivatives",
    next_gate="plan-scaleup",
):
    return {
        "rank": rank,
        "profile": profile,
        "strategy": strategy,
        "market": market,
        "ready": ready,
        "readiness_score": readiness_score,
        "passed_required_run_types": int(round(readiness_score * 6)),
        "required_run_type_count": 6,
        "missing_required_run_types": "" if ready else "imbalance_replay_walkforward",
        "blocked_required_run_types": "",
        "next_required_run_type": "" if ready else "imbalance_replay_walkforward",
        "next_gate": next_gate,
        "next_gate_help_command": f"python -m hft_cli {next_gate} --help",
        "failed_checks": 0 if ready else 1,
        "dirty_runs": 0,
        "git_commit_count": 1,
        "latest_generated_at_utc": "2026-06-18T09:30:00Z",
        "recommendation": "ready_for_shadow_scaleup_review" if ready else "complete_profile_evidence_gaps",
    }


def mixed_scorecard():
    return pd.DataFrame(
        [
            scorecard_row(1, "leadlag", "lead_lag_taker"),
            scorecard_row(2, "parity", "parity_box"),
            scorecard_row(
                3,
                "imbalance",
                "imbalance",
                ready=False,
                readiness_score=0.4,
                next_gate="walkforward-imbalance-replay",
            ),
        ]
    )


def test_strategy_portfolio_allocates_ready_profiles_with_reserve():
    report = evaluate_strategy_portfolio(
        mixed_scorecard(),
        config=StrategyPortfolioConfig(total_capital=1_000_000, reserve_weight=0.10, max_profile_weight=0.60),
    )

    allocations = report.allocations.set_index("profile")
    assert report.ready
    assert bool(allocations.loc["leadlag", "eligible"])
    assert bool(allocations.loc["parity", "eligible"])
    assert not bool(allocations.loc["imbalance", "eligible"])
    assert allocations.loc["imbalance", "eligibility_reason"] == "profile_not_ready"
    assert allocations.loc["leadlag", "allocation_weight"] == 0.45
    assert allocations.loc["parity", "allocation_weight"] == 0.45
    assert allocations.loc["leadlag", "allocation_notional"] == 450_000
    assert report.summary.loc[0, "allocated_weight"] == 0.90
    assert report.summary.loc[0, "reserve_notional"] == 100_000
    assert int(report.summary.loc[0, "failed_check_count"]) == 0
    assert report.config["schema_version"] == 1
    assert report.config["allocation_count"] == 2
    assert report.config["ready_allocations"][0]["profile"] == "leadlag"
    assert report.config["blocked_allocations"][0]["profile"] == "imbalance"
    assert report.action_queue is not None
    assert int(report.summary.loc[0, "action_queue_count"]) == 3
    assert int(report.summary.loc[0, "ready_action_count"]) == 2
    assert int(report.summary.loc[0, "blocked_action_count"]) == 1
    assert report.summary.loc[0, "next_gate"] == "plan-scaleup"
    assert report.config["action_queue_count"] == 3
    assert report.config["ready_action_count"] == 2
    assert report.config["blocked_action_count"] == 1
    assert report.config["primary_action_status"] == "ready"
    assert report.config["primary_action"]["profile"] == "leadlag"
    assert {item["profile"] for item in report.config["ready_actions"]} == {"leadlag", "parity"}
    assert {item["profile"] for item in report.config["blocked_actions"]} == {"imbalance"}


def test_strategy_portfolio_caps_profiles_and_leaves_unallocated_budget():
    report = evaluate_strategy_portfolio(
        mixed_scorecard().iloc[:2],
        config=StrategyPortfolioConfig(total_capital=1_000, reserve_weight=0.0, max_profile_weight=0.40),
    )

    allocations = report.allocations.set_index("profile")
    assert report.ready
    assert allocations.loc["leadlag", "allocation_weight"] == 0.40
    assert allocations.loc["parity", "allocation_weight"] == 0.40
    assert report.summary.loc[0, "allocated_weight"] == 0.80
    assert round(report.summary.loc[0, "unallocated_weight"], 6) == 0.20


def test_strategy_portfolio_fails_closed_when_no_profile_is_ready():
    report = evaluate_strategy_portfolio(
        pd.DataFrame(
            [
                scorecard_row(
                    1,
                    "imbalance",
                    "imbalance",
                    ready=False,
                    readiness_score=0.8,
                    next_gate="walkforward-imbalance-replay",
                )
            ]
        )
    )

    assert not report.ready
    assert int(report.summary.loc[0, "failed_check_count"]) == 2
    assert report.summary.loc[0, "primary_blocker_check"] == "eligible_profile_count"
    assert report.summary.loc[0, "first_failed_reason"] == (
        "at least one strategy profile must pass readiness filters before allocation"
    )
    assert report.config["failed_checks"][0] == "eligible_profile_count"
    assert report.config["primary_blocker"]["check"] == "eligible_profile_count"
    assert report.action_queue is not None
    assert set(report.action_queue["queue_status"]) == {"blocked"}
    assert "profile_eligible:imbalance" in set(report.action_queue["check"])
    assert "eligible_profile_count" in set(report.action_queue["check"])
    assert int(report.summary.loc[0, "blocked_action_count"]) == len(report.action_queue)
    assert report.config["primary_action_status"] == "blocked"
    assert report.config["next_gate"] == "walkforward-imbalance-replay"


def test_write_strategy_portfolio_outputs_files_and_manifest(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    out_dir = tmp_path / "portfolio"
    mixed_scorecard().to_csv(scorecard_path, index=False)

    report = write_strategy_portfolio_allocations(
        scorecard_path,
        output_dir=out_dir,
        config=StrategyPortfolioConfig(total_capital=500_000, reserve_weight=0.20, max_profile_weight=0.50),
    )

    assert report.output_dir == out_dir
    assert report.ready
    assert (out_dir / "strategy_portfolio_allocations.csv").exists()
    assert (out_dir / "strategy_portfolio_checks.csv").exists()
    assert (out_dir / "strategy_portfolio_summary.csv").exists()
    assert (out_dir / "strategy_portfolio_action_queue.csv").exists()
    assert (out_dir / "strategy_portfolio_config.json").exists()
    assert (out_dir / "strategy_portfolio_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    action_queue = pd.read_csv(out_dir / "strategy_portfolio_action_queue.csv")
    config = json.loads((out_dir / "strategy_portfolio_config.json").read_text(encoding="utf-8"))
    assert config == report.config
    assert config["ready"]
    assert config["allocation_config"]["total_capital"] == 500_000
    assert len(action_queue) == config["action_queue_count"]
    assert int((action_queue["queue_status"] == "ready").sum()) == config["ready_action_count"]
    assert int((action_queue["queue_status"] == "blocked").sum()) == config["blocked_action_count"]
    runbook = (out_dir / "strategy_portfolio_runbook.md").read_text(encoding="utf-8")
    assert "# Strategy Portfolio Allocation Runbook" in runbook
    assert "## Allocations" in runbook
    assert "## Scheduler Actions" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "strategy_portfolio_allocations.csv" in artifact_paths
    assert "strategy_portfolio_action_queue.csv" in artifact_paths
    assert "strategy_portfolio_runbook.md" in artifact_paths


def test_cli_strategy_portfolio_returns_breach_when_no_profile_is_ready(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    out_dir = tmp_path / "portfolio"
    blocked_dir = tmp_path / "portfolio_blocked"
    actions_dir = tmp_path / "portfolio_actions"
    pd.DataFrame(
        [
            scorecard_row(
                1,
                "imbalance",
                "imbalance",
                ready=False,
                readiness_score=0.8,
                next_gate="walkforward-imbalance-replay",
            )
        ]
    ).to_csv(scorecard_path, index=False)

    code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(out_dir),
            "--total-capital",
            "1000000",
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.5",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "strategy_portfolio_summary.csv")
    checks = pd.read_csv(out_dir / "strategy_portfolio_checks.csv")
    action_queue = pd.read_csv(out_dir / "strategy_portfolio_action_queue.csv")
    config = json.loads((out_dir / "strategy_portfolio_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert summary.loc[0, "primary_blocker_check"] == "eligible_profile_count"
    assert "eligible_profile_count" in set(checks.loc[~checks["passed"].astype(bool), "check"])
    assert int(summary.loc[0, "blocked_action_count"]) == len(action_queue)
    assert config["primary_blocker"]["check"] == "eligible_profile_count"
    assert config["blocked_action_count"] == len(action_queue)
    assert config["primary_action_status"] == "blocked"

    blocked_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(blocked_dir),
            "--total-capital",
            "1000000",
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.5",
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(actions_dir),
            "--total-capital",
            "1000000",
            "--reserve-weight",
            "0.1",
            "--max-profile-weight",
            "0.5",
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


def test_cli_strategy_portfolio_action_gates_on_ready_allocation(tmp_path):
    scorecard_path = tmp_path / "strategy_scorecard.csv"
    blocked_dir = tmp_path / "portfolio_blocked"
    actions_dir = tmp_path / "portfolio_actions"
    mixed_scorecard().iloc[:2].to_csv(scorecard_path, index=False)

    blocked_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(blocked_dir),
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "allocate-strategy-portfolio",
            "--scorecard",
            str(scorecard_path),
            "--out",
            str(actions_dir),
            "--fail-on-actions",
        ]
    )

    assert blocked_code == 0
    assert actions_code == 2
