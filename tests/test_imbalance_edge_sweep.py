import json

import pandas as pd

from hft_cli import main
from reports.imbalance_edge_sweep import (
    ImbalanceEdgeSweepThresholds,
    evaluate_imbalance_edge_sweep,
    write_imbalance_edge_sweep,
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


def test_imbalance_edge_sweep_ranks_candidate_configs():
    sweep = evaluate_imbalance_edge_sweep(
        edge_ticks(),
        tick_size=0.05,
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=1.0,
        thresholds=ImbalanceEdgeSweepThresholds(
            min_passed_configs=1,
            min_best_usable_signals=2,
            min_best_mean_forward_edge_ticks=1.0,
            min_best_win_rate=1.0,
        ),
    )

    assert sweep.passed
    assert int(sweep.summary.iloc[0]["scenario_count"]) == 2
    assert int(sweep.summary.iloc[0]["passed_configs"]) == 2
    assert sweep.runs.iloc[0]["robust_score"] >= sweep.runs.iloc[-1]["robust_score"]
    assert sweep.candidate_config["ready"]
    assert sweep.candidate_config["strategy"] == "imbalance"
    assert sweep.candidate_config["replay_defaults"]["hold_ns"] == 100_000


def test_write_imbalance_edge_sweep_outputs_artifacts(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "edge_sweep"
    edge_ticks().to_csv(ticks_path, index=False)

    report = write_imbalance_edge_sweep(
        ticks_path,
        output_dir=out_dir,
        entry_imbalance_values=[0.6],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        thresholds=ImbalanceEdgeSweepThresholds(min_best_usable_signals=2),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert (out_dir / "imbalance_edge_sweep_runs.csv").exists()
    assert (out_dir / "imbalance_edge_sweep_checks.csv").exists()
    assert (out_dir / "imbalance_edge_sweep_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_edge_sweep_can_fail_on_breach(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "edge_sweep"
    edge_ticks().to_csv(ticks_path, index=False)

    code = main(
        [
            "sweep-imbalance-edge",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--min-microprice-edge-ticks",
            "0.25",
            "--forward-horizon-ns",
            "100000",
            "--min-best-usable-signals",
            "99",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_edge_sweep_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
