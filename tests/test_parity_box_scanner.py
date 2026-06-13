import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind
from scanners.parity_box import (
    ScannerCosts,
    ScannerInstruments,
    opportunity_report,
    scan_boxes,
    scan_parity,
)


def no_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def instruments():
    return ScannerInstruments(
        option=Instrument("NIFTY-OPT", Kind.OPT, lot_size=75, tick=0.05),
        future=Instrument("NIFTY-FUT", Kind.FUT, lot_size=75, tick=0.05),
    )


def costs():
    return ScannerCosts(option=no_costs(), future=no_costs())


def parity_chain():
    rows = []
    for ts in [100, 200, 300]:
        rows.append(
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
                "regime": "post_stt_hike",
            }
        )
    return pd.DataFrame(rows)


def test_scan_parity_finds_touchable_dislocation_and_persistence():
    futures = pd.DataFrame(
        {
            "ts": [100, 200, 300],
            "bid": [1002.0, 1001.0, 994.0],
            "ask": [1003.0, 1002.0, 995.0],
            "bid_qty": [300, 300, 300],
            "ask_qty": [300, 300, 300],
        }
    )

    opps = scan_parity(
        parity_chain(),
        futures,
        instruments=instruments(),
        costs=costs(),
        asof_latency_ns=0,
        depth_fraction=0.25,
    )

    assert list(opps["ts"]) == [100, 200]
    assert list(opps["direction"]) == ["buy_synthetic_sell_future"] * 2
    assert list(opps["qty"]) == [75, 75]
    assert list(opps["edge_per_unit"]) == [7.0, 6.0]
    assert list(opps["net_edge"]) == [525.0, 450.0]
    assert list(opps["persistence_ticks"]) == [1, 0]
    assert list(opps["call_side"]) == [1, 1]
    assert list(opps["put_side"]) == [-1, -1]
    assert list(opps["future_side"]) == [-1, -1]
    assert list(opps["call_price"]) == [55.0, 55.0]
    assert list(opps["put_price"]) == [60.0, 60.0]
    assert list(opps["future_price"]) == [1002.0, 1001.0]


def test_scan_parity_asof_latency_prevents_future_lookahead():
    futures = pd.DataFrame(
        {
            "ts": [100],
            "bid": [1002.0],
            "ask": [1003.0],
            "bid_qty": [300],
            "ask_qty": [300],
        }
    )
    chain = parity_chain().iloc[[1]].copy()

    stale = scan_parity(
        chain,
        futures,
        instruments=instruments(),
        costs=costs(),
        asof_latency_ns=150,
        depth_fraction=0.25,
    )
    tradable = scan_parity(
        chain,
        futures,
        instruments=instruments(),
        costs=costs(),
        asof_latency_ns=0,
        depth_fraction=0.25,
    )

    assert stale.empty
    assert not tradable.empty


def box_chain():
    rows = []
    for ts, high_call_bid in [(100, 45.0), (200, 43.0)]:
        rows.extend(
            [
                {
                    "ts": ts,
                    "expiry": "2026-06-30",
                    "strike": 1000.0,
                    "call_bid": 51.0,
                    "call_ask": 52.0,
                    "call_bid_qty": 300,
                    "call_ask_qty": 300,
                    "put_bid": 45.0,
                    "put_ask": 46.0,
                    "put_bid_qty": 300,
                    "put_ask_qty": 300,
                    "regime": "post_stt_hike",
                },
                {
                    "ts": ts,
                    "expiry": "2026-06-30",
                    "strike": 1010.0,
                    "call_bid": high_call_bid,
                    "call_ask": high_call_bid + 1.0,
                    "call_bid_qty": 300,
                    "call_ask_qty": 300,
                    "put_bid": 45.0,
                    "put_ask": 46.0,
                    "put_bid_qty": 300,
                    "put_ask_qty": 300,
                    "regime": "post_stt_hike",
                },
            ]
        )
    return pd.DataFrame(rows)


def test_scan_boxes_finds_planted_box_and_reports_summary():
    opps = scan_boxes(
        box_chain(),
        option_instrument=instruments().option,
        option_costs=no_costs(),
        depth_fraction=0.25,
    )

    assert len(opps) == 1
    row = opps.iloc[0]
    assert row["direction"] == "buy_box"
    assert row["low_strike"] == 1000.0
    assert row["high_strike"] == 1010.0
    assert row["qty"] == 75
    assert row["edge_per_unit"] == 2.0
    assert row["net_edge"] == 150.0
    assert row["persistence_ticks"] == 0
    assert row["low_call_side"] == 1
    assert row["low_put_side"] == -1
    assert row["high_call_side"] == -1
    assert row["high_put_side"] == 1
    assert row["low_call_price"] == 52.0
    assert row["low_put_price"] == 45.0
    assert row["high_call_price"] == 45.0
    assert row["high_put_price"] == 46.0

    report = opportunity_report(opps)
    assert report.iloc[0]["regime"] == "post_stt_hike"
    assert report.iloc[0]["count"] == 1
    assert report.iloc[0]["net_edge_sum"] == 150.0
