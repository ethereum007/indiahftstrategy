import json

import pandas as pd

from hft_cli import main
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds
from reports.imbalance_edge_walkforward import write_imbalance_edge_walkforward


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def edge_ticks(day: str):
    ts0 = ns_ist(f"{day} 09:15:00")
    ts1 = ns_ist(f"{day} 09:15:00.000100")
    ts2 = ns_ist(f"{day} 09:15:00.000200")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts2, "bid": 100.00, "ask": 100.05, "bid_qty": 500, "ask_qty": 500},
        ]
    )


def write_ticks(path, day: str):
    edge_ticks(day).to_csv(path, index=False)


def test_write_imbalance_edge_walkforward_outputs_replay_ready_candidate(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    fold_b = tmp_path / "fold_b.csv"
    out_dir = tmp_path / "walkforward"
    write_ticks(fold_a, "2026-06-10")
    write_ticks(fold_b, "2026-06-11")

    report = write_imbalance_edge_walkforward(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=1.0,
        selection_thresholds=ImbalanceEdgeSelectionThresholds(min_sweeps=2, min_median_usable_signals=2),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.passed
    assert report.output_dir == out_dir
    assert int(report.summary.loc[0, "fold_count"]) == 2
    assert int(report.summary.loc[0, "passed_sweeps"]) == 2
    assert config["ready"]
    assert config["source_run_type"] == "imbalance_edge_walkforward"
    assert config["replay_defaults"]["entry_imbalance"] == 0.6
    assert config["replay_defaults"]["hold_ns"] == 100_000
    assert (out_dir / "imbalance_edge_walkforward_folds.csv").exists()
    assert (out_dir / "imbalance_edge_walkforward_checks.csv").exists()
    assert (out_dir / "imbalance_edge_walkforward_summary.csv").exists()
    assert (out_dir / "selection" / "imbalance_edge_selection_summary.csv").exists()
    assert (out_dir / "sweeps" / "01_day1" / "imbalance_edge_sweep_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_edge_walkforward_can_fail_on_breach(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    out_dir = tmp_path / "walkforward"
    write_ticks(fold_a, "2026-06-10")

    code = main(
        [
            "walkforward-imbalance-edge",
            "--ticks",
            str(fold_a),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--min-microprice-edge-ticks",
            "0.25",
            "--forward-horizon-ns",
            "100000",
            "--min-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_edge_walkforward_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert not config["ready"]
    assert "fold_count" in config["failed_checks"]
