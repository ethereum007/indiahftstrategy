import math

import numpy as np
import pandas as pd
import pytest

from engine.hft_backtest import (
    BacktestEngine,
    IndianCostModel,
    Instrument,
    Kind,
    LatencyModel,
    OrderType,
    Strategy,
)


class SendOnce(Strategy):
    def __init__(self, side, qty, price, otype=OrderType.IOC):
        self.side = side
        self.qty = qty
        self.price = price
        self.otype = otype
        self.sent = False

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if not self.sent:
            engine.send(self.side, self.qty, self.price, self.otype)
            self.sent = True

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class CancelAfterSend(Strategy):
    def __init__(self, qty, price):
        self.qty = qty
        self.price = price
        self.oid = None

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if self.oid is None:
            self.oid = engine.send(+1, self.qty, self.price, OrderType.LIMIT)
        elif self.oid in engine.open_orders:
            engine.cancel(self.oid)

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class CancelThenProbeRisk(Strategy):
    def __init__(self, qty, price):
        self.qty = qty
        self.price = price
        self.stage = 0
        self.first_oid = None
        self.second_oid = None

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if self.stage == 0:
            self.first_oid = engine.send(
                +1,
                self.qty,
                self.price,
                OrderType.LIMIT,
            )
        elif self.stage == 1:
            engine.cancel(self.first_oid)
            engine.cancel(self.first_oid)
        elif self.stage == 2:
            self.second_oid = engine.send(
                +1,
                self.qty,
                self.price,
                OrderType.LIMIT,
            )
        self.stage += 1

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class CancelPartialIocOnFill(Strategy):
    def __init__(self):
        self.sent = False

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if self.sent:
            return
        engine.send(+1, 150, 101.00, OrderType.IOC)
        self.sent = True

    def on_fill(self, engine, fill):
        engine.cancel(fill.oid)

    def on_end(self, engine):
        pass


class BuyAndHold(Strategy):
    def __init__(self, qty):
        self.qty = qty
        self.sent = False

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if not self.sent:
            engine.send(+1, self.qty, tick["ask"] + 1.0, OrderType.IOC)
            self.sent = True

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class SendBurst(Strategy):
    def __init__(self, orders):
        self.orders = orders
        self.oids = []
        self.sent = False

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if self.sent:
            return
        self.oids = [
            engine.send(side, qty, price, order_type)
            for side, qty, price, order_type in self.orders
        ]
        self.sent = True

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class CancelFirstOfPair(Strategy):
    def __init__(self, price):
        self.price = price
        self.oids = []
        self.cancelled = False

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if not self.oids:
            self.oids = [
                engine.send(+1, 75, self.price, OrderType.LIMIT),
                engine.send(+1, 75, self.price, OrderType.LIMIT),
            ]
        elif not self.cancelled:
            engine.cancel(self.oids[0])
            self.cancelled = True

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


class CancelThenReplace(Strategy):
    def __init__(self, price):
        self.price = price
        self.first_oid = None
        self.replacement_oid = None

    def on_start(self, engine):
        pass

    def on_tick(self, engine, tick):
        if self.first_oid is None:
            self.first_oid = engine.send(
                +1,
                75,
                self.price,
                OrderType.LIMIT,
            )
        elif self.replacement_oid is None:
            engine.cancel(self.first_oid)
            self.replacement_oid = engine.send(
                +1,
                75,
                self.price,
                OrderType.LIMIT,
            )

    def on_fill(self, engine, fill):
        pass

    def on_end(self, engine):
        pass


def inst(kind=Kind.OPT, *, lot_size=75):
    return Instrument("NIFTY-TEST", kind, lot_size=lot_size, tick=0.05)


def no_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def fixed_latency(feed_us=0.0, order_us=0.0):
    return LatencyModel(feed_us=feed_us, order_us=order_us, jitter_us=0.0)


class SequencedLatency:
    def __init__(self, order_delays_ns, feed_delay_ns=0):
        self.order_delays_ns = iter(order_delays_ns)
        self.feed_delay = int(feed_delay_ns)

    def feed_delay_ns(self):
        return self.feed_delay

    def order_delay_ns(self):
        return int(next(self.order_delays_ns))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"feed_us": -1},
        {"order_us": float("nan")},
        {"jitter_us": -1},
    ],
)
def test_latency_model_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        LatencyModel(**kwargs)


def test_latency_model_clamps_negative_jitter_samples_to_zero():
    class MinimumRng:
        @staticmethod
        def uniform(low, high):
            return low

    latency = LatencyModel(
        feed_us=0,
        order_us=0,
        jitter_us=10,
        _rng=MinimumRng(),
    )

    assert latency.feed_delay_ns() == 0
    assert latency.order_delay_ns() == 0


@pytest.mark.parametrize(
    ("order_type", "order_us", "price", "expected_state", "active"),
    [
        (OrderType.IOC, 0.0, 101.00, "active_ioc", True),
        (OrderType.IOC, 100.0, 101.00, "pending_activation", False),
        (OrderType.LIMIT, 0.0, 100.00, "active_limit", True),
    ],
)
def test_live_orders_at_replay_horizon_are_classified(
    order_type,
    order_us,
    price,
    expected_state,
    active,
):
    strategy = SendOnce(+1, 75, price, order_type)
    engine = BacktestEngine(
        ticks([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
        inst(),
        strategy,
        latency=fixed_latency(order_us=order_us),
        costs=no_costs(),
    )

    result = engine.run()

    assert len(result.order_horizon_states) == 1
    horizon_state = result.order_horizon_states.iloc[0]
    assert horizon_state["instrument_id"] == "NIFTY-TEST"
    assert horizon_state["order_type"] == order_type.value
    assert horizon_state["qty"] == 75
    assert horizon_state["filled_qty"] == 0
    assert horizon_state["remaining_qty"] == 75
    assert bool(horizon_state["active_at_horizon"]) is active
    assert not bool(horizon_state["cancel_pending"])
    assert horizon_state["state"] == expected_state


def ticks(rows):
    return pd.DataFrame(
        rows,
        columns=["ts", "bid", "ask", "bid_qty", "ask_qty", "last", "last_qty"],
    )


def test_ioc_fill_uses_arrival_time_book_not_decision_time():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (200_000, 100.20, 100.25, 75, 75, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 75, 100.30, OrderType.IOC)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(feed_us=0, order_us=150),
        costs=no_costs(),
    )

    res = eng.run()

    assert res.fills.iloc[0]["ts_ns"] == 200_000
    assert res.fills.iloc[0]["price"] == 100.25


def test_ioc_orders_share_displayed_liquidity_and_audit_shortfall():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 300, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
        ]
    )
    strategy = SendBurst(
        [
            (+1, 75, 101.00, OrderType.IOC),
            (+1, 75, 101.00, OrderType.IOC),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [75]
    assert int(strategy_fills["qty"].sum()) == 75
    assert len(result.liquidity_shortfalls) == 1
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["oid"] == strategy.oids[1]
    assert shortfall["requested_qty"] == 75
    assert shortfall["available_qty"] == 25
    assert shortfall["filled_qty"] == 0
    assert shortfall["shortfall_qty"] == 75
    assert shortfall["liquidity_source"] == "ask_display"


def test_marketable_limit_waits_for_observed_depth_replenishment():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (2_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (3_000, 100.00, 100.05, 300, 150, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 150, 101.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 3_000]
    assert result.liquidity_shortfalls["available_qty"].tolist() == [100, 0]
    assert result.liquidity_shortfalls["observed_qty"].tolist() == [100, 100]
    assert result.liquidity_shortfalls["carried_depletion_qty"].tolist() == [
        0,
        100,
    ]


def test_marketable_limit_waits_until_replenishment_completes_a_market_lot():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (2_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (3_000, 100.00, 100.05, 300, 150, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 150, 101.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [75, 75]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 3_000]
    assert result.liquidity_shortfalls["available_qty"].tolist() == [100, 25]
    assert result.liquidity_shortfalls["filled_qty"].tolist() == [75, 0]
    assert result.liquidity_shortfalls["carried_depletion_qty"].tolist() == [
        0,
        75,
    ]


def test_marketable_limit_residual_joins_visible_resting_queue():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (2_000, 100.05, 100.10, 200, 100, np.nan, 0),
            (3_000, 100.05, 100.10, 200, 100, 100.05, 200),
            (4_000, 100.05, 100.10, 200, 100, 100.05, 50),
        ]
    )
    strategy = SendOnce(+1, 150, 100.05, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 4_000]
    assert strategy_fills["maker"].tolist() == [False, True]
    transition = result.resting_transitions.iloc[0]
    assert transition["ts_ns"] == 2_000
    assert transition["transition_lag_ns"] == 2_000
    assert transition["filled_qty"] == 100
    assert transition["remaining_qty"] == 50
    assert transition["book_relation"] == "bid_touch"
    assert not bool(transition["deferred_at_transition"])
    assert transition["mode"] == "residual_resting_snapshot"
    assert bool(transition["queue_initialized"])
    assert transition["queue_initialization_ts_ns"] == 2_000
    assert transition["queue_initialization_lag_ns"] == 0
    assert transition["initialization_book_relation"] == "bid_touch"
    assert transition["observed_qty"] == 200
    assert transition["public_queue_ahead"] == 200
    assert transition["queue_ahead"] == 200


def test_off_touch_marketable_residual_defers_queue_and_ignores_stale_print():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (2_000, 100.10, 100.15, 200, 100, np.nan, 0),
            (3_000, 100.10, 100.15, 200, 100, 100.05, 1_000),
            (4_000, 100.05, 100.10, 225, 100, np.nan, 0),
            (5_000, 100.05, 100.10, 225, 100, 100.05, 225),
            (6_000, 100.05, 100.10, 225, 100, 100.05, 50),
        ]
    )
    strategy = SendOnce(+1, 150, 100.05, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 6_000]
    assert strategy_fills["maker"].tolist() == [False, True]
    transition = result.resting_transitions.iloc[0]
    assert transition["ts_ns"] == 2_000
    assert transition["book_relation"] == "away_from_touch"
    assert bool(transition["deferred_at_transition"])
    assert transition["mode"] == "residual_first_touch_snapshot"
    assert bool(transition["queue_initialized"])
    assert transition["queue_initialization_ts_ns"] == 4_000
    assert transition["queue_initialization_lag_ns"] == 2_000
    assert transition["initialization_book_relation"] == "bid_touch"
    assert transition["observed_qty"] == 225
    assert transition["public_queue_ahead"] == 225
    assert transition["queue_ahead"] == 225


def test_price_change_resets_persistent_displayed_liquidity():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (2_000, 100.05, 100.10, 300, 100, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 150, 101.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 2_000]
    assert len(result.liquidity_shortfalls) == 1


def test_session_change_resets_persistent_displayed_liquidity():
    next_day = 86_400_000_000_000
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (next_day + 1_000, 100.00, 100.05, 300, 100, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 150, 101.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, next_day + 1_000]
    assert len(result.liquidity_shortfalls) == 1


def test_persistent_displayed_liquidity_can_be_disabled_for_sensitivity():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 100, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 100, np.nan, 0),
            (2_000, 100.00, 100.05, 300, 100, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 150, 101.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        persist_displayed_liquidity_depletion=False,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [100, 50]
    assert strategy_fills["ts_ns"].tolist() == [1_000, 2_000]
    assert not eng.persist_displayed_liquidity_depletion


def test_feed_latency_is_part_of_order_arrival_time():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (120_000, 100.10, 100.15, 75, 75, np.nan, 0),
            (220_000, 100.30, 100.35, 75, 75, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 75, 100.40, OrderType.IOC)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(feed_us=100, order_us=100),
        costs=no_costs(),
    )

    res = eng.run()

    assert res.fills.iloc[0]["ts_ns"] == 220_000
    assert res.fills.iloc[0]["price"] == 100.35


def test_delayed_feed_callback_observes_intervening_market_fill():
    class PositionObserver(Strategy):
        def __init__(self):
            self.sent = False
            self.positions = {}
            self.timeline = []

        def on_start(self, engine):
            pass

        def on_tick(self, engine, tick):
            market_ts = int(tick["market_ts"])
            self.positions[market_ts] = engine.position
            self.timeline.append(("tick", market_ts, int(tick["ts"])))
            if not self.sent:
                engine.send(+1, 75, 100.00, OrderType.LIMIT)
                self.sent = True

        def on_fill(self, engine, fill):
            self.timeline.append(("fill", int(fill.ts_ns), engine.position))

        def on_end(self, engine):
            pass

    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (200_000, 100.00, 100.05, 75, 75, np.nan, 0),
            (300_000, 100.00, 100.05, 75, 75, 100.00, 75),
        ]
    )
    strategy = PositionObserver()
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(feed_us=150, order_us=0),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    assert strategy.positions[200_000] == 75
    assert strategy.timeline[:3] == [
        ("tick", 0, 150_000),
        ("fill", 300_000, 75),
        ("tick", 200_000, 350_000),
    ]
    assert result.fills["ts_ns"].tolist() == [300_000, 450_000]


def test_limit_order_waits_for_queue_burn_before_fill():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 75, np.nan, 0),
            (1_000, 100.00, 100.05, 150, 75, 100.00, 75),
            (2_000, 100.00, 100.05, 150, 75, 100.00, 75),
            (3_000, 100.00, 100.05, 150, 75, 100.00, 75),
        ]
    )
    strategy = SendOnce(+1, 75, 100.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    res = eng.run()

    assert list(res.fills["ts_ns"])[:1] == [3_000]
    assert res.fills.iloc[0]["qty"] == 75
    initialization = res.queue_initializations.iloc[0]
    assert initialization["mode"] == "send_snapshot"
    assert initialization["ts_ns"] == 0
    assert initialization["arrival_ts_ns"] == 0
    assert initialization["arrival_lag_ns"] == 0
    assert initialization["arrival_book_relation"] == "bid_touch"
    assert initialization["initialization_lag_ns"] == 0
    assert initialization["observed_qty"] == 150


def test_delayed_limit_uses_arrival_snapshot_for_public_queue():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (200_000, 100.00, 100.05, 225, 75, np.nan, 0),
            (300_000, 100.00, 100.05, 225, 75, 100.00, 225),
            (400_000, 100.00, 100.05, 225, 75, 100.00, 75),
        ]
    )
    strategy = SendOnce(+1, 75, 100.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(order_us=100),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["ts_ns"].tolist() == [400_000]
    initialization = result.queue_initializations.iloc[0]
    assert initialization["mode"] == "arrival_snapshot"
    assert initialization["ts_ns"] == 200_000
    assert initialization["ts_active_ns"] == 100_000
    assert initialization["arrival_ts_ns"] == 200_000
    assert initialization["arrival_lag_ns"] == 100_000
    assert initialization["arrival_book_relation"] == "bid_touch"
    assert initialization["initialization_lag_ns"] == 100_000
    assert initialization["book_relation"] == "bid_touch"
    assert initialization["observed_qty"] == 225
    assert initialization["public_queue_ahead"] == 225
    assert initialization["own_queue_tail"] == 0
    assert initialization["queue_ahead"] == 225


def test_delayed_limit_that_moves_through_before_arrival_is_taker():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 75, np.nan, 0),
            (200_000, 99.90, 99.95, 150, 75, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 75, 100.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(order_us=100),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    fill = result.fills.loc[result.fills["side"] > 0].iloc[0]
    assert fill["ts_ns"] == 200_000
    assert fill["price"] == 99.95
    assert not bool(fill["maker"])
    initialization = result.queue_initializations.iloc[0]
    assert initialization["mode"] == "arrival_snapshot"
    assert initialization["arrival_book_relation"] == "marketable"
    assert initialization["book_relation"] == "marketable"
    assert initialization["observed_qty"] == 0
    assert initialization["queue_ahead"] == 0


def test_away_limit_defers_queue_until_first_observable_touch():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 75, np.nan, 0),
            (1_000, 100.00, 100.05, 150, 75, 99.95, 1_000),
            (2_000, 99.95, 100.00, 225, 75, np.nan, 0),
            (3_000, 99.95, 100.00, 225, 75, 99.95, 225),
            (4_000, 99.95, 100.00, 225, 75, 99.95, 75),
        ]
    )
    strategy = SendOnce(+1, 75, 99.95, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    fill = result.fills.loc[result.fills["side"] > 0].iloc[0]
    assert fill["ts_ns"] == 4_000
    assert fill["qty"] == 75
    assert bool(fill["maker"])
    initialization = result.queue_initializations.iloc[0]
    assert initialization["mode"] == "first_touch_snapshot"
    assert initialization["arrival_ts_ns"] == 0
    assert initialization["arrival_lag_ns"] == 0
    assert initialization["arrival_book_relation"] == "away_from_touch"
    assert initialization["ts_ns"] == 2_000
    assert initialization["initialization_lag_ns"] == 2_000
    assert initialization["book_relation"] == "bid_touch"
    assert initialization["observed_qty"] == 225
    assert initialization["public_queue_ahead"] == 225
    assert initialization["queue_ahead"] == 225


def test_zero_queue_resting_limit_keeps_maker_status_when_market_trades_through():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 75, np.nan, 0),
            (1_000, 99.90, 99.95, 150, 75, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 75, 100.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    fill = result.fills.loc[result.fills["side"] > 0].iloc[0]
    assert fill["ts_ns"] == 1_000
    assert fill["price"] == 100.00
    assert fill["qty"] == 75
    assert bool(fill["maker"])
    assert result.queue_initializations.iloc[0]["queue_ahead"] == 0


def test_deferred_orders_keep_earlier_order_queue_priority():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 300, np.nan, 0),
            (200_000, 100.00, 100.05, 300, 300, np.nan, 0),
            (300_000, 100.00, 100.05, 300, 300, 100.00, 100),
        ]
    )
    strategy = SendBurst(
        [
            (+1, 75, 100.00, OrderType.LIMIT),
            (+1, 75, 100.00, OrderType.LIMIT),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(order_us=100),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [75, 25]
    initialization = result.queue_initializations.set_index("oid")
    assert initialization.loc[strategy.oids[0], "own_queue_tail"] == 0
    assert initialization.loc[strategy.oids[1], "own_queue_tail"] == 75


def test_resting_orders_share_trade_print_volume_in_queue_priority():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 300, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 300, 100.00, 100),
        ]
    )
    strategy = SendBurst(
        [
            (+1, 75, 100.00, OrderType.LIMIT),
            (+1, 75, 100.00, OrderType.LIMIT),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["qty"].tolist() == [75, 25]
    assert int(strategy_fills["qty"].sum()) == 100
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["oid"] == strategy.oids[1]
    assert shortfall["queue_ahead_before"] == 75
    assert shortfall["queue_consumed"] == 75
    assert shortfall["available_qty"] == 25
    assert shortfall["shortfall_qty"] == 50
    assert shortfall["liquidity_source"] == "trade_print"


def test_trade_print_fill_waits_for_a_complete_market_lot():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (1_000, 100.00, 100.05, 75, 75, 100.00, 50),
            (2_000, 100.00, 100.05, 75, 75, 100.00, 75),
        ]
    )
    strategy = SendOnce(+1, 75, 100.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] > 0]
    assert strategy_fills["qty"].tolist() == [75]
    assert strategy_fills["ts_ns"].tolist() == [2_000]
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["liquidity_source"] == "trade_print"
    assert shortfall["available_qty"] == 50
    assert shortfall["filled_qty"] == 0
    assert shortfall["shortfall_qty"] == 75


def test_cancelled_own_order_releases_later_queue_position():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 300, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 300, np.nan, 0),
            (2_000, 100.00, 100.05, 300, 300, 100.00, 75),
        ]
    )
    strategy = CancelFirstOfPair(100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy.oids)]
    assert strategy_fills["oid"].tolist() == [strategy.oids[1]]
    assert strategy_fills["qty"].tolist() == [75]
    assert result.liquidity_shortfalls.empty


def test_cancelled_own_order_does_not_erase_public_queue_floor():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 300, np.nan, 0),
            (1_000, 100.00, 100.05, 300, 300, np.nan, 0),
            (2_000, 100.00, 100.05, 300, 300, 100.00, 75),
        ]
    )
    strategy = CancelFirstOfPair(100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    assert result.fills.empty
    assert eng.open_orders[strategy.oids[1]].queue_ahead == 225


def test_replacement_excluded_from_pending_cancel_queue_is_not_released_twice():
    df = ticks(
        [
            (0, 100.00, 100.05, 300, 300, np.nan, 0),
            (200_000, 100.00, 100.05, 300, 300, np.nan, 0),
            (300_000, 100.00, 100.05, 300, 300, 100.00, 75),
        ]
    )
    strategy = CancelThenReplace(100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(order_us=100),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    assert result.fills.empty
    assert eng.open_orders[strategy.replacement_oid].queue_ahead == 225


def test_price_through_fill_is_constrained_to_persistent_displayed_depth():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 75, np.nan, 0),
            (1_000, 99.90, 99.95, 150, 75, np.nan, 0),
            (2_000, 99.90, 99.95, 150, 75, np.nan, 0),
        ]
    )
    strategy = SendOnce(+1, 150, 100.00, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=2.0,
    )

    res = eng.run()

    strategy_fills = res.fills.loc[res.fills["side"] > 0]
    assert strategy_fills["ts_ns"].tolist() == [1_000]
    assert strategy_fills["qty"].tolist() == [75]
    assert strategy_fills["maker"].tolist() == [True]
    price_throughs = res.passive_price_throughs
    assert price_throughs["requested_qty"].tolist() == [150, 75]
    assert price_throughs["available_qty"].tolist() == [75, 0]
    assert price_throughs["filled_qty"].tolist() == [75, 0]
    assert price_throughs["shortfall_qty"].tolist() == [75, 75]
    assert price_throughs["observed_qty"].tolist() == [75, 75]
    assert price_throughs["carried_depletion_qty"].tolist() == [0, 75]
    assert price_throughs["queue_ahead_before"].tolist() == [300, 0]
    assert price_throughs["own_queue_tail"].tolist() == [0, 0]
    assert price_throughs["contra_touch_price"].tolist() == [99.95, 99.95]
    assert price_throughs["liquidity_source"].tolist() == [
        "passive_ask_price_through_display",
        "passive_ask_price_through_display",
    ]
    assert price_throughs["complete"].tolist() == [False, False]
    shortfalls = res.liquidity_shortfalls.loc[
        res.liquidity_shortfalls["liquidity_source"]
        == "passive_ask_price_through_display"
    ]
    assert shortfalls["shortfall_qty"].tolist() == [75, 75]
    assert shortfalls["carried_depletion_qty"].tolist() == [0, 75]


def test_sell_price_through_consumes_bid_depth_as_maker():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 150, np.nan, 0),
            (1_000, 100.10, 100.15, 50, 150, np.nan, 0),
        ]
    )
    strategy = SendOnce(-1, 150, 100.05, OrderType.LIMIT)
    eng = BacktestEngine(
        df,
        inst(lot_size=25),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        queue_conservatism=1.0,
    )

    result = eng.run()

    strategy_fills = result.fills.loc[result.fills["side"] < 0]
    assert strategy_fills["ts_ns"].tolist() == [1_000]
    assert strategy_fills["price"].tolist() == [100.05]
    assert strategy_fills["qty"].tolist() == [50]
    assert strategy_fills["maker"].tolist() == [True]
    price_through = result.passive_price_throughs.iloc[0]
    assert price_through["contra_touch_price"] == 100.10
    assert price_through["available_qty"] == 50
    assert price_through["filled_qty"] == 50
    assert price_through["shortfall_qty"] == 100
    assert (
        price_through["liquidity_source"]
        == "passive_bid_price_through_display"
    )
    assert not bool(price_through["complete"])


def test_cancel_takes_latency_and_order_can_fill_in_flight():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (100_000, 100.00, 100.05, 75, 75, np.nan, 0),
            (150_000, 100.00, 100.05, 75, 75, np.nan, 0),
            (175_000, 99.90, 99.95, 75, 75, np.nan, 0),
        ]
    )
    strategy = CancelAfterSend(75, 100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(feed_us=0, order_us=100),
        costs=no_costs(),
    )

    res = eng.run()

    assert res.fills.iloc[0]["ts_ns"] == 175_000
    assert res.fills.iloc[0]["maker"]
    cancellation = res.order_cancellations.iloc[0]
    assert cancellation["ts_sent_ns"] == 100_000
    assert cancellation["ts_effective_ns"] == 200_000
    assert cancellation["ts_status_ns"] == 175_000
    assert cancellation["filled_while_pending_qty"] == 75
    assert cancellation["remaining_qty"] == 0
    assert cancellation["status"] == "filled_before_effective"


def test_cancel_expires_before_later_feed_callback_and_releases_risk():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (100, 100.00, 100.05, 75, 75, np.nan, 0),
            (200, 100.00, 100.05, 75, 75, np.nan, 0),
        ]
    )
    strategy = CancelThenProbeRisk(75, 100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(feed_us=1.0, order_us=0.05),
        costs=no_costs(),
        max_position_lots=1,
    )

    result = eng.run()

    assert strategy.first_oid not in eng.open_orders
    assert strategy.second_oid in eng.open_orders
    assert eng.orders_sent == 2
    assert len(result.order_cancellations) == 1
    cancellation = result.order_cancellations.iloc[0]
    assert cancellation["ts_sent_ns"] == 1_100
    assert cancellation["ts_effective_ns"] == 1_150
    assert cancellation["ts_status_ns"] == 1_150
    assert cancellation["status"] == "effective"
    horizon_state = result.order_horizon_states.iloc[0]
    assert horizon_state["oid"] == strategy.second_oid
    assert horizon_state["remaining_qty"] == 75
    assert horizon_state["state"] == "pending_activation"


def test_cancel_pending_beyond_replay_horizon_is_reported():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (100, 100.00, 100.05, 75, 75, np.nan, 0),
        ]
    )
    strategy = CancelAfterSend(75, 100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(feed_us=1.0, order_us=1.0),
        costs=no_costs(),
    )

    result = eng.run()

    cancellation = result.order_cancellations.iloc[0]
    assert cancellation["ts_sent_ns"] == 1_100
    assert cancellation["ts_effective_ns"] == 2_100
    assert cancellation["ts_status_ns"] == 1_100
    assert cancellation["remaining_qty"] == 75
    assert cancellation["status"] == "pending_at_replay_end"
    horizon_state = result.order_horizon_states.iloc[0]
    assert horizon_state["oid"] == strategy.oid
    assert horizon_state["remaining_qty"] == 75
    assert bool(horizon_state["cancel_pending"])
    assert horizon_state["cancel_effective_ns"] == 2_100
    assert horizon_state["state"] == "cancel_pending"


def test_cancel_effective_after_partial_inflight_fill_is_reported():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 150, np.nan, 0),
            (50_000, 100.00, 100.05, 150, 150, np.nan, 0),
            (100_000, 99.90, 99.95, 150, 75, np.nan, 0),
            (250_000, 99.90, 99.95, 150, 75, np.nan, 0),
        ]
    )
    strategy = CancelAfterSend(150, 100.00)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=SequencedLatency([0, 200_000]),
        costs=no_costs(),
        queue_conservatism=0.0,
    )

    result = eng.run()

    cancellation = result.order_cancellations.iloc[0]
    assert cancellation["ts_sent_ns"] == 50_000
    assert cancellation["ts_effective_ns"] == 250_000
    assert cancellation["ts_status_ns"] == 250_000
    assert cancellation["requested_qty"] == 150
    assert cancellation["filled_while_pending_qty"] == 75
    assert cancellation["remaining_qty"] == 75
    assert cancellation["status"] == "effective_after_partial_fill"


def test_ioc_close_can_resolve_cancel_before_effective_timestamp():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (50_000, 100.00, 100.05, 75, 75, np.nan, 0),
        ]
    )
    strategy = CancelPartialIocOnFill()
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=SequencedLatency([0, 100_000]),
        costs=no_costs(),
    )

    result = eng.run()

    cancellation = result.order_cancellations.iloc[0]
    assert cancellation["ts_sent_ns"] == 50_000
    assert cancellation["ts_effective_ns"] == 150_000
    assert cancellation["ts_status_ns"] == 50_000
    assert cancellation["requested_qty"] == 75
    assert cancellation["filled_while_pending_qty"] == 0
    assert cancellation["remaining_qty"] == 75
    assert cancellation["status"] == "closed_before_effective"


def test_indian_cost_model_hand_computed_futures_sell_and_options_round_trip():
    fut = inst(Kind.FUT)
    fut_costs = IndianCostModel.nse_index_futures()
    # One futures lot sell at 25,000:
    # turnover 1,875,000; STT 0.05%=937.5; exchange 0.00173%=32.4375;
    # SEBI 0.0001%=1.875; GST 18% of exchange+SEBI=6.17625.
    fut_sell = fut_costs.cost(-1, 25_000.0, 75, fut)
    assert math.isclose(fut_sell, 978.0 - 0.01125)

    opt = inst(Kind.OPT)
    opt_costs = IndianCostModel.nse_index_options()
    # Buy turnover 11,250: stamp 0.003%=0.3375; exchange 0.03503%=3.940875;
    # SEBI 0.0001%=0.01125; GST on exchange+SEBI=0.7113825.
    opt_buy = opt_costs.cost(+1, 150.0, 75, opt)
    assert math.isclose(opt_buy, 5.0010075)

    # Sell turnover 11,250: STT 0.15%=16.875; exchange 3.940875;
    # SEBI 0.01125; GST on exchange+SEBI=0.7113825.
    opt_sell = opt_costs.cost(-1, 150.0, 75, opt)
    assert math.isclose(opt_sell, 21.5385075)
    assert math.isclose(opt_buy + opt_sell, 26.539515)


def test_terminal_flatten_happens_at_touch_with_taker_costs_and_final_equity():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (1_000, 100.20, 100.25, 75, 75, np.nan, 0),
        ]
    )
    strategy = BuyAndHold(75)
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    res = eng.run()

    assert list(res.fills["side"]) == [1, -1]
    assert list(res.fills["price"]) == [100.25, 100.20]
    assert eng.position == 0
    assert res.equity.iloc[-1]["equity"] == eng.cash
    assert math.isclose(eng.cash, (100.20 - 100.25) * 75)
    liquidation = res.terminal_liquidations.iloc[0]
    assert liquidation["requested_qty"] == 75
    assert liquidation["available_qty"] == 75
    assert liquidation["filled_qty"] == 75
    assert liquidation["shortfall_qty"] == 0
    assert liquidation["residual_position"] == 0
    assert bool(liquidation["complete"])
    assert res.liquidity_shortfalls.empty


def test_terminal_flatten_preserves_residual_when_final_depth_is_insufficient():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (1_000, 100.20, 100.25, 25, 75, np.nan, 0),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        BuyAndHold(75),
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    assert result.fills["qty"].tolist() == [75]
    assert result.fills["side"].tolist() == [1]
    assert eng.position == 75
    liquidation = result.terminal_liquidations.iloc[0]
    assert liquidation["liquidity_source"] == "terminal_bid_display"
    assert liquidation["requested_qty"] == 75
    assert liquidation["available_qty"] == 25
    assert liquidation["filled_qty"] == 0
    assert liquidation["shortfall_qty"] == 75
    assert liquidation["residual_position"] == 75
    assert not bool(liquidation["complete"])
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["liquidity_source"] == "terminal_bid_display"
    assert shortfall["requested_qty"] == 75
    assert shortfall["filled_qty"] == 0
    assert shortfall["shortfall_qty"] == 75


def test_terminal_liquidation_uses_replay_horizon_and_retains_book_timestamp():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (200_000, 100.20, 100.25, 75, 75, np.nan, 0),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        BuyAndHold(75),
        latency=fixed_latency(feed_us=100, order_us=0),
        costs=no_costs(),
    )

    result = eng.run()

    assert result.fills["ts_ns"].tolist() == [200_000, 300_000]
    liquidation = result.terminal_liquidations.iloc[0]
    assert liquidation["ts_ns"] == 300_000
    assert liquidation["book_ts_ns"] == 200_000
    assert result.equity.iloc[-1]["ts"] == 300_000


def test_venue_order_rules_reject_invalid_lot_and_tick_intents_before_admission():
    df = ticks([(0, 100.00, 100.05, 75, 75, np.nan, 0)])
    strategy = SendBurst(
        [
            (+1, 50, 100.00, OrderType.LIMIT),
            (+1, 75, 100.03, OrderType.LIMIT),
            (+1, 75, np.nan, OrderType.LIMIT),
            (+1, 75, 100.00, OrderType.LIMIT),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    assert strategy.oids == [None, None, None, 1]
    assert eng.orders_sent == 1
    assert eng.limit_orders_sent == 1
    assert eng.venue_order_validation_enabled
    assert result.order_rejections["reason"].tolist() == [
        "quantity_not_lot_multiple",
        "price_not_tick_aligned",
        "invalid_order_price",
    ]
    assert result.order_rejections["projected_min"].tolist() == [0, 0, 0]
    assert result.order_rejections["projected_max"].tolist() == [0, 0, 0]
    assert result.order_rejections["limit"].iloc[0] == 75
    assert result.order_rejections["limit"].iloc[1] == 0.05
    assert math.isnan(result.order_rejections["limit"].iloc[2])


@pytest.mark.parametrize(
    ("lot_size", "tick", "message"),
    [
        (0, 0.05, "lot_size"),
        (75.5, 0.05, "lot_size"),
        (75, 0.0, "tick"),
        (75, np.inf, "tick"),
    ],
)
def test_engine_fails_fast_on_invalid_venue_order_metadata(
    lot_size,
    tick,
    message,
):
    with pytest.raises(ValueError, match=message):
        BacktestEngine(
            ticks([(0, 100.00, 100.05, 75, 75, np.nan, 0)]),
            Instrument("INVALID", Kind.OPT, lot_size=lot_size, tick=tick),
            SendOnce(+1, 75, 100.05),
            latency=fixed_latency(),
            costs=no_costs(),
        )


def test_open_order_quantity_is_reserved_against_position_limit():
    df = ticks([(0, 100.00, 100.05, 75, 75, np.nan, 0)])
    strategy = SendBurst(
        [
            (+1, 75, 100.00, OrderType.LIMIT),
            (+1, 75, 100.00, OrderType.LIMIT),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        max_position_lots=1,
    )

    result = eng.run()

    assert strategy.oids == [1, None]
    assert eng.orders_sent == 1
    assert result.order_rejections["reason"].tolist() == [
        "instrument_position_limit"
    ]
    rejection = result.order_rejections.iloc[0]
    assert rejection["projected_min"] == 0
    assert rejection["projected_max"] == 150
    assert rejection["limit"] == 75


def test_crossing_own_resting_order_is_rejected_and_audited():
    df = ticks([(0, 100.00, 100.05, 75, 75, np.nan, 0)])
    strategy = SendBurst(
        [
            (-1, 75, 100.05, OrderType.LIMIT),
            (+1, 75, 100.05, OrderType.LIMIT),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
    )

    result = eng.run()

    assert strategy.oids == [1, None]
    rejection = result.order_rejections.iloc[0]
    assert rejection["reason"] == "aggressive_self_cross"
    assert rejection["conflicting_oid"] == 1


def test_self_cross_prevention_can_be_disabled_explicitly():
    df = ticks([(0, 100.00, 100.05, 75, 75, np.nan, 0)])
    strategy = SendBurst(
        [
            (-1, 75, 100.05, OrderType.LIMIT),
            (+1, 75, 100.05, OrderType.LIMIT),
        ]
    )
    eng = BacktestEngine(
        df,
        inst(),
        strategy,
        latency=fixed_latency(),
        costs=no_costs(),
        ban_aggressive_self_cross=False,
    )

    result = eng.run()

    assert strategy.oids == [1, 2]
    assert result.order_rejections.empty


def test_determinism_same_seed_gives_identical_equity_curve():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (150_000, 100.10, 100.15, 75, 75, np.nan, 0),
            (300_000, 100.00, 100.05, 75, 75, np.nan, 0),
        ]
    )

    def run_once():
        strategy = SendOnce(+1, 75, 100.20, OrderType.IOC)
        latency = LatencyModel(
            feed_us=50,
            order_us=75,
            jitter_us=10,
            _rng=np.random.default_rng(123),
        )
        eng = BacktestEngine(df, inst(), strategy, latency=latency, costs=no_costs())
        return eng.run().equity

    pd.testing.assert_frame_equal(run_once(), run_once())
