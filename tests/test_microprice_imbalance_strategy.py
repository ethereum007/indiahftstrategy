import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiInstrumentEngine, VenueConfig
from strategies.microprice_imbalance import MicropriceImbalanceConfig, MicropriceImbalanceStrategy


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


def test_microprice_imbalance_resets_run_state_when_reused():
    strategy = MicropriceImbalanceStrategy(
        MicropriceImbalanceConfig(
            instrument_id="NIFTY",
            qty=75,
            tick_size=0.05,
            entry_imbalance=0.6,
            exit_imbalance=0.15,
            min_microprice_edge_ticks=0.25,
            hold_ns=1_000_000,
            cooloff_ns=1_000_000,
        )
    )

    first = _imbalance_engine(strategy)
    first.run()
    assert strategy.entry_orders == [1]
    assert strategy.exit_orders == [2]
    assert len(strategy.fills) == 2
    assert len(strategy.signals) == 2

    second = _imbalance_engine(strategy)
    second.run()
    assert strategy.entry_orders == [1]
    assert strategy.exit_orders == [2]
    assert len(strategy.fills) == 2
    assert len(strategy.signals) == 2


def _imbalance_engine(strategy):
    return MultiInstrumentEngine(
        instruments={
            "NIFTY": InstrumentConfig(
                Instrument("NIFTY", Kind.FUT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 100.00, 100.05, 900, 100, np.nan, 0),
                        (100, 100.00, 100.05, 900, 100, np.nan, 0),
                        (200, 100.30, 100.35, 100, 900, np.nan, 0),
                        (300, 100.30, 100.35, 100, 900, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )
