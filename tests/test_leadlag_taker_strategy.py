import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiInstrumentEngine, VenueConfig
from strategies.leadlag_taker import LeadLagTakerConfig, LeadLagTakerStrategy


def no_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def book(rows):
    return pd.DataFrame(
        rows,
        columns=["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"],
    )


def venue():
    return VenueConfig(
        "NSE",
        LatencyModel(feed_us=0, order_us=0, jitter_us=0, _rng=np.random.default_rng(1)),
    )


def test_leadlag_taker_enters_on_leader_jump_and_flattens_after_hold():
    strategy = LeadLagTakerStrategy(
        LeadLagTakerConfig(
            leader_id="FUT",
            laggard_id="CALL",
            qty=75,
            delta=1.0,
            leader_tick=0.05,
            laggard_tick=0.05,
            trigger_ticks=10.0,
            flat_after_ns=200,
        )
    )
    engine = MultiInstrumentEngine(
        instruments={
            "FUT": InstrumentConfig(
                Instrument("FUT", Kind.FUT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 100.00, 100.10, 75, 75, np.nan, 0),
                        (100, 101.00, 101.10, 75, 75, np.nan, 0),
                        (300, 101.00, 101.10, 75, 75, np.nan, 0),
                        (400, 101.00, 101.10, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "CALL": InstrumentConfig(
                Instrument("CALL", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 50.00, 50.05, 75, 75, np.nan, 0),
                        (100, 50.00, 50.05, 75, 75, np.nan, 0),
                        (200, 50.00, 50.05, 75, 75, np.nan, 0),
                        (300, 50.50, 50.55, 75, 75, np.nan, 0),
                        (400, 50.50, 50.55, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )

    result = engine.run()

    assert engine.orders_sent == 2
    assert len(strategy.entry_orders) == 1
    assert len(strategy.exit_orders) == 1
    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.entry_orders + strategy.exit_orders)]
    assert list(strategy_fills["side"]) == [1, -1]
    assert list(strategy_fills["price"]) == [50.05, 50.50]
    assert engine.positions["CALL"] == 0
