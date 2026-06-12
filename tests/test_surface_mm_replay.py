import pandas as pd

from hft_cli import main
from strategies.run_surface_mm_replay import SurfaceMMReplayConfig, run_surface_mm_replay


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def chain_rows():
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:01")
    ts2 = ns_ist("2026-06-10 09:15:02")
    return pd.DataFrame(
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


def surface_quotes():
    ts0 = ns_ist("2026-06-10 09:15:00")
    return pd.DataFrame(
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


def write_inputs(tmp_path, quotes=None):
    chain_path = tmp_path / "chain.csv"
    quotes_path = tmp_path / "surface_quotes.csv"
    chain_rows().to_csv(chain_path, index=False)
    (surface_quotes() if quotes is None else quotes).to_csv(quotes_path, index=False)
    return quotes_path, chain_path


def test_surface_mm_replay_fills_passive_touches_and_writes_proof_artifacts(tmp_path):
    quotes_path, chain_path = write_inputs(tmp_path)
    out_dir = tmp_path / "surface_mm_replay"

    result = run_surface_mm_replay(
        quotes_path=quotes_path,
        chain_path=chain_path,
        output_dir=out_dir,
        config=SurfaceMMReplayConfig(quote_ttl_ns=2_000_000_000, markout_horizon_ns=1_000_000_000),
    )

    assert len(result.fills) == 2
    assert result.summary.iloc[0]["fills"] == 2
    assert result.summary.iloc[0]["net_pnl"] > 0
    assert result.markouts["markout"].mean() > 0
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "fills.csv").exists()
    assert (out_dir / "equity.csv").exists()
    assert (out_dir / "markouts.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_surface_mm_replay_reports_unfilled_quotes_when_not_touched(tmp_path):
    quotes = surface_quotes()
    quotes.loc[:, "price"] = [9.0, 12.0]
    quotes_path, chain_path = write_inputs(tmp_path, quotes)

    result = run_surface_mm_replay(
        quotes_path=quotes_path,
        chain_path=chain_path,
        config=SurfaceMMReplayConfig(quote_ttl_ns=2_000_000_000),
    )

    assert result.fills.empty
    assert len(result.unfilled) == 2
    assert set(result.unfilled["unfilled_reason"]) == {"no_touch"}
    assert result.summary.iloc[0]["fills"] == 0


def test_unified_cli_replay_surface_mm_dispatches(tmp_path):
    quotes_path, chain_path = write_inputs(tmp_path)
    out_dir = tmp_path / "cli_surface_mm"

    code = main(
        [
            "replay-surface-mm",
            "--quotes",
            str(quotes_path),
            "--chain",
            str(chain_path),
            "--out",
            str(out_dir),
            "--quote-ttl-ns",
            "2000000000",
            "--markout-horizon-ns",
            "1000000000",
        ]
    )

    assert code == 0
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "manifest.json").exists()
