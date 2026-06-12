import json

import pandas as pd

from hft_cli import main
from reports.imbalance_replay_walkforward import (
    ImbalanceReplayWalkForwardThresholds,
    write_imbalance_replay_walkforward,
)
from reports.proof import ProofThresholds


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def imbalance_ticks(day: str):
    ts0 = ns_ist(f"{day} 09:15:00")
    ts1 = ns_ist(f"{day} 09:15:00.000100")
    ts2 = ns_ist(f"{day} 09:15:00.000200")
    ts3 = ns_ist(f"{day} 09:15:00.000300")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts3, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
        ]
    )


def write_ticks(path, day: str):
    imbalance_ticks(day).to_csv(path, index=False)


def write_candidate(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "imbalance",
                "source_run_type": "imbalance_edge_walkforward",
                "failed_checks": [],
                "replay_defaults": {
                    "tick_size": 0.05,
                    "entry_imbalance": 0.6,
                    "min_microprice_edge_ticks": 0.25,
                    "hold_ns": 1_000_000,
                    "markout_horizons_ns": [100_000],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_write_imbalance_replay_walkforward_outputs_proof_and_candidate(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    fold_b = tmp_path / "fold_b.csv"
    candidate_dir = tmp_path / "edge_walkforward"
    out_dir = tmp_path / "replay_walkforward"
    write_ticks(fold_a, "2026-06-10")
    write_ticks(fold_b, "2026-06-11")
    write_candidate(candidate_dir)

    report = write_imbalance_replay_walkforward(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        candidate_config=candidate_dir,
        cooloff_ns=1_000_000,
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        thresholds=ImbalanceReplayWalkForwardThresholds(min_folds=2, min_proof_pass_rate=1.0),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert report.passed
    assert report.output_dir == out_dir
    assert int(report.summary.loc[0, "fold_count"]) == 2
    assert int(report.summary.loc[0, "proof_passed_folds"]) == 2
    assert float(report.summary.loc[0, "proof_pass_rate"]) == 1.0
    assert config["ready"]
    assert config["source_run_type"] == "imbalance_replay_walkforward"
    assert config["replay_defaults"]["entry_imbalance"] == 0.6
    assert config["replay_defaults"]["hold_ns"] == 1_000_000
    assert (out_dir / "imbalance_replay_walkforward_folds.csv").exists()
    assert (out_dir / "imbalance_replay_walkforward_checks.csv").exists()
    assert (out_dir / "imbalance_replay_walkforward_summary.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
    assert (out_dir / "runs" / "01_day1" / "summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_replay_walkforward_can_fail_on_breach(tmp_path):
    fold_a = tmp_path / "fold_a.csv"
    candidate_dir = tmp_path / "edge_walkforward"
    out_dir = tmp_path / "replay_walkforward"
    write_ticks(fold_a, "2026-06-10")
    write_candidate(candidate_dir)

    code = main(
        [
            "walkforward-imbalance-replay",
            "--ticks",
            str(fold_a),
            "--out",
            str(out_dir),
            "--candidate-config",
            str(candidate_dir),
            "--cooloff-ns",
            "1000000",
            "--min-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_replay_walkforward_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert not config["ready"]
    assert "fold_count" in config["failed_checks"]
