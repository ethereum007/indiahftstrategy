import json

import pandas as pd

from hft_cli import main
from reports.imbalance_replay_walkforward import (
    ImbalanceReplayWalkForwardThresholds,
    write_imbalance_replay_walkforward,
)
from reports.proof import ProofThresholds, verify_proof_report


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def ns_us(value: str) -> int:
    return pd.Timestamp(value, tz="America/New_York").value


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


def us_imbalance_ticks(day: str):
    ts0 = ns_us(f"{day} 09:29:59")
    ts1 = ns_us(f"{day} 09:30:00")
    ts2 = ns_us(f"{day} 09:30:00.000100")
    ts3 = ns_us(f"{day} 09:30:00.000200")
    ts4 = ns_us(f"{day} 09:30:00.000300")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 99.00, "ask": 99.01, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.01, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.00, "ask": 100.01, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts3, "bid": 100.10, "ask": 100.11, "bid_qty": 500, "ask_qty": 500},
            {"ts": ts4, "bid": 100.10, "ask": 100.11, "bid_qty": 500, "ask_qty": 500},
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


def write_us_candidate(path):
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
                    "market": "us_equities_regular",
                    "tick_size": 0.01,
                    "entry_imbalance": 0.6,
                    "min_microprice_edge_ticks": 0.25,
                    "hold_ns": 1_000_000,
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
    assert report.folds["pending_order_risk_reservation_enabled"].all()
    assert report.folds["aggressive_self_cross_prevention_enabled"].all()
    assert int(report.summary.loc[0, "pending_order_risk_reservation_enabled_folds"]) == 2
    assert int(report.summary.loc[0, "aggressive_self_cross_prevention_enabled_folds"]) == 2
    assert int(report.summary.loc[0, "total_pretrade_rejections"]) == 0
    assert int(report.summary.loc[0, "total_position_risk_rejections"]) == 0
    assert int(report.summary.loc[0, "total_self_cross_rejections"]) == 0
    assert config["ready"]
    assert config["source_run_type"] == "imbalance_replay_walkforward"
    assert config["replay_defaults"]["instrument_id"] == "BOOK"
    assert config["replay_defaults"]["instrument_kind"] == "OPT"
    assert config["replay_defaults"]["lot_size"] == 75
    assert config["replay_defaults"]["qty"] == 75
    assert config["replay_defaults"]["entry_imbalance"] == 0.6
    assert config["replay_defaults"]["exit_imbalance"] == 0.15
    assert config["replay_defaults"]["max_spread_ticks"] == 2.0
    assert config["replay_defaults"]["min_depth"] == 1
    assert config["replay_defaults"]["hold_ns"] == 1_000_000
    assert config["replay_defaults"]["cooloff_ns"] == 1_000_000
    assert config["replay_walkforward"]["pending_order_risk_reservation_enabled_folds"] == 2
    assert config["replay_walkforward"]["aggressive_self_cross_prevention_enabled_folds"] == 2
    assert config["replay_walkforward"]["total_pretrade_rejections"] == 0
    assert (out_dir / "imbalance_replay_walkforward_folds.csv").exists()
    assert (out_dir / "imbalance_replay_walkforward_checks.csv").exists()
    assert (out_dir / "imbalance_replay_walkforward_summary.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
    assert verify_proof_report(out_dir / "proof").verified
    assert (out_dir / "runs" / "01_day1" / "summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_write_imbalance_replay_walkforward_inherits_us_generic_costs(tmp_path):
    fold_a = tmp_path / "us_fold_a.csv"
    fold_b = tmp_path / "us_fold_b.csv"
    candidate_dir = tmp_path / "us_edge_walkforward"
    out_dir = tmp_path / "us_replay_walkforward"
    us_imbalance_ticks("2026-06-10").to_csv(fold_a, index=False)
    us_imbalance_ticks("2026-06-11").to_csv(fold_b, index=False)
    write_us_candidate(candidate_dir)

    report = write_imbalance_replay_walkforward(
        [fold_a, fold_b],
        output_dir=out_dir,
        labels=["day1", "day2"],
        candidate_config=candidate_dir,
        instrument_kind="EQ",
        lot_size=1,
        qty=1,
        cooloff_ns=1_000_000,
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
        thresholds=ImbalanceReplayWalkForwardThresholds(
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
    assert config["replay_defaults"]["market"] == "us_equities_regular"
    assert config["replay_defaults"]["instrument_kind"] == "EQ"
    assert config["replay_defaults"]["lot_size"] == 1
    assert config["replay_defaults"]["qty"] == 1
    assert config["replay_defaults"]["generic_costs"]["per_order_fee"] == 0.01
    assert manifest["parameters"]["instrument_kind"] == "EQ"
    assert manifest["parameters"]["qty"] == 1
    assert manifest["parameters"]["generic_costs"]["per_order_fee"] == 0.01


def test_cli_imbalance_replay_walkforward_inherits_us_generic_costs_from_candidate(tmp_path):
    fold_a = tmp_path / "us_fold_a.csv"
    fold_b = tmp_path / "us_fold_b.csv"
    candidate_dir = tmp_path / "us_edge_walkforward"
    out_dir = tmp_path / "us_replay_walkforward"
    us_imbalance_ticks("2026-06-10").to_csv(fold_a, index=False)
    us_imbalance_ticks("2026-06-11").to_csv(fold_b, index=False)
    write_us_candidate(candidate_dir)

    code = main(
        [
            "walkforward-imbalance-replay",
            "--ticks",
            str(fold_a),
            str(fold_b),
            "--out",
            str(out_dir),
            "--candidate-config",
            str(candidate_dir),
            "--instrument-kind",
            "EQ",
            "--lot-size",
            "1",
            "--qty",
            "1",
            "--cooloff-ns",
            "1000000",
            "--min-total-fills",
            "4",
            "--min-total-net-pnl",
            "0.01",
        ]
    )

    summary = pd.read_csv(out_dir / "imbalance_replay_walkforward_summary.csv")
    folds = pd.read_csv(out_dir / "imbalance_replay_walkforward_folds.csv")
    config = json.loads((out_dir / "candidate_config.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert code == 0
    assert int(summary.loc[0, "total_fills"]) == 4
    assert abs(float(folds["total_costs"].sum()) - 0.04) < 1e-12
    assert config["replay_defaults"]["generic_costs"]["per_order_fee"] == 0.01
    assert manifest["parameters"]["generic_costs"]["per_order_fee"] == 0.01


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
