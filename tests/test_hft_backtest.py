import math

import numpy as np
import pandas as pd

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


def inst(kind=Kind.OPT):
    return Instrument("NIFTY-TEST", kind, lot_size=75, tick=0.05)


def no_costs():
    return IndianCostModel(stt_sell=0.0, exch_txn=0.0, sebi_fee=0.0, stamp_buy=0.0)


def fixed_latency(feed_us=0.0, order_us=0.0):
    return LatencyModel(feed_us=feed_us, order_us=order_us, jitter_us=0.0)


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
    assert strategy_fills["qty"].tolist() == [75, 25]
    assert int(strategy_fills["qty"].sum()) == 100
    assert len(result.liquidity_shortfalls) == 1
    shortfall = result.liquidity_shortfalls.iloc[0]
    assert shortfall["oid"] == strategy.oids[1]
    assert shortfall["requested_qty"] == 75
    assert shortfall["available_qty"] == 25
    assert shortfall["filled_qty"] == 25
    assert shortfall["shortfall_qty"] == 50
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
        inst(),
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
        inst(),
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
        inst(),
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
        inst(),
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
    assert initialization["book_relation"] == "marketable"
    assert initialization["observed_qty"] == 0
    assert initialization["queue_ahead"] == 0


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
        inst(),
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
        inst(),
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


def test_price_trading_through_limit_level_fills_full_order():
    df = ticks(
        [
            (0, 100.00, 100.05, 150, 75, np.nan, 0),
            (1_000, 99.90, 99.95, 150, 75, np.nan, 0),
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

    assert res.fills.iloc[0]["ts_ns"] == 1_000
    assert res.fills.iloc[0]["qty"] == 150
    assert res.fills.iloc[0]["maker"]


def test_cancel_takes_latency_and_order_can_fill_in_flight():
    df = ticks(
        [
            (0, 100.00, 100.05, 75, 75, np.nan, 0),
            (100_000, 100.00, 100.05, 75, 75, np.nan, 0),
            (150_000, 100.00, 100.05, 75, 75, np.nan, 0),
            (200_000, 99.90, 99.95, 75, 75, np.nan, 0),
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

    assert res.fills.iloc[0]["ts_ns"] == 200_000
    assert res.fills.iloc[0]["maker"]


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
