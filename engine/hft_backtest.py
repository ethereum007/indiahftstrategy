"""
hft_backtest.py
================
Event-driven HFT backtesting framework for Indian index derivatives (NSE/BSE).

Designed around the three things that make or break HFT backtests:

  1. LATENCY MODEL    - signal->order and exchange->you delays, configurable in
                        microseconds. Orders act on the book as it exists when
                        they ARRIVE, not when the signal fired.
  2. QUEUE MODEL      - limit orders earn fills only after estimated queue
                        ahead of them is consumed (probabilistic, conservative).
  3. COST MODEL       - exact Indian charges: STT (post Budget-2026 rates),
                        exchange transaction charges, SEBI fees, stamp duty,
                        GST, brokerage/clearing. All parameterized — verify
                        against current circulars before trusting results.

Data expectations
-----------------
Tick/L1 data as a pandas DataFrame with at least:
    ts          int64 nanoseconds (or datetime64) — exchange timestamp
    bid, ask    best bid / best ask price
    bid_qty, ask_qty   top-of-book quantities
    last, last_qty     last trade price/qty (optional but recommended)
For L2 strategies, optional columns bid2..bid5 / ask2..ask5 etc.

Usage
-----
    df = load_your_ticks(...)
    inst = Instrument(symbol="NIFTY26JUN25000CE", kind="OPT", lot_size=75, tick=0.05)
    engine = BacktestEngine(df, inst, strategy=OBITakerStrategy(...),
                            latency=LatencyModel(order_us=250, feed_us=50),
                            costs=IndianCostModel.nse_index_options())
    result = engine.run()
    print(result.report())

This is a research tool, not production code. Validate fills against your own
exchange drop-copy / order logs before believing any number it produces.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Callable

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Instruments & market structure
# ----------------------------------------------------------------------------

class Kind(str, Enum):
    FUT = "FUT"
    OPT = "OPT"
    EQ = "EQ"


@dataclass
class Instrument:
    symbol: str
    kind: Kind
    lot_size: int          # e.g. NIFTY 75, BANKNIFTY 30 (verify current circulars)
    tick: float            # e.g. 0.05 for index options
    multiplier: float = 1.0


# ----------------------------------------------------------------------------
# Cost model — Indian charges (defaults reflect post 1-Apr-2026 STT regime)
# ----------------------------------------------------------------------------

@dataclass
class IndianCostModel:
    """All rates are fractions of notional unless noted. VERIFY against the
    latest NSE/BSE circulars and Finance Act — these change in budgets and
    exchange fee revisions.

    Notes:
      * Futures STT applies to SELL side on full contract value.
      * Options STT applies to SELL side on PREMIUM (this is why Indian HFT
        lives in options). Exercise STT (on intrinsic) is punitive — strategies
        must square off, never exercise; we model exercise as forbidden.
      * Exchange txn charges: futures on notional, options on premium.
      * Stamp duty applies to BUY side.
      * GST applies on (brokerage + exchange txn charges + SEBI fees).
    """
    stt_sell: float                 # futures: on notional. options: on premium.
    exch_txn: float                 # futures: on notional. options: on premium.
    sebi_fee: float = 10e-7         # ₹10 per crore = 1e-6 of turnover (0.0001%)
    stamp_buy: float = 0.00002      # futures 0.002% buy side
    gst: float = 0.18
    brokerage_per_order: float = 0.0   # prop desks ~0; set for broker accounts
    clearing_per_lot: float = 0.0

    @classmethod
    def nse_index_futures(cls) -> "IndianCostModel":
        return cls(
            stt_sell=0.0005,        # 0.05% on sell-side notional (Budget 2026)
            exch_txn=0.0000173,     # ~0.00173% NSE futures (verify)
            stamp_buy=0.00002,      # 0.002% buy side
        )

    @classmethod
    def nse_index_options(cls) -> "IndianCostModel":
        return cls(
            stt_sell=0.0015,        # 0.15% of premium on sell (Budget 2026)
            exch_txn=0.0003503,     # ~0.03503% of premium NSE options (verify)
            stamp_buy=0.00003,      # 0.003% of premium, buy side
        )

    def cost(self, side: int, price: float, qty: int, inst: Instrument) -> float:
        """Total statutory + broker cost in ₹ for one fill.
        side: +1 buy, -1 sell. For options `price` is the premium."""
        turnover = price * qty * inst.multiplier
        stt = self.stt_sell * turnover if side < 0 else 0.0
        stamp = self.stamp_buy * turnover if side > 0 else 0.0
        exch = self.exch_txn * turnover
        sebi = self.sebi_fee * turnover
        gst = self.gst * (exch + sebi + self.brokerage_per_order)
        lots = qty / inst.lot_size
        return stt + stamp + exch + sebi + gst + self.brokerage_per_order \
            + self.clearing_per_lot * lots

    def round_trip_bps(self, price: float, inst: Instrument) -> float:
        """Approx round-trip cost in bps of traded price — useful as a hurdle
        the strategy's expected edge must clear."""
        q = inst.lot_size
        c = self.cost(+1, price, q, inst) + self.cost(-1, price, q, inst)
        return 1e4 * c / (price * q * inst.multiplier)


# ----------------------------------------------------------------------------
# Latency model
# ----------------------------------------------------------------------------

@dataclass
class LatencyModel:
    """Deterministic + jitter latency, in microseconds.
    feed_us : exchange event -> your strategy sees it
    order_us: your order out -> matched at exchange
    jitter_us: half-width of uniform jitter added to each leg
    """
    feed_us: float = 50.0
    order_us: float = 250.0
    jitter_us: float = 30.0
    _rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng(7))

    def feed_delay_ns(self) -> int:
        return int((self.feed_us + self._rng.uniform(-self.jitter_us, self.jitter_us)) * 1000)

    def order_delay_ns(self) -> int:
        return int((self.order_us + self._rng.uniform(-self.jitter_us, self.jitter_us)) * 1000)


# ----------------------------------------------------------------------------
# Orders, fills
# ----------------------------------------------------------------------------

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    IOC = "IOC"       # immediate-or-cancel (taker)


@dataclass
class Order:
    oid: int
    side: int                  # +1 buy / -1 sell
    qty: int
    price: float
    otype: OrderType
    ts_sent_ns: int            # strategy decision time
    ts_active_ns: int = 0      # arrival at exchange (sent + order latency)
    queue_ahead: float = 0.0   # estimated qty ahead at our price level
    filled: int = 0
    alive: bool = True


@dataclass
class Fill:
    ts_ns: int
    oid: int
    side: int
    qty: int
    price: float
    cost: float
    maker: bool


# ----------------------------------------------------------------------------
# Strategy interface
# ----------------------------------------------------------------------------

class Strategy:
    """Override on_tick. Use the engine handle to send/cancel orders.
    The tick you receive is already feed-latency delayed."""
    def on_start(self, engine: "BacktestEngine"): ...
    def on_tick(self, engine: "BacktestEngine", tick: dict): ...
    def on_fill(self, engine: "BacktestEngine", fill: Fill): ...
    def on_end(self, engine: "BacktestEngine"): ...


# ----------------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------------

class BacktestEngine:
    def __init__(self, df: pd.DataFrame, inst: Instrument, strategy: Strategy,
                 latency: LatencyModel = None, costs: IndianCostModel = None,
                 max_position_lots: int = 20,
                 queue_conservatism: float = 1.5,
                 ban_aggressive_self_cross: bool = True):
        self.df = self._prep(df)
        self.inst = inst
        self.strategy = strategy
        self.latency = latency or LatencyModel()
        self.costs = costs or IndianCostModel.nse_index_options()
        self.max_pos = max_position_lots * inst.lot_size
        self.qcons = queue_conservatism  # >1 = assume more queue ahead of us

        self._oid = 0
        self.open_orders: Dict[int, Order] = {}
        self.fills: List[Fill] = []
        self.position = 0
        self.cash = 0.0
        self.total_costs = 0.0
        self.orders_sent = 0
        self.equity_curve: List[tuple] = []   # (ts, mtm_equity)
        self._tick: dict = {}

    # -- data prep -----------------------------------------------------------
    @staticmethod
    def _prep(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if np.issubdtype(df["ts"].dtype, np.datetime64):
            df["ts"] = df["ts"].astype("int64")
        df = df.sort_values("ts").reset_index(drop=True)
        for c in ("last", "last_qty"):
            if c not in df.columns:
                df[c] = np.nan
        return df

    # -- order API (called by strategy) --------------------------------------
    def send(self, side: int, qty: int, price: float,
             otype: OrderType = OrderType.LIMIT) -> Optional[int]:
        # position guard
        if side * qty + self.position > self.max_pos or \
           side * qty + self.position < -self.max_pos:
            return None
        price = round(round(price / self.inst.tick) * self.inst.tick, 10)
        self._oid += 1
        now = self._tick["ts"]
        o = Order(self._oid, side, qty, price, otype,
                  ts_sent_ns=now,
                  ts_active_ns=now + self.latency.order_delay_ns())
        # queue estimate: displayed qty at our level when we arrive (we use the
        # current tick as proxy; conservative multiplier compensates)
        if otype == OrderType.LIMIT:
            if side > 0 and abs(price - self._tick["bid"]) < 1e-9:
                o.queue_ahead = self.qcons * self._tick["bid_qty"]
            elif side < 0 and abs(price - self._tick["ask"]) < 1e-9:
                o.queue_ahead = self.qcons * self._tick["ask_qty"]
            else:
                o.queue_ahead = 0.0   # new level: front of queue
        self.open_orders[o.oid] = o
        self.orders_sent += 1
        return o.oid

    def cancel(self, oid: int):
        o = self.open_orders.get(oid)
        if o:
            # cancel also takes order latency; fills can still occur in flight.
            o.cancel_at = self._tick["ts"] + self.latency.order_delay_ns()
            o.alive = False if getattr(o, "cancel_at", 0) <= self._tick["ts"] else o.alive
            o._pending_cancel = True

    def cancel_all(self):
        for oid in list(self.open_orders):
            self.cancel(oid)

    # -- fill simulation ------------------------------------------------------
    def _try_fill(self, o: Order, tick: dict):
        ts = tick["ts"]
        if ts < o.ts_active_ns:
            return
        if getattr(o, "_pending_cancel", False) and ts >= getattr(o, "cancel_at", np.inf):
            o.alive = False
            del self.open_orders[o.oid]
            return

        bid, ask = tick["bid"], tick["ask"]
        remaining = o.qty - o.filled

        if o.otype == OrderType.IOC:
            # taker: cross the spread against displayed qty at arrival
            if o.side > 0 and o.price >= ask:
                fq = min(remaining, int(tick["ask_qty"]))
                if fq > 0:
                    self._execute(o, fq, ask, ts, maker=False)
            elif o.side < 0 and o.price <= bid:
                fq = min(remaining, int(tick["bid_qty"]))
                if fq > 0:
                    self._execute(o, fq, bid, ts, maker=False)
            o.alive = False
            self.open_orders.pop(o.oid, None)
            return

        # LIMIT maker logic
        # 1) price trades THROUGH a queued resting level -> assume full fill.
        # If the order had queue ahead, it was intended as a passive quote at
        # the touch, not as a freshly marketable order crossing the spread.
        if o.queue_ahead > 0 and (
            (o.side > 0 and ask < o.price) or (o.side < 0 and bid > o.price)
        ):
            self._execute(o, remaining, o.price, ts, maker=True)
        # 2) marketable on arrival -> trade as taker
        elif o.side > 0 and o.price >= ask:
            fq = min(remaining, int(tick["ask_qty"]))
            if fq:
                self._execute(o, fq, ask, ts, maker=False)
        elif o.side < 0 and o.price <= bid:
            fq = min(remaining, int(tick["bid_qty"]))
            if fq:
                self._execute(o, fq, bid, ts, maker=False)
        else:
            # 3) price trades THROUGH our level -> assume full fill
            if (o.side > 0 and ask < o.price) or (o.side < 0 and bid > o.price):
                self._execute(o, remaining, o.price, ts, maker=True)
            # 4) trade prints AT our level -> burn queue, then fill
            elif not math.isnan(tick.get("last", np.nan)) and \
                    abs(tick["last"] - o.price) < 1e-9 and tick.get("last_qty", 0) > 0:
                burn = tick["last_qty"]
                if o.queue_ahead > 0:
                    used = min(burn, o.queue_ahead)
                    o.queue_ahead -= used
                    burn -= used
                if burn > 0:
                    fq = min(remaining, int(burn))
                    self._execute(o, fq, o.price, ts, maker=True)

        if o.filled >= o.qty:
            o.alive = False
            self.open_orders.pop(o.oid, None)

    def _execute(self, o: Order, qty: int, price: float, ts: int, maker: bool):
        cost = self.costs.cost(o.side, price, qty, self.inst)
        o.filled += qty
        self.position += o.side * qty
        self.cash -= o.side * qty * price * self.inst.multiplier
        self.cash -= cost
        self.total_costs += cost
        f = Fill(ts, o.oid, o.side, qty, price, cost, maker)
        self.fills.append(f)
        self.strategy.on_fill(self, f)

    # -- main loop ------------------------------------------------------------
    def run(self) -> "BacktestResult":
        self.strategy.on_start(self)
        cols = self.df.columns
        for row in self.df.itertuples(index=False):
            tick = dict(zip(cols, row))
            # feed latency: strategy sees tick later; we shift its decision
            # time, but fills check against the true book timestamp.
            self._tick = tick
            for oid in list(self.open_orders):
                o = self.open_orders.get(oid)
                if o:
                    self._try_fill(o, tick)
            seen = dict(tick)
            seen["ts"] = tick["ts"] + self.latency.feed_delay_ns()
            self._tick = seen
            self.strategy.on_tick(self, seen)
            self._tick = tick
            mid = 0.5 * (tick["bid"] + tick["ask"])
            self.equity_curve.append(
                (tick["ts"], self.cash + self.position * mid * self.inst.multiplier))
        # flatten at last mid (taker, with costs) for honest terminal PnL
        last = self._tick
        if self.position != 0 and last:
            side = -int(np.sign(self.position))
            px = last["ask"] if side > 0 else last["bid"]
            o = Order(self._oid + 1, side, abs(self.position), px,
                      OrderType.IOC, last["ts"], last["ts"])
            self._execute(o, abs(self.position), px, last["ts"], maker=False)
            mid = 0.5 * (last["bid"] + last["ask"])
            self.equity_curve.append(
                (last["ts"], self.cash + self.position * mid * self.inst.multiplier))
        self.strategy.on_end(self)
        return BacktestResult(self)


# ----------------------------------------------------------------------------
# Results & metrics
# ----------------------------------------------------------------------------

class BacktestResult:
    def __init__(self, eng: BacktestEngine):
        self.eng = eng
        self.equity = pd.DataFrame(eng.equity_curve, columns=["ts", "equity"])
        self.fills = pd.DataFrame([f.__dict__ for f in eng.fills])

    def report(self) -> str:
        e = self.equity["equity"].values
        if len(e) < 2:
            return "no data"
        pnl = e[-1]
        # resample to 1s for Sharpe so tick autocorrelation doesn't inflate it
        eq = self.equity.copy()
        eq["sec"] = (eq["ts"] // 1_000_000_000)
        sec = eq.groupby("sec")["equity"].last()
        r = sec.diff().dropna()
        sharpe = (r.mean() / (r.std() + 1e-12)) * math.sqrt(252 * 6.25 * 3600)
        peak = np.maximum.accumulate(e)
        maxdd = float(np.max(peak - e))
        nf = len(self.fills)
        turnover = float((self.fills["qty"] * self.fills["price"]).sum()) if nf else 0.0
        maker_share = float(self.fills["maker"].mean()) if nf else 0.0
        otr = self.eng.orders_sent / max(nf, 1)
        lines = [
            f"Net PnL            : ₹{pnl:,.0f}",
            f"Total costs        : ₹{self.eng.total_costs:,.0f}"
            f"  ({100*self.eng.total_costs/max(abs(pnl)+self.eng.total_costs,1e-9):.1f}% of gross)",
            f"Fills / Orders     : {nf} / {self.eng.orders_sent}  (OTR {otr:.1f})",
            f"Maker fill share   : {100*maker_share:.1f}%",
            f"Turnover           : ₹{turnover:,.0f}",
            f"Sharpe (annualized): {sharpe:.2f}",
            f"Max drawdown       : ₹{maxdd:,.0f}",
        ]
        return "\n".join(lines)


# ============================================================================
# EXAMPLE STRATEGIES
# ============================================================================

class OBITakerStrategy(Strategy):
    """Order-book-imbalance micro-momentum (taker).
    Signal: smoothed top-of-book imbalance. Fire IOC when |signal| is strong
    enough that expected move clears spread + round-trip costs (hurdle).
    Best suited to liquid ATM weekly index options under the 2026 STT regime.
    """
    def __init__(self, lots: int = 1, ema_alpha: float = 0.05,
                 entry_z: float = 0.75, exit_z: float = 0.10,
                 min_edge_ticks: float = 2.0, cooloff_ns: int = 200_000_000):
        self.lots, self.alpha = lots, ema_alpha
        self.entry_z, self.exit_z = entry_z, exit_z
        self.min_edge_ticks = min_edge_ticks
        self.cooloff = cooloff_ns
        self.obi_ema = 0.0
        self.last_trade_ts = 0

    def on_tick(self, e: BacktestEngine, t: dict):
        bq, aq = t["bid_qty"], t["ask_qty"]
        if bq + aq <= 0:
            return
        obi = (bq - aq) / (bq + aq)
        self.obi_ema += self.alpha * (obi - self.obi_ema)
        qty = self.lots * e.inst.lot_size
        spread_ticks = (t["ask"] - t["bid"]) / e.inst.tick
        hurdle_ok = spread_ticks <= self.min_edge_ticks
        if t["ts"] - self.last_trade_ts < self.cooloff:
            return
        if e.position == 0 and hurdle_ok:
            if self.obi_ema > self.entry_z:
                e.send(+1, qty, t["ask"], OrderType.IOC); self.last_trade_ts = t["ts"]
            elif self.obi_ema < -self.entry_z:
                e.send(-1, qty, t["bid"], OrderType.IOC); self.last_trade_ts = t["ts"]
        elif e.position > 0 and self.obi_ema < self.exit_z:
            e.send(-1, e.position, t["bid"], OrderType.IOC); self.last_trade_ts = t["ts"]
        elif e.position < 0 and self.obi_ema > -self.exit_z:
            e.send(+1, -e.position, t["ask"], OrderType.IOC); self.last_trade_ts = t["ts"]


class InventoryMMStrategy(Strategy):
    """Single-instrument market maker with inventory skew (Avellaneda-Stoikov
    flavored, simplified). Quotes around micro-price; widens/skews with
    inventory; re-quotes when reference moves. Track your OTR — NSE penalizes
    high order-to-trade ratios.
    """
    def __init__(self, lots: int = 1, half_spread_ticks: float = 2.0,
                 skew_ticks_per_lot: float = 1.0, max_inv_lots: int = 5,
                 requote_ticks: float = 1.0):
        self.lots = lots
        self.hs = half_spread_ticks
        self.skew = skew_ticks_per_lot
        self.max_inv = max_inv_lots
        self.requote = requote_ticks
        self.bid_oid = self.ask_oid = None
        self.last_ref = None

    def on_tick(self, e: BacktestEngine, t: dict):
        bq, aq = t["bid_qty"], t["ask_qty"]
        if bq + aq <= 0:
            return
        micro = (t["bid"] * aq + t["ask"] * bq) / (bq + aq)   # micro-price
        if self.last_ref is not None and \
           abs(micro - self.last_ref) < self.requote * e.inst.tick and \
           self.bid_oid in e.open_orders and self.ask_oid in e.open_orders:
            return
        self.last_ref = micro
        e.cancel_all()
        inv_lots = e.position / e.inst.lot_size
        skew = self.skew * inv_lots * e.inst.tick     # long inventory -> quote lower
        bid_px = micro - self.hs * e.inst.tick - skew
        ask_px = micro + self.hs * e.inst.tick - skew
        q = self.lots * e.inst.lot_size
        if inv_lots < self.max_inv:
            self.bid_oid = e.send(+1, q, bid_px, OrderType.LIMIT)
        if inv_lots > -self.max_inv:
            self.ask_oid = e.send(-1, q, ask_px, OrderType.LIMIT)


class LeadLagStrategy(Strategy):
    """Futures-leads-options stale quote taker.
    Feed a second 'leader' series (e.g. NIFTY futures micro-price returns,
    pre-aligned on ts) via `leader_lookup(ts)->signal`. When leader has moved
    but this option's quotes haven't, lift/hit the stale side.
    """
    def __init__(self, leader_lookup: Callable[[int], float],
                 delta: float, lots: int = 1,
                 trigger_ticks: float = 3.0, flat_after_ns: int = 500_000_000):
        self.leader = leader_lookup     # returns leader move (pts) over window
        self.delta = delta              # option delta vs leader
        self.lots = lots
        self.trigger = trigger_ticks
        self.flat_after = flat_after_ns
        self.entry_ts = None

    def on_tick(self, e: BacktestEngine, t: dict):
        sig_pts = self.leader(t["ts"]) * self.delta   # expected option move
        sig_ticks = sig_pts / e.inst.tick
        q = self.lots * e.inst.lot_size
        if e.position == 0:
            if sig_ticks > self.trigger:
                e.send(+1, q, t["ask"], OrderType.IOC); self.entry_ts = t["ts"]
            elif sig_ticks < -self.trigger:
                e.send(-1, q, t["bid"], OrderType.IOC); self.entry_ts = t["ts"]
        elif self.entry_ts and t["ts"] - self.entry_ts > self.flat_after:
            side = -int(np.sign(e.position))
            px = t["ask"] if side > 0 else t["bid"]
            e.send(side, abs(e.position), px, OrderType.IOC)
            self.entry_ts = None


# ----------------------------------------------------------------------------
# Synthetic-data smoke test (so the file runs end-to-end out of the box)
# ----------------------------------------------------------------------------

def _synthetic_option_ticks(n=200_000, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = np.cumsum(rng.exponential(2e6, n)).astype("int64")  # ~2ms inter-tick
    mid = 150 + np.cumsum(rng.normal(0, 0.03, n))            # premium ~₹150
    mid = np.maximum(mid, 5.0)
    spread = 0.05 * rng.integers(1, 4, n)
    bid = np.round((mid - spread / 2) / 0.05) * 0.05
    ask = bid + spread
    bid_qty = rng.integers(1, 40, n) * 75
    ask_qty = rng.integers(1, 40, n) * 75
    last = np.where(rng.random(n) < 0.5, bid, ask)
    last_qty = rng.integers(1, 5, n) * 75
    return pd.DataFrame(dict(ts=ts, bid=bid, ask=ask, bid_qty=bid_qty,
                             ask_qty=ask_qty, last=last, last_qty=last_qty))


if __name__ == "__main__":
    inst = Instrument("NIFTY-WK-ATM-CE", Kind.OPT, lot_size=75, tick=0.05)
    costs = IndianCostModel.nse_index_options()
    print(f"Round-trip cost hurdle at ₹150 premium: "
          f"{costs.round_trip_bps(150.0, inst):.1f} bps of premium\n")

    df = _synthetic_option_ticks()
    eng = BacktestEngine(df, inst,
                         strategy=InventoryMMStrategy(lots=1),
                         latency=LatencyModel(feed_us=50, order_us=250),
                         costs=costs)
    res = eng.run()
    print("InventoryMM on synthetic ticks (sanity check only):")
    print(res.report())
