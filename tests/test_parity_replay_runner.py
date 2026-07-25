import pandas as pd

from strategies.run_parity_replay import run_parity_replay


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_run_parity_replay_writes_outputs_and_executes_signal(tmp_path):
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
    out_dir = tmp_path / "replay"
    chain.to_csv(chain_path, index=False)
    futures.to_csv(futures_path, index=False)

    replay = run_parity_replay(
        chain_path=chain_path,
        futures_path=futures_path,
        output_dir=out_dir,
        depth_fraction=0.25,
        signal_limit=1,
    )

    assert not replay.signals.empty
    assert replay.result.engine.orders_sent == 3
    assert replay.legging.iloc[0]["fill_count"] == 3
    assert replay.summary.iloc[0]["fills"] == 3
    assert (out_dir / "fills.csv").exists()
    assert (out_dir / "terminal_liquidations.csv").exists()
    assert (out_dir / "equity.csv").exists()
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "pnl_decomposition.csv").exists()
    assert (out_dir / "spread_pairs.csv").exists()
    assert (out_dir / "spread_summary.csv").exists()
    assert (out_dir / "residual_inventory.csv").exists()
    assert (out_dir / "fills_by_regime.csv").exists()
    assert (out_dir / "equity_by_regime.csv").exists()
    assert (out_dir / "signals.csv").exists()
    assert (out_dir / "legging.csv").exists()
    assert (out_dir / "input_quarantine.csv").exists()
    assert (out_dir / "manifest.json").exists()
    input_quarantine = pd.read_csv(out_dir / "input_quarantine.csv")
    assert input_quarantine["dataset"].tolist() == ["chain", "futures"]
    assert input_quarantine["dataset_type"].tolist() == [
        "option_chain",
        "l1_ticks",
    ]
    summary = replay.summary.iloc[0]
    assert bool(summary["input_quarantine_tracking_enabled"])
    assert int(summary["input_dataset_count"]) == 2
    assert int(summary["input_total_rows"]) == 4
    assert int(summary["input_kept_rows"]) == 4
    assert int(summary["input_integrity_dropped_rows"]) == 0
    assert int(summary["input_empty_datasets"]) == 0
