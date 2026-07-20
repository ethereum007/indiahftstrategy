import json

import pandas as pd

from hft_cli import main
from reports.leadlag_edge import (
    LeadLagEdgeThresholds,
    evaluate_leadlag_edge,
    write_leadlag_edge_audit,
)
from reports.manifest import verify_experiment_manifest, write_experiment_manifest
from research.leadlag import MEASUREMENT_REQUIRED_ARTIFACTS, MEASUREMENT_RUN_TYPE


def cross_correlation():
    return pd.DataFrame(
        [
            {"lag_ns": 0, "correlation": 0.12, "samples": 8},
            {"lag_ns": 100_000, "correlation": 0.82, "samples": 8},
            {"lag_ns": 250_000, "correlation": 0.41, "samples": 8},
        ]
    )


def lag_profile():
    return pd.DataFrame(
        [
            {"event_ts": 100, "leader_move": 2.0, "time_to_update_ns": 100_000, "updated_within_window": True},
            {"event_ts": 200, "leader_move": -2.0, "time_to_update_ns": 150_000, "updated_within_window": True},
            {"event_ts": 300, "leader_move": 2.5, "time_to_update_ns": 200_000, "updated_within_window": True},
        ]
    )


def latency_curve():
    return pd.DataFrame(
        [
            {
                "latency_ns": 50_000,
                "events": 3,
                "fills": 3,
                "fill_rate": 1.0,
                "profitable_fills": 3,
                "win_rate": 1.0,
                "gross_pnl": 18.0,
                "round_trip_cost": 3.0,
                "net_pnl": 15.0,
                "avg_edge": 6.0,
                "avg_net_edge": 5.0,
                "cost_drag_ratio": 1.0 / 6.0,
                "net_edge_bps": 3.0,
            },
            {
                "latency_ns": 150_000,
                "events": 3,
                "fills": 2,
                "fill_rate": 2.0 / 3.0,
                "profitable_fills": 2,
                "win_rate": 1.0,
                "gross_pnl": 10.0,
                "round_trip_cost": 2.0,
                "net_pnl": 8.0,
                "avg_edge": 5.0,
                "avg_net_edge": 4.0,
                "cost_drag_ratio": 0.2,
                "net_edge_bps": 2.0,
            },
            {
                "latency_ns": 300_000,
                "events": 3,
                "fills": 1,
                "fill_rate": 1.0 / 3.0,
                "profitable_fills": 1,
                "win_rate": 1.0,
                "gross_pnl": 4.0,
                "round_trip_cost": 2.0,
                "net_pnl": 2.0,
                "avg_edge": 4.0,
                "avg_net_edge": 2.0,
                "cost_drag_ratio": 0.5,
                "net_edge_bps": 1.0,
            },
        ]
    )


def write_measure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    leader_path = path.parent / f"{path.name}_leader.csv"
    laggard_path = path.parent / f"{path.name}_laggard.csv"
    leader_path.write_text("ts,bid,ask,bid_qty,ask_qty\n0,99,101,100,100\n", encoding="utf-8")
    laggard_path.write_text("ts,bid,ask,bid_qty,ask_qty\n0,49,51,100,100\n", encoding="utf-8")
    cross_correlation().to_csv(path / "cross_correlation.csv", index=False)
    lag_profile().to_csv(path / "lag_profile.csv", index=False)
    latency_curve().to_csv(path / "latency_curve.csv", index=False)
    pd.DataFrame(
        [
            {
                "completed": True,
                "strategy": "lead_lag_taker",
                "market": "india_nse_index_derivatives",
                "authorizes_submission": False,
                "next_gate": "audit-leadlag-edge",
            }
        ]
    ).to_csv(path / "leadlag_measure_summary.csv", index=False)
    (path / "leadlag_measure_config.json").write_text(
        json.dumps(
            {
                "run_type": MEASUREMENT_RUN_TYPE,
                "authorizes_submission": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "leadlag_measure_runbook.md").write_text(
        "# Lead-Lag Measurement Runbook\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        path,
        run_type=MEASUREMENT_RUN_TYPE,
        parameters={"strategy": "lead_lag_taker"},
        inputs={"leader": leader_path, "laggard": laggard_path},
        extra={"authorizes_submission": False},
    )
    return leader_path, laggard_path


def test_leadlag_edge_audit_passes_strong_measurement():
    audit = evaluate_leadlag_edge(
        cross_correlation(),
        lag_profile(),
        latency_curve(),
        thresholds=LeadLagEdgeThresholds(
            min_events=3,
            min_abs_correlation=0.8,
            min_update_rate=1.0,
            max_median_update_ns=150_000,
            min_best_latency_net_pnl=10.0,
            min_best_latency_fills=3,
            min_profitable_latency_ns=50_000,
            min_best_latency_fill_rate=1.0,
            min_best_latency_avg_net_edge=5.0,
            max_best_latency_cost_drag_ratio=0.2,
        ),
    )

    metrics = audit.metrics.iloc[0]
    assert audit.passed
    assert metrics["best_lag_ns"] == 100_000
    assert metrics["best_abs_correlation"] == 0.82
    assert metrics["update_rate"] == 1.0
    assert metrics["max_profitable_latency_ns"] == 50_000
    assert metrics["best_latency_fill_rate"] == 1.0
    assert metrics["best_latency_win_rate"] == 1.0
    assert metrics["best_latency_gross_pnl"] == 18.0
    assert metrics["best_latency_round_trip_cost"] == 3.0
    assert metrics["best_latency_avg_net_edge"] == 5.0
    assert metrics["best_latency_cost_drag_ratio"] == 1.0 / 6.0
    assert audit.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert audit.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert audit.summary.iloc[0]["recommendation"] == "replay_or_sweep_candidate"


def test_leadlag_edge_audit_fails_weak_update_rate_and_latency():
    weak_lag_profile = lag_profile()
    weak_lag_profile.loc[1:, "updated_within_window"] = False
    weak_lag_profile.loc[1:, "time_to_update_ns"] = pd.NA
    weak_latency = latency_curve()
    weak_latency["net_pnl"] = [-1.0, -2.0, -3.0]

    audit = evaluate_leadlag_edge(
        cross_correlation(),
        weak_lag_profile,
        weak_latency,
        thresholds=LeadLagEdgeThresholds(
            min_events=3,
            min_abs_correlation=0.8,
            min_update_rate=0.8,
            min_best_latency_net_pnl=0.0,
            min_best_latency_fills=1,
        ),
    )

    assert not audit.passed
    failed = set(audit.checks.loc[~audit.checks["passed"].astype(bool), "check"])
    assert "update_rate" in failed
    assert "best_latency_net_pnl" in failed
    assert "max_profitable_latency_ns" in failed


def test_leadlag_edge_audit_can_gate_per_fill_edge_and_cost_drag():
    viable = evaluate_leadlag_edge(
        cross_correlation(),
        lag_profile(),
        latency_curve(),
        thresholds=LeadLagEdgeThresholds(
            min_profitable_latency_ns=150_000,
            min_best_latency_fill_rate=0.5,
            min_best_latency_avg_net_edge=4.0,
            max_best_latency_cost_drag_ratio=0.2,
        ),
    )
    assert viable.passed
    assert viable.metrics.iloc[0]["max_profitable_latency_ns"] == 150_000

    audit = evaluate_leadlag_edge(
        cross_correlation(),
        lag_profile(),
        latency_curve(),
        thresholds=LeadLagEdgeThresholds(
            min_best_latency_avg_net_edge=5.1,
            max_best_latency_cost_drag_ratio=0.1,
        ),
    )

    failed = set(audit.checks.loc[~audit.checks["passed"].astype(bool), "check"])
    assert not audit.passed
    assert "best_latency_avg_net_edge" in failed
    assert "best_latency_cost_drag_ratio" in failed


def test_write_leadlag_edge_audit_outputs_report_files(tmp_path):
    measure_dir = tmp_path / "measure"
    out_dir = tmp_path / "audit"
    write_measure_dir(measure_dir)

    audit = write_leadlag_edge_audit(
        measure_dir,
        output_dir=out_dir,
        thresholds=LeadLagEdgeThresholds(min_abs_correlation=0.8),
    )

    assert audit.output_dir == out_dir
    assert (out_dir / "leadlag_edge_metrics.csv").exists()
    assert (out_dir / "leadlag_edge_checks.csv").exists()
    assert (out_dir / "leadlag_edge_summary.csv").exists()
    assert (out_dir / "leadlag_edge_measurement_provenance.csv").exists()
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "leadlag_edge_summary.csv")
    provenance = pd.read_csv(out_dir / "leadlag_edge_measurement_provenance.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert summary.loc[0, "strategy"] == "lead_lag_taker"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert bool(summary.loc[0, "measurement_manifest_current"])
    assert bool(provenance.loc[0, "passed"])
    assert int(provenance.loc[0, "required_artifact_count"]) == len(
        MEASUREMENT_REQUIRED_ARTIFACTS
    )
    assert manifest["parameters"]["strategy"] == "lead_lag_taker"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="leadlag_edge_audit",
        required_artifacts=(
            "leadlag_edge_metrics.csv",
            "leadlag_edge_checks.csv",
            "leadlag_edge_summary.csv",
            "leadlag_edge_measurement_provenance.csv",
        ),
        require_input_fingerprints=True,
    )
    assert integrity.passed


def test_leadlag_edge_audit_fails_when_measurement_source_drifted(tmp_path):
    measure_dir = tmp_path / "measure"
    out_dir = tmp_path / "audit"
    leader_path, _ = write_measure_dir(measure_dir)
    leader_path.write_text(
        leader_path.read_text(encoding="utf-8") + "1,100,102,100,100\n",
        encoding="utf-8",
    )

    audit = write_leadlag_edge_audit(measure_dir, output_dir=out_dir)

    assert not audit.passed
    failed = set(audit.checks.loc[~audit.checks["passed"].astype(bool), "check"])
    assert failed == {"measurement_manifest_current"}
    assert audit.summary.iloc[0]["measurement_manifest_error"] == "input_drift"
    assert not bool(audit.provenance.iloc[0]["passed"])
    assert audit.provenance.iloc[0]["error"] == "input_drift"


def test_leadlag_edge_manifest_tracks_raw_measurement_dependencies(tmp_path):
    measure_dir = tmp_path / "measure"
    out_dir = tmp_path / "audit"
    leader_path, _ = write_measure_dir(measure_dir)
    audit = write_leadlag_edge_audit(measure_dir, output_dir=out_dir)
    assert audit.passed

    leader_path.write_text(
        leader_path.read_text(encoding="utf-8") + "1,100,102,100,100\n",
        encoding="utf-8",
    )
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type="leadlag_edge_audit",
        require_input_fingerprints=True,
    )

    assert not integrity.passed
    assert integrity.error == "input_drift"


def test_cli_leadlag_edge_audit_can_fail_on_breach(tmp_path):
    measure_dir = tmp_path / "measure"
    out_dir = tmp_path / "audit"
    write_measure_dir(measure_dir)

    code = main(
        [
            "audit-leadlag-edge",
            "--measure",
            str(measure_dir),
            "--out",
            str(out_dir),
            "--min-abs-correlation",
            "0.95",
            "--min-best-latency-fill-rate",
            "1.0",
            "--min-best-latency-avg-net-edge",
            "5.0",
            "--max-best-latency-cost-drag-ratio",
            "0.2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "leadlag_edge_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert int(summary.loc[0, "failed_checks"]) == 1
    assert summary.loc[0, "strategy"] == "lead_lag_taker"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
