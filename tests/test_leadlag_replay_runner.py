import json

import pandas as pd

from strategies.run_leadlag_replay import run_leadlag_replay


def ns_ist(value: str) -> int:
    return pd.Timestamp(value, tz="Asia/Kolkata").value


def test_run_leadlag_replay_writes_outputs_and_markouts(tmp_path):
    ts0 = ns_ist("2026-06-10 09:15:00")
    ts1 = ns_ist("2026-06-10 09:15:00.000100")
    ts2 = ns_ist("2026-06-10 09:15:00.000200")
    ts3 = ns_ist("2026-06-10 09:15:00.000300")
    ts4 = ns_ist("2026-06-10 09:15:00.000400")
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
    leader_path = tmp_path / "leader.csv"
    laggard_path = tmp_path / "laggard.csv"
    out_dir = tmp_path / "leadlag_replay"
    leader.to_csv(leader_path, index=False)
    laggard.to_csv(laggard_path, index=False)

    replay = run_leadlag_replay(
        leader_path=leader_path,
        laggard_path=laggard_path,
        output_dir=out_dir,
        leader_tick=0.05,
        laggard_tick=0.05,
        delta=1.0,
        trigger_ticks=10.0,
        qty=75,
        flat_after_ns=200_000,
        markout_horizons_ns=[100_000],
    )

    assert replay.result.engine.orders_sent == 2
    assert replay.summary.iloc[0]["strategy"] == "lead_lag_taker"
    assert replay.summary.iloc[0]["market"] == "india_nse_index_derivatives"
    assert replay.summary.iloc[0]["fills"] == 2
    assert not replay.markouts.empty
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
    assert (out_dir / "markouts.csv").exists()
    assert (out_dir / "manifest.json").exists()
    summary = pd.read_csv(out_dir / "summary.csv")
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert summary.loc[0, "strategy"] == "lead_lag_taker"
    assert summary.loc[0, "market"] == "india_nse_index_derivatives"
    assert manifest["parameters"]["strategy"] == "lead_lag_taker"
    assert manifest["parameters"]["market"] == "india_nse_index_derivatives"
    assert bool(summary.loc[0, "terminal_liquidation_depth_constrained_enabled"])
    assert bool(summary.loc[0, "terminal_liquidation_complete"])
    assert int(summary.loc[0, "terminal_residual_position_qty"]) == 0
