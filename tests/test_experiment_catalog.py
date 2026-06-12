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
