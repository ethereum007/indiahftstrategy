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
