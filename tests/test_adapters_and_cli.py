import pandas as pd

from adapters.broker import (
    get_adapter,
    load_adapter_ticks,
    run_calibration_report,
)
from hft_cli import main


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_adapter_loads_normalized_ticks_and_known_specs(tmp_path):
    assert get_adapter("arrow_money").name == "arrow_money"
    ticks = pd.DataFrame(
        [
            {
                "ts": ns_ist("2026-06-10 09:15:00"),
                "bid": 100.0,
                "ask": 100.05,
                "bid_qty": 75,
                "ask_qty": 75,
                "last": 100.05,
                "last_qty": 75,
            }
        ]
    )
    path = tmp_path / "ticks.csv"
    ticks.to_csv(path, index=False)

    loaded = load_adapter_ticks(path, adapter="normalized")

    assert len(loaded.data) == 1
    assert loaded.data.iloc[0]["bid"] == 100.0


def test_calibration_adapter_writes_outputs(tmp_path):
    simulated = pd.DataFrame(
        [
            {
                "client_order_id": "a",
                "instrument_id": "OPT",
                "ts_sent_ns": 100,
                "side": 1,
                "qty": 75,
                "price": 100.0,
            }
        ]
    )
    live = pd.DataFrame(
        [
            {
                "client_order_id": "a",
                "instrument_id": "OPT",
                "ts_fill_ns": 150,
                "side": 1,
                "qty": 75,
                "price": 100.1,
            }
        ]
    )
    sim_path = tmp_path / "sim.csv"
    live_path = tmp_path / "live.csv"
    out_dir = tmp_path / "calibration"
    simulated.to_csv(sim_path, index=False)
    live.to_csv(live_path, index=False)

    comparison, summary = run_calibration_report(
        simulated_orders_path=sim_path,
        live_fills_path=live_path,
        output_dir=out_dir,
    )

    assert comparison.iloc[0]["filled_live"]
    assert summary.iloc[0]["live_fill_rate"] == 1.0
    assert (out_dir / "calibration_comparison.csv").exists()
    assert (out_dir / "calibration_summary.csv").exists()


def test_unified_cli_scan_parity_box_dispatch(tmp_path):
    ts = ns_ist("2026-06-10 09:15:00")
    chain = pd.DataFrame(
        [
            {
                "ts": ts,
                "expiry": "2026-06-30",
                "strike": 1000.0,
                "call_bid": 54.0,
                "call_ask": 55.0,
                "call_bid_qty": 1200,
                "call_ask_qty": 1200,
                "put_bid": 60.0,
                "put_ask": 61.0,
                "put_bid_qty": 1200,
                "put_ask_qty": 1200,
            }
        ]
    )
    futures = pd.DataFrame(
        [
            {
                "ts": ts,
                "bid": 1100.0,
                "ask": 1101.0,
                "bid_qty": 1200,
                "ask_qty": 1200,
            }
        ]
    )
    chain_path = tmp_path / "chain.csv"
    futures_path = tmp_path / "futures.csv"
    out_dir = tmp_path / "scan"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    code = main(
        [
            "scan-parity-box",
            "--chain",
            str(chain_path),
            "--futures",
            str(futures_path),
            "--out",
            str(out_dir),
            "--max-futures-quote-age-ns",
            "0",
        ]
    )

    assert code == 0
    assert (out_dir / "parity_opportunities.csv").exists()
    assert (out_dir / "opportunity_report.csv").exists()
    assert (out_dir / "parity_futures_join_audit.csv").exists()
