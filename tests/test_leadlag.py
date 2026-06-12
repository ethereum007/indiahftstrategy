import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind
from research.leadlag import (
    cross_correlation,
    event_lag_profile,
    latency_viability_curve,
    summarize_pair,
)
from research.run_leadlag import run_leadlag


def no_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def book_from_mid(ts, mid, spread=1.0, qty=300):
    return pd.DataFrame(
        {
            "ts": ts,
            "bid": np.array(mid) - spread / 2,
            "ask": np.array(mid) + spread / 2,
            "bid_qty": [qty] * len(ts),
            "ask_qty": [qty] * len(ts),
        }
    )


def test_cross_correlation_recovers_planted_lag():
    ts = np.arange(80) * 100
    leader_moves = np.tile([1.0, -0.5, 1.5, -1.0], 20)
    leader_mid = 100 + np.cumsum(leader_moves)
    laggard_mid = 50 + np.concatenate([np.zeros(2), np.cumsum(leader_moves[:-2])])
    leader = book_from_mid(ts, leader_mid, spread=0.1)
    laggard = book_from_mid(ts, laggard_mid, spread=0.1)

    corr = cross_correlation(leader, laggard, lags_ns=[0, 100, 200, 300], tolerance_ns=0)

    best = corr.sort_values("correlation", ascending=False).iloc[0]
    assert best["lag_ns"] == 200
    assert best["correlation"] > 0.95


def test_event_lag_profile_measures_time_until_laggard_quote_update():
    leader = book_from_mid([0, 100, 200, 300], [100.0, 110.0, 110.0, 110.0])
    laggard = book_from_mid([0, 100, 200, 300], [50.0, 50.0, 50.0, 60.0])

    profile = event_lag_profile(
        leader,
        laggard,
        leader_tick_size=1.0,
        innovation_ticks=5.0,
        max_lag_ns=500,
    )

    assert len(profile) == 1
    assert profile.iloc[0]["event_ts"] == 100
    assert profile.iloc[0]["time_to_update_ns"] == 200
    assert profile.iloc[0]["updated_within_window"]
    assert profile.iloc[0]["cdf"] == 1.0


def test_latency_viability_curve_dies_after_stale_quote_updates():
    leader = book_from_mid([0, 100, 200, 300], [100.0, 110.0, 110.0, 110.0])
    laggard = book_from_mid([0, 100, 200, 300], [50.0, 50.0, 50.0, 60.0])
    inst = Instrument("NIFTY-ATM-CE", Kind.OPT, lot_size=75, tick=0.05)

    curve = latency_viability_curve(
        leader,
        laggard,
        leader_tick_size=1.0,
        laggard_tick_size=0.05,
        instrument=inst,
        costs=no_costs(),
        delta=1.0,
        innovation_ticks=5.0,
        latency_sweep_ns=[50, 150, 250],
        depth_fraction=0.25,
    )

    assert list(curve["fills"]) == [1, 1, 0]
    assert list(curve["net_pnl"]) == [750.0, 750.0, 0.0]


def test_summarize_pair_returns_all_three_outputs():
    leader = book_from_mid([0, 100, 200, 300], [100.0, 110.0, 110.0, 110.0])
    laggard = book_from_mid([0, 100, 200, 300], [50.0, 50.0, 50.0, 60.0])
    inst = Instrument("NIFTY-ATM-CE", Kind.OPT, lot_size=75, tick=0.05)

    summary = summarize_pair(
        leader,
        laggard,
        leader_tick_size=1.0,
        laggard_tick_size=0.05,
        laggard_instrument=inst,
        laggard_costs=no_costs(),
        delta=1.0,
        innovation_ticks=5.0,
        lags_ns=[0, 100, 200],
        latency_sweep_ns=[50, 250],
        max_lag_ns=500,
    )

    assert not summary.cross_correlation.empty
    assert not summary.lag_profile.empty
    assert not summary.latency_curve.empty


def test_run_leadlag_writes_report_files(tmp_path):
    leader = book_from_mid([0, 100, 200, 300], [100.0, 110.0, 110.0, 110.0])
    laggard = book_from_mid([0, 100, 200, 300], [50.0, 50.0, 50.0, 60.0])
    leader_path = tmp_path / "leader.csv"
    laggard_path = tmp_path / "laggard.csv"
    out_dir = tmp_path / "leadlag"
    leader.to_csv(leader_path, index=False)
    laggard.to_csv(laggard_path, index=False)

    result = run_leadlag(
        leader_path=leader_path,
        laggard_path=laggard_path,
        output_dir=out_dir,
        leader_tick_size=1.0,
        laggard_tick_size=0.05,
        delta=1.0,
        innovation_ticks=5.0,
        lags_ns=[0, 100, 200],
        latency_sweep_ns=[50, 250],
        max_lag_ns=500,
        depth_fraction=0.25,
        timestamp_unit="ns",
        filter_session=False,
        correlation_tolerance_ns=0,
    )

    assert not result.summary.latency_curve.empty
    assert (out_dir / "cross_correlation.csv").exists()
    assert (out_dir / "lag_profile.csv").exists()
    assert (out_dir / "latency_curve.csv").exists()
