import pandas as pd

from hft_cli import main
from reports.imbalance_edge import (
    ImbalanceEdgeThresholds,
    evaluate_imbalance_edge,
    write_imbalance_edge_audit,
)


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def edge_ticks():
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    ts2 = ns_ist("2026-06-10 09:15:00.000200")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts2, "bid": 100.00, "ask": 100.05, "bid_qty": 500, "ask_qty": 500},
        ]
    )


def test_imbalance_edge_audit_passes_positive_forward_response():
    audit = evaluate_imbalance_edge(
        edge_ticks(),
        tick_size=0.05,
        thresholds=ImbalanceEdgeThresholds(
            entry_imbalance=0.6,
            min_microprice_edge_ticks=0.25,
            forward_horizon_ns=100_000,
            min_signals=2,
            min_direction_count=2,
            min_mean_forward_edge_ticks=1.0,
            min_win_rate=1.0,
        ),
    )

    assert audit.passed
    assert len(audit.signals) == 2
    assert audit.summary.iloc[0]["usable_signals"] == 2
    assert audit.summary.iloc[0]["direction_count"] == 2
    assert audit.summary.iloc[0]["mean_forward_edge_ticks"] > 1.0


def test_write_imbalance_edge_audit_outputs_artifacts(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_edge"
    edge_ticks().to_csv(ticks_path, index=False)

    audit = write_imbalance_edge_audit(
        ticks_path,
        output_dir=out_dir,
        tick_size=0.05,
        thresholds=ImbalanceEdgeThresholds(forward_horizon_ns=100_000, min_signals=2),
    )

    assert audit.output_dir == out_dir
    assert (out_dir / "imbalance_signals.csv").exists()
    assert (out_dir / "imbalance_edge_metrics.csv").exists()
    assert (out_dir / "imbalance_edge_checks.csv").exists()
    assert (out_dir / "imbalance_edge_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_edge_can_fail_on_breach(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_edge"
    edge_ticks().to_csv(ticks_path, index=False)

    code = main(
        [
            "audit-imbalance-edge",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--forward-horizon-ns",
            "100000",
            "--min-signals",
            "99",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_edge_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
