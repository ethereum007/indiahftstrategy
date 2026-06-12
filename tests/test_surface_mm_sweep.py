import pandas as pd

from hft_cli import main
from reports.proof import ProofThresholds
from strategies.run_surface_mm_sweep import run_surface_mm_sweep


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def write_surface_mm_inputs(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:01")
    ts2 = ns_ist("2026-06-10 09:15:02")
    chain = pd.DataFrame(
        [
            {
                "ts": ts0,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 10.35,
                "call_ask": 10.50,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 10.40,
                "put_ask": 10.55,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            },
            {
                "ts": ts1,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 9.85,
                "call_ask": 9.95,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 11.05,
                "put_ask": 11.20,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            },
            {
                "ts": ts2,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 10.25,
                "call_ask": 10.35,
                "call_bid_qty": 300,
                "call_ask_qty": 300,
                "put_bid": 10.75,
                "put_ask": 10.85,
                "put_bid_qty": 300,
                "put_ask_qty": 300,
            },
        ]
    )
    quotes = pd.DataFrame(
        [
            {
                "ts": ts0,
                "expiry": "2026-06-30",
                "instrument_id": "CALL_1000_0",
                "strike": 1000.0,
                "option_type": "C",
                "side": 1,
                "price": 10.00,
                "qty": 75,
                "theo": 10.20,
                "quote_edge": 0.20,
            },
            {
                "ts": ts0,
                "expiry": "2026-06-30",
                "instrument_id": "PUT_1000_0",
                "strike": 1000.0,
                "option_type": "P",
                "side": -1,
                "price": 11.00,
                "qty": 75,
                "theo": 10.80,
                "quote_edge": 0.20,
            },
        ]
    )
    chain_path = tmp_path / "chain.csv"
    quotes_path = tmp_path / "surface_quotes.csv"
    chain.to_csv(chain_path, index=False)
    quotes.to_csv(quotes_path, index=False)
    return quotes_path, chain_path


def test_run_surface_mm_sweep_writes_runs_proof_and_summary(tmp_path):
    quotes_path, chain_path = write_surface_mm_inputs(tmp_path)
    out_dir = tmp_path / "surface_mm_sweep"

    result = run_surface_mm_sweep(
        quotes_path=quotes_path,
        chain_path=chain_path,
        output_dir=out_dir,
        quote_ttl_ns_values=[500_000_000, 2_000_000_000],
        order_latency_us_values=[0.0],
        fill_depth_fraction_values=[1.0],
        markout_horizon_ns_values=[1_000_000_000],
        proof_thresholds=ProofThresholds(min_net_pnl=-1_000_000.0, min_fills=1, min_maker_share=1.0),
    )

    assert len(result.runs) == 2
    assert result.summary.iloc[0]["scenario_count"] == 2
    assert result.summary.iloc[0]["passed_scenarios"] == 1
    assert result.summary.iloc[0]["pass_rate"] == 0.5
    assert (out_dir / "sweep_runs.csv").exists()
    assert (out_dir / "sweep_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "proof" / "proof_checks.csv").exists()
    assert (out_dir / "proof" / "manifest.json").exists()
    assert (
        out_dir
        / "runs"
        / "ttl_2000000000ns__order_0us__depth_1__markout_1000000000ns"
        / "summary.csv"
    ).exists()


def test_unified_cli_sweep_surface_mm_dispatches_and_can_fail_on_breach(tmp_path):
    quotes_path, chain_path = write_surface_mm_inputs(tmp_path)
    out_dir = tmp_path / "cli_surface_mm_sweep"

    code = main(
        [
            "sweep-surface-mm",
            "--quotes",
            str(quotes_path),
            "--chain",
            str(chain_path),
            "--out",
            str(out_dir),
            "--quote-ttl-ns",
            "500000000",
            "2000000000",
            "--fill-depth-fraction",
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
