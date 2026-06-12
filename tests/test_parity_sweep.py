import pandas as pd

from hft_cli import main
from reports.proof import ProofThresholds
from strategies.run_parity_sweep import run_parity_sweep


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def write_parity_books(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    chain = pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            }
            for ts in [ts0, ts1]
        ]
    )
    futures = pd.DataFrame(
        [
            {"ts": ts, "bid": 1100.0, "ask": 1101.0, "bid_qty": 300, "ask_qty": 300}
            for ts in [ts0, ts1]
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)
    return chain_path, futures_path


def test_run_parity_sweep_writes_runs_proof_and_robust_summary(tmp_path):
    chain_path, futures_path = write_parity_books(tmp_path)
    out_dir = tmp_path / "parity_sweep"

    result = run_parity_sweep(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction_values=[0.25],
        asof_latency_ns_values=[0, 200_000],
        feed_latency_us_values=[0.0],
        order_latency_us_values=[0.0],
        signal_limit=1,
        proof_thresholds=ProofThresholds(min_net_pnl=-1_000_000.0, min_fills=1),
    )

    assert len(result.runs) == 2
    assert result.summary.iloc[0]["scenario_count"] == 2
    assert result.summary.iloc[0]["passed_scenarios"] == 1
    assert result.summary.iloc[0]["pass_rate"] == 0.5
    assert result.runs["signal_count"].sum() == 1
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "sweep_summary.csv").exists()
    assert (out_dir / "proof" / "proof_checks.csv").exists()
    assert (out_dir / "runs" / "depth_0p25__asof_0ns__feed_0us__order_0us" / "summary.csv").exists()


def test_unified_cli_sweep_parity_dispatches_and_can_fail_on_breach(tmp_path):
    chain_path, futures_path = write_parity_books(tmp_path)
    out_dir = tmp_path / "cli_parity_sweep"

    code = main(
        [
            "sweep-parity",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--depth-fraction",
            "0.25",
            "--asof-latency-ns",
            "0",
            "200000",
            "--signal-limit",
            "1",
            "--min-net-pnl",
            "-1000000",
            "--min-fills",
            "1",
            "--fail-on-breach",
        ]
    )

    assert code == 2
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "proof" / "proof_summary.csv").exists()
