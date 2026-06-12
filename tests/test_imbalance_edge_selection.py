import json

import pandas as pd

from hft_cli import main
from reports.imbalance_edge_selection import (
    ImbalanceEdgeSelectionThresholds,
    compare_imbalance_edge_sweeps,
    write_imbalance_edge_selection,
)


def sweep_runs(*, pass_second=True):
    return pd.DataFrame(
        [
            {
                "run": "imb_0p6__edge_0p25__horizon_100000ns",
                "entry_imbalance": 0.6,
                "min_microprice_edge_ticks": 0.25,
                "forward_horizon_ns": 100_000,
                "passed": True,
                "usable_signals": 120,
                "mean_forward_edge_ticks": 1.2,
                "median_forward_edge_ticks": 1.0,
                "win_rate": 0.62,
                "robust_score": 15.0,
                "direction_count": 2,
            },
            {
                "run": "imb_0p8__edge_1__horizon_100000ns",
                "entry_imbalance": 0.8,
                "min_microprice_edge_ticks": 1.0,
                "forward_horizon_ns": 100_000,
                "passed": pass_second,
                "usable_signals": 20,
                "mean_forward_edge_ticks": 1.6,
                "median_forward_edge_ticks": 1.4,
                "win_rate": 0.55,
                "robust_score": 8.0,
                "direction_count": 1,
            },
        ]
    )


def write_sweep(path, frame):
    path.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path / "imbalance_edge_sweep_runs.csv", index=False)


def test_compare_imbalance_edge_sweeps_selects_stable_candidate(tmp_path):
    sweep_a = tmp_path / "sweep_a"
    sweep_b = tmp_path / "sweep_b"
    write_sweep(sweep_a, sweep_runs(pass_second=True))
    write_sweep(sweep_b, sweep_runs(pass_second=False))

    report = compare_imbalance_edge_sweeps(
        [sweep_a, sweep_b],
        labels=["day1", "day2"],
        thresholds=ImbalanceEdgeSelectionThresholds(
            min_sweeps=2,
            min_pass_rate=1.0,
            min_median_usable_signals=50,
            min_median_mean_forward_edge_ticks=1.0,
            min_min_win_rate=0.6,
        ),
    )

    assert report.has_selection
    assert report.summary.iloc[0]["best_scenario_key"] == (
        "entry_imbalance=0.6|min_microprice_edge_ticks=0.25|forward_horizon_ns=100000"
    )
    assert report.candidate_config["ready"]
    assert report.candidate_config["replay_defaults"]["entry_imbalance"] == 0.6
    assert report.candidate_config["replay_defaults"]["hold_ns"] == 100_000


def test_write_imbalance_edge_selection_outputs_artifacts(tmp_path):
    sweep_a = tmp_path / "sweep_a"
    out_dir = tmp_path / "selection"
    write_sweep(sweep_a, sweep_runs())

    report = write_imbalance_edge_selection(
        [sweep_a],
        output_dir=out_dir,
        thresholds=ImbalanceEdgeSelectionThresholds(min_median_usable_signals=50),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.output_dir == out_dir
    assert config["ready"]
    assert (out_dir / "imbalance_edge_scenario_runs.csv").exists()
    assert (out_dir / "imbalance_edge_scenario_scores.csv").exists()
    assert (out_dir / "imbalance_edge_selection_checks.csv").exists()
    assert (out_dir / "imbalance_edge_selection_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_edge_selection_can_fail_on_breach(tmp_path):
    sweep_a = tmp_path / "sweep_a"
    out_dir = tmp_path / "selection"
    write_sweep(sweep_a, sweep_runs())

    code = main(
        [
            "compare-imbalance-edge-sweeps",
            "--sweeps",
            str(sweep_a),
            "--out",
            str(out_dir),
            "--min-sweeps",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_edge_selection_summary.csv")
    assert code == 2
    assert int(summary.loc[0, "selectable_scenarios"]) == 0
