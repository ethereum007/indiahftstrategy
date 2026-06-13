import json

import pandas as pd

from hft_cli import main
from reports.leadlag_edge import (
    LeadLagEdgeThresholds,
    evaluate_leadlag_edge,
    write_leadlag_edge_audit,
)


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
            {"latency_ns": 50_000, "events": 3, "fills": 3, "win_rate": 1.0, "net_pnl": 15.0, "avg_edge": 6.0},
            {"latency_ns": 150_000, "events": 3, "fills": 2, "win_rate": 0.67, "net_pnl": 8.0, "avg_edge": 5.0},
            {"latency_ns": 300_000, "events": 3, "fills": 1, "win_rate": 0.33, "net_pnl": 2.0, "avg_edge": 4.0},
        ]
    )


def write_measure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    cross_correlation().to_csv(path / "cross_correlation.csv", index=False)
    lag_profile().to_csv(path / "lag_profile.csv", index=False)
    latency_curve().to_csv(path / "latency_curve.csv", index=False)


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
        ),
    )

    metrics = audit.metrics.iloc[0]
    assert audit.passed
    assert metrics["best_lag_ns"] == 100_000
    assert metrics["best_abs_correlation"] == 0.82
    assert metrics["update_rate"] == 1.0
    assert metrics["max_profitable_latency_ns"] == 50_000
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
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "leadlag_edge_summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert summary.loc[0, "strategy"] == "lead_lag_taker"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "lead_lag_taker"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"


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
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "leadlag_edge_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert int(summary.loc[0, "failed_checks"]) == 1
    assert summary.loc[0, "strategy"] == "lead_lag_taker"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
