import numpy as np
import pandas as pd

from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel, OrderType
from engine.multi_engine import (
    InstrumentConfig,
    MultiInstrumentEngine,
    MultiInstrumentStrategy,
    PortfolioLimits,
    VenueConfig,
)


class InterleaveStrategy(MultiInstrumentStrategy):
    def __init__(self):
        self.events = []
        self.sent = False

    def on_start(self, engine):
        pass

    def on_tick(self, engine, instrument_id, tick):
        self.events.append(("tick", instrument_id, tick["ts"]))
        if instrument_id == "A" and not self.sent:
            engine.send("A", +1, 75, tick["ask"] + 1.0, OrderType.IOC)
            self.sent = True

    def on_fill(self, engine, fill):
        self.events.append(("fill", fill.instrument_id, fill.ts_ns))

    def on_end(self, engine):
        pass


class LoggingStrategy(MultiInstrumentStrategy):
    def __init__(self):
        self.ticks = []

    def on_start(self, engine):
        pass

    def on_tick(self, engine, instrument_id, tick):
        self.ticks.append((instrument_id, tick["ts"], tick.get("market_ts")))

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class RiskProbeStrategy(MultiInstrumentStrategy):
    def __init__(self, qty):
        self.qty = qty
        self.oid = "not-sent"

    def on_start(self, engine):
        pass

    def on_tick(self, engine, instrument_id, tick):
        if self.oid == "not-sent":
            self.oid = engine.send(
                instrument_id,
                +1,
                self.qty,
                tick["ask"] + 1.0,
                OrderType.IOC,
            )

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


def frame(rows):
    return pd.DataFrame(
        rows,
        columns=["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"],
    )


def option_inst(symbol):
    return Instrument(symbol, Kind.OPT, lot_size=75, tick=0.05)


def free_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def venue(feed_us=0.0, order_us=0.0, skew_ns=0):
    return VenueConfig(
        "V",
        latency=LatencyModel(
            feed_us=feed_us,
            order_us=order_us,
            jitter_us=0.0,
            _rng=np.random.default_rng(1),
        ),
        clock_skew_ns=skew_ns,
    )


def test_global_clock_interleaves_other_instrument_before_fill():
    strategy = InterleaveStrategy()
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 75, 75, np.nan, 0),
                        (120_000, 100.20, 100.25, 75, 75, np.nan, 0),
                    ]
                ),
                costs=free_costs(),
            ),
            "B": InstrumentConfig(
                option_inst("B"),
                "BSE",
                frame([(60_000, 200.00, 200.10, 75, 75, np.nan, 0)]),
                costs=free_costs(),
            ),
        },
        venues={
            "NSE": VenueConfig("NSE", LatencyModel(0, 0, 0, np.random.default_rng(2))),
            "BSE": VenueConfig("BSE", LatencyModel(0, 0, 0, np.random.default_rng(3))),
        },
        strategy=strategy,
    )

    result = engine.run()

    assert result.fills.iloc[0]["instrument_id"] == "A"
    assert result.fills.iloc[0]["ts_ns"] == 120_000
    assert strategy.events[:3] == [
        ("tick", "A", 0),
        ("tick", "B", 60_000),
        ("fill", "A", 120_000),
    ]


def test_feed_callbacks_are_ordered_by_latency_adjusted_global_time_and_skew():
    strategy = LoggingStrategy()
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
                costs=free_costs(),
            ),
            "B": InstrumentConfig(
                option_inst("B"),
                "BSE",
                frame([(150_000, 200.00, 200.10, 75, 75, np.nan, 0)]),
                costs=free_costs(),
            ),
        },
        venues={
            "NSE": venue(feed_us=100, order_us=0, skew_ns=0),
            "BSE": venue(feed_us=0, order_us=0, skew_ns=-100_000),
        },
        strategy=strategy,
    )

    engine.run()

    assert strategy.ticks == [
        ("B", 50_000, 50_000),
        ("A", 100_000, 0),
    ]


def test_instrument_and_portfolio_risk_limits_reject_orders():
    too_large = RiskProbeStrategy(qty=150)
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
                costs=free_costs(),
                max_position_lots=1,
            )
        },
        venues={"NSE": venue()},
        strategy=too_large,
    )

    engine.run()

    assert too_large.oid is None
    assert engine.orders_sent == 0

    too_much_delta = RiskProbeStrategy(qty=75)
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
                costs=free_costs(),
                max_position_lots=10,
                delta_per_unit=1.0,
            )
        },
        venues={"NSE": venue()},
        strategy=too_much_delta,
        portfolio_limits=PortfolioLimits(max_abs_delta=50.0),
    )

    engine.run()

    assert too_much_delta.oid is None
    assert engine.orders_sent == 0
