import json

import pandas as pd

from hft_cli import main
from reports.proof import ProofThresholds, verify_proof_report
from strategies.run_imbalance_sweep import run_imbalance_sweep


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def imbalance_ticks():
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    ts2 = ns_ist("2026-06-10 09:15:00.000200")
    ts3 = ns_ist("2026-06-10 09:15:00.000300")
    return pd.DataFrame(
        [
            {"ts": ts0, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts1, "bid": 100.00, "ask": 100.05, "bid_qty": 900, "ask_qty": 100},
            {"ts": ts2, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
            {"ts": ts3, "bid": 100.30, "ask": 100.35, "bid_qty": 100, "ask_qty": 900},
        ]
    )


def write_candidate(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "candidate_config.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ready": True,
                "strategy": "imbalance",
                "failed_checks": [],
                "replay_defaults": {
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


def test_run_imbalance_sweep_writes_runs_summary_and_proof(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_sweep"
    imbalance_ticks().to_csv(ticks_path, index=False)

    sweep = run_imbalance_sweep(
        ticks_path=ticks_path,
        output_dir=out_dir,
        entry_imbalance_values=[0.6, 0.7],
        min_microprice_edge_ticks_values=[0.25],
        hold_ns_values=[1_000_000],
        feed_latency_us_values=[0.0],
        order_latency_us_values=[0.0],
        cooloff_ns=1_000_000,
        markout_horizons_ns=[100_000],
        proof_thresholds=ProofThresholds(min_net_pnl=0.0, min_fills=1),
    )

    assert sweep.output_dir == out_dir
    assert int(sweep.summary.iloc[0]["scenario_count"]) == 2
    assert float(sweep.summary.iloc[0]["pass_rate"]) == 1.0
    assert int(sweep.summary.iloc[0]["total_pretrade_rejections"]) == 0
    assert int(sweep.summary.iloc[0]["total_position_risk_rejections"]) == 0
    assert int(sweep.summary.iloc[0]["total_self_cross_rejections"]) == 0
    assert sweep.runs["pending_order_risk_reservation_enabled"].all()
    assert sweep.runs["aggressive_self_cross_prevention_enabled"].all()
    assert sweep.proof.passed
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "sweep_summary.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
    assert verify_proof_report(out_dir / "proof").verified
    assert (out_dir / "runs").is_dir()
    assert (out_dir / "manifest.json").exists()


def test_cli_imbalance_sweep_can_fail_on_breach(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    out_dir = tmp_path / "imbalance_sweep"
    imbalance_ticks().to_csv(ticks_path, index=False)

    code = main(
        [
            "sweep-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--entry-imbalance",
            "0.6",
            "--min-microprice-edge-ticks",
            "0.25",
            "--hold-ns",
            "1000000",
            "--cooloff-ns",
            "1000000",
            "--markout-horizons-ns",
            "100000",
            "--min-fills",
            "99",
            "--fail-on-breach",
        ]
    )

    summary = pd.read_csv(out_dir / "proof" / "proof_summary.csv")
    assert code == 2
    assert not bool(summary.loc[0, "all_passed"])


def test_cli_imbalance_sweep_uses_candidate_config(tmp_path):
    ticks_path = tmp_path / "ticks.csv"
    candidate_dir = tmp_path / "edge_sweep"
    out_dir = tmp_path / "imbalance_sweep"
    imbalance_ticks().to_csv(ticks_path, index=False)
    write_candidate(candidate_dir)

    code = main(
        [
            "sweep-imbalance",
            "--ticks",
            str(ticks_path),
            "--out",
            str(out_dir),
            "--candidate-config",
            str(candidate_dir),
            "--cooloff-ns",
            "1000000",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )

    runs = pd.read_csv(out_dir / "sweep_runs.csv")
    assert code == 0
    assert int(len(runs)) == 1
    assert float(runs.loc[0, "entry_imbalance"]) == 0.6
    assert float(runs.loc[0, "min_microprice_edge_ticks"]) == 0.25
    assert int(runs.loc[0, "hold_ns"]) == 1_000_000
