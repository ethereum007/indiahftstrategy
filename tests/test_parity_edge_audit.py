import pandas as pd

from hft_cli import main
from reports.parity_edge import (
    PARITY_EDGE_REQUIRED_ARTIFACTS,
    PARITY_EDGE_RUN_TYPE,
    ParityEdgeThresholds,
    evaluate_parity_edge,
    write_parity_edge_audit,
)
from reports.manifest import (
    verify_experiment_manifest,
    write_experiment_manifest,
)
from scanners.run_parity_box import PARITY_SCAN_RUN_TYPE


def parity_opportunities():
    return pd.DataFrame(
        [
            {
                "ts": 1_000,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "direction": "buy_synthetic_sell_future",
                "qty": 75,
                "edge_per_unit": 7.0,
                "gross_edge": 525.0,
                "total_cost": 25.0,
                "net_edge": 500.0,
                "displayed_depth": 75,
                "future_ts": 900,
                "regime": "open",
                "persistence_ticks": 2,
            },
            {
                "ts": 2_000,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "direction": "buy_synthetic_sell_future",
                "qty": 75,
                "edge_per_unit": 5.0,
                "gross_edge": 375.0,
                "total_cost": 25.0,
                "net_edge": 350.0,
                "displayed_depth": 75,
                "future_ts": 1_900,
                "regime": "open",
                "persistence_ticks": 1,
            },
        ]
    )


def box_opportunities():
    return pd.DataFrame(
        [
            {
                "ts": 1_500,
                "expiry": "2026-06-30",
                "low_strike": 1000.0,
                "high_strike": 1010.0,
                "direction": "buy_box",
                "qty": 75,
                "edge_per_unit": 3.0,
                "gross_edge": 225.0,
                "total_cost": 25.0,
                "net_edge": 200.0,
                "displayed_depth": 75,
                "regime": "midday",
                "persistence_ticks": 0,
            }
        ]
    )


def write_scan_dir(path, *, parity=None, boxes=None):
    path.mkdir(parents=True, exist_ok=True)
    (parity_opportunities() if parity is None else parity).to_csv(path / "parity_opportunities.csv", index=False)
    (box_opportunities() if boxes is None else boxes).to_csv(path / "box_opportunities.csv", index=False)
    pd.DataFrame([{"opportunities": 3}]).to_csv(
        path / "opportunity_report.csv",
        index=False,
    )
    pd.DataFrame([{"reason": "fresh"}]).to_csv(
        path / "parity_futures_join_audit.csv",
        index=False,
    )
    chain_path = path.parent / "chain.csv"
    futures_path = path.parent / "futures.csv"
    pd.DataFrame([{"ts": 1}]).to_csv(chain_path, index=False)
    pd.DataFrame([{"ts": 1}]).to_csv(
        futures_path,
        index=False,
    )
    write_experiment_manifest(
        path,
        run_type=PARITY_SCAN_RUN_TYPE,
        inputs={
            "chain": chain_path,
            "futures": futures_path,
        },
        parameters={
            "market": "india_nse_index_derivatives",
            "chain_column_map": None,
            "futures_column_map": None,
            "timestamp_unit": "ns",
            "timestamp_tz": None,
            "filter_session": True,
            "lot_size": 75,
            "option_tick": 0.05,
            "future_tick": 0.05,
            "asof_latency_ns": 0,
            "max_futures_quote_age_ns": 100,
            "depth_fraction": 0.25,
        },
    )


def test_parity_edge_audit_passes_strong_mixed_scan():
    audit = evaluate_parity_edge(
        parity_opportunities(),
        box_opportunities(),
        thresholds=ParityEdgeThresholds(
            min_total_opportunities=3,
            min_parity_opportunities=2,
            min_box_opportunities=1,
            min_total_net_edge=1_000.0,
            min_median_net_edge=300.0,
            min_best_net_edge=500.0,
            min_median_persistence_ticks=1.0,
            min_direction_count=2,
            max_future_staleness_ns=100,
        ),
    )

    metrics = audit.metrics.iloc[0]
    assert audit.passed
    assert metrics["total_opportunities"] == 3
    assert metrics["total_net_edge"] == 1050.0
    assert metrics["direction_count"] == 2
    assert metrics["max_future_staleness_ns"] == 100.0
    assert audit.summary.iloc[0]["recommendation"] == "replay_or_sweep_candidate"


def test_parity_edge_audit_fails_weak_empty_scan():
    empty = parity_opportunities().iloc[0:0]
    audit = evaluate_parity_edge(
        empty,
        empty,
        thresholds=ParityEdgeThresholds(min_total_opportunities=1, min_total_net_edge=1.0),
    )

    assert not audit.passed
    failed = set(audit.checks.loc[~audit.checks["passed"].astype(bool), "check"])
    assert "total_opportunities" in failed
    assert "median_net_edge" in failed
    assert "best_net_edge" in failed


def test_write_parity_edge_audit_outputs_report_files(tmp_path):
    scan_dir = tmp_path / "scan"
    out_dir = tmp_path / "audit"
    write_scan_dir(scan_dir)

    audit = write_parity_edge_audit(
        scan_dir,
        output_dir=out_dir,
        thresholds=ParityEdgeThresholds(min_total_opportunities=3),
    )

    assert audit.output_dir == out_dir
    assert (out_dir / "parity_edge_metrics.csv").exists()
    assert (out_dir / "parity_edge_checks.csv").exists()
    assert (out_dir / "parity_edge_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    assert audit.passed
    assert bool(audit.summary.loc[0, "scan_manifest_current"])
    integrity = verify_experiment_manifest(
        out_dir / "manifest.json",
        expected_run_type=PARITY_EDGE_RUN_TYPE,
        required_artifacts=PARITY_EDGE_REQUIRED_ARTIFACTS,
        require_input_fingerprints=True,
    )
    assert integrity.passed


def test_parity_edge_audit_rejects_drifted_scan_manifest(tmp_path):
    scan_dir = tmp_path / "scan"
    out_dir = tmp_path / "audit"
    write_scan_dir(scan_dir)
    parity_opportunities().iloc[:1].to_csv(
        scan_dir / "parity_opportunities.csv",
        index=False,
    )

    audit = write_parity_edge_audit(
        scan_dir,
        output_dir=out_dir,
    )

    assert not audit.passed
    failed = set(
        audit.checks.loc[
            ~audit.checks["passed"].astype(bool),
            "check",
        ]
    )
    assert "scan_manifest_current" in failed
    assert audit.summary.loc[0, "scan_manifest_error"] == (
        "artifact_drift"
    )


def test_cli_parity_edge_audit_can_fail_on_breach(tmp_path):
    scan_dir = tmp_path / "scan"
    out_dir = tmp_path / "audit"
    write_scan_dir(scan_dir)

    code = main(
        [
            "audit-parity-edge",
            "--scan",
            str(scan_dir),
            "--out",
            str(out_dir),
            "--min-total-net-edge",
            "2000",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "parity_edge_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert int(summary.loc[0, "failed_checks"]) == 1
