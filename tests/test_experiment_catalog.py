import pandas as pd

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
    assert (out_dir / "manifest.json").exists()
    assert report.summary.iloc[0]["run_count"] == 1


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
