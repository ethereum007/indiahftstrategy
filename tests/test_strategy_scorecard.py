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


def complete_ops_launch_rows(
    strategy="lead_lag_taker",
    *,
    market="india_nse_index_derivatives",
    concentration_breach=False,
    resume_route_breach=False,
):
    run_types = [
        ("scaleup_plan", "scaleup_summary.csv"),
        ("runtime_telemetry_snapshot", "runtime_telemetry_summary.csv"),
        ("runtime_guard", "runtime_guard_summary.csv"),
        ("runtime_session_monitor", "runtime_session_summary.csv"),
        ("broker_vendor_data_readiness_pipeline", "broker_vendor_data_readiness_summary.csv"),
        ("broker_readiness", "broker_readiness_summary.csv"),
        ("cutover_gate", "cutover_summary.csv"),
        ("route_enable_packet", "route_enable_summary.csv"),
        ("broker_dispatch_plan", "broker_dispatch_summary.csv"),
        ("broker_dispatch_send_packet", "broker_dispatch_send_summary.csv"),
        ("broker_dispatch_ack_reconciliation", "broker_dispatch_ack_summary.csv"),
        ("broker_dispatch_roundtrip", "broker_dispatch_roundtrip_summary.csv"),
    ]
    rows = [
        row(run_type, summary_file, strategy, market=market, minute=10 + index)
        for index, (run_type, summary_file) in enumerate(run_types)
    ]
    for item in rows:
        if item["run_type"] != "broker_dispatch_roundtrip":
            continue
        item["summary_dispatch_total_notional"] = 1500.0
        item["summary_strategy_portfolio_provided"] = True
        item["summary_strategy_portfolio_ready"] = True
        item["summary_strategy_portfolio_selected_allocation_notional"] = 2000.0
        item["summary_strategy_portfolio_min_strategy_count"] = 2
        item["summary_strategy_portfolio_min_market_count"] = 1
        item["summary_strategy_portfolio_max_strategy_weight"] = 0.60
        item["summary_strategy_portfolio_max_market_weight"] = 0.90
        item["summary_strategy_portfolio_allocated_strategy_count"] = 1 if concentration_breach else 2
        item["summary_strategy_portfolio_allocated_market_count"] = 1
        item["summary_strategy_portfolio_max_strategy_allocation_weight"] = (
            0.80 if concentration_breach else 0.45
        )
        item["summary_strategy_portfolio_max_market_allocation_weight"] = 0.80
        item.update(
            resume_route_columns(
                "summary_route_broker_resume_broker_route_readiness",
                ready=not resume_route_breach,
                route_ready_pairs=0 if resume_route_breach else 1,
                gap_pairs=2 if resume_route_breach else 0,
                controls_ready=not resume_route_breach,
            )
        )
        item.update(
            resume_route_columns(
                "summary_route_broker_resume_incident_broker_route_readiness",
                route_ready_pairs=2,
            )
        )
    return rows


def complete_provider_imbalance_ops_launch_rows(
    strategy="imbalance",
    *,
    market="india_nse_index_derivatives",
    sidecar_breach=False,
):
    run_types = [
        ("provider_market_data_imbalance_scorecard", "provider_market_data_imbalance_scorecard_summary.csv"),
        (
            "provider_market_data_imbalance_route_readiness",
            "provider_market_data_imbalance_route_readiness_summary.csv",
        ),
        ("provider_market_data_imbalance_scaleup_plan", "provider_market_data_imbalance_scaleup_summary.csv"),
        (
            "provider_market_data_imbalance_runtime_telemetry_snapshot",
            "provider_market_data_imbalance_runtime_telemetry_summary.csv",
        ),
        (
            "provider_market_data_imbalance_runtime_guard",
            "provider_market_data_imbalance_runtime_guard_summary.csv",
        ),
        (
            "provider_market_data_imbalance_runtime_session",
            "provider_market_data_imbalance_runtime_session_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_readiness",
            "provider_market_data_imbalance_broker_readiness_summary.csv",
        ),
        ("provider_market_data_imbalance_cutover", "provider_market_data_imbalance_cutover_summary.csv"),
        (
            "provider_market_data_imbalance_route_enable",
            "provider_market_data_imbalance_route_enable_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch",
            "provider_market_data_imbalance_broker_dispatch_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch_send",
            "provider_market_data_imbalance_broker_dispatch_send_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch_ack",
            "provider_market_data_imbalance_broker_dispatch_ack_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_dispatch_roundtrip",
            "provider_market_data_imbalance_broker_dispatch_roundtrip_summary.csv",
        ),
        (
            "provider_market_data_imbalance_broker_rehearsal_certificate",
            "provider_market_data_imbalance_broker_rehearsal_certificate_summary.csv",
        ),
    ]
    rows = [
        row(run_type, summary_file, strategy, market=market, minute=10 + index)
        for index, (run_type, summary_file) in enumerate(run_types)
    ]
    for item in rows:
        if item["run_type"] == "provider_market_data_imbalance_broker_rehearsal_certificate":
            item["summary_target_mode"] = "live_dryrun"
            item["summary_authorizes_submission"] = False
            item["summary_digitally_signed"] = False
            item["summary_certificate_sha256"] = "a" * 64
        if item["run_type"] != "provider_market_data_imbalance_broker_dispatch_roundtrip":
            continue
        item["summary_dispatch_total_notional"] = 1500.0
        item["summary_strategy_portfolio_provided"] = True
        item["summary_strategy_portfolio_ready"] = True
        item["summary_strategy_portfolio_selected_allocation_notional"] = 2000.0
        item["summary_strategy_portfolio_min_strategy_count"] = 2
        item["summary_strategy_portfolio_min_market_count"] = 1
        item["summary_strategy_portfolio_max_strategy_weight"] = 0.60
        item["summary_strategy_portfolio_max_market_weight"] = 0.90
        item["summary_strategy_portfolio_allocated_strategy_count"] = 2
        item["summary_strategy_portfolio_allocated_market_count"] = 1
        item["summary_strategy_portfolio_max_strategy_allocation_weight"] = 0.45
        item["summary_strategy_portfolio_max_market_allocation_weight"] = 0.80
        item["summary_dispatch_roundtrip_synthetic_dataset_count"] = 2
        item["summary_dispatch_roundtrip_synthetic_sidecar_proof_ready"] = not sidecar_breach
        item["summary_dispatch_roundtrip_synthetic_sidecar_count"] = 1 if sidecar_breach else 2
        item["summary_dispatch_roundtrip_synthetic_sidecar_readable_count"] = 1 if sidecar_breach else 2
        item.update(resume_route_columns("summary_route_broker_resume_broker_route_readiness"))
        item.update(
            resume_route_columns(
                "summary_route_broker_resume_incident_broker_route_readiness",
                route_ready_pairs=2,
            )
        )
    return rows


def resume_route_columns(prefix, *, ready=True, route_ready_pairs=1, gap_pairs=0, controls_ready=True):
    return {
        f"{prefix}_required": True,
        f"{prefix}_provided": True,
        f"{prefix}_ready": ready,
        f"{prefix}_strategy": "lead_lag_taker",
        f"{prefix}_market": "india_nse_index_derivatives",
        f"{prefix}_route_ready_pairs": route_ready_pairs,
        f"{prefix}_gap_pairs": gap_pairs,
        f"{prefix}_ops_launch_controls_ready": controls_ready,
        f"{prefix}_ops_broker_roundtrip_portfolio_safe_runs": 1 if ready else 0,
        f"{prefix}_ops_broker_roundtrip_portfolio_breach_runs": 0 if ready else 1,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_ok_runs": 1 if ready else 0,
        f"{prefix}_ops_broker_roundtrip_portfolio_concentration_breach_runs": 0 if ready else 1,
    }


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
    assert int(report.summary.loc[0, "failed_check_count"]) == 1
    assert report.summary.loc[0, "failed_check_names"] == "profile_ready:imbalance"
    assert report.summary.loc[0, "first_failed_reason"] == (
        "imbalance profile is missing required run type imbalance_replay_walkforward"
    )
    assert report.summary.loc[0, "primary_blocker_check"] == "profile_ready:imbalance"
    assert not bool(report.summary.loc[0, "primary_blocker_value"])
    assert report.summary.loc[0, "primary_blocker_operator"] == "is"
    assert bool(report.summary.loc[0, "primary_blocker_threshold"])
    assert report.summary.loc[0, "primary_blocker_profile"] == "imbalance"
    assert report.summary.loc[0, "primary_blocker_next_gate"] == "walkforward-imbalance-replay"
    assert report.config["schema_version"] == 1
    assert report.config["best_profile"] == "leadlag"
    assert report.config["next_gate"] == "plan-scaleup"
    assert report.config["next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert report.config["ready_action_count"] == 1
    assert report.config["blocked_action_count"] == 1
    assert report.config["gap_count"] == len(report.config["gaps"])
    assert report.config["failed_check_count"] == 1
    assert report.config["failed_checks"] == ["profile_ready:imbalance"]
    assert report.config["first_failed_reason"] == (
        "imbalance profile is missing required run type imbalance_replay_walkforward"
    )
    assert report.config["primary_blocker"]["check"] == "profile_ready:imbalance"
    assert report.config["primary_blocker"]["profile"] == "imbalance"
    assert report.config["primary_blocker"]["next_required_run_type"] == "imbalance_replay_walkforward"
    assert report.config["primary_blocker"]["next_gate"] == "walkforward-imbalance-replay"
    assert report.action_queue is not None
    assert list(report.action_queue["queue_status"]) == ["ready", "blocked"]
    assert list(report.action_queue["profile"]) == ["leadlag", "imbalance"]
    assert report.config["next_actions"][0]["next_gate"] == "plan-scaleup"
    assert report.config["next_actions"][0]["next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert report.config["ready_actions"][0]["profile"] == "leadlag"
    assert report.config["blocked_actions"][0]["profile"] == "imbalance"
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
    assert (out_dir / "strategy_scorecard_action_queue.csv").exists()
    assert (out_dir / "strategy_scorecard_next_actions.json").exists()
    assert (out_dir / "strategy_scorecard_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    queue = pd.read_csv(out_dir / "strategy_scorecard_action_queue.csv")
    assert report.action_queue is not None
    assert len(report.action_queue) == len(queue)
    assert queue.loc[0, "priority"] == 1
    assert queue.loc[0, "queue_status"] == "ready"
    assert queue.loc[0, "profile"] == "leadlag"
    assert queue.loc[0, "next_gate"] == "plan-scaleup"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    config = json.loads((out_dir / "strategy_scorecard_next_actions.json").read_text(encoding="utf-8"))
    assert config == report.config
    assert config["schema_version"] == 1
    assert config["next_gate"] == "plan-scaleup"
    assert config["next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert config["ready_action_count"] == 1
    assert config["blocked_action_count"] == 0
    assert config["failed_check_count"] == 0
    assert config["failed_checks"] == []
    assert config["first_failed_reason"] == ""
    assert config["primary_blocker"] == {}
    assert config["primary_action_status"] == "ready"
    assert config["primary_action"]["profile"] == "leadlag"
    assert config["primary_action"]["next_gate"] == "plan-scaleup"
    assert config["ready_actions"][0]["profile"] == "leadlag"
    assert config["next_actions"][0]["profile"] == "leadlag"
    runbook = (out_dir / "strategy_scorecard_runbook.md").read_text(encoding="utf-8")
    assert "# Strategy Scorecard Runbook" in runbook
    assert "- Ready: yes" in runbook
    assert "## Ready Actions" in runbook
    assert "`plan-scaleup`" in runbook
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "strategy_scorecard_action_queue.csv" in artifact_paths
    assert "strategy_scorecard_runbook.md" in artifact_paths

    ready_blocked_dir = tmp_path / "scorecard_ready_blocked_gate"
    ready_actions_dir = tmp_path / "scorecard_ready_action_gate"
    blocked_code = main(
        [
            "score-strategy-readiness",
            "--catalog",
            str(catalog_path),
            "--out",
            str(ready_blocked_dir),
            "--profile",
            "leadlag",
            "--market",
            "india_nse_index_derivatives",
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "score-strategy-readiness",
            "--catalog",
            str(catalog_path),
            "--out",
            str(ready_actions_dir),
            "--profile",
            "leadlag",
            "--market",
            "india_nse_index_derivatives",
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 0
    assert actions_code == 2


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
    summary = pd.read_csv(out_dir / "strategy_scorecard_summary.csv")
    gaps = pd.read_csv(out_dir / "strategy_scorecard_gaps.csv")
    queue = pd.read_csv(out_dir / "strategy_scorecard_action_queue.csv")
    config = json.loads((out_dir / "strategy_scorecard_next_actions.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(scorecard.loc[0, "ready"])
    assert scorecard.loc[0, "next_gate"] == "walkforward-imbalance-replay"
    assert scorecard.loc[0, "next_gate_help_command"] == "python -m hft_cli walkforward-imbalance-replay --help"
    assert int(summary.loc[0, "failed_check_count"]) == 1
    assert summary.loc[0, "failed_check_names"] == "profile_ready:imbalance"
    assert summary.loc[0, "first_failed_reason"] == (
        "imbalance profile is missing required run type imbalance_replay_walkforward"
    )
    assert summary.loc[0, "primary_blocker_check"] == "profile_ready:imbalance"
    assert not bool(summary.loc[0, "primary_blocker_value"])
    assert bool(summary.loc[0, "primary_blocker_threshold"])
    assert summary.loc[0, "primary_blocker_next_gate"] == "walkforward-imbalance-replay"
    assert queue.loc[0, "queue_status"] == "blocked"
    assert queue.loc[0, "next_required_run_type"] == "imbalance_replay_walkforward"
    assert queue.loc[0, "next_gate"] == "walkforward-imbalance-replay"
    assert config["next_gate"] == "walkforward-imbalance-replay"
    assert config["next_gate_help_command"] == "python -m hft_cli walkforward-imbalance-replay --help"
    assert config["ready_action_count"] == 0
    assert config["blocked_action_count"] == 1
    assert config["failed_check_count"] == 1
    assert config["failed_checks"] == ["profile_ready:imbalance"]
    assert config["first_failed_reason"] == (
        "imbalance profile is missing required run type imbalance_replay_walkforward"
    )
    assert config["primary_blocker"]["check"] == "profile_ready:imbalance"
    assert config["primary_blocker"]["next_required_run_type"] == "imbalance_replay_walkforward"
    assert config["primary_blocker"]["next_gate"] == "walkforward-imbalance-replay"
    assert config["primary_action_status"] == "blocked"
    assert config["primary_action"]["profile"] == "imbalance"
    assert config["primary_action"]["next_gate"] == "walkforward-imbalance-replay"
    open_gap_count = int(gaps["gap"].fillna("").astype(str).str.len().gt(0).sum())
    assert config["gap_count"] == open_gap_count
    assert config["blocked_actions"][0]["profile"] == "imbalance"
    assert config["blocked_actions"][0]["next_gate"] == "walkforward-imbalance-replay"
    assert "missing_required_run_type" in set(gaps["gap"])
    next_gate = gaps.loc[gaps["required_run_type"] == "imbalance_replay_walkforward", "next_gate"].iloc[0]
    assert next_gate == "walkforward-imbalance-replay"
    help_command = gaps.loc[
        gaps["required_run_type"] == "imbalance_replay_walkforward",
        "next_gate_help_command",
    ].iloc[0]
    assert help_command == "python -m hft_cli walkforward-imbalance-replay --help"

    blocked_dir = tmp_path / "scorecard_blocked_action_gate"
    actions_dir = tmp_path / "scorecard_any_action_gate"
    blocked_code = main(
        [
            "score-strategy-readiness",
            "--catalog",
            str(catalog_path),
            "--out",
            str(blocked_dir),
            "--profile",
            "imbalance",
            "--market",
            "india_nse_index_derivatives",
            "--fail-on-blocked-actions",
        ]
    )
    actions_code = main(
        [
            "score-strategy-readiness",
            "--catalog",
            str(catalog_path),
            "--out",
            str(actions_dir),
            "--profile",
            "imbalance",
            "--market",
            "india_nse_index_derivatives",
            "--fail-on-actions",
        ]
    )
    assert blocked_code == 2
    assert actions_code == 2


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
    assert int(score["broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(score["broker_roundtrip_portfolio_concentration_ok_runs"]) == 1
    assert int(score["broker_roundtrip_portfolio_concentration_breach_runs"]) == 0
    assert int(score["broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(score["broker_roundtrip_resume_route_breach_runs"]) == 0
    assert score["evidence_failed_checks"] == ""
    assert report.summary.loc[0, "recommendation"] == "promote_ready_route_to_live_dryrun_review"
    assert report.summary.loc[0, "best_next_gate"] == "review-route-readiness"
    assert report.summary.loc[0, "best_next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert report.config["best_next_gate"] == "review-route-readiness"
    assert report.config["best_next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert report.config["next_gate"] == "review-route-readiness"
    assert report.config["next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert report.config["ready_action_count"] == 1
    assert report.config["blocked_action_count"] == 0
    assert report.config["ready_actions"][0]["next_gate"] == "review-route-readiness"
    assert int(report.config["ready_actions"][0]["broker_roundtrip_resume_route_ready_runs"]) == 1
    assert report.config["next_actions"][0]["next_gate"] == "review-route-readiness"
    assert report.config["next_actions"][0]["next_gate_help_command"] == (
        "python -m hft_cli review-route-readiness --help"
    )
    assert set(report.gaps["total_runs"]) == {1}


def test_strategy_scorecard_scores_provider_imbalance_ops_launch_profile():
    catalog = pd.DataFrame(
        complete_provider_imbalance_ops_launch_rows("imbalance")
        + complete_ops_launch_rows("lead_lag_taker")
    )

    report = evaluate_strategy_scorecard(
        catalog,
        thresholds=StrategyScorecardThresholds(
            profiles=("provider_market_data_imbalance_ops_launch",),
            expected_market="india_nse_index_derivatives",
            require_file_inputs=True,
        ),
    )

    score = report.scorecard.iloc[0]
    assert report.ready
    assert score["profile"] == "provider_imbalance_ops_launch"
    assert score["strategy"] == "imbalance"
    assert score["recommendation"] == "ready_for_live_dryrun_route_review"
    assert score["next_gate"] == "review-route-readiness"
    assert score["next_gate_help_command"] == "python -m hft_cli review-route-readiness --help"
    assert int(score["broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(score["broker_roundtrip_resume_route_ready_runs"]) == 1
    assert int(score["provider_broker_roundtrip_synthetic_dataset_count"]) == 2
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_count"]) == 2
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_readable_count"]) == 2
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_ready_runs"]) == 1
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_breach_runs"]) == 0
    assert int(score["provider_broker_rehearsal_certificate_live_dryrun_runs"]) == 1
    assert int(score["provider_broker_rehearsal_certificate_authorizing_runs"]) == 0
    assert int(score["provider_broker_rehearsal_certificate_non_authorizing_runs"]) == 1
    assert int(score["provider_broker_rehearsal_certificate_hashed_runs"]) == 1
    assert score["evidence_failed_checks"] == ""
    assert report.summary.loc[0, "recommendation"] == "promote_ready_route_to_live_dryrun_review"
    assert report.config["ready_actions"][0]["profile"] == "provider_imbalance_ops_launch"
    assert report.config["ready_actions"][0]["next_gate"] == "review-route-readiness"
    assert report.config["ready_actions"][0]["provider_broker_roundtrip_synthetic_sidecar_ready_runs"] == 1
    assert report.config["ready_actions"][0][
        "provider_broker_rehearsal_certificate_live_dryrun_runs"
    ] == 1


def test_strategy_scorecard_provider_imbalance_ops_launch_blocks_sidecar_breach():
    catalog = pd.DataFrame(complete_provider_imbalance_ops_launch_rows(sidecar_breach=True))

    report = evaluate_strategy_scorecard(
        catalog,
        thresholds=StrategyScorecardThresholds(
            profiles=("provider_market_data_imbalance_ops_launch",),
            expected_market="india_nse_index_derivatives",
            require_file_inputs=True,
        ),
    )

    score = report.scorecard.iloc[0]
    failed_checks = set(str(score["evidence_failed_checks"]).split(";"))
    assert not report.ready
    assert not bool(score["ready"])
    assert score["profile"] == "provider_imbalance_ops_launch"
    assert score["recommendation"] == "review_ops_launch_checks"
    assert score["next_gate"] == "review-strategy-evidence"
    assert "provider_broker_roundtrip_synthetic_sidecar_ready" in failed_checks
    assert "provider_broker_roundtrip_synthetic_sidecar_breach" in failed_checks
    assert int(score["provider_broker_roundtrip_synthetic_dataset_count"]) == 2
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_count"]) == 1
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_readable_count"]) == 1
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_ready_runs"]) == 0
    assert int(score["provider_broker_roundtrip_synthetic_sidecar_breach_runs"]) == 1
    assert report.summary.loc[0, "first_failed_reason"] == (
        "provider_imbalance_ops_launch profile failed evidence check "
        "provider_broker_roundtrip_synthetic_sidecar_ready"
    )
    assert report.config["primary_blocker"]["evidence_failed_checks"] == [
        "provider_broker_roundtrip_synthetic_sidecar_ready",
        "provider_broker_roundtrip_synthetic_sidecar_breach",
    ]
    assert report.config["blocked_actions"][0][
        "provider_broker_roundtrip_synthetic_sidecar_breach_runs"
    ] == 1
    assert report.action_queue is not None
    assert "provider_broker_roundtrip_synthetic_sidecar_breach" in str(
        report.action_queue.loc[0, "evidence_failed_checks"]
    )


def test_strategy_scorecard_ops_launch_blocks_portfolio_concentration_breach():
    catalog = pd.DataFrame(complete_ops_launch_rows("lead_lag_taker", concentration_breach=True))

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
    failed_checks = set(str(score["evidence_failed_checks"]).split(";"))
    assert not report.ready
    assert not bool(score["ready"])
    assert score["readiness_score"] == 1.0
    assert score["recommendation"] == "review_ops_launch_checks"
    assert score["next_required_run_type"] == ""
    assert score["next_gate"] == "review-strategy-evidence"
    assert "broker_roundtrip_portfolio_concentration_ok" in failed_checks
    assert "broker_roundtrip_portfolio_concentration_breach" in failed_checks
    assert int(score["broker_roundtrip_portfolio_concentration_breach_runs"]) == 1
    assert report.summary.loc[0, "first_failed_reason"] == (
        "ops_launch profile failed evidence check broker_roundtrip_portfolio_concentration_ok"
    )
    assert report.config["primary_blocker"]["evidence_failed_checks"] == [
        "broker_roundtrip_portfolio_concentration_ok",
        "broker_roundtrip_portfolio_concentration_breach",
    ]
    assert report.action_queue is not None
    assert "broker_roundtrip_portfolio_concentration_breach" in str(
        report.action_queue.loc[0, "evidence_failed_checks"]
    )


def test_strategy_scorecard_ops_launch_blocks_resume_route_breach():
    catalog = pd.DataFrame(complete_ops_launch_rows("lead_lag_taker", resume_route_breach=True))

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
    failed_checks = set(str(score["evidence_failed_checks"]).split(";"))
    assert not report.ready
    assert not bool(score["ready"])
    assert score["recommendation"] == "review_ops_launch_checks"
    assert score["next_gate"] == "review-strategy-evidence"
    assert "broker_roundtrip_resume_route_ready" in failed_checks
    assert "broker_roundtrip_resume_route_breach" in failed_checks
    assert int(score["broker_roundtrip_resume_route_breach_runs"]) == 1
    assert int(score["broker_roundtrip_resume_route_gap_breach_runs"]) == 1
    assert report.summary.loc[0, "first_failed_reason"] == (
        "ops_launch profile failed evidence check broker_roundtrip_resume_route_ready"
    )
    assert report.config["primary_blocker"]["evidence_failed_checks"] == [
        "broker_roundtrip_resume_route_ready",
        "broker_roundtrip_resume_route_breach",
    ]
    assert int(report.config["blocked_actions"][0]["broker_roundtrip_resume_route_breach_runs"]) == 1


def test_strategy_scorecard_points_ops_launch_to_broker_vendor_data_readiness_pipeline():
    catalog = pd.DataFrame(complete_ops_launch_rows("lead_lag_taker"))
    catalog = catalog.loc[catalog["run_type"] != "broker_vendor_data_readiness_pipeline"].copy()

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
    assert not report.ready
    assert score["next_required_run_type"] == "broker_vendor_data_readiness_pipeline"
    assert score["next_gate"] == "pipeline-broker-vendor-readiness"
    assert score["next_gate_help_command"] == "python -m hft_cli pipeline-broker-vendor-readiness --help"
    gap = report.gaps.loc[
        report.gaps["required_run_type"] == "broker_vendor_data_readiness_pipeline"
    ].iloc[0]
    assert gap["next_gate"] == "pipeline-broker-vendor-readiness"
    assert gap["next_gate_help_command"] == "python -m hft_cli pipeline-broker-vendor-readiness --help"
    assert report.config["blocked_actions"][0]["next_required_run_type"] == "broker_vendor_data_readiness_pipeline"


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
