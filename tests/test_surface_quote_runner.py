import pandas as pd

from engine.surface import black76_price
from hft_cli import main
from strategies.run_surface_quotes import run_surface_quote_generation


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def option_row(ts, strike, *, forward=1000.0, vol=0.2, tte=30 / 365):
    call_mid = black76_price(option_type="C", forward=forward, strike=strike, tte_years=tte, vol=vol)
    put_mid = black76_price(option_type="P", forward=forward, strike=strike, tte_years=tte, vol=vol)
    return {
        "ts": ts,
        "expiry": "2026-06-30",
        "strike": float(strike),
        "call_bid": round(max(call_mid - 0.10, 0.05), 2),
        "call_ask": round(call_mid + 0.10, 2),
        "call_bid_qty": 300,
        "call_ask_qty": 300,
        "put_bid": round(max(put_mid - 0.10, 0.05), 2),
        "put_ask": round(put_mid + 0.10, 2),
        "put_bid_qty": 300,
        "put_ask_qty": 300,
    }


def write_surface_inputs(tmp_path):
    ts = ns_ist("2026-06-10 09:15:00")
    chain = pd.DataFrame([option_row(ts, strike) for strike in [950.0, 1000.0, 1050.0]])
    futures = pd.DataFrame(
        [
            {
                "ts": ts,
                "bid": 999.95,
                "ask": 1000.05,
                "bid_qty": 300,
                "ask_qty": 300,
            }
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)
    return chain_path, futures_path


def test_run_surface_quote_generation_writes_quotes_summary_and_manifest(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "surface_quotes"

    result = run_surface_quote_generation(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        tte_years=30 / 365,
        tick_size=0.05,
        lot_size=75,
        quote_lots=1,
        edge_ticks=2.0,
        max_market_spread_ticks=10,
        max_quotes_per_snapshot=4,
    )

    assert len(result.quotes) == 4
    assert result.summary.iloc[0]["quotes"] == 4
    assert result.summary.iloc[0]["marketable_quotes"] == 0
    assert set(result.quotes["side"]) == {-1, 1}
    assert (out_dir / "surface_quotes.csv").exists()
    assert (out_dir / "surface_quote_summary.csv").exists()
    assert (out_dir / "manifest.json").exists()


def test_unified_cli_quote_surface_dispatches(tmp_path):
    chain_path, futures_path = write_surface_inputs(tmp_path)
    out_dir = tmp_path / "cli_surface_quotes"

    code = main(
        [
            "quote-surface",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--tte-years",
            str(30 / 365),
            "--max-quotes-per-snapshot",
            "2",
            "--max-market-spread-ticks",
            "10",
        ]
    )

    assert code == 0
    assert (out_dir / "surface_quotes.csv").exists()
    assert (out_dir / "manifest.json").exists()
