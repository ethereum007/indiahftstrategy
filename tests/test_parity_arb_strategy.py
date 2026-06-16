import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiInstrumentEngine, VenueConfig
from strategies.parity_arb import ParityArbConfig, ParityArbTakerStrategy, ParityLegMap


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


def test_parity_arb_taker_routes_three_ioc_legs_and_tracks_fills():
    signals = pd.DataFrame(
        [
            {
                "ts": 0,
                "strike": 1000.0,
                "direction": "buy_synthetic_sell_future",
                "qty": 75,
            }
        ]
    )
    strategy = ParityArbTakerStrategy(
        signals,
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
        ParityArbConfig(max_signal_age_ns=1_000),
    )
    engine = MultiInstrumentEngine(
        instruments={
            "CALL1000": InstrumentConfig(
                Instrument("CALL1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 54.0, 55.0, 75, 75, np.nan, 0),
                        (100, 54.0, 55.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "PUT1000": InstrumentConfig(
                Instrument("PUT1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 60.0, 61.0, 75, 75, np.nan, 0),
                        (100, 60.0, 61.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "FUT": InstrumentConfig(
                Instrument("FUT", Kind.FUT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 1008.0, 1009.0, 75, 75, np.nan, 0),
                        (100, 1008.0, 1009.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )

    result = engine.run()

    assert engine.orders_sent == 3
    strategy_fills = result.fills.loc[result.fills["oid"].isin([1, 2, 3])]
    assert len(strategy_fills) == 3
    assert set(strategy_fills["instrument_id"]) == {"CALL1000", "PUT1000", "FUT"}
    assert engine.positions == {"CALL1000": 0, "PUT1000": 0, "FUT": 0}
    legging = strategy.legging_report()
    assert not bool(legging.iloc[0]["partial"])
    assert legging.iloc[0]["fill_count"] == 3


def test_parity_arb_taker_resets_run_state_when_reused():
    strategy = ParityArbTakerStrategy(
        pd.DataFrame(
            [
                {
                    "ts": 0,
                    "strike": 1000.0,
                    "direction": "buy_synthetic_sell_future",
                    "qty": 75,
                }
            ]
        ),
        ParityLegMap(
            future_id="FUT",
            call_by_strike={1000.0: "CALL1000"},
            put_by_strike={1000.0: "PUT1000"},
        ),
        ParityArbConfig(max_signal_age_ns=1_000),
    )

    first = _parity_engine(strategy)
    first.run()
    assert len(strategy.executions) == 1
    assert len(strategy.order_to_execution) == 3

    second = _parity_engine(strategy)
    second.run()
    assert len(strategy.executions) == 1
    assert len(strategy.order_to_execution) == 3
    assert strategy.legging_report().iloc[0]["fill_count"] == 3


def _parity_engine(strategy):
    return MultiInstrumentEngine(
        instruments={
            "CALL1000": InstrumentConfig(
                Instrument("CALL1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 54.0, 55.0, 75, 75, np.nan, 0),
                        (100, 54.0, 55.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "PUT1000": InstrumentConfig(
                Instrument("PUT1000", Kind.OPT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 60.0, 61.0, 75, 75, np.nan, 0),
                        (100, 60.0, 61.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
            "FUT": InstrumentConfig(
                Instrument("FUT", Kind.FUT, lot_size=75, tick=0.05),
                "NSE",
                book(
                    [
                        (0, 1008.0, 1009.0, 75, 75, np.nan, 0),
                        (100, 1008.0, 1009.0, 75, 75, np.nan, 0),
                    ]
                ),
                costs=no_costs(),
            ),
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )
