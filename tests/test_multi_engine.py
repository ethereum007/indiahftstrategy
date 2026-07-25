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
from reports.replay import replay_summary


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


class BurstRiskStrategy(MultiInstrumentStrategy):
    def __init__(self, orders_by_instrument):
        self.orders_by_instrument = orders_by_instrument
        self.oids = []
        self.sent_instruments = set()

    def on_start(self, engine):
        pass

    def on_tick(self, engine, instrument_id, tick):
        if instrument_id in self.sent_instruments:
            return
        for side, qty, price, order_type in self.orders_by_instrument.get(
            instrument_id,
            [],
        ):
            self.oids.append(
                engine.send(
                    instrument_id,
                    side,
                    qty,
                    price,
                    order_type,
                )
            )
        self.sent_instruments.add(instrument_id)

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class EnterThenReduceStrategy(MultiInstrumentStrategy):
    def __init__(self):
        self.stage = 0

    def on_start(self, engine):
        pass

    def on_tick(self, engine, instrument_id, tick):
        if instrument_id != "A":
            return
        if self.stage == 0:
            engine.send(
                instrument_id,
                +1,
                75,
                tick["ask"] + 1.0,
                OrderType.IOC,
            )
            self.stage = 1
        elif self.stage == 1:
            engine.send(
                instrument_id,
                -1,
                25,
                tick["bid"] - 1.0,
                OrderType.IOC,
            )
            self.stage = 2

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


def test_multi_engine_orders_share_instrument_event_liquidity():
    strategy = BurstRiskStrategy(
        {
            "A": [
                (+1, 75, 101.00, OrderType.IOC),
                (+1, 75, 101.00, OrderType.IOC),
            ]
        }
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 300, 300, np.nan, 0),
                        (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [75, 25]
    assert int(strategy_fills["qty"].sum()) == 100
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["instrument_id"] == "A"
    assert shortfall["oid"] == strategy.oids[1]
    assert shortfall["available_qty"] == 25
    assert shortfall["shortfall_qty"] == 50
    assert shortfall["liquidity_source"] == "ask_display"


def test_multi_engine_carries_depletion_until_size_replenishes():
    strategy = BurstRiskStrategy(
        {"A": [(+1, 150, 101.00, OrderType.LIMIT)]}
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 300, 100, np.nan, 0),
                        (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
                        (2_000, 100.00, 100.05, 300, 100, np.nan, 0),
                        (3_000, 100.00, 100.05, 300, 150, np.nan, 0),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 3_000]
    assert result.liquidity_shortfalls["carried_depletion_qty"].tolist() == [
        0,
        100,
    ]
    summary = replay_summary(result).iloc[0]
    assert bool(summary["persistent_displayed_liquidity_enabled"])
    assert int(summary["liquidity_shortfall_events"]) == 2
    assert int(summary["liquidity_shortfall_qty"]) == 100
    assert int(summary["carried_depletion_shortfall_events"]) == 1
    assert int(summary["carried_depletion_shortfall_qty"]) == 50
    assert bool(summary["arrival_queue_initialization_enabled"])
    assert int(summary["limit_orders_sent"]) == 1
    assert int(summary["queue_initialization_events"]) == 1
    assert int(summary["deferred_queue_initialization_events"]) == 0
    assert int(summary["uninitialized_limit_orders"]) == 0
    assert int(summary["max_queue_initialization_lag_ns"]) == 0


def test_multi_engine_marketable_residual_defers_until_resting_touch():
    strategy = BurstRiskStrategy(
        {"A": [(+1, 150, 100.05, OrderType.LIMIT)]}
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 300, 100, np.nan, 0),
                        (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
                        (2_000, 100.10, 100.15, 200, 100, np.nan, 0),
                        (3_000, 100.10, 100.15, 200, 100, 100.05, 1_000),
                        (4_000, 100.05, 100.10, 225, 100, np.nan, 0),
                        (5_000, 100.05, 100.10, 225, 100, 100.05, 225),
                        (6_000, 100.05, 100.10, 225, 100, 100.05, 50),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
        queue_conservatism=1.0,
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 6_000]
    assert strategy_fills["maker"].tolist() == [False, True]
    transition = result.resting_transitions.iloc[0]
    assert transition["instrument_id"] == "A"
    assert transition["ts_ns"] == 2_000
    assert transition["book_relation"] == "away_from_touch"
    assert bool(transition["deferred_at_transition"])
    assert transition["mode"] == "residual_first_touch_snapshot"
    assert bool(transition["queue_initialized"])
    assert transition["queue_initialization_ts_ns"] == 4_000
    assert transition["queue_initialization_lag_ns"] == 2_000
    assert transition["initialization_book_relation"] == "bid_touch"
    assert transition["observed_qty"] == 225
    assert transition["queue_ahead"] == 225
    summary = replay_summary(result).iloc[0]
    assert int(summary["residual_resting_transition_events"]) == 1
    assert int(summary["residual_resting_transition_qty"]) == 50
    assert int(summary["deferred_residual_queue_events"]) == 1
    assert int(summary["unresolved_residual_queue_events"]) == 0
    assert int(summary["max_residual_queue_initialization_lag_ns"]) == 2_000


def test_multi_engine_reports_residual_queue_unresolved_at_replay_end():
    strategy = BurstRiskStrategy(
        {"A": [(+1, 150, 100.05, OrderType.LIMIT)]}
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 300, 100, np.nan, 0),
                        (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
                        (2_000, 100.10, 100.15, 200, 100, np.nan, 0),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
        queue_conservatism=1.0,
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [100]
    transition = result.resting_transitions.iloc[0]
    assert transition["book_relation"] == "away_from_touch"
    assert bool(transition["deferred_at_transition"])
    assert transition["mode"] == "residual_queue_deferred"
    assert not bool(transition["queue_initialized"])
    assert pd.isna(transition["queue_initialization_ts_ns"])
    assert pd.isna(transition["queue_initialization_lag_ns"])
    summary = replay_summary(result).iloc[0]
    assert int(summary["residual_resting_transition_events"]) == 1
    assert int(summary["residual_resting_transition_qty"]) == 50
    assert int(summary["deferred_residual_queue_events"]) == 1
    assert int(summary["unresolved_residual_queue_events"]) == 1
    assert int(summary["max_residual_queue_initialization_lag_ns"]) == 0


def test_multi_engine_uses_arrival_snapshot_for_limit_queue():
    strategy = BurstRiskStrategy(
        {"A": [(+1, 75, 100.00, OrderType.LIMIT)]}
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 75, 75, np.nan, 0),
                        (200_000, 100.00, 100.05, 225, 75, np.nan, 0),
                        (300_000, 100.00, 100.05, 225, 75, 100.00, 225),
                        (400_000, 100.00, 100.05, 225, 75, 100.00, 75),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue(order_us=100)},
        strategy=strategy,
        queue_conservatism=1.0,
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["ts_ns"].tolist() == [400_000]
    initialization = result.queue_initializations.iloc[0]
    assert initialization["instrument_id"] == "A"
    assert initialization["mode"] == "arrival_snapshot"
    assert initialization["ts_ns"] == 200_000
    assert initialization["arrival_ts_ns"] == 200_000
    assert initialization["arrival_lag_ns"] == 100_000
    assert initialization["arrival_book_relation"] == "bid_touch"
    assert initialization["initialization_lag_ns"] == 100_000
    assert initialization["observed_qty"] == 225
    assert initialization["queue_ahead"] == 225
    summary = replay_summary(result).iloc[0]
    assert int(summary["deferred_queue_initialization_events"]) == 1
    assert int(summary["max_queue_initialization_lag_ns"]) == 100_000


def test_multi_engine_defers_away_limit_queue_until_first_touch():
    strategy = BurstRiskStrategy(
        {"A": [(+1, 75, 99.95, OrderType.LIMIT)]}
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 150, 75, np.nan, 0),
                        (1_000, 100.00, 100.05, 150, 75, 99.95, 1_000),
                        (2_000, 99.95, 100.00, 225, 75, np.nan, 0),
                        (3_000, 99.95, 100.00, 225, 75, 99.95, 225),
                        (4_000, 99.95, 100.00, 225, 75, 99.95, 75),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
        queue_conservatism=1.0,
    )

    result = engine.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["ts_ns"].tolist() == [4_000]
    assert strategy_fills["maker"].tolist() == [True]
    initialization = result.queue_initializations.iloc[0]
    assert initialization["instrument_id"] == "A"
    assert initialization["mode"] == "first_touch_snapshot"
    assert initialization["arrival_ts_ns"] == 0
    assert initialization["arrival_lag_ns"] == 0
    assert initialization["arrival_book_relation"] == "away_from_touch"
    assert initialization["ts_ns"] == 2_000
    assert initialization["initialization_lag_ns"] == 2_000
    assert initialization["book_relation"] == "bid_touch"
    assert initialization["observed_qty"] == 225
    assert initialization["queue_ahead"] == 225
    summary = replay_summary(result).iloc[0]
    assert int(summary["deferred_queue_initialization_events"]) == 1
    assert int(summary["uninitialized_limit_orders"]) == 0
    assert int(summary["max_queue_initialization_lag_ns"]) == 2_000


def test_terminal_liquidation_reuses_no_depth_consumed_on_final_snapshot():
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame(
                    [
                        (0, 100.00, 100.05, 75, 75, np.nan, 0),
                        (1_000, 100.10, 100.15, 75, 75, np.nan, 0),
                        (2_000, 100.20, 100.25, 50, 75, np.nan, 0),
                    ]
                ),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=EnterThenReduceStrategy(),
        persist_displayed_liquidity_depletion=False,
    )

    result = engine.run()

    assert result.fills["qty"].tolist() == [75, 25, 25]
    assert result.fills["side"].tolist() == [1, -1, -1]
    assert engine.positions["A"] == 25
    liquidation = result.terminal_liquidations.iloc[0]
    assert liquidation["book_ts_ns"] == 2_000
    assert liquidation["liquidity_source"] == "terminal_bid_display"
    assert liquidation["requested_qty"] == 50
    assert liquidation["available_qty"] == 25
    assert liquidation["filled_qty"] == 25
    assert liquidation["shortfall_qty"] == 25
    assert liquidation["residual_position"] == 25
    assert liquidation["observed_qty"] == 50
    assert liquidation["carried_depletion_qty"] == 0
    assert not bool(liquidation["complete"])
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["liquidity_source"] == "terminal_bid_display"
    assert shortfall["carried_depletion_qty"] == 0
    summary = replay_summary(result).iloc[0]
    assert bool(summary["terminal_liquidation_depth_constrained_enabled"])
    assert int(summary["terminal_liquidation_events"]) == 1
    assert int(summary["terminal_liquidation_requested_qty"]) == 50
    assert int(summary["terminal_liquidation_filled_qty"]) == 25
    assert int(summary["terminal_liquidation_shortfall_qty"]) == 25
    assert int(summary["terminal_liquidation_incomplete_events"]) == 1
    assert int(summary["terminal_residual_position_qty"]) == 25
    assert int(summary["terminal_residual_instruments"]) == 1
    assert not bool(summary["terminal_liquidation_complete"])
    assert int(summary["displayed_liquidity_shortfall_events"]) == 1
    assert int(summary["carried_depletion_shortfall_events"]) == 0


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


def test_pending_orders_are_reserved_against_instrument_position_limit():
    strategy = BurstRiskStrategy(
        {
            "A": [
                (+1, 75, 100.00, OrderType.LIMIT),
                (+1, 75, 100.00, OrderType.LIMIT),
            ]
        }
    )
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
        strategy=strategy,
    )

    result = engine.run()

    assert strategy.oids == [1, None]
    assert engine.orders_sent == 1
    rejection = result.order_rejections.iloc[0]
    assert rejection["reason"] == "instrument_position_limit"
    assert rejection["projected_min"] == 0
    assert rejection["projected_max"] == 150
    assert rejection["limit"] == 75


def test_pending_orders_are_reserved_against_portfolio_delta_limit():
    strategy = BurstRiskStrategy(
        {
            "A": [(+1, 75, 100.00, OrderType.LIMIT)],
            "B": [(+1, 75, 200.00, OrderType.LIMIT)],
        }
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
                costs=free_costs(),
                max_position_lots=10,
                delta_per_unit=1.0,
            ),
            "B": InstrumentConfig(
                option_inst("B"),
                "NSE",
                frame([(0, 200.00, 200.05, 75, 75, np.nan, 0)]),
                costs=free_costs(),
                max_position_lots=10,
                delta_per_unit=1.0,
            ),
        },
        venues={"NSE": venue()},
        strategy=strategy,
        portfolio_limits=PortfolioLimits(max_abs_delta=100.0),
    )

    result = engine.run()

    assert strategy.oids == [1, None]
    rejection = result.order_rejections.iloc[0]
    assert rejection["instrument_id"] == "B"
    assert rejection["reason"] == "portfolio_delta_limit"
    assert rejection["projected_min"] == 0
    assert rejection["projected_max"] == 150
    assert rejection["limit"] == 100


def test_multi_engine_rejects_crossing_own_resting_order():
    strategy = BurstRiskStrategy(
        {
            "A": [
                (-1, 75, 100.05, OrderType.LIMIT),
                (+1, 75, 100.05, OrderType.LIMIT),
            ]
        }
    )
    engine = MultiInstrumentEngine(
        instruments={
            "A": InstrumentConfig(
                option_inst("A"),
                "NSE",
                frame([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
                costs=free_costs(),
            )
        },
        venues={"NSE": venue()},
        strategy=strategy,
    )

    result = engine.run()

    assert strategy.oids == [1, None]
    rejection = result.order_rejections.iloc[0]
    assert rejection["reason"] == "aggressive_self_cross"
    assert rejection["conflicting_oid"] == 1
