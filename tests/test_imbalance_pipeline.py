import json

import pandas as pd

from hft_cli import main
from reports.imbalance_edge_selection import ImbalanceEdgeSelectionThresholds
from reports.imbalance_edge_walkforward import ImbalanceEdgeWalkForwardThresholds
from reports.imbalance_pipeline import write_imbalance_research_pipeline
from reports.imbalance_replay_walkforward import ImbalanceReplayWalkForwardThresholds
from reports.proof import ProofThresholds


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def imbalance_ticks(day: str):
    ts0 = ns_ist(f"{day} 09:15:00")
    ts1 = ns_ist(f"{day} 09:15:00.000100")
    ts2 = ns_ist(f"{day} 09:15:00.000200")
    ts3 = ns_ist(f"{day} 09:15:00.000300")
    ts4 = ns_ist(f"{day} 09:15:00.000400")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts3, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts4, "bid": 100.00, "ask": 100.05, "bid_qty": 500, "ask_qty": 500},
        ]
    )


def write_ticks(path, day: str):
    imbalance_ticks(day).to_csv(path, index=False)


def test_imbalance_research_pipeline_promotes_candidate_end_to_end(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    fold_b = tmp_path / "fold_b.csv"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")
    write_ticks(fold_b, "2026-06-11")

    report = write_imbalance_research_pipeline(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        forward_horizon_ns_values=[100_000],
        min_signals=2,
        min_direction_count=2,
        min_mean_forward_edge_ticks=1.0,
        min_win_rate=0.5,
        cooloff_ns=100_000,
        selection_thresholds=ImbalanceEdgeSelectionThresholds(min_sweeps=2, min_median_usable_signals=2),
        edge_walkforward_thresholds=ImbalanceEdgeWalkForwardThresholds(min_folds=2, min_passed_sweeps=2),
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        replay_walkforward_thresholds=ImbalanceReplayWalkForwardThresholds(
            min_folds=2,
            min_proof_pass_rate=1.0,
            min_total_fills=2,
        ),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.ready
    assert report.replay is not None
    assert report.promotion is not None
    assert int(report.summary.loc[0, "edge_selectable_scenarios"]) >= 1
    assert int(report.summary.loc[0, "replay_total_fills"]) >= 2
    assert set(report.stages["stage"]) == {"edge_walkforward", "replay_walkforward", "promotion"}
    assert config["ready"]
    assert config["source_run_type"] == "imbalance_research_pipeline"
    assert config["strategy"] == "imbalance"
    assert (out_dir / "edge_walkforward" / "candidate_config.json").exists()
    assert (out_dir / "replay_walkforward" / "imbalance_replay_walkforward_summary.csv").exists()
    assert (out_dir / "promotion" / "promotion_summary.csv").exists()
    assert (out_dir / "imbalance_pipeline_stages.csv").exists()
    assert (out_dir / "imbalance_pipeline_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_research_pipeline_fails_closed_when_edge_gate_fails(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    out_dir = tmp_path / "pipeline"
    write_ticks(fold_a, "2026-06-10")

    code = main(
        [
            "pipeline-imbalance-research",
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
            "--min-signals",
            "2",
            "--min-direction-count",
            "2",
            "--min-mean-forward-edge-ticks",
            "1",
            "--min-win-rate",
            "0.5",
            "--min-edge-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_pipeline_summary.csv")
    stages = pd.read_csv(out_dir / "imbalance_pipeline_stages.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "ready"])
    assert bool(stages.loc[stages["stage"] == "replay_walkforward", "skipped"].iloc[0])
    assert "edge_walkforward" in config["failed_checks"]
