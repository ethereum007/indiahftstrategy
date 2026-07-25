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


NANOSECONDS_PER_DAY = 86_400_000_000_000


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
    public_queue_ahead: float = 0.0  # floor unaffected by own-order cancels
    filled: int = 0
    alive: bool = True
    queue_initialized: bool = False
    arrival_observed: bool = False
    arrival_ts_ns: int | None = None
    arrival_book_relation: str = ""
    resting_at_venue: bool = False
    resting_transition_index: int | None = None


@dataclass
class Fill:
    ts_ns: int
    oid: int
    side: int
    qty: int
    price: float
    cost: float
    maker: bool


@dataclass
class OrderRejection:
    ts_ns: int
    instrument_id: str
    side: int
    qty: int
    price: float
    order_type: str
    reason: str
    projected_min: float
    projected_max: float
    limit: float
    conflicting_oid: int | None = None


@dataclass
class LiquidityShortfall:
    ts_ns: int
    instrument_id: str
    oid: int
    side: int
    order_type: str
    requested_qty: int
    available_qty: float
    filled_qty: int
    shortfall_qty: int
    liquidity_source: str
    reason: str
    queue_ahead_before: float = 0.0
    queue_consumed: float = 0.0
    observed_qty: float = 0.0
    carried_depletion_qty: float = 0.0


@dataclass
class QueueInitialization:
    ts_ns: int
    instrument_id: str
    oid: int
    side: int
    price: float
    ts_sent_ns: int
    ts_active_ns: int
    arrival_ts_ns: int
    arrival_lag_ns: int
    arrival_book_relation: str
    initialization_lag_ns: int
    mode: str
    book_relation: str
    observed_qty: float
    public_queue_ahead: float
    own_queue_tail: float
    queue_ahead: float


@dataclass
class RestingTransition:
    ts_ns: int
    instrument_id: str
    oid: int
    side: int
    price: float
    ts_active_ns: int
    transition_lag_ns: int
    filled_qty: int
    remaining_qty: int
    book_relation: str
    deferred_at_transition: bool
    mode: str
    queue_initialized: bool
    queue_initialization_ts_ns: int | None
    queue_initialization_lag_ns: int | None
    initialization_book_relation: str
    observed_qty: float
    public_queue_ahead: float
    own_queue_tail: float
    queue_ahead: float


@dataclass
class PassivePriceThrough:
    ts_ns: int
    instrument_id: str
    oid: int
    side: int
    limit_price: float
    contra_touch_price: float
    requested_qty: int
    available_qty: float
    filled_qty: int
    shortfall_qty: int
    observed_qty: float
    carried_depletion_qty: float
    queue_ahead_before: float
    own_queue_tail: float
    liquidity_source: str
    complete: bool


@dataclass
class TerminalLiquidation:
    ts_ns: int
    book_ts_ns: int
    instrument_id: str
    oid: int
    side: int
    price: float
    requested_qty: int
    available_qty: float
    filled_qty: int
    shortfall_qty: int
    residual_position: int
    liquidity_source: str
    observed_qty: float
    carried_depletion_qty: float
    complete: bool


@dataclass
class EventLiquidity:
    """Observed liquidity attached to one market-data event.

    Displayed bid/ask depth is consumed once across aggressive orders and
    conservative passive price-through proxies. Trade-print volume is applied
    to absolute passive queue positions, which lets one print advance multiple
    orders without allocating more fills than the print contains.
    """

    bid_qty: float
    ask_qty: float
    last_qty: float
    bid_observed_qty: float = 0.0
    ask_observed_qty: float = 0.0
    bid_carried_depletion_qty: float = 0.0
    ask_carried_depletion_qty: float = 0.0
    _ledger: Optional["DisplayedLiquidityLedger"] = field(
        default=None,
        repr=False,
    )

    @classmethod
    def from_tick(cls, tick: dict) -> "EventLiquidity":
        bid_qty = _nonnegative_qty(tick.get("bid_qty", 0))
        ask_qty = _nonnegative_qty(tick.get("ask_qty", 0))
        return cls(
            bid_qty=bid_qty,
            ask_qty=ask_qty,
            last_qty=_nonnegative_qty(tick.get("last_qty", 0)),
            bid_observed_qty=bid_qty,
            ask_observed_qty=ask_qty,
        )

    def consume_displayed(self, side: int, requested_qty: int) -> tuple[float, int]:
        attr = "ask_qty" if side > 0 else "bid_qty"
        available = float(getattr(self, attr))
        filled = min(int(requested_qty), max(int(math.floor(available)), 0))
        setattr(self, attr, max(available - filled, 0.0))
        if self._ledger is not None and filled > 0:
            self._ledger.consume(side, filled)
        return available, filled

    def displayed_context(self, side: int) -> tuple[float, float]:
        prefix = "ask" if side > 0 else "bid"
        return (
            float(getattr(self, f"{prefix}_observed_qty")),
            float(getattr(self, f"{prefix}_carried_depletion_qty")),
        )


@dataclass
class _DisplayedSideLiquidity:
    price: float | None = None
    observed_qty: float = 0.0
    remaining_qty: float = 0.0

    def refresh(self, price: object, observed_qty: object, *, enabled: bool) -> None:
        next_price = float(price)
        next_observed = _nonnegative_qty(observed_qty)
        same_level = (
            self.price is not None
            and math.isfinite(next_price)
            and abs(next_price - self.price) < 1e-9
        )
        if not enabled or not same_level:
            next_remaining = next_observed
        else:
            observed_delta = next_observed - self.observed_qty
            next_remaining = min(
                max(self.remaining_qty + observed_delta, 0.0),
                next_observed,
            )
        self.price = next_price
        self.observed_qty = next_observed
        self.remaining_qty = next_remaining


@dataclass
class DisplayedLiquidityLedger:
    enabled: bool = True
    bid: _DisplayedSideLiquidity = field(
        default_factory=_DisplayedSideLiquidity,
    )
    ask: _DisplayedSideLiquidity = field(
        default_factory=_DisplayedSideLiquidity,
    )
    _session_day: int | None = field(default=None, init=False, repr=False)

    def event_liquidity(self, tick: dict) -> EventLiquidity:
        session_day = _timestamp_day(tick.get("ts"))
        if (
            session_day is not None
            and self._session_day is not None
            and session_day != self._session_day
        ):
            self.bid = _DisplayedSideLiquidity()
            self.ask = _DisplayedSideLiquidity()
        if session_day is not None:
            self._session_day = session_day
        self.bid.refresh(
            tick.get("bid", np.nan),
            tick.get("bid_qty", 0),
            enabled=self.enabled,
        )
        self.ask.refresh(
            tick.get("ask", np.nan),
            tick.get("ask_qty", 0),
            enabled=self.enabled,
        )
        return EventLiquidity(
            bid_qty=self.bid.remaining_qty,
            ask_qty=self.ask.remaining_qty,
            last_qty=_nonnegative_qty(tick.get("last_qty", 0)),
            bid_observed_qty=self.bid.observed_qty,
            ask_observed_qty=self.ask.observed_qty,
            bid_carried_depletion_qty=max(
                self.bid.observed_qty - self.bid.remaining_qty,
                0.0,
            ),
            ask_carried_depletion_qty=max(
                self.ask.observed_qty - self.ask.remaining_qty,
                0.0,
            ),
            _ledger=self,
        )

    def consume(self, side: int, qty: int) -> None:
        state = self.ask if side > 0 else self.bid
        state.remaining_qty = max(state.remaining_qty - qty, 0.0)


def _timestamp_day(value: object) -> int | None:
    try:
        timestamp_ns = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(timestamp_ns):
        return None
    return math.floor(timestamp_ns / NANOSECONDS_PER_DAY)


ORDER_REJECTION_COLUMNS = [
    "ts_ns",
    "instrument_id",
    "side",
    "qty",
    "price",
    "order_type",
    "reason",
    "projected_min",
    "projected_max",
    "limit",
    "conflicting_oid",
]

LIQUIDITY_SHORTFALL_COLUMNS = [
    "ts_ns",
    "instrument_id",
    "oid",
    "side",
    "order_type",
    "requested_qty",
    "available_qty",
    "filled_qty",
    "shortfall_qty",
    "liquidity_source",
    "reason",
    "queue_ahead_before",
    "queue_consumed",
    "observed_qty",
    "carried_depletion_qty",
]

QUEUE_INITIALIZATION_COLUMNS = [
    "ts_ns",
    "instrument_id",
    "oid",
    "side",
    "price",
    "ts_sent_ns",
    "ts_active_ns",
    "arrival_ts_ns",
    "arrival_lag_ns",
    "arrival_book_relation",
    "initialization_lag_ns",
    "mode",
    "book_relation",
    "observed_qty",
    "public_queue_ahead",
    "own_queue_tail",
    "queue_ahead",
]

RESTING_TRANSITION_COLUMNS = [
    "ts_ns",
    "instrument_id",
    "oid",
    "side",
    "price",
    "ts_active_ns",
    "transition_lag_ns",
    "filled_qty",
    "remaining_qty",
    "book_relation",
    "deferred_at_transition",
    "mode",
    "queue_initialized",
    "queue_initialization_ts_ns",
    "queue_initialization_lag_ns",
    "initialization_book_relation",
    "observed_qty",
    "public_queue_ahead",
    "own_queue_tail",
    "queue_ahead",
]

PASSIVE_PRICE_THROUGH_COLUMNS = [
    "ts_ns",
    "instrument_id",
    "oid",
    "side",
    "limit_price",
    "contra_touch_price",
    "requested_qty",
    "available_qty",
    "filled_qty",
    "shortfall_qty",
    "observed_qty",
    "carried_depletion_qty",
    "queue_ahead_before",
    "own_queue_tail",
    "liquidity_source",
    "complete",
]

TERMINAL_LIQUIDATION_COLUMNS = [
    "ts_ns",
    "book_ts_ns",
    "instrument_id",
    "oid",
    "side",
    "price",
    "requested_qty",
    "available_qty",
    "filled_qty",
    "shortfall_qty",
    "residual_position",
    "liquidity_source",
    "observed_qty",
    "carried_depletion_qty",
    "complete",
]


def _nonnegative_qty(value: object) -> float:
    try:
        qty = float(value)
    except (TypeError, ValueError):
        return 0.0
    return qty if math.isfinite(qty) and qty > 0 else 0.0


def _limit_book_relation(order: Order, tick: dict) -> str:
    bid = float(tick["bid"])
    ask = float(tick["ask"])
    if order.side > 0:
        if order.price >= ask:
            return "marketable"
        if abs(order.price - bid) < 1e-9:
            return "bid_touch"
        if bid < order.price < ask:
            return "price_improving"
    else:
        if order.price <= bid:
            return "marketable"
        if abs(order.price - ask) < 1e-9:
            return "ask_touch"
        if bid < order.price < ask:
            return "price_improving"
    return "away_from_touch"


VENUE_ORDER_REJECTION_REASONS = frozenset(
    {
        "quantity_not_lot_multiple",
        "invalid_order_price",
        "price_not_tick_aligned",
    }
)


def _quantize_price(price: float, tick: float) -> float:
    return round(round(price / tick) * tick, 10)


def _validate_venue_order_metadata(inst: Instrument) -> None:
    if (
        isinstance(inst.lot_size, bool)
        or not isinstance(inst.lot_size, (int, np.integer))
        or inst.lot_size <= 0
    ):
        raise ValueError("instrument lot_size must be a positive integer")
    try:
        tick = float(inst.tick)
    except (TypeError, ValueError) as exc:
        raise ValueError("instrument tick must be positive and finite") from exc
    if not math.isfinite(tick) or tick <= 0:
        raise ValueError("instrument tick must be positive and finite")
    inst.lot_size = int(inst.lot_size)
    inst.tick = tick


def _venue_order_rejection(
    inst: Instrument,
    qty: int,
    price: float,
) -> tuple[str, float] | None:
    if qty % inst.lot_size != 0:
        return "quantity_not_lot_multiple", float(inst.lot_size)
    if not math.isfinite(price) or price <= 0:
        return "invalid_order_price", float("nan")
    tick_ratio = price / inst.tick
    if not math.isfinite(tick_ratio):
        return "invalid_order_price", float("nan")
    quantized = _quantize_price(price, inst.tick)
    if quantized <= 0:
        return "invalid_order_price", float("nan")
    tolerance = max(1e-9, abs(inst.tick) * 1e-9)
    if not math.isclose(price, quantized, rel_tol=0.0, abs_tol=tolerance):
        return "price_not_tick_aligned", float(inst.tick)
    return None


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
                 ban_aggressive_self_cross: bool = True,
                 reserve_open_order_risk: bool = True,
                 persist_displayed_liquidity_depletion: bool = True):
        _validate_venue_order_metadata(inst)
        self.df = self._prep(df)
        self.inst = inst
        self.strategy = strategy
        self.latency = latency or LatencyModel()
        self.costs = costs or IndianCostModel.nse_index_options()
        self.max_pos = max_position_lots * inst.lot_size
        self.qcons = queue_conservatism  # >1 = assume more queue ahead of us
        self.reserve_open_order_risk = reserve_open_order_risk
        self.ban_aggressive_self_cross = ban_aggressive_self_cross
        self.persist_displayed_liquidity_depletion = (
            persist_displayed_liquidity_depletion
        )

        self._oid = 0
        self.open_orders: Dict[int, Order] = {}
        self.fills: List[Fill] = []
        self.order_rejections: List[OrderRejection] = []
        self.liquidity_shortfalls: List[LiquidityShortfall] = []
        self.queue_initializations: List[QueueInitialization] = []
        self.resting_transitions: List[RestingTransition] = []
        self.passive_price_throughs: List[PassivePriceThrough] = []
        self.terminal_liquidations: List[TerminalLiquidation] = []
        self.shared_event_liquidity_enabled = True
        self.arrival_queue_initialization_enabled = True
        self.venue_order_validation_enabled = True
        self.passive_price_through_depth_constrained_enabled = True
        self.terminal_liquidation_depth_constrained_enabled = True
        self.limit_orders_sent = 0
        self._displayed_liquidity = DisplayedLiquidityLedger(
            enabled=persist_displayed_liquidity_depletion,
        )
        self.position = 0
        self.cash = 0.0
        self.total_costs = 0.0
        self.orders_sent = 0
        self.equity_curve: List[tuple] = []   # (ts, mtm_equity)
        self._tick: dict = {}
        self._horizon_ns = 0
        self._latest_liquidity: EventLiquidity | None = None

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
        if side not in (-1, 1):
            raise ValueError("side must be +1 buy or -1 sell")
        if isinstance(qty, bool) or not isinstance(qty, (int, np.integer)):
            raise ValueError("qty must be an integer")
        if qty <= 0:
            raise ValueError("qty must be positive")

        try:
            price = float(price)
        except (TypeError, ValueError) as exc:
            raise ValueError("price must be numeric") from exc
        now = int(self._tick["ts"])
        venue_rejection = _venue_order_rejection(self.inst, qty, price)
        if venue_rejection is not None:
            reason, limit = venue_rejection
            self._reject(
                ts_ns=now,
                side=side,
                qty=qty,
                price=price,
                otype=otype,
                reason=reason,
                projected_min=self.position,
                projected_max=self.position,
                limit=limit,
            )
            return None

        price = _quantize_price(price, self.inst.tick)
        projected_min, projected_max = self._position_envelope(side, qty)
        if projected_min < -self.max_pos or projected_max > self.max_pos:
            self._reject(
                ts_ns=now,
                side=side,
                qty=qty,
                price=price,
                otype=otype,
                reason="instrument_position_limit",
                projected_min=projected_min,
                projected_max=projected_max,
                limit=self.max_pos,
            )
            return None

        active_ns = now + self.latency.order_delay_ns()
        conflict = self._self_cross_conflict(
            side=side,
            price=price,
            otype=otype,
            active_ns=active_ns,
        )
        if conflict is not None:
            self._reject(
                ts_ns=now,
                side=side,
                qty=qty,
                price=price,
                otype=otype,
                reason="aggressive_self_cross",
                projected_min=projected_min,
                projected_max=projected_max,
                limit=float("nan"),
                conflicting_oid=conflict.oid,
            )
            return None

        self._oid += 1
        o = Order(self._oid, side, qty, price, otype,
                  ts_sent_ns=now,
                  ts_active_ns=active_ns)
        if otype == OrderType.LIMIT:
            self.limit_orders_sent += 1
            market_ts = int(self._tick.get("market_ts", self._tick["ts"]))
            if active_ns <= market_ts:
                self._initialize_limit_queue(
                    o,
                    self._tick,
                    snapshot_ts=market_ts,
                    mode="send_snapshot",
                )
        self.open_orders[o.oid] = o
        self.orders_sent += 1
        return o.oid

    def _own_queue_tail(
        self,
        *,
        side: int,
        price: float,
        active_ns: int,
        priority_oid: int,
    ) -> float:
        tail = 0.0
        for order in self.open_orders.values():
            if (
                not order.alive
                or order.otype != OrderType.LIMIT
                or order.side != side
                or abs(order.price - price) >= 1e-9
                or order.filled >= order.qty
                or (order.ts_active_ns, order.oid)
                >= (active_ns, priority_oid)
            ):
                continue
            if (
                getattr(order, "_pending_cancel", False)
                and getattr(order, "cancel_at", np.inf) <= active_ns
            ):
                continue
            remaining = max(int(order.qty) - int(order.filled), 0)
            tail = max(tail, float(order.queue_ahead) + remaining)
        return tail

    def _initialize_limit_queue(
        self,
        order: Order,
        tick: dict,
        *,
        snapshot_ts: int,
        mode: str,
    ) -> None:
        if order.otype != OrderType.LIMIT or order.queue_initialized:
            return

        relation = _limit_book_relation(order, tick)
        if not order.arrival_observed:
            order.arrival_observed = True
            order.arrival_ts_ns = int(snapshot_ts)
            order.arrival_book_relation = relation
            order.resting_at_venue = relation != "marketable"
        elif relation == "bid_touch" or relation == "ask_touch":
            mode = "first_touch_snapshot"
        elif relation == "price_improving":
            mode = "resting_price_improvement_snapshot"
        elif relation == "marketable":
            mode = "resting_marketable_snapshot"

        # L1 has no public depth for an away order. Keep its queue unresolved
        # until the order price first becomes observable at or inside the touch.
        if relation == "away_from_touch":
            return

        public_queue = 0.0
        observed_qty = 0.0
        if relation == "bid_touch":
            observed_qty = _nonnegative_qty(tick.get("bid_qty", 0))
            public_queue = self.qcons * observed_qty
        elif relation == "ask_touch":
            observed_qty = _nonnegative_qty(tick.get("ask_qty", 0))
            public_queue = self.qcons * observed_qty

        own_queue_tail = self._own_queue_tail(
            side=order.side,
            price=order.price,
            active_ns=order.ts_active_ns,
            priority_oid=order.oid,
        )
        order.public_queue_ahead = max(float(public_queue), 0.0)
        order.queue_ahead = max(
            order.public_queue_ahead,
            own_queue_tail,
        )
        order.queue_initialized = True
        self.queue_initializations.append(
            QueueInitialization(
                ts_ns=int(snapshot_ts),
                instrument_id=self.inst.symbol,
                oid=order.oid,
                side=order.side,
                price=float(order.price),
                ts_sent_ns=int(order.ts_sent_ns),
                ts_active_ns=int(order.ts_active_ns),
                arrival_ts_ns=int(
                    order.arrival_ts_ns
                    if order.arrival_ts_ns is not None
                    else snapshot_ts
                ),
                arrival_lag_ns=max(
                    int(
                        order.arrival_ts_ns
                        if order.arrival_ts_ns is not None
                        else snapshot_ts
                    )
                    - int(order.ts_active_ns),
                    0,
                ),
                arrival_book_relation=order.arrival_book_relation,
                initialization_lag_ns=max(
                    int(snapshot_ts) - int(order.ts_active_ns),
                    0,
                ),
                mode=mode,
                book_relation=relation,
                observed_qty=float(observed_qty),
                public_queue_ahead=float(order.public_queue_ahead),
                own_queue_tail=float(own_queue_tail),
                queue_ahead=float(order.queue_ahead),
            )
        )

    def _transition_limit_to_resting(
        self,
        order: Order,
        tick: dict,
        *,
        snapshot_ts: int,
    ) -> None:
        if (
            order.otype != OrderType.LIMIT
            or order.resting_at_venue
            or order.resting_transition_index is not None
        ):
            return

        relation = _limit_book_relation(order, tick)
        if relation == "marketable":
            return

        order.resting_at_venue = True
        order.public_queue_ahead = 0.0
        order.queue_ahead = 0.0
        order.queue_initialized = relation != "away_from_touch"
        observed_qty = 0.0
        public_queue = 0.0
        own_queue_tail = 0.0
        if order.queue_initialized:
            if relation == "bid_touch":
                observed_qty = _nonnegative_qty(tick.get("bid_qty", 0))
                public_queue = self.qcons * observed_qty
            elif relation == "ask_touch":
                observed_qty = _nonnegative_qty(tick.get("ask_qty", 0))
                public_queue = self.qcons * observed_qty
            own_queue_tail = self._own_queue_tail(
                side=order.side,
                price=order.price,
                active_ns=order.ts_active_ns,
                priority_oid=order.oid,
            )
            order.public_queue_ahead = max(float(public_queue), 0.0)
            order.queue_ahead = max(
                order.public_queue_ahead,
                own_queue_tail,
            )

        transition = RestingTransition(
            ts_ns=int(snapshot_ts),
            instrument_id=self.inst.symbol,
            oid=order.oid,
            side=order.side,
            price=float(order.price),
            ts_active_ns=int(order.ts_active_ns),
            transition_lag_ns=max(
                int(snapshot_ts) - int(order.ts_active_ns),
                0,
            ),
            filled_qty=int(order.filled),
            remaining_qty=max(int(order.qty) - int(order.filled), 0),
            book_relation=relation,
            deferred_at_transition=not order.queue_initialized,
            mode=(
                "residual_resting_snapshot"
                if order.queue_initialized
                else "residual_queue_deferred"
            ),
            queue_initialized=bool(order.queue_initialized),
            queue_initialization_ts_ns=(
                int(snapshot_ts)
                if order.queue_initialized
                else None
            ),
            queue_initialization_lag_ns=(
                0
                if order.queue_initialized
                else None
            ),
            initialization_book_relation=(
                relation
                if order.queue_initialized
                else ""
            ),
            observed_qty=float(observed_qty),
            public_queue_ahead=float(order.public_queue_ahead),
            own_queue_tail=float(own_queue_tail),
            queue_ahead=float(order.queue_ahead),
        )
        order.resting_transition_index = len(self.resting_transitions)
        self.resting_transitions.append(transition)

    def _initialize_deferred_residual_queue(
        self,
        order: Order,
        tick: dict,
        *,
        snapshot_ts: int,
    ) -> None:
        if (
            order.resting_transition_index is None
            or order.queue_initialized
        ):
            return

        relation = _limit_book_relation(order, tick)
        if relation == "away_from_touch":
            return

        observed_qty = 0.0
        public_queue = 0.0
        if relation == "bid_touch":
            observed_qty = _nonnegative_qty(tick.get("bid_qty", 0))
            public_queue = self.qcons * observed_qty
            mode = "residual_first_touch_snapshot"
        elif relation == "ask_touch":
            observed_qty = _nonnegative_qty(tick.get("ask_qty", 0))
            public_queue = self.qcons * observed_qty
            mode = "residual_first_touch_snapshot"
        elif relation == "price_improving":
            mode = "residual_price_improvement_snapshot"
        else:
            mode = "residual_marketable_snapshot"

        own_queue_tail = self._own_queue_tail(
            side=order.side,
            price=order.price,
            active_ns=order.ts_active_ns,
            priority_oid=order.oid,
        )
        order.public_queue_ahead = max(float(public_queue), 0.0)
        order.queue_ahead = max(
            order.public_queue_ahead,
            own_queue_tail,
        )
        order.queue_initialized = True
        transition = self.resting_transitions[
            order.resting_transition_index
        ]
        transition.mode = mode
        transition.queue_initialized = True
        transition.queue_initialization_ts_ns = int(snapshot_ts)
        transition.queue_initialization_lag_ns = max(
            int(snapshot_ts) - int(transition.ts_ns),
            0,
        )
        transition.initialization_book_relation = relation
        transition.observed_qty = float(observed_qty)
        transition.public_queue_ahead = float(order.public_queue_ahead)
        transition.own_queue_tail = float(own_queue_tail)
        transition.queue_ahead = float(order.queue_ahead)

    def _position_envelope(self, side: int, qty: int) -> tuple[int, int]:
        if not self.reserve_open_order_risk:
            proposed = self.position + side * qty
            return proposed, proposed

        pending_buys = 0
        pending_sells = 0
        for order in self.open_orders.values():
            if not order.alive:
                continue
            remaining = max(int(order.qty) - int(order.filled), 0)
            if order.side > 0:
                pending_buys += remaining
            else:
                pending_sells += remaining
        if side > 0:
            pending_buys += qty
        else:
            pending_sells += qty
        return self.position - pending_sells, self.position + pending_buys

    def _self_cross_conflict(
        self,
        *,
        side: int,
        price: float,
        otype: OrderType,
        active_ns: int,
    ) -> Order | None:
        if not self.ban_aggressive_self_cross:
            return None
        for order in self.open_orders.values():
            if (
                not order.alive
                or order.side == side
                or order.otype != OrderType.LIMIT
                or order.filled >= order.qty
            ):
                continue
            prices_cross = (
                side > 0 and price >= order.price
            ) or (
                side < 0 and price <= order.price
            )
            if not prices_cross:
                continue
            if otype == OrderType.IOC and order.ts_active_ns > active_ns:
                continue
            overlap_ns = max(active_ns, order.ts_active_ns)
            if (
                getattr(order, "_pending_cancel", False)
                and getattr(order, "cancel_at", np.inf) <= overlap_ns
            ):
                continue
            return order
        return None

    def _reject(
        self,
        *,
        ts_ns: int,
        side: int,
        qty: int,
        price: float,
        otype: OrderType,
        reason: str,
        projected_min: float,
        projected_max: float,
        limit: float,
        conflicting_oid: int | None = None,
    ) -> None:
        self.order_rejections.append(
            OrderRejection(
                ts_ns=ts_ns,
                instrument_id=self.inst.symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=otype.value,
                reason=reason,
                projected_min=float(projected_min),
                projected_max=float(projected_max),
                limit=float(limit),
                conflicting_oid=conflicting_oid,
            )
        )

    def cancel(self, oid: int):
        o = self.open_orders.get(oid)
        if o:
            # cancel also takes order latency; fills can still occur in flight.
            o.cancel_sent_ns = self._tick["ts"]
            o.cancel_at = self._tick["ts"] + self.latency.order_delay_ns()
            o._pending_cancel = True
            if o.cancel_at <= self._tick["ts"]:
                self._remove_order(o, release_queue=True)

    def cancel_all(self):
        for oid in list(self.open_orders):
            self.cancel(oid)

    # -- fill simulation ------------------------------------------------------
    def _advance_later_own_queue(
        self,
        order: Order,
        qty: int,
        *,
        pending_after_ns: int | None = None,
        exclude_post_cancel_orders: bool = False,
    ) -> None:
        if qty <= 0 or order.otype != OrderType.LIMIT:
            return
        priority = (order.ts_active_ns, order.oid)
        for later in self.open_orders.values():
            if (
                later.oid == order.oid
                or not later.alive
                or later.otype != OrderType.LIMIT
                or later.side != order.side
                or abs(later.price - order.price) >= 1e-9
                or (later.ts_active_ns, later.oid) <= priority
            ):
                continue
            if pending_after_ns is not None and later.ts_active_ns <= pending_after_ns:
                continue
            if (
                exclude_post_cancel_orders
                and later.ts_sent_ns >= getattr(order, "cancel_sent_ns", np.inf)
                and later.ts_active_ns >= getattr(order, "cancel_at", np.inf)
            ):
                continue
            later.queue_ahead = max(
                float(later.public_queue_ahead),
                float(later.queue_ahead) - qty,
            )

    def _release_own_queue(self, order: Order) -> None:
        remaining = max(int(order.qty) - int(order.filled), 0)
        self._advance_later_own_queue(
            order,
            remaining,
            exclude_post_cancel_orders=True,
        )

    def _remove_order(self, order: Order, *, release_queue: bool = False) -> None:
        if release_queue:
            self._release_own_queue(order)
        order.alive = False
        self.open_orders.pop(order.oid, None)

    def _record_liquidity_shortfall(
        self,
        *,
        order: Order,
        ts_ns: int,
        requested_qty: int,
        available_qty: float,
        filled_qty: int,
        liquidity_source: str,
        queue_ahead_before: float = 0.0,
        queue_consumed: float = 0.0,
        observed_qty: float = 0.0,
        carried_depletion_qty: float = 0.0,
    ) -> None:
        shortfall = int(requested_qty) - int(filled_qty)
        if shortfall <= 0:
            return
        state = "exhausted" if available_qty < 1 else "partial"
        self.liquidity_shortfalls.append(
            LiquidityShortfall(
                ts_ns=int(ts_ns),
                instrument_id=self.inst.symbol,
                oid=order.oid,
                side=order.side,
                order_type=order.otype.value,
                requested_qty=int(requested_qty),
                available_qty=float(available_qty),
                filled_qty=int(filled_qty),
                shortfall_qty=shortfall,
                liquidity_source=liquidity_source,
                reason=f"{liquidity_source}_liquidity_{state}",
                queue_ahead_before=float(queue_ahead_before),
                queue_consumed=float(queue_consumed),
                observed_qty=float(observed_qty),
                carried_depletion_qty=float(carried_depletion_qty),
            )
        )

    def _fill_from_displayed(
        self,
        order: Order,
        *,
        liquidity: EventLiquidity,
        price: float,
        ts_ns: int,
        requested_qty: int,
        liquidity_source: str | None = None,
        maker: bool = False,
        queue_ahead_before: float = 0.0,
        queue_consumed: float = 0.0,
    ) -> tuple[float, int, float, float]:
        source = liquidity_source or (
            "ask_display" if order.side > 0 else "bid_display"
        )
        observed_qty, carried_depletion_qty = liquidity.displayed_context(
            order.side
        )
        available, fill_qty = liquidity.consume_displayed(
            order.side,
            requested_qty,
        )
        if fill_qty > 0:
            self._advance_later_own_queue(order, fill_qty)
            self._execute(order, fill_qty, price, ts_ns, maker=maker)
        self._record_liquidity_shortfall(
            order=order,
            ts_ns=ts_ns,
            requested_qty=requested_qty,
            available_qty=available,
            filled_qty=fill_qty,
            liquidity_source=source,
            queue_ahead_before=queue_ahead_before,
            queue_consumed=queue_consumed,
            observed_qty=observed_qty,
            carried_depletion_qty=carried_depletion_qty,
        )
        return available, fill_qty, observed_qty, carried_depletion_qty

    def _fill_resting_from_price_through(
        self,
        order: Order,
        tick: dict,
        liquidity: EventLiquidity,
        *,
        ts_ns: int,
        requested_qty: int,
    ) -> None:
        """Bound a maker price-through by shared opposite-touch L1 depth."""
        queue_ahead_before = max(float(order.queue_ahead), 0.0)
        own_queue_tail = self._own_queue_tail(
            side=order.side,
            price=order.price,
            active_ns=order.ts_active_ns,
            priority_oid=order.oid,
        )
        order.public_queue_ahead = 0.0
        order.queue_ahead = max(float(own_queue_tail), 0.0)
        source = (
            "passive_ask_price_through_display"
            if order.side > 0
            else "passive_bid_price_through_display"
        )
        contra_touch_price = (
            float(tick["ask"])
            if order.side > 0
            else float(tick["bid"])
        )
        (
            available_qty,
            filled_qty,
            observed_qty,
            carried_depletion_qty,
        ) = self._fill_from_displayed(
            order,
            liquidity=liquidity,
            price=float(order.price),
            ts_ns=ts_ns,
            requested_qty=requested_qty,
            liquidity_source=source,
            maker=True,
            queue_ahead_before=queue_ahead_before,
            queue_consumed=max(
                queue_ahead_before - float(own_queue_tail),
                0.0,
            ),
        )
        shortfall_qty = int(requested_qty) - int(filled_qty)
        self.passive_price_throughs.append(
            PassivePriceThrough(
                ts_ns=int(ts_ns),
                instrument_id=self.inst.symbol,
                oid=order.oid,
                side=order.side,
                limit_price=float(order.price),
                contra_touch_price=contra_touch_price,
                requested_qty=int(requested_qty),
                available_qty=float(available_qty),
                filled_qty=int(filled_qty),
                shortfall_qty=shortfall_qty,
                observed_qty=float(observed_qty),
                carried_depletion_qty=float(carried_depletion_qty),
                queue_ahead_before=queue_ahead_before,
                own_queue_tail=float(own_queue_tail),
                liquidity_source=source,
                complete=shortfall_qty == 0,
            )
        )

    def _try_fill(self, o: Order, tick: dict, liquidity: EventLiquidity):
        ts = tick["ts"]
        if ts < o.ts_active_ns:
            return
        if getattr(o, "_pending_cancel", False) and ts >= getattr(o, "cancel_at", np.inf):
            self._remove_order(o, release_queue=True)
            return

        if o.otype == OrderType.LIMIT:
            if o.resting_transition_index is not None:
                self._initialize_deferred_residual_queue(
                    o,
                    tick,
                    snapshot_ts=int(ts),
                )
            else:
                self._initialize_limit_queue(
                    o,
                    tick,
                    snapshot_ts=int(ts),
                    mode="arrival_snapshot",
                )
            if not o.queue_initialized:
                return

        bid, ask = tick["bid"], tick["ask"]
        remaining = o.qty - o.filled

        if o.otype == OrderType.IOC:
            # taker: cross the spread against displayed qty at arrival
            if o.side > 0 and o.price >= ask:
                self._fill_from_displayed(
                    o,
                    liquidity=liquidity,
                    price=ask,
                    ts_ns=ts,
                    requested_qty=remaining,
                )
            elif o.side < 0 and o.price <= bid:
                self._fill_from_displayed(
                    o,
                    liquidity=liquidity,
                    price=bid,
                    ts_ns=ts,
                    requested_qty=remaining,
                )
            self._remove_order(o)
            return

        if not o.resting_at_venue:
            self._transition_limit_to_resting(
                o,
                tick,
                snapshot_ts=int(ts),
            )
            if not o.queue_initialized:
                return

        # LIMIT maker logic
        # A resting order remains maker even when configured queue depth is
        # zero; queue quantity is not evidence of whether the order crossed.
        if o.resting_at_venue and (
            (o.side > 0 and ask < o.price) or (o.side < 0 and bid > o.price)
        ):
            self._fill_resting_from_price_through(
                o,
                tick,
                liquidity,
                ts_ns=int(ts),
                requested_qty=remaining,
            )
        # A limit that was already marketable at its first venue snapshot is
        # aggressive and consumes displayed touch depth as a taker.
        elif not o.resting_at_venue and o.side > 0 and o.price >= ask:
            self._fill_from_displayed(
                o,
                liquidity=liquidity,
                price=ask,
                ts_ns=ts,
                requested_qty=remaining,
            )
        elif not o.resting_at_venue and o.side < 0 and o.price <= bid:
            self._fill_from_displayed(
                o,
                liquidity=liquidity,
                price=bid,
                ts_ns=ts,
                requested_qty=remaining,
            )
        else:
            # Trade prints at a resting level burn public and own queue first.
            if not math.isnan(tick.get("last", np.nan)) and \
                    abs(tick["last"] - o.price) < 1e-9 and liquidity.last_qty > 0:
                queue_before = max(float(o.queue_ahead), 0.0)
                queue_consumed = min(liquidity.last_qty, queue_before)
                o.queue_ahead = max(queue_before - liquidity.last_qty, 0.0)
                o.public_queue_ahead = max(
                    float(o.public_queue_ahead) - liquidity.last_qty,
                    0.0,
                )
                available = max(liquidity.last_qty - queue_before, 0.0)
                fq = min(remaining, max(int(math.floor(available)), 0))
                if fq > 0:
                    self._advance_later_own_queue(
                        o,
                        fq,
                        pending_after_ns=ts,
                    )
                    self._execute(o, fq, o.price, ts, maker=True)
                if 0 < fq < remaining:
                    self._record_liquidity_shortfall(
                        order=o,
                        ts_ns=ts,
                        requested_qty=remaining,
                        available_qty=available,
                        filled_qty=fq,
                        liquidity_source="trade_print",
                        queue_ahead_before=queue_before,
                        queue_consumed=queue_consumed,
                    )

        if o.filled >= o.qty:
            self._remove_order(o)

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
            self._horizon_ns = max(self._horizon_ns, int(tick["ts"]))
            # feed latency: strategy sees tick later; we shift its decision
            # time, but fills check against the true book timestamp.
            self._tick = tick
            liquidity = self._displayed_liquidity.event_liquidity(tick)
            self._latest_liquidity = liquidity
            order_ids = sorted(
                self.open_orders,
                key=lambda oid: (
                    self.open_orders[oid].ts_active_ns,
                    oid,
                ),
            )
            for oid in order_ids:
                o = self.open_orders.get(oid)
                if o:
                    self._try_fill(o, tick, liquidity)
            seen = dict(tick)
            seen["ts"] = tick["ts"] + self.latency.feed_delay_ns()
            seen["market_ts"] = tick["ts"]
            self._horizon_ns = max(self._horizon_ns, int(seen["ts"]))
            self._tick = seen
            self.strategy.on_tick(self, seen)
            self._tick = tick
            mid = 0.5 * (tick["bid"] + tick["ask"])
            self.equity_curve.append(
                (tick["ts"], self.cash + self.position * mid * self.inst.multiplier))
        # Attempt a terminal taker close against depth still available at the
        # final touch. Any remainder stays marked as residual inventory.
        last = self._tick
        if self.position != 0 and last:
            book_ts_ns = int(last["ts"])
            terminal_ts_ns = max(book_ts_ns, self._horizon_ns)
            side = -int(np.sign(self.position))
            px = last["ask"] if side > 0 else last["bid"]
            requested_qty = abs(self.position)
            self._oid += 1
            o = Order(self._oid, side, requested_qty, px,
                      OrderType.IOC, terminal_ts_ns, terminal_ts_ns)
            source = (
                "terminal_ask_display"
                if side > 0
                else "terminal_bid_display"
            )
            liquidity = self._latest_liquidity
            if liquidity is None:
                liquidity = self._displayed_liquidity.event_liquidity(last)
            terminal_tick = dict(last)
            terminal_tick["ts"] = terminal_ts_ns
            terminal_tick["market_ts"] = book_ts_ns
            self._tick = terminal_tick
            (
                available_qty,
                filled_qty,
                observed_qty,
                carried_depletion_qty,
            ) = self._fill_from_displayed(
                o,
                liquidity=liquidity,
                price=px,
                ts_ns=terminal_ts_ns,
                requested_qty=requested_qty,
                liquidity_source=source,
            )
            shortfall_qty = requested_qty - filled_qty
            self.terminal_liquidations.append(
                TerminalLiquidation(
                    ts_ns=terminal_ts_ns,
                    book_ts_ns=book_ts_ns,
                    instrument_id=self.inst.symbol,
                    oid=o.oid,
                    side=side,
                    price=float(px),
                    requested_qty=requested_qty,
                    available_qty=float(available_qty),
                    filled_qty=filled_qty,
                    shortfall_qty=shortfall_qty,
                    residual_position=int(self.position),
                    liquidity_source=source,
                    observed_qty=float(observed_qty),
                    carried_depletion_qty=float(carried_depletion_qty),
                    complete=(
                        shortfall_qty == 0
                        and self.position == 0
                    ),
                )
            )
            mid = 0.5 * (last["bid"] + last["ask"])
            self.equity_curve.append(
                (
                    terminal_ts_ns,
                    self.cash + self.position * mid * self.inst.multiplier,
                )
            )
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
        self.order_rejections = pd.DataFrame(
            [rejection.__dict__ for rejection in eng.order_rejections],
            columns=ORDER_REJECTION_COLUMNS,
        )
        self.liquidity_shortfalls = pd.DataFrame(
            [shortfall.__dict__ for shortfall in eng.liquidity_shortfalls],
            columns=LIQUIDITY_SHORTFALL_COLUMNS,
        )
        self.queue_initializations = pd.DataFrame(
            [initialization.__dict__ for initialization in eng.queue_initializations],
            columns=QUEUE_INITIALIZATION_COLUMNS,
        )
        self.resting_transitions = pd.DataFrame(
            [transition.__dict__ for transition in eng.resting_transitions],
            columns=RESTING_TRANSITION_COLUMNS,
        )
        self.passive_price_throughs = pd.DataFrame(
            [
                price_through.__dict__
                for price_through in eng.passive_price_throughs
            ],
            columns=PASSIVE_PRICE_THROUGH_COLUMNS,
        )
        self.terminal_liquidations = pd.DataFrame(
            [liquidation.__dict__ for liquidation in eng.terminal_liquidations],
            columns=TERMINAL_LIQUIDATION_COLUMNS,
        )

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
            f"Pre-trade rejects  : {len(self.order_rejections)}",
            f"Liquidity shortfall: {len(self.liquidity_shortfalls)} events",
            f"Terminal residual  : {abs(self.eng.position)} units",
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
        bid_px = _quantize_price(
            micro - self.hs * e.inst.tick - skew,
            e.inst.tick,
        )
        ask_px = _quantize_price(
            micro + self.hs * e.inst.tick - skew,
            e.inst.tick,
        )
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
