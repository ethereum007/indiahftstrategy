import json

import pandas as pd

from hft_cli import main
from reports.catalog import catalog_experiment_runs
from reports.leadlag_replay_walkforward import (
    LeadLagReplayWalkForwardThresholds,
    write_leadlag_replay_walkforward,
)
from reports.proof import ProofThresholds


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def ns_us(value: str) -> int:
    return pd.Timestamp(value, tz="America/New_York").value


def leadlag_books(day: str):
    ts0 = ns_ist(f"{day} 09:15:00")
    ts1 = ns_ist(f"{day} 09:15:00.000100")
    ts2 = ns_ist(f"{day} 09:15:00.000200")
    ts3 = ns_ist(f"{day} 09:15:00.000300")
    ts4 = ns_ist(f"{day} 09:15:00.000400")
    leader = pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts2, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts3, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts4, "bid": 101.00, "ask": 101.10, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    laggard = pd.DataFrame(
        [
            {"ts": ts0, "bid": 50.00, "ask": 50.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 50.00, "ask": 50.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts2, "bid": 50.00, "ask": 50.05, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts3, "bid": 50.50, "ask": 50.55, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts4, "bid": 50.50, "ask": 50.55, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    return leader, laggard


def us_leadlag_books(day: str):
    ts0 = ns_us(f"{day} 09:30:00")
    ts1 = ns_us(f"{day} 09:30:00.000100")
    ts2 = ns_us(f"{day} 09:30:00.000200")
    ts3 = ns_us(f"{day} 09:30:00.000300")
    ts4 = ns_us(f"{day} 09:30:00.000400")
    leader = pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 101.00, "ask": 101.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts2, "bid": 101.00, "ask": 101.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts3, "bid": 101.00, "ask": 101.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts4, "bid": 101.00, "ask": 101.01, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    laggard = pd.DataFrame(
        [
            {"ts": ts0, "bid": 50.00, "ask": 50.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts1, "bid": 50.00, "ask": 50.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts2, "bid": 50.00, "ask": 50.01, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts3, "bid": 50.50, "ask": 50.51, "bid_qty": 300, "ask_qty": 300},
            {"ts": ts4, "bid": 50.50, "ask": 50.51, "bid_qty": 300, "ask_qty": 300},
        ]
    )
    return leader, laggard


def write_pair(tmp_path, day: str, *, us=False, label="fold"):
    leader, laggard = us_leadlag_books(day) if us else leadlag_books(day)
    leader_path = tmp_path / f"{label}_leader.csv"
    laggard_path = tmp_path / f"{label}_laggard.csv"
    leader.to_csv(leader_path, index=False)
    laggard.to_csv(laggard_path, index=False)
    return leader_path, laggard_path


def write_us_candidate(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "lead_lag_taker",
                "source_run_type": "leadlag_edge_audit",
                "failed_checks": [],
                "replay_defaults": {
                    "market": "us_options_regular",
                    "leader_tick": 0.01,
                    "laggard_tick": 0.01,
                    "delta": 1.0,
                    "trigger_ticks": 10.0,
                    "qty": 1,
                    "flat_after_ns": 200_000,
                    "markout_horizons_ns": [100_000],
                    "generic_costs": {
                        "buy_notional_rate": 0.0,
                        "sell_notional_rate": 0.0,
                        "per_unit_fee": 0.0,
                        "per_contract_fee": 0.0,
                        "per_order_fee": 0.01,
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_write_leadlag_replay_walkforward_outputs_proof_candidate_and_catalog_row(tmp_path):
    leader_a, laggard_a = write_pair(tmp_path, "2026-06-10", label="day1")
    leader_b, laggard_b = write_pair(tmp_path, "2026-06-11", label="day2")
    out_dir = tmp_path / "leadlag_walkforward"

    report = write_leadlag_replay_walkforward(
        [leader_a, leader_b],
        [laggard_a, laggard_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        leader_tick=0.05,
        laggard_tick=0.05,
        delta=1.0,
        trigger_ticks=10.0,
        qty=75,
        flat_after_ns=200_000,
        markout_horizons_ns=[100_000],
        proof_thresholds=ProofThresholds(min_net_pnl=-1000.0, min_fills=1),
        thresholds=LeadLagReplayWalkForwardThresholds(min_folds=2, min_proof_pass_rate=1.0, min_total_net_pnl=-1000.0),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    catalog = catalog_experiment_runs([out_dir]).catalog
    walkforward_row = catalog.loc[catalog["run_type"] == "leadlag_replay_walkforward"].iloc[0]
    assert report.passed
    assert report.output_dir == out_dir
    assert int(report.summary.loc[0, "fold_count"]) == 2
    assert int(report.summary.loc[0, "proof_passed_folds"]) == 2
    assert report.summary.loc[0, "strategy"] == "lead_lag_taker"
    assert report.summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert config["ready"]
    assert config["source_run_type"] == "leadlag_replay_walkforward"
    assert config["replay_defaults"]["trigger_ticks"] == 10.0
    assert walkforward_row["summary_file"] == "leadlag_replay_walkforward_summary.csv"
    assert bool(walkforward_row["summary_status"])
    assert (out_dir / "leadlag_replay_walkforward_folds.csv").exists()
    assert (out_dir / "leadlag_replay_walkforward_checks.csv").exists()
    assert (out_dir / "leadlag_replay_walkforward_summary.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
    assert (out_dir / "runs" / "01_day1" / "summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_write_leadlag_replay_walkforward_inherits_us_generic_costs(tmp_path):
    leader_a, laggard_a = write_pair(tmp_path, "2026-06-10", us=True, label="us_day1")
    leader_b, laggard_b = write_pair(tmp_path, "2026-06-11", us=True, label="us_day2")
    candidate_dir = tmp_path / "us_edge"
    out_dir = tmp_path / "us_leadlag_walkforward"
    write_us_candidate(candidate_dir)

    report = write_leadlag_replay_walkforward(
        [leader_a, leader_b],
        [laggard_a, laggard_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        candidate_config=candidate_dir,
        lot_size=1,
        proof_thresholds=ProofThresholds(min_net_pnl=-1000.0, min_fills=1),
        thresholds=LeadLagReplayWalkForwardThresholds(
            min_folds=2,
            min_proof_pass_rate=1.0,
            min_total_fills=4,
            min_total_net_pnl=0.01,
        ),
    )

    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report.passed
    assert int(report.summary.loc[0, "total_fills"]) == 4
    assert abs(float(report.folds["total_costs"].sum()) - 0.04) < 1e-12
    assert float(report.summary.loc[0, "total_net_pnl"]) > 0.0
    assert config["replay_defaults"]["market"] == "us_options_regular"
    assert config["replay_defaults"]["generic_costs"]["per_order_fee"] == 0.01
    assert manifest["parameters"]["generic_costs"]["per_order_fee"] == 0.01


def test_cli_leadlag_replay_walkforward_can_fail_on_breach(tmp_path):
    leader_a, laggard_a = write_pair(tmp_path, "2026-06-10", label="day1")
    out_dir = tmp_path / "leadlag_walkforward"

    code = main(
        [
            "walkforward-leadlag-replay",
            "--leaders",
            str(leader_a),
            "--laggards",
            str(laggard_a),
            "--out",
            str(out_dir),
            "--leader-tick",
            "0.05",
            "--laggard-tick",
            "0.05",
            "--delta",
            "1",
            "--trigger-ticks",
            "10",
            "--qty",
            "75",
            "--flat-after-ns",
            "200000",
            "--markout-horizons-ns",
            "100000",
            "--min-net-pnl",
            "-1000",
            "--min-folds",
            "2",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "leadlag_replay_walkforward_summary.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    assert code == 2
    assert not bool(summary.loc[0, "passed"])
    assert not config["ready"]
    assert "fold_count" in config["failed_checks"]
