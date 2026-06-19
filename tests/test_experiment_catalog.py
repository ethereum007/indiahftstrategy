import json

import pandas as pd

from adapters.vendor_intake import VendorCsvIntakeConfig, write_vendor_csv_intake_report
from hft_cli import main
from reports.catalog import catalog_experiment_runs, write_experiment_catalog
from reports.manifest import write_experiment_manifest


def write_run(path, *, run_type, summary_name, summary_row):
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([summary_row]).to_csv(path / summary_name, index=False)
    write_experiment_manifest(
        path,
        run_type=run_type,
        parameters={"scenario": path.name},
        inputs={},
    )


def test_catalog_experiment_runs_collects_manifests_and_summary_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "parity_edge",
        run_type="parity_edge_audit",
        summary_name="parity_edge_summary.csv",
        summary_row={"passed": True, "failed_checks": 0, "total_net_edge": 1250.0},
    )
    write_run(
        root / "promotion",
        run_type="promotion_report",
        summary_name="promotion_summary.csv",
        summary_row={"ready": False, "failed_checks": 1, "candidate_scenario_key": "trigger_ticks=3"},
    )

    report = catalog_experiment_runs([root])

    assert report.run_count == 2
    assert set(report.catalog["run_type"]) == {"parity_edge_audit", "promotion_report"}
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert report.summary.iloc[0]["status_false_runs"] == 1
    assert "summary_total_net_edge" in report.catalog.columns
    assert "summary_candidate_scenario_key" in report.catalog.columns


def test_write_experiment_catalog_outputs_catalog_summary_and_manifest(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    write_run(
        root / "proof",
        run_type="proof_report",
        summary_name="proof_summary.csv",
        summary_row={"all_passed": True, "failed_runs": 0, "total_net_pnl": 42.0},
    )

    report = write_experiment_catalog([root], output_dir=out_dir)

    assert report.output_dir == out_dir
    assert (out_dir / "experiment_catalog.csv").exists()
    assert (out_dir / "experiment_catalog_summary.csv").exists()
    assert (out_dir / "experiment_catalog_action_queue.csv").exists()
    assert (out_dir / "experiment_catalog_action_plan.json").exists()
    assert (out_dir / "experiment_catalog_hygiene_gaps.csv").exists()
    assert (out_dir / "experiment_catalog_runbook.md").exists()
    assert (out_dir / "manifest.json").exists()
    assert report.summary.iloc[0]["run_count"] == 1
    assert report.summary.iloc[0]["hygiene_gap_count"] == 0
    assert report.hygiene_gaps is not None
    hygiene = pd.read_csv(out_dir / "experiment_catalog_hygiene_gaps.csv")
    assert hygiene.empty
    assert list(hygiene.columns) == [
        "priority",
        "gap_type",
        "run_type",
        "run_dir",
        "summary_file",
        "summary_status",
        "git_dirty",
        "input_unfingerprinted_count",
        "next_gate",
        "next_gate_help_command",
        "recommendation",
        "generated_at_utc",
    ]
    assert report.summary.iloc[0]["action_queue_count"] == 0
    assert report.summary.iloc[0]["action_queue_ready_count"] == 0
    assert report.summary.iloc[0]["action_queue_blocked_count"] == 0
    assert report.summary.iloc[0]["action_queue_unknown_count"] == 0
    queue = pd.read_csv(out_dir / "experiment_catalog_action_queue.csv")
    assert queue.empty
    assert list(queue.columns) == [
        "priority",
        "queue_status",
        "run_type",
        "run_dir",
        "strategy",
        "market",
        "profile",
        "summary_status",
        "action_source_file",
        "action_source",
        "dataset",
        "component",
        "check",
        "failed_check_count",
        "failed_check_names",
        "first_failed_reason",
        "primary_blocker_check",
        "primary_blocker_value",
        "primary_blocker_operator",
        "primary_blocker_threshold",
        "primary_blocker_reason",
        "pipeline_dir",
        "next_gate",
        "next_gate_help_command",
        "recommendation",
        "generated_at_utc",
    ]
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "# Experiment Catalog Runbook" in runbook
    assert "- Runs: 1" in runbook
    assert "- Queue rows: 0" in runbook
    assert "- Ready actions: 0" in runbook
    assert "- Blocked actions: 0" in runbook
    assert "_None_" in runbook
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["schema_version"] == 1
    assert action_plan["action_queue_count"] == 0
    assert action_plan["ready_action_count"] == 0
    assert action_plan["blocked_action_count"] == 0
    assert action_plan["catalog_hygiene_ready"] is True
    assert action_plan["hygiene_gap_count"] == 0
    assert action_plan["hygiene_gaps"] == []
    assert action_plan["scheduler_recommendation"] == "no_catalog_actions"
    assert action_plan["failed_check_count"] == 0
    assert action_plan["failed_checks"] == []
    assert action_plan["first_failed_reason"] == ""
    assert action_plan["primary_blocker"] == {}
    assert action_plan["next_gate"] == ""
    assert action_plan["next_gate_help_command"] == ""
    assert action_plan["primary_action_status"] == ""
    assert action_plan["primary_action"] == {}
    assert action_plan["next_actions"] == []
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_paths = {artifact["path"] for artifact in manifest["artifacts"]}
    assert "experiment_catalog_action_queue.csv" in artifact_paths
    assert "experiment_catalog_action_plan.json" in artifact_paths
    assert "experiment_catalog_hygiene_gaps.csv" in artifact_paths
    assert "experiment_catalog_runbook.md" in artifact_paths


def test_experiment_catalog_promotes_vendor_intake_action_queue(tmp_path):
    sample = tmp_path / "partial_arrow_ticks.csv"
    intake_dir = tmp_path / "intake"
    catalog_dir = tmp_path / "catalog"
    pd.DataFrame([{"exchange_ts": "2026-06-10 09:15:00", "best_bid": 100.0}]).to_csv(
        sample,
        index=False,
    )
    write_vendor_csv_intake_report(
        sample,
        output_dir=intake_dir,
        config=VendorCsvIntakeConfig(adapter="arrow_money", kind="ticks"),
    )

    report = write_experiment_catalog([intake_dir], output_dir=catalog_dir)

    queue = pd.read_csv(catalog_dir / "experiment_catalog_action_queue.csv")
    action_plan = json.loads((catalog_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert int(report.summary.iloc[0]["action_queue_blocked_count"]) == 5
    assert set(queue["action_source_file"]) == {"vendor_intake_action_queue.csv"}
    assert queue.loc[0, "run_type"] == "vendor_csv_intake"
    assert queue.loc[0, "check"] == "unmapped_required:ask"
    assert queue.loc[0, "component"] == "mapping"
    assert queue.loc[0, "next_gate"] == "intake-vendor-csv"
    assert queue.loc[0, "next_gate_help_command"] == "python -m hft_cli intake-vendor-csv --help"
    assert action_plan["blocked_action_count"] == 5
    assert action_plan["primary_action_status"] == "blocked"
    assert action_plan["primary_action"]["check"] == "unmapped_required:ask"


def test_write_experiment_catalog_outputs_hygiene_gap_sidecar(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    write_run(
        root / "stress",
        run_type="stress_report",
        summary_name="stress_summary.csv",
        summary_row={
            "all_scenarios_passed": False,
            "failed_rows": 2,
            "worst_stressed_net_pnl": -10.0,
            "next_gate": "review-strategy-evidence --profile ops_launch --require-file-inputs",
            "next_gate_help_command": (
                "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
            ),
        },
    )
    missing_summary = root / "missing_summary"
    missing_summary.mkdir(parents=True)
    write_experiment_manifest(
        missing_summary,
        run_type="custom_report",
        parameters={},
        inputs={},
    )
    write_run(
        root / "dirty",
        run_type="proof_report",
        summary_name="proof_summary.csv",
        summary_row={"all_passed": True, "failed_runs": 0},
    )
    dirty_manifest = root / "dirty" / "manifest.json"
    dirty_payload = json.loads(dirty_manifest.read_text(encoding="utf-8"))
    dirty_payload["git"]["dirty"] = True
    dirty_manifest.write_text(json.dumps(dirty_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inline_input = root / "inline_input"
    inline_input.mkdir(parents=True)
    pd.DataFrame([{"ready": True, "failed_steps": 0}]).to_csv(
        inline_input / "runtime_session_summary.csv",
        index=False,
    )
    write_experiment_manifest(
        inline_input,
        run_type="runtime_session_monitor",
        parameters={},
        inputs={"inline_payload": "inline"},
    )

    report = write_experiment_catalog([root], output_dir=out_dir)

    gaps = pd.read_csv(out_dir / "experiment_catalog_hygiene_gaps.csv")
    assert report.hygiene_gaps is not None
    assert int(report.summary.iloc[0]["hygiene_gap_count"]) == 4
    assert int(report.summary.iloc[0]["hygiene_failed_status_count"]) == 1
    assert int(report.summary.iloc[0]["hygiene_missing_summary_count"]) == 1
    assert int(report.summary.iloc[0]["hygiene_dirty_run_count"]) == 1
    assert int(report.summary.iloc[0]["hygiene_unfingerprinted_input_count"]) == 1
    assert set(gaps["gap_type"]) == {
        "summary_failed",
        "missing_summary",
        "dirty_git",
        "unfingerprinted_inputs",
    }
    rows = gaps.set_index("gap_type")
    assert rows.loc["summary_failed", "recommendation"] == "resolve_failed_summary_status"
    assert rows.loc["summary_failed", "next_gate"] == (
        "review-strategy-evidence --profile ops_launch --require-file-inputs"
    )
    assert rows.loc["summary_failed", "next_gate_help_command"] == (
        "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
    )
    assert rows.loc["missing_summary", "recommendation"] == "write_recognized_summary_artifact"
    assert rows.loc["dirty_git", "recommendation"] == "rerun_from_clean_git_state"
    assert rows.loc["unfingerprinted_inputs", "input_unfingerprinted_count"] == 1
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "## Hygiene Gaps" in runbook
    assert "summary_failed" in runbook
    assert "replace_unfingerprinted_inputs_with_file_or_directory_manifest_inputs" in runbook
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["catalog_hygiene_ready"] is False
    assert action_plan["hygiene_gap_count"] == 4
    assert action_plan["scheduler_recommendation"] == "repair_catalog_hygiene_gaps_before_scheduling_actions"
    assert action_plan["top_hygiene_gap"]["gap_type"] == "summary_failed"
    assert action_plan["top_hygiene_gap"]["next_gate"] == (
        "review-strategy-evidence --profile ops_launch --require-file-inputs"
    )
    assert {gap["gap_type"] for gap in action_plan["hygiene_gaps"]} == set(gaps["gap_type"])


def test_write_experiment_catalog_action_plan_prioritizes_hygiene_without_actions(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    missing_summary = root / "missing_summary"
    missing_summary.mkdir(parents=True)
    write_experiment_manifest(
        missing_summary,
        run_type="custom_report",
        parameters={},
        inputs={},
    )

    write_experiment_catalog([root], output_dir=out_dir)

    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["catalog_hygiene_ready"] is False
    assert action_plan["hygiene_gap_count"] == 1
    assert action_plan["action_queue_count"] == 0
    assert action_plan["scheduler_recommendation"] == "repair_catalog_hygiene_gaps"
    assert action_plan["top_hygiene_gap"]["gap_type"] == "missing_summary"


def test_catalog_experiment_runs_reports_input_fingerprint_provenance(tmp_path):
    root = tmp_path / "runs"
    run = root / "runtime_session"
    exact_file = tmp_path / "runtime_telemetry.csv"
    directory_input = tmp_path / "runtime_guard"
    missing_input = tmp_path / "missing_snapshot.csv"
    run.mkdir(parents=True, exist_ok=True)
    directory_input.mkdir()
    pd.DataFrame([{"guard_action": "continue"}]).to_csv(directory_input / "runtime_guard_summary.csv", index=False)
    pd.DataFrame([{"ready": True, "failed_steps": 0}]).to_csv(run / "runtime_session_summary.csv", index=False)
    pd.DataFrame([{"orders_sent": 0}]).to_csv(exact_file, index=False)
    write_experiment_manifest(
        run,
        run_type="runtime_session_monitor",
        parameters={"scenario": "runtime_session"},
        inputs={
            "telemetry": exact_file,
            "guard_dir": directory_input,
            "missing_snapshot": missing_input,
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    summary = report.summary.iloc[0]
    assert int(row["input_count"]) == 3
    assert int(row["input_file_count"]) == 1
    assert int(row["input_directory_count"]) == 1
    assert int(row["input_hashed_count"]) == 2
    assert int(row["input_unfingerprinted_count"]) == 1
    assert int(summary["input_file_count"]) == 1
    assert int(summary["input_directory_count"]) == 1
    assert int(summary["input_unfingerprinted_count"]) == 1
    assert int(summary["runs_with_directory_inputs"]) == 1
    assert int(summary["runs_with_unfingerprinted_inputs"]) == 1


def test_catalog_experiment_runs_recognizes_proof_refresh_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "proof_refresh",
        run_type="proof_refresh_gate",
        summary_name="proof_refresh_summary.csv",
        summary_row={
            "ready": True,
            "proof_source": "latest",
            "fresh_proof_required": True,
            "failed_checks": 0,
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["summary_file"] == "proof_refresh_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_proof_source"] == "latest"


def test_catalog_experiment_runs_recognizes_strategy_scorecard_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "strategy_scorecard",
        run_type="strategy_scorecard",
        summary_name="strategy_scorecard_summary.csv",
        summary_row={
            "ready": True,
            "best_profile": "leadlag",
            "best_strategy": "lead_lag_taker",
            "best_next_gate": "plan-scaleup",
            "failed_check_count": 1,
            "failed_check_names": "profile_ready:imbalance",
            "first_failed_reason": "imbalance profile is missing required run type imbalance_replay_walkforward",
            "primary_blocker_check": "profile_ready:imbalance",
            "primary_blocker_value": False,
            "primary_blocker_operator": "is",
            "primary_blocker_threshold": True,
            "primary_blocker_reason": "imbalance profile is missing required run type imbalance_replay_walkforward",
            "ready_profiles": 1,
            "blocked_profiles": 4,
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "strategy_scorecard"
    assert row["summary_file"] == "strategy_scorecard_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_best_profile"] == "leadlag"
    assert row["summary_best_next_gate"] == "plan-scaleup"
    assert int(row["summary_failed_check_count"]) == 1
    assert row["summary_primary_blocker_check"] == "profile_ready:imbalance"
    assert row["summary_first_failed_reason"] == (
        "imbalance profile is missing required run type imbalance_replay_walkforward"
    )


def test_catalog_experiment_runs_recognizes_strategy_portfolio_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "strategy_portfolio",
        run_type="strategy_portfolio_allocation",
        summary_name="strategy_portfolio_summary.csv",
        summary_row={
            "ready": True,
            "deployment_mode": "paper_shadow",
            "allocation_mode": "readiness_weighted",
            "capital_currency": "INR",
            "total_capital": 1_000_000.0,
            "allocated_weight": 0.90,
            "allocated_notional": 900_000.0,
            "reserve_weight": 0.10,
            "top_profile": "leadlag",
            "top_strategy": "lead_lag_taker",
            "failed_check_count": 0,
            "failed_check_names": "",
            "first_failed_reason": "",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "strategy_portfolio_allocation"
    assert row["summary_file"] == "strategy_portfolio_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_top_profile"] == "leadlag"
    assert row["summary_top_strategy"] == "lead_lag_taker"
    assert float(row["summary_allocated_weight"]) == 0.90


def test_write_experiment_catalog_summarizes_broker_roundtrip_portfolio_proofs(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    write_run(
        root / "roundtrip_safe",
        run_type="broker_dispatch_roundtrip",
        summary_name="broker_dispatch_roundtrip_summary.csv",
        summary_row={
            "passed": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "failed_checks": 0,
            "dispatch_total_notional": 1575.0,
            "strategy_portfolio_provided": True,
            "strategy_portfolio_ready": True,
            "strategy_portfolio_selected_profile": "leadlag-live-dryrun",
            "strategy_portfolio_selected_strategy": "lead_lag_taker",
            "strategy_portfolio_selected_market": "india_nse_index_derivatives",
            "strategy_portfolio_selected_allocation_notional": 2000.0,
        },
    )
    write_run(
        root / "roundtrip_breach",
        run_type="broker_dispatch_roundtrip",
        summary_name="broker_dispatch_roundtrip_summary.csv",
        summary_row={
            "passed": False,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "failed_checks": 1,
            "dispatch_total_notional": 2500.0,
            "strategy_portfolio_provided": True,
            "strategy_portfolio_ready": True,
            "strategy_portfolio_selected_profile": "leadlag-live-dryrun",
            "strategy_portfolio_selected_strategy": "lead_lag_taker",
            "strategy_portfolio_selected_market": "india_nse_index_derivatives",
            "strategy_portfolio_selected_allocation_notional": 2000.0,
        },
    )

    report = write_experiment_catalog([root], output_dir=out_dir)

    summary = report.summary.iloc[0]
    assert int(summary["broker_roundtrip_runs"]) == 2
    assert int(summary["broker_roundtrip_passed_runs"]) == 1
    assert int(summary["broker_roundtrip_portfolio_provided_runs"]) == 2
    assert int(summary["broker_roundtrip_portfolio_ready_runs"]) == 2
    assert int(summary["broker_roundtrip_portfolio_safe_runs"]) == 1
    assert int(summary["broker_roundtrip_portfolio_breach_runs"]) == 1
    persisted = pd.read_csv(out_dir / "experiment_catalog_summary.csv")
    assert int(persisted.loc[0, "broker_roundtrip_portfolio_breach_runs"]) == 1
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["broker_roundtrip_portfolio_safe_runs"] == 1
    assert action_plan["broker_roundtrip_portfolio_breach_runs"] == 1
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "## Broker Round-Trip Portfolio Proofs" in runbook
    assert "- Portfolio-safe broker round-trip runs: 1" in runbook
    assert "- Portfolio-breach broker round-trip runs: 1" in runbook
    rows = report.catalog.set_index("run_dir")
    safe_row = rows.loc[str(root / "roundtrip_safe")]
    assert safe_row["summary_strategy_portfolio_selected_profile"] == "leadlag-live-dryrun"
    assert float(safe_row["summary_dispatch_total_notional"]) == 1575.0


def test_catalog_experiment_runs_recognizes_route_readiness_next_action(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "route_readiness",
        run_type="route_readiness_review",
        summary_name="route_readiness_summary.csv",
        summary_row={
            "ready": False,
            "strategy": "microprice_imbalance",
            "market": "india_nse_index_derivatives",
            "route_ready_pairs": 0,
            "gap_pairs": 1,
            "ready_action_count": 0,
            "blocked_action_count": 1,
            "next_gate": "review-strategy-evidence --profile ops_launch --require-file-inputs",
            "next_gate_help_command": (
                "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
            ),
            "failed_check_count": 1,
            "failed_check_names": "route_pairs_ready",
            "first_failed_reason": "ops-launch route evidence is not ready",
            "primary_blocker_check": "route_pairs_ready",
            "primary_blocker_value": False,
            "primary_blocker_operator": "is",
            "primary_blocker_threshold": True,
            "primary_blocker_reason": "ops-launch route evidence is not ready",
            "recommendation": "complete_route_readiness_gaps",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_false_runs"] == 1
    assert row["run_type"] == "route_readiness_review"
    assert row["summary_file"] == "route_readiness_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_next_gate"] == "review-strategy-evidence --profile ops_launch --require-file-inputs"
    assert row["summary_next_gate_help_command"] == (
        "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
    )
    assert int(row["summary_blocked_action_count"]) == 1


def test_write_experiment_catalog_outputs_next_action_queue(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    write_run(
        root / "strategy_scorecard",
        run_type="strategy_scorecard",
        summary_name="strategy_scorecard_summary.csv",
        summary_row={
            "ready": True,
            "best_profile": "leadlag",
            "best_strategy": "lead_lag_taker",
            "best_market": "india_nse_index_derivatives",
            "best_next_gate": "plan-scaleup",
            "best_next_gate_help_command": "python -m hft_cli plan-scaleup --help",
            "recommendation": "promote_ready_strategy_to_shadow_scaleup_review",
        },
    )
    write_run(
        root / "route_readiness",
        run_type="route_readiness_review",
        summary_name="route_readiness_summary.csv",
        summary_row={
            "ready": False,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "next_gate": "review-strategy-evidence --profile ops_launch --require-file-inputs",
            "next_gate_help_command": (
                "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
            ),
            "failed_check_count": 1,
            "failed_check_names": "route_pairs_ready",
            "first_failed_reason": "ops-launch route evidence is not ready",
            "primary_blocker_check": "route_pairs_ready",
            "primary_blocker_value": False,
            "primary_blocker_operator": "is",
            "primary_blocker_threshold": True,
            "primary_blocker_reason": "ops-launch route evidence is not ready",
            "recommendation": "complete_route_readiness_gaps",
        },
    )

    report = write_experiment_catalog([root], output_dir=out_dir)

    queue = pd.read_csv(out_dir / "experiment_catalog_action_queue.csv")
    assert report.action_queue is not None
    assert len(queue) == 2
    assert report.summary.iloc[0]["action_queue_count"] == 2
    assert report.summary.iloc[0]["action_queue_ready_count"] == 1
    assert report.summary.iloc[0]["action_queue_blocked_count"] == 1
    assert report.summary.iloc[0]["action_queue_unknown_count"] == 0
    rows = queue.set_index("run_type")
    assert rows.loc["strategy_scorecard", "queue_status"] == "ready"
    assert rows.loc["strategy_scorecard", "strategy"] == "lead_lag_taker"
    assert rows.loc["strategy_scorecard", "profile"] == "leadlag"
    assert rows.loc["strategy_scorecard", "next_gate"] == "plan-scaleup"
    assert rows.loc["route_readiness_review", "queue_status"] == "blocked"
    assert rows.loc["route_readiness_review", "strategy"] == "lead_lag_taker"
    assert rows.loc["route_readiness_review", "next_gate"] == (
        "review-strategy-evidence --profile ops_launch --require-file-inputs"
    )
    assert rows.loc["route_readiness_review", "check"] == "route_pairs_ready"
    assert int(rows.loc["route_readiness_review", "failed_check_count"]) == 1
    assert rows.loc["route_readiness_review", "failed_check_names"] == "route_pairs_ready"
    assert rows.loc["route_readiness_review", "first_failed_reason"] == "ops-launch route evidence is not ready"
    assert rows.loc["route_readiness_review", "primary_blocker_check"] == "route_pairs_ready"
    assert str(rows.loc["route_readiness_review", "primary_blocker_value"]) == "False"
    assert rows.loc["route_readiness_review", "primary_blocker_operator"] == "is"
    assert str(rows.loc["route_readiness_review", "primary_blocker_threshold"]) == "True"
    assert rows.loc["route_readiness_review", "primary_blocker_reason"] == "ops-launch route evidence is not ready"
    assert rows.loc["route_readiness_review", "recommendation"] == "complete_route_readiness_gaps"
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "## Action Queue" in runbook
    assert "- Ready actions: 1" in runbook
    assert "- Blocked actions: 1" in runbook
    assert "plan-scaleup" in runbook
    assert "review-strategy-evidence --profile ops_launch --require-file-inputs" in runbook
    assert "complete_route_readiness_gaps" in runbook
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["action_queue_count"] == 2
    assert action_plan["ready_action_count"] == 1
    assert action_plan["blocked_action_count"] == 1
    assert action_plan["unknown_action_count"] == 0
    assert action_plan["catalog_hygiene_ready"] is False
    assert action_plan["scheduler_recommendation"] == "repair_catalog_hygiene_gaps_before_scheduling_actions"
    assert action_plan["next_gate"] == "plan-scaleup"
    assert action_plan["next_gate_help_command"] == "python -m hft_cli plan-scaleup --help"
    assert action_plan["primary_action_status"] == "ready"
    assert action_plan["primary_action"]["strategy"] == "lead_lag_taker"
    assert action_plan["failed_check_count"] == 1
    assert action_plan["failed_checks"] == ["route_pairs_ready"]
    assert action_plan["first_failed_reason"] == "ops-launch route evidence is not ready"
    assert action_plan["primary_blocker"]["check"] == "route_pairs_ready"
    assert action_plan["primary_blocker"]["reason"] == "ops-launch route evidence is not ready"
    assert action_plan["primary_blocker"]["next_gate"] == (
        "review-strategy-evidence --profile ops_launch --require-file-inputs"
    )
    assert action_plan["ready_actions"][0]["next_gate"] == "plan-scaleup"
    assert action_plan["blocked_actions"][0]["next_gate"] == (
        "review-strategy-evidence --profile ops_launch --require-file-inputs"
    )
    assert action_plan["top_ready_action"]["strategy"] == "lead_lag_taker"
    assert action_plan["top_blocked_action"]["recommendation"] == "complete_route_readiness_gaps"


def test_write_experiment_catalog_promotes_sidecar_action_queue(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    run_dir = root / "broker_readiness"
    write_run(
        run_dir,
        run_type="broker_readiness",
        summary_name="broker_readiness_summary.csv",
        summary_row={
            "ready": False,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "adapter": "arrow_money",
            "failed_checks": 1,
            "recommendation": "obtain_vendor_schema_samples",
        },
    )
    pd.DataFrame(
        [
            {
                "priority": 1,
                "queue_status": "blocked",
                "check": "schema_reviewed",
                "component": "schema_audit",
                "next_gate": "audit-adapter-schema",
                "next_gate_help_command": "python -m hft_cli audit-adapter-schema --help",
                "actual": "False",
                "operator": "==",
                "expected": "True",
                "reason": "schema review missing",
            }
        ]
    ).to_csv(run_dir / "broker_readiness_action_queue.csv", index=False)

    report = write_experiment_catalog([root], output_dir=out_dir)

    queue = pd.read_csv(out_dir / "experiment_catalog_action_queue.csv")
    assert report.action_queue is not None
    assert len(queue) == 1
    assert report.summary.iloc[0]["action_queue_count"] == 1
    assert report.summary.iloc[0]["action_queue_ready_count"] == 0
    assert report.summary.iloc[0]["action_queue_blocked_count"] == 1
    assert report.summary.iloc[0]["action_queue_unknown_count"] == 0
    row = queue.iloc[0]
    assert row["queue_status"] == "blocked"
    assert row["run_type"] == "broker_readiness"
    assert row["strategy"] == "lead_lag_taker"
    assert row["market"] == "india_nse_index_derivatives"
    assert row["action_source_file"] == "broker_readiness_action_queue.csv"
    assert row["component"] == "schema_audit"
    assert row["check"] == "schema_reviewed"
    assert int(row["failed_check_count"]) == 1
    assert row["failed_check_names"] == "schema_reviewed"
    assert row["first_failed_reason"] == "schema review missing"
    assert row["primary_blocker_check"] == "schema_reviewed"
    assert not bool(row["primary_blocker_value"])
    assert row["primary_blocker_operator"] == "=="
    assert bool(row["primary_blocker_threshold"])
    assert row["primary_blocker_reason"] == "schema review missing"
    assert row["next_gate"] == "audit-adapter-schema"
    assert row["next_gate_help_command"] == "python -m hft_cli audit-adapter-schema --help"
    assert row["recommendation"] == "schema review missing"
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "audit-adapter-schema" in runbook
    assert "schema review missing" in runbook
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["catalog_hygiene_ready"] is False
    assert action_plan["scheduler_recommendation"] == "repair_catalog_hygiene_gaps_before_scheduling_actions"
    assert action_plan["next_gate"] == "audit-adapter-schema"
    assert action_plan["next_gate_help_command"] == "python -m hft_cli audit-adapter-schema --help"
    assert action_plan["primary_action_status"] == "blocked"
    assert action_plan["failed_check_count"] == 1
    assert action_plan["failed_checks"] == ["schema_reviewed"]
    assert action_plan["primary_blocker"]["check"] == "schema_reviewed"
    assert action_plan["primary_blocker"]["value"] is False
    assert action_plan["primary_blocker"]["operator"] == "=="
    assert action_plan["primary_blocker"]["threshold"] is True
    assert action_plan["primary_blocker"]["reason"] == "schema review missing"
    assert action_plan["primary_action"]["action_source_file"] == "broker_readiness_action_queue.csv"
    assert action_plan["blocked_actions"][0]["next_gate"] == "audit-adapter-schema"
    assert action_plan["blocked_actions"][0]["action_source_file"] == "broker_readiness_action_queue.csv"
    assert action_plan["blocked_actions"][0]["component"] == "schema_audit"
    assert action_plan["blocked_actions"][0]["check"] == "schema_reviewed"
    assert action_plan["blocked_actions"][0]["recommendation"] == "schema review missing"


def test_write_experiment_catalog_preserves_vendor_action_queue_context(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    run_dir = root / "vendor_batch"
    write_run(
        run_dir,
        run_type="vendor_market_data_batch_pipeline",
        summary_name="vendor_market_data_batch_summary.csv",
        summary_row={
            "ready": False,
            "adapter": "arrow_money",
            "kind": "ticks",
            "market": "india_nse_index_derivatives",
            "dataset_count": 2,
            "blocked_action_count": 1,
            "next_gate": "pipeline-vendor-market-data-batch",
            "next_gate_help_command": "python -m hft_cli pipeline-vendor-market-data-batch --help",
            "recommendation": "fix_vendor_market_data_batch",
        },
    )
    pd.DataFrame(
        [
            {
                "priority": 1,
                "queue_status": "blocked",
                "source": "comparison",
                "dataset": "day1",
                "component": "data_readiness",
                "check": "unique_source_files",
                "next_gate": "pipeline-vendor-market-data-batch",
                "next_gate_help_command": "python -m hft_cli pipeline-vendor-market-data-batch --help",
                "reason": "source file fingerprint reused across datasets",
                "recommendation": "provide_distinct_vendor_export_files",
                "pipeline_dir": "comparison",
            }
        ]
    ).to_csv(run_dir / "vendor_market_data_batch_action_queue.csv", index=False)

    report = write_experiment_catalog([root], output_dir=out_dir)

    queue = pd.read_csv(out_dir / "experiment_catalog_action_queue.csv")
    row = queue.iloc[0]
    assert report.action_queue is not None
    assert len(queue) == 1
    assert report.summary.iloc[0]["action_queue_blocked_count"] == 1
    assert row["run_type"] == "vendor_market_data_batch_pipeline"
    assert row["market"] == "india_nse_index_derivatives"
    assert row["action_source_file"] == "vendor_market_data_batch_action_queue.csv"
    assert row["action_source"] == "comparison"
    assert row["dataset"] == "day1"
    assert row["component"] == "data_readiness"
    assert row["check"] == "unique_source_files"
    assert row["pipeline_dir"] == "comparison"
    assert row["next_gate"] == "pipeline-vendor-market-data-batch"
    assert row["recommendation"] == "provide_distinct_vendor_export_files"
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "vendor_market_data_batch_action_queue.csv" in runbook
    assert "unique_source_files" in runbook
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    action = action_plan["blocked_actions"][0]
    assert action["action_source_file"] == "vendor_market_data_batch_action_queue.csv"
    assert action["action_source"] == "comparison"
    assert action["dataset"] == "day1"
    assert action["component"] == "data_readiness"
    assert action["check"] == "unique_source_files"
    assert action["pipeline_dir"] == "comparison"


def test_catalog_experiment_runs_recognizes_imbalance_edge_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_edge",
        run_type="imbalance_edge_audit",
        summary_name="imbalance_edge_summary.csv",
        summary_row={
            "passed": True,
            "failed_checks": 0,
            "signal_count": 12,
            "mean_forward_edge_ticks": 1.25,
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["summary_file"] == "imbalance_edge_summary.csv"
    assert row["summary_status_column"] == "passed"
    assert row["summary_signal_count"] == 12


def test_catalog_experiment_runs_recognizes_imbalance_edge_sweep_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_edge_sweep",
        run_type="imbalance_edge_sweep",
        summary_name="imbalance_edge_sweep_summary.csv",
        summary_row={
            "passed": True,
            "failed_checks": 0,
            "scenario_count": 6,
            "passed_configs": 3,
            "best_run": "imb_0p6__edge_0p25__horizon_100000ns",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["summary_file"] == "imbalance_edge_sweep_summary.csv"
    assert row["summary_status_column"] == "passed"
    assert row["summary_passed_configs"] == 3


def test_catalog_experiment_runs_recognizes_imbalance_edge_selection_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_edge_selection",
        run_type="imbalance_edge_selection",
        summary_name="imbalance_edge_selection_summary.csv",
        summary_row={
            "passed": True,
            "failed_checks": 0,
            "selectable_scenarios": 1,
            "best_scenario_key": "entry_imbalance=0.6|min_microprice_edge_ticks=0.25|forward_horizon_ns=100000",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["summary_file"] == "imbalance_edge_selection_summary.csv"
    assert row["summary_status_column"] == "passed"
    assert row["summary_selectable_scenarios"] == 1


def test_catalog_experiment_runs_recognizes_imbalance_edge_walkforward_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_edge_walkforward",
        run_type="imbalance_edge_walkforward",
        summary_name="imbalance_edge_walkforward_summary.csv",
        summary_row={
            "passed": True,
            "failed_checks": 0,
            "fold_count": 2,
            "passed_sweeps": 2,
            "selectable_scenarios": 1,
            "best_scenario_key": "entry_imbalance=0.6|min_microprice_edge_ticks=0.25|forward_horizon_ns=100000",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["summary_file"] == "imbalance_edge_walkforward_summary.csv"
    assert row["summary_status_column"] == "passed"
    assert row["summary_fold_count"] == 2


def test_catalog_experiment_runs_recognizes_imbalance_replay_walkforward_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_replay_walkforward",
        run_type="imbalance_replay_walkforward",
        summary_name="imbalance_replay_walkforward_summary.csv",
        summary_row={
            "passed": True,
            "failed_checks": 0,
            "fold_count": 2,
            "proof_passed_folds": 2,
            "proof_pass_rate": 1.0,
            "total_net_pnl": 42.0,
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["summary_file"] == "imbalance_replay_walkforward_summary.csv"
    assert row["summary_status_column"] == "passed"
    assert row["summary_proof_passed_folds"] == 2


def test_catalog_experiment_runs_recognizes_imbalance_candidate_promotion_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_candidate_promotion",
        run_type="promotion_report",
        summary_name="promotion_summary.csv",
        summary_row={
            "ready": True,
            "candidate_scenario_key": "strategy=imbalance|entry_imbalance=0.6|min_microprice_edge_ticks=0.25|hold_ns=1000000",
            "checks": 5,
            "failed_checks": 0,
            "recommendation": "paper_or_shadow_candidate",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "promotion_report"
    assert row["summary_file"] == "promotion_summary.csv"
    assert row["summary_status_column"] == "ready"


def test_catalog_experiment_runs_recognizes_imbalance_pipeline_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "imbalance_pipeline",
        run_type="imbalance_research_pipeline",
        summary_name="imbalance_pipeline_summary.csv",
        summary_row={
            "ready": True,
            "failed_stages": 0,
            "recommendation": "paper_or_shadow_candidate",
            "edge_passed": True,
            "replay_passed": True,
            "promotion_ready": True,
            "candidate_scenario_key": "strategy=imbalance|entry_imbalance=0.6|min_microprice_edge_ticks=0.25|hold_ns=1000000",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "imbalance_research_pipeline"
    assert row["summary_file"] == "imbalance_pipeline_summary.csv"
    assert row["summary_status_column"] == "ready"


def test_catalog_experiment_runs_recognizes_settlement_walkforward_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "settlement_convergence_walkforward",
        run_type="settlement_convergence_walkforward",
        summary_name="settlement_convergence_walkforward_summary.csv",
        summary_row={
            "passed": True,
            "failed_checks": 0,
            "fold_count": 2,
            "passed_folds": 2,
            "total_net_edge": 250.0,
            "best_direction": "buy_underpriced",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "settlement_convergence_walkforward"
    assert row["summary_file"] == "settlement_convergence_walkforward_summary.csv"
    assert row["summary_status_column"] == "passed"
    assert row["summary_passed_folds"] == 2


def test_catalog_experiment_runs_recognizes_settlement_launch_pipeline_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "settlement_launch_pipeline",
        run_type="settlement_launch_pipeline",
        summary_name="settlement_launch_pipeline_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "mode": "shadow",
            "components": 6,
            "failed_components": 0,
            "recommendation": "paper_or_shadow_handoff",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "settlement_launch_pipeline"
    assert row["summary_file"] == "settlement_launch_pipeline_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_components"] == 6


def test_catalog_experiment_runs_recognizes_parity_order_plan_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "parity_order_plan",
        run_type="parity_order_plan",
        summary_name="parity_order_summary.csv",
        summary_row={
            "ready": True,
            "strategy": "parity_box",
            "market": "india_nse_index_derivatives",
            "direction": "buy_synthetic_sell_future",
            "orders": 3,
            "failed_checks": 0,
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "parity_order_plan"
    assert row["summary_file"] == "parity_order_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_direction"] == "buy_synthetic_sell_future"


def test_catalog_experiment_runs_recognizes_parity_launch_pipeline_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "parity_launch_pipeline",
        run_type="parity_launch_pipeline",
        summary_name="parity_launch_pipeline_summary.csv",
        summary_row={
            "ready": True,
            "strategy": "parity_box",
            "market": "india_nse_index_derivatives",
            "adapter": "arrow_money",
            "mode": "shadow",
            "components": 6,
            "failed_components": 0,
            "recommendation": "paper_or_shadow_handoff",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "parity_launch_pipeline"
    assert row["summary_file"] == "parity_launch_pipeline_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_components"] == 6


def test_catalog_experiment_runs_recognizes_broker_upload_and_readiness_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "upload_pack",
        run_type="order_upload_pack",
        summary_name="broker_upload_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "orders": 2,
            "failed_checks": 0,
            "recommendation": "dry_run_or_paper_review",
        },
    )
    write_run(
        root / "broker_readiness",
        run_type="broker_readiness",
        summary_name="broker_readiness_summary.csv",
        summary_row={
            "ready": False,
            "adapter": "arrow_money",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "failed_checks": 1,
            "recommendation": "obtain_vendor_schema_samples",
        },
    )

    report = catalog_experiment_runs([root])

    rows = report.catalog.set_index("run_type")
    assert int(report.summary.iloc[0]["status_true_runs"]) == 1
    assert int(report.summary.iloc[0]["status_false_runs"]) == 1
    assert rows.loc["order_upload_pack", "summary_file"] == "broker_upload_summary.csv"
    assert rows.loc["broker_readiness", "summary_file"] == "broker_readiness_summary.csv"
    assert rows.loc["broker_readiness", "summary_status_column"] == "ready"
    assert rows.loc["broker_readiness", "summary_adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"


def test_catalog_experiment_runs_recognizes_broker_vendor_data_readiness_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "broker_vendor_data_readiness",
        run_type="broker_vendor_data_readiness_pipeline",
        summary_name="broker_vendor_data_readiness_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "kind": "ticks",
            "market": "india_nse_index_derivatives",
            "vendor_batch_ready": True,
            "broker_readiness_ready": True,
            "broker_vendor_data_ready": True,
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "schema_review_required": False,
            "schema_reviewed": False,
            "schema_review_mode": "placeholder_unreviewed",
            "placeholder_schema_active": True,
            "placeholder_schema_allowed": True,
            "placeholder_schema_warning": "placeholder adapter schema allowed for dry-run review only",
            "dataset_count": 2,
            "ready_datasets": 2,
            "failed_checks": 0,
            "recommendation": "broker_data_proof_ready",
        },
    )

    report = catalog_experiment_runs([root])

    row = report.catalog.iloc[0]
    assert report.summary.iloc[0]["status_true_runs"] == 1
    assert row["run_type"] == "broker_vendor_data_readiness_pipeline"
    assert row["summary_file"] == "broker_vendor_data_readiness_summary.csv"
    assert row["summary_status_column"] == "ready"
    assert row["summary_adapter"] == "arrow_money"
    assert bool(row["summary_broker_vendor_data_ready"])
    assert row["summary_adapter_schema_status"] == "placeholder_normalized_pending_vendor_schema"
    assert bool(row["summary_placeholder_schema_active"])
    assert bool(row["summary_placeholder_schema_allowed"])
    assert row["summary_placeholder_schema_warning"] == "placeholder adapter schema allowed for dry-run review only"
    assert row["summary_dataset_count"] == 2


def test_write_experiment_catalog_summarizes_placeholder_schema_state(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    write_run(
        root / "broker_vendor_allowed",
        run_type="broker_vendor_data_readiness_pipeline",
        summary_name="broker_vendor_data_readiness_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "schema_review_required": False,
            "schema_reviewed": False,
            "schema_review_mode": "placeholder_unreviewed",
            "placeholder_schema_active": True,
            "placeholder_schema_allowed": True,
            "failed_checks": 0,
        },
    )
    write_run(
        root / "broker_readiness_reviewed",
        run_type="broker_readiness",
        summary_name="broker_readiness_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "schema_review_required": True,
            "schema_reviewed": True,
            "schema_review_mode": "reviewed_vendor_mapping",
            "failed_checks": 0,
        },
    )
    write_run(
        root / "broker_readiness_blocked",
        run_type="broker_readiness",
        summary_name="broker_readiness_summary.csv",
        summary_row={
            "ready": False,
            "adapter": "irage",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "schema_review_required": True,
            "schema_reviewed": False,
            "schema_review_mode": "placeholder_unreviewed",
            "failed_checks": 1,
        },
    )
    write_run(
        root / "native_readiness",
        run_type="broker_readiness",
        summary_name="broker_readiness_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "normalized",
            "adapter_schema_status": "native_normalized",
            "schema_review_required": True,
            "schema_reviewed": True,
            "schema_review_mode": "native_schema",
            "failed_checks": 0,
        },
    )

    report = write_experiment_catalog([root], output_dir=out_dir)

    summary = report.summary.iloc[0]
    assert int(summary["placeholder_schema_active_runs"]) == 3
    assert int(summary["placeholder_schema_allowed_runs"]) == 1
    assert int(summary["placeholder_schema_reviewed_runs"]) == 1
    assert int(summary["placeholder_schema_unreviewed_runs"]) == 2
    assert int(summary["placeholder_schema_blocked_runs"]) == 1
    persisted = pd.read_csv(out_dir / "experiment_catalog_summary.csv")
    assert int(persisted.loc[0, "placeholder_schema_blocked_runs"]) == 1
    action_plan = json.loads((out_dir / "experiment_catalog_action_plan.json").read_text(encoding="utf-8"))
    assert action_plan["placeholder_schema_active_runs"] == 3
    assert action_plan["placeholder_schema_allowed_runs"] == 1
    assert action_plan["placeholder_schema_reviewed_runs"] == 1
    assert action_plan["placeholder_schema_unreviewed_runs"] == 2
    assert action_plan["placeholder_schema_blocked_runs"] == 1
    runbook = (out_dir / "experiment_catalog_runbook.md").read_text(encoding="utf-8")
    assert "## Broker Schema Review" in runbook
    assert "- Placeholder-schema allowed runs: 1" in runbook
    assert "- Placeholder-schema blocked runs: 1" in runbook


def test_catalog_experiment_runs_recognizes_runtime_and_halt_control_status(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "runtime_telemetry",
        run_type="runtime_telemetry_snapshot",
        summary_name="runtime_telemetry_summary.csv",
        summary_row={
            "ready": True,
            "scenario_key": "trigger_ticks=2",
            "adapter": "arrow_money",
            "orders_sent": 4,
            "failed_checks": 0,
        },
    )
    write_run(
        root / "runtime_guard",
        run_type="runtime_guard",
        summary_name="runtime_guard_summary.csv",
        summary_row={
            "guard_action": "continue",
            "halted": False,
            "failed_checks": 0,
            "scenario_key": "trigger_ticks=2",
            "adapter": "arrow_money",
        },
    )
    write_run(
        root / "runtime_session",
        run_type="runtime_session_monitor",
        summary_name="runtime_session_summary.csv",
        summary_row={
            "ready": True,
            "guard_action": "continue",
            "halted": False,
            "scenario_key": "trigger_ticks=2",
            "adapter": "arrow_money",
            "failed_checks": 0,
        },
    )
    write_run(
        root / "halt_response",
        run_type="halt_response_plan",
        summary_name="halt_response_summary.csv",
        summary_row={
            "ready": True,
            "guard_action": "halt",
            "cancel_orders": 1,
            "flatten_orders": 1,
            "failed_checks": 0,
        },
    )
    write_run(
        root / "halt_export",
        run_type="halt_response_export",
        summary_name="halt_response_export_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "cancel_orders": 1,
            "flatten_orders": 1,
            "failed_checks": 0,
        },
    )
    write_run(
        root / "halt_execution",
        run_type="halt_execution_reconciliation",
        summary_name="halt_execution_summary.csv",
        summary_row={
            "passed": True,
            "cancel_actions": 1,
            "flatten_actions": 1,
            "nonflat_positions": 0,
            "failed_checks": 0,
        },
    )
    write_run(
        root / "halt_incident",
        run_type="halt_incident_review",
        summary_name="halt_incident_summary.csv",
        summary_row={
            "passed": True,
            "incident_status": "halt_completed",
            "scenario_key": "trigger_ticks=2",
            "adapter": "arrow_money",
            "failed_checks": 0,
        },
    )
    write_run(
        root / "resume",
        run_type="resume_gate",
        summary_name="resume_summary.csv",
        summary_row={
            "ready": True,
            "scenario_key": "trigger_ticks=2",
            "adapter": "arrow_money",
            "failed_checks": 0,
        },
    )

    report = catalog_experiment_runs([root])

    rows = report.catalog.set_index("run_type")
    assert int(report.summary.iloc[0]["status_true_runs"]) == 8
    assert rows.loc["runtime_telemetry_snapshot", "summary_file"] == "runtime_telemetry_summary.csv"
    assert rows.loc["runtime_guard", "summary_file"] == "runtime_guard_summary.csv"
    assert rows.loc["runtime_guard", "summary_status_column"] == "failed_checks"
    assert rows.loc["runtime_session_monitor", "summary_file"] == "runtime_session_summary.csv"
    assert rows.loc["runtime_session_monitor", "summary_status_column"] == "ready"
    assert rows.loc["halt_response_plan", "summary_status_column"] == "ready"
    assert rows.loc["halt_execution_reconciliation", "summary_status_column"] == "passed"
    assert rows.loc["halt_incident_review", "summary_file"] == "halt_incident_summary.csv"
    assert rows.loc["resume_gate", "summary_status_column"] == "ready"


def test_catalog_experiment_runs_recognizes_scaleup_calibration_and_data_ops_status(tmp_path):
    root = tmp_path / "runs"
    cases = [
        (
            "strategy_evidence",
            "strategy_evidence_review",
            "strategy_evidence_summary.csv",
            {"ready": True, "required_run_type_count": 4, "failed_checks": 0},
            "ready",
        ),
        (
            "scaleup",
            "scaleup_plan",
            "scaleup_summary.csv",
            {"ready": True, "target_mode": "shadow", "failed_checks": 0},
            "ready",
        ),
        (
            "market_profile",
            "market_profile_report",
            "market_profile_summary.csv",
            {"failed_checks": 0, "market": "india_nse_index_derivatives", "currency": "INR"},
            "failed_checks",
        ),
        (
            "market_portability",
            "market_portability_report",
            "market_portability_summary.csv",
            {"failed_checks": 0, "markets": 2, "strategies": 3},
            "failed_checks",
        ),
        (
            "instrument_metadata",
            "instrument_metadata_report",
            "instrument_metadata_summary.csv",
            {"passed": True, "parse_coverage": 1.0, "unparsed_instruments": 0},
            "passed",
        ),
        (
            "quote_lifecycle",
            "quote_lifecycle_plan",
            "quote_lifecycle_summary.csv",
            {"ready": True, "order_messages": 10, "max_active_quotes": 4, "failed_checks": 0},
            "ready",
        ),
        (
            "leadlag_order",
            "leadlag_order_plan",
            "leadlag_order_summary.csv",
            {"ready": True, "orders": 2, "failed_checks": 0},
            "ready",
        ),
        (
            "leadlag_launch_pipeline",
            "leadlag_launch_pipeline",
            "leadlag_launch_pipeline_summary.csv",
            {"ready": True, "components": 6, "failed_components": 0},
            "ready",
        ),
        (
            "imbalance_order",
            "imbalance_order_plan",
            "imbalance_order_summary.csv",
            {"ready": True, "orders": 2, "failed_checks": 0},
            "ready",
        ),
        (
            "imbalance_launch_pipeline",
            "imbalance_launch_pipeline",
            "imbalance_launch_pipeline_summary.csv",
            {"ready": True, "components": 6, "failed_components": 0},
            "ready",
        ),
        (
            "settlement_order",
            "settlement_order_plan",
            "settlement_order_summary.csv",
            {"ready": True, "orders": 1, "failed_checks": 0},
            "ready",
        ),
        (
            "order_mapping_draft",
            "order_mapping_draft",
            "order_mapping_draft_summary.csv",
            {"ready": True, "unmapped_required_columns": 0, "failed_checks": 0},
            "ready",
        ),
        (
            "fill_model",
            "fill_model_calibration",
            "fill_model_summary.csv",
            {"ready": True, "orders": 12, "failed_checks": 0},
            "ready",
        ),
        (
            "fill_model_drift",
            "fill_model_drift",
            "fill_model_drift_summary.csv",
            {"ready": True, "failed_checks": 0, "recommendation": "reuse_existing_proof"},
            "ready",
        ),
        (
            "calibrated_replay",
            "calibrated_replay_plan",
            "calibrated_replay_summary.csv",
            {"ready": True, "failed_checks": 0, "runs": 2},
            "ready",
        ),
        (
            "mapped_data",
            "mapped_data_normalization",
            "mapped_data_summary.csv",
            {"ready": True, "rows": 100, "failed_checks": 0},
            "ready",
        ),
        (
            "diagnostics",
            "data_diagnostics",
            "diagnostic_summary.csv",
            {"passed": True, "rows": 100, "failed_checks": 0},
            "passed",
        ),
    ]
    for folder, run_type, summary_name, summary_row, _ in cases:
        write_run(
            root / folder,
            run_type=run_type,
            summary_name=summary_name,
            summary_row=summary_row,
        )

    report = catalog_experiment_runs([root])

    rows = report.catalog.set_index("run_type")
    assert int(report.summary.iloc[0]["status_true_runs"]) == len(cases)
    for _, run_type, summary_name, _, status_column in cases:
        assert rows.loc[run_type, "summary_file"] == summary_name
        assert rows.loc[run_type, "summary_status_column"] == status_column
    assert rows.loc["scaleup_plan", "summary_target_mode"] == "shadow"
    assert rows.loc["market_profile_report", "summary_currency"] == "INR"
    assert rows.loc["instrument_metadata_report", "summary_parse_coverage"] == 1.0


def test_cli_catalog_runs_writes_catalog(tmp_path):
    root = tmp_path / "runs"
    out_dir = tmp_path / "catalog"
    write_run(
        root / "stress",
        run_type="stress_report",
        summary_name="stress_summary.csv",
        summary_row={"all_scenarios_passed": False, "failed_rows": 2, "worst_stressed_net_pnl": -10.0},
    )

    code = main(["catalog-runs", "--roots", str(root), "--out", str(out_dir)])

    summary = pd.read_csv(out_dir / "experiment_catalog_summary.csv")
    catalog = pd.read_csv(out_dir / "experiment_catalog.csv")
    assert code == 0
    assert int(summary.loc[0, "run_count"]) == 1
    assert int(summary.loc[0, "status_false_runs"]) == 1
    assert catalog.loc[0, "run_type"] == "stress_report"


def test_cli_catalog_runs_can_fail_on_catalog_gaps(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "stress",
        run_type="stress_report",
        summary_name="stress_summary.csv",
        summary_row={"all_scenarios_passed": False, "failed_rows": 2, "worst_stressed_net_pnl": -10.0},
    )

    code = main(
        [
            "catalog-runs",
            "--roots",
            str(root),
            "--out",
            str(tmp_path / "catalog"),
            "--fail-on-catalog-gaps",
        ]
    )

    assert code == 2


def test_cli_catalog_runs_catalog_gap_gate_passes_clean_catalog(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "proof",
        run_type="proof_report",
        summary_name="proof_summary.csv",
        summary_row={"all_passed": True, "failed_runs": 0, "total_net_pnl": 42.0},
    )

    code = main(
        [
            "catalog-runs",
            "--roots",
            str(root),
            "--out",
            str(tmp_path / "catalog"),
            "--fail-on-catalog-gaps",
        ]
    )

    assert code == 0


def test_cli_catalog_runs_can_fail_on_placeholder_schema_gates(tmp_path):
    allowed_root = tmp_path / "allowed_runs"
    write_run(
        allowed_root / "broker_vendor_allowed",
        run_type="broker_vendor_data_readiness_pipeline",
        summary_name="broker_vendor_data_readiness_summary.csv",
        summary_row={
            "ready": True,
            "adapter": "arrow_money",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "schema_reviewed": False,
            "placeholder_schema_active": True,
            "placeholder_schema_allowed": True,
            "failed_checks": 0,
        },
    )
    blocked_root = tmp_path / "blocked_runs"
    write_run(
        blocked_root / "broker_readiness_blocked",
        run_type="broker_readiness",
        summary_name="broker_readiness_summary.csv",
        summary_row={
            "ready": False,
            "adapter": "irage",
            "adapter_schema_status": "placeholder_normalized_pending_vendor_schema",
            "schema_reviewed": False,
            "failed_checks": 1,
        },
    )

    allowed_blocked_gate = main(
        [
            "catalog-runs",
            "--roots",
            str(allowed_root),
            "--out",
            str(tmp_path / "catalog_allowed_blocked_gate"),
            "--fail-on-blocked-placeholder-schema",
        ]
    )
    allowed_strict_gate = main(
        [
            "catalog-runs",
            "--roots",
            str(allowed_root),
            "--out",
            str(tmp_path / "catalog_allowed_strict_gate"),
            "--fail-on-placeholder-schema",
        ]
    )
    blocked_gate = main(
        [
            "catalog-runs",
            "--roots",
            str(blocked_root),
            "--out",
            str(tmp_path / "catalog_blocked_gate"),
            "--fail-on-blocked-placeholder-schema",
        ]
    )

    summary = pd.read_csv(tmp_path / "catalog_blocked_gate" / "experiment_catalog_summary.csv")
    assert allowed_blocked_gate == 0
    assert allowed_strict_gate == 2
    assert blocked_gate == 2
    assert int(summary.loc[0, "placeholder_schema_blocked_runs"]) == 1


def test_cli_catalog_runs_can_gate_broker_roundtrip_portfolio_proofs(tmp_path):
    safe_root = tmp_path / "safe_runs"
    write_run(
        safe_root / "broker_roundtrip_safe",
        run_type="broker_dispatch_roundtrip",
        summary_name="broker_dispatch_roundtrip_summary.csv",
        summary_row={
            "passed": True,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "dispatch_total_notional": 1500.0,
            "strategy_portfolio_provided": True,
            "strategy_portfolio_ready": True,
            "strategy_portfolio_selected_allocation_notional": 2000.0,
            "failed_checks": 0,
        },
    )
    breach_root = tmp_path / "breach_runs"
    write_run(
        breach_root / "broker_roundtrip_breach",
        run_type="broker_dispatch_roundtrip",
        summary_name="broker_dispatch_roundtrip_summary.csv",
        summary_row={
            "passed": False,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "dispatch_total_notional": 2500.0,
            "strategy_portfolio_provided": True,
            "strategy_portfolio_ready": True,
            "strategy_portfolio_selected_allocation_notional": 2000.0,
            "failed_checks": 1,
        },
    )
    missing_root = tmp_path / "missing_runs"
    write_run(
        missing_root / "proof",
        run_type="proof_report",
        summary_name="proof_summary.csv",
        summary_row={"all_passed": True, "failed_runs": 0},
    )

    safe_code = main(
        [
            "catalog-runs",
            "--roots",
            str(safe_root),
            "--out",
            str(tmp_path / "catalog_safe"),
            "--require-broker-roundtrip-portfolio-safe",
            "--fail-on-broker-roundtrip-portfolio-breach",
        ]
    )
    breach_code = main(
        [
            "catalog-runs",
            "--roots",
            str(breach_root),
            "--out",
            str(tmp_path / "catalog_breach"),
            "--fail-on-broker-roundtrip-portfolio-breach",
        ]
    )
    missing_code = main(
        [
            "catalog-runs",
            "--roots",
            str(missing_root),
            "--out",
            str(tmp_path / "catalog_missing"),
            "--require-broker-roundtrip-portfolio-safe",
        ]
    )

    breach_summary = pd.read_csv(tmp_path / "catalog_breach" / "experiment_catalog_summary.csv")
    assert safe_code == 0
    assert breach_code == 2
    assert missing_code == 2
    assert int(breach_summary.loc[0, "broker_roundtrip_portfolio_breach_runs"]) == 1


def test_cli_catalog_runs_can_fail_on_any_actions(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "scorecard",
        run_type="strategy_scorecard",
        summary_name="strategy_scorecard_summary.csv",
        summary_row={
            "ready": True,
            "best_strategy": "lead_lag_taker",
            "best_market": "india_nse_index_derivatives",
            "best_next_gate": "plan-scaleup",
            "best_next_gate_help_command": "python -m hft_cli plan-scaleup --help",
        },
    )

    blocked_code = main(
        [
            "catalog-runs",
            "--roots",
            str(root),
            "--out",
            str(tmp_path / "catalog_blocked_only"),
            "--fail-on-blocked-actions",
        ]
    )
    any_code = main(
        [
            "catalog-runs",
            "--roots",
            str(root),
            "--out",
            str(tmp_path / "catalog_any_action"),
            "--fail-on-actions",
        ]
    )

    assert blocked_code == 0
    assert any_code == 2


def test_cli_catalog_runs_can_fail_on_blocked_actions(tmp_path):
    root = tmp_path / "runs"
    write_run(
        root / "route_readiness",
        run_type="route_readiness_review",
        summary_name="route_readiness_summary.csv",
        summary_row={
            "ready": False,
            "strategy": "lead_lag_taker",
            "market": "india_nse_index_derivatives",
            "next_gate": "review-strategy-evidence --profile ops_launch --require-file-inputs",
            "next_gate_help_command": (
                "python -m hft_cli review-strategy-evidence --profile ops_launch --require-file-inputs --help"
            ),
        },
    )

    code = main(
        [
            "catalog-runs",
            "--roots",
            str(root),
            "--out",
            str(tmp_path / "catalog"),
            "--fail-on-blocked-actions",
        ]
    )

    assert code == 2
