from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from engine.hft_backtest import (
    Fill,
    IndianCostModel,
    Instrument,
    Kind,
    LatencyModel,
    Order,
    OrderType,
)


@dataclass
class VenueConfig:
    name: str
    latency: LatencyModel = field(default_factory=LatencyModel)
    clock_skew_ns: int = 0


@dataclass
class InstrumentConfig:
    instrument: Instrument
    venue: str
    data: pd.DataFrame
    costs: Optional[IndianCostModel] = None
    max_position_lots: int = 20
    delta_per_unit: float = 0.0
    vega_per_unit: float = 0.0


@dataclass
class PortfolioLimits:
    max_abs_position: Optional[int] = None
    max_abs_delta: Optional[float] = None
    max_abs_vega: Optional[float] = None


@dataclass
class RoutedFill:
    instrument_id: str
    ts_ns: int
    oid: int
    side: int
    qty: int
    price: float
    cost: float
    maker: bool

    @classmethod
    def from_fill(cls, instrument_id: str, fill: Fill) -> "RoutedFill":
        return cls(instrument_id=instrument_id, **fill.__dict__)


class MultiInstrumentStrategy:
    def on_start(self, engine: "MultiInstrumentEngine"): ...
    def on_tick(self, engine: "MultiInstrumentEngine", instrument_id: str, tick: dict): ...
    def on_fill(self, engine: "MultiInstrumentEngine", fill: RoutedFill): ...
    def on_end(self, engine: "MultiInstrumentEngine"): ...


@dataclass(order=True)
class _Event:
    ts_ns: int
    priority: int
    seq: int
    kind: str
    instrument_id: str
    tick: dict


class MultiInstrumentEngine:
    """Shared-clock event replay for correlated Indian index instruments.

    Market events update the book and attempt fills at the true aligned market
    timestamp. Feed events are delivered later to the strategy, ordered by the
    timestamp at which that tick would be visible to the strategy.
    """

    def __init__(
        self,
        instruments: Mapping[str, InstrumentConfig],
        venues: Mapping[str, VenueConfig],
        strategy: MultiInstrumentStrategy,
        portfolio_limits: PortfolioLimits | None = None,
        queue_conservatism: float = 1.5,
    ):
        if not instruments:
            raise ValueError("at least one instrument is required")
        self.instruments = dict(instruments)
        self.venues = dict(venues)
        self.strategy = strategy
        self.portfolio_limits = portfolio_limits or PortfolioLimits()
        self.qcons = queue_conservatism

        for iid, cfg in self.instruments.items():
            if cfg.venue not in self.venues:
                raise ValueError(f"instrument {iid} references unknown venue {cfg.venue}")
            cfg.data = self._prep(cfg.data)
            if cfg.costs is None:
                cfg.costs = self._default_costs(cfg.instrument)

        self._oid = 0
        self._now_ns = 0
        self._visible_ticks: Dict[str, dict] = {}
        self._latest_books: Dict[str, dict] = {}
        self._order_instrument: Dict[int, str] = {}

        self.open_orders: Dict[int, Order] = {}
        self.fills: List[RoutedFill] = []
        self.positions: Dict[str, int] = {iid: 0 for iid in self.instruments}
        self.cash = 0.0
        self.total_costs = 0.0
        self.orders_sent = 0
        self.equity_curve: List[tuple[int, float]] = []

    @staticmethod
    def _prep(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "ts" not in df.columns:
            raise ValueError("tick data must contain a ts column")
        if np.issubdtype(df["ts"].dtype, np.datetime64):
            df["ts"] = df["ts"].astype("int64")
        for col in ("bid", "ask", "bid_qty", "ask_qty"):
            if col not in df.columns:
                raise ValueError(f"tick data must contain {col}")
        for col in ("last", "last_qty"):
            if col not in df.columns:
                df[col] = np.nan
        return df.sort_values("ts").reset_index(drop=True)

    @staticmethod
    def _default_costs(inst: Instrument) -> IndianCostModel:
        if inst.kind == Kind.FUT:
            return IndianCostModel.nse_index_futures()
        return IndianCostModel.nse_index_options()

    def send(
        self,
        instrument_id: str,
        side: int,
        qty: int,
        price: float,
        otype: OrderType = OrderType.LIMIT,
    ) -> Optional[int]:
        if instrument_id not in self.instruments:
            raise KeyError(f"unknown instrument_id {instrument_id}")
        if side not in (-1, 1):
            raise ValueError("side must be +1 buy or -1 sell")
        if qty <= 0:
            raise ValueError("qty must be positive")
        if not self._passes_risk(instrument_id, side, qty):
            return None
        visible = self._visible_ticks.get(instrument_id)
        if visible is None:
            return None

        cfg = self.instruments[instrument_id]
        venue = self.venues[cfg.venue]
        inst = cfg.instrument
        price = round(round(price / inst.tick) * inst.tick, 10)
        self._oid += 1
        order = Order(
            self._oid,
            side,
            qty,
            price,
            otype,
            ts_sent_ns=self._now_ns,
            ts_active_ns=self._now_ns + venue.latency.order_delay_ns(),
        )
        if otype == OrderType.LIMIT:
            if side > 0 and abs(price - visible["bid"]) < 1e-9:
                order.queue_ahead = self.qcons * visible["bid_qty"]
            elif side < 0 and abs(price - visible["ask"]) < 1e-9:
                order.queue_ahead = self.qcons * visible["ask_qty"]
            else:
                order.queue_ahead = 0.0

        self.open_orders[order.oid] = order
        self._order_instrument[order.oid] = instrument_id
        self.orders_sent += 1
        return order.oid

    def cancel(self, oid: int):
        order = self.open_orders.get(oid)
        if order is None:
            return
        instrument_id = self._order_instrument[oid]
        cfg = self.instruments[instrument_id]
        venue = self.venues[cfg.venue]
        order.cancel_at = self._now_ns + venue.latency.order_delay_ns()
        order.alive = False if order.cancel_at <= self._now_ns else order.alive
        order._pending_cancel = True

    def cancel_all(self, instrument_id: str | None = None):
        for oid in list(self.open_orders):
            if instrument_id is None or self._order_instrument.get(oid) == instrument_id:
                self.cancel(oid)

    def portfolio_delta(self) -> float:
        return sum(
            self.positions[iid] * cfg.delta_per_unit
            for iid, cfg in self.instruments.items()
        )

    def portfolio_vega(self) -> float:
        return sum(
            self.positions[iid] * cfg.vega_per_unit
            for iid, cfg in self.instruments.items()
        )

    def last_tick(self, instrument_id: str) -> Optional[dict]:
        return self._visible_ticks.get(instrument_id)

    def _passes_risk(self, instrument_id: str, side: int, qty: int) -> bool:
        cfg = self.instruments[instrument_id]
        inst_limit = cfg.max_position_lots * cfg.instrument.lot_size
        proposed_positions = dict(self.positions)
        proposed_positions[instrument_id] += side * qty
        if abs(proposed_positions[instrument_id]) > inst_limit:
            return False

        limits = self.portfolio_limits
        if limits.max_abs_position is not None:
            gross = sum(abs(pos) for pos in proposed_positions.values())
            if gross > limits.max_abs_position:
                return False
        if limits.max_abs_delta is not None:
            delta = sum(
                proposed_positions[iid] * cfg.delta_per_unit
                for iid, cfg in self.instruments.items()
            )
            if abs(delta) > limits.max_abs_delta:
                return False
        if limits.max_abs_vega is not None:
            vega = sum(
                proposed_positions[iid] * cfg.vega_per_unit
                for iid, cfg in self.instruments.items()
            )
            if abs(vega) > limits.max_abs_vega:
                return False
        return True

    def _events(self) -> list[_Event]:
        events: list[_Event] = []
        seq = 0
        for instrument_id, cfg in self.instruments.items():
            venue = self.venues[cfg.venue]
            cols = cfg.data.columns
            for row in cfg.data.itertuples(index=False):
                raw_tick = dict(zip(cols, row))
                raw_ts = int(raw_tick["ts"])
                aligned_ts = raw_ts + venue.clock_skew_ns
                market_tick = dict(raw_tick)
                market_tick["ts"] = aligned_ts
                market_tick["exchange_ts"] = raw_ts
                feed_tick = dict(market_tick)
                feed_ts = aligned_ts + venue.latency.feed_delay_ns()
                feed_tick["ts"] = feed_ts
                feed_tick["market_ts"] = aligned_ts
                events.append(_Event(aligned_ts, 0, seq, "market", instrument_id, market_tick))
                seq += 1
                events.append(_Event(feed_ts, 1, seq, "feed", instrument_id, feed_tick))
                seq += 1
        return sorted(events)

    def _try_fill(self, instrument_id: str, order: Order, tick: dict):
        ts = tick["ts"]
        if ts < order.ts_active_ns:
            return
        if getattr(order, "_pending_cancel", False) and ts >= getattr(order, "cancel_at", np.inf):
            order.alive = False
            self.open_orders.pop(order.oid, None)
            self._order_instrument.pop(order.oid, None)
            return

        bid, ask = tick["bid"], tick["ask"]
        remaining = order.qty - order.filled
        if remaining <= 0:
            return

        if order.otype == OrderType.IOC:
            if order.side > 0 and order.price >= ask:
                fill_qty = min(remaining, int(tick["ask_qty"]))
                if fill_qty:
                    self._execute(instrument_id, order, fill_qty, ask, ts, maker=False)
            elif order.side < 0 and order.price <= bid:
                fill_qty = min(remaining, int(tick["bid_qty"]))
                if fill_qty:
                    self._execute(instrument_id, order, fill_qty, bid, ts, maker=False)
            order.alive = False
            self.open_orders.pop(order.oid, None)
            self._order_instrument.pop(order.oid, None)
            return

        if order.queue_ahead > 0 and (
            (order.side > 0 and ask < order.price)
            or (order.side < 0 and bid > order.price)
        ):
            self._execute(instrument_id, order, remaining, order.price, ts, maker=True)
        elif order.side > 0 and order.price >= ask:
            fill_qty = min(remaining, int(tick["ask_qty"]))
            if fill_qty:
                self._execute(instrument_id, order, fill_qty, ask, ts, maker=False)
        elif order.side < 0 and order.price <= bid:
            fill_qty = min(remaining, int(tick["bid_qty"]))
            if fill_qty:
                self._execute(instrument_id, order, fill_qty, bid, ts, maker=False)
        else:
            if (order.side > 0 and ask < order.price) or (
                order.side < 0 and bid > order.price
            ):
                self._execute(instrument_id, order, remaining, order.price, ts, maker=True)
            elif (
                not math.isnan(tick.get("last", np.nan))
                and abs(tick["last"] - order.price) < 1e-9
                and tick.get("last_qty", 0) > 0
            ):
                burn = tick["last_qty"]
                if order.queue_ahead > 0:
                    used = min(burn, order.queue_ahead)
                    order.queue_ahead -= used
                    burn -= used
                if burn > 0:
                    self._execute(
                        instrument_id,
                        order,
                        min(remaining, int(burn)),
                        order.price,
                        ts,
                        maker=True,
                    )

        if order.filled >= order.qty:
            order.alive = False
            self.open_orders.pop(order.oid, None)
            self._order_instrument.pop(order.oid, None)

    def _execute(
        self,
        instrument_id: str,
        order: Order,
        qty: int,
        price: float,
        ts_ns: int,
        maker: bool,
    ):
        cfg = self.instruments[instrument_id]
        cost = cfg.costs.cost(order.side, price, qty, cfg.instrument)
        order.filled += qty
        self.positions[instrument_id] += order.side * qty
        self.cash -= order.side * qty * price * cfg.instrument.multiplier
        self.cash -= cost
        self.total_costs += cost
        fill = RoutedFill.from_fill(
            instrument_id,
            Fill(ts_ns, order.oid, order.side, qty, price, cost, maker),
        )
        self.fills.append(fill)
        self.strategy.on_fill(self, fill)

    def _mark_equity(self, ts_ns: int):
        equity = self.cash
        for instrument_id, tick in self._latest_books.items():
            pos = self.positions[instrument_id]
            inst = self.instruments[instrument_id].instrument
            mid = 0.5 * (tick["bid"] + tick["ask"])
            equity += pos * mid * inst.multiplier
        self.equity_curve.append((ts_ns, equity))

    def run(self) -> "MultiBacktestResult":
        self.strategy.on_start(self)
        for event in self._events():
            self._now_ns = event.ts_ns
            if event.kind == "market":
                self._latest_books[event.instrument_id] = event.tick
                for oid in list(self.open_orders):
                    if self._order_instrument.get(oid) != event.instrument_id:
                        continue
                    order = self.open_orders.get(oid)
                    if order is not None:
                        self._try_fill(event.instrument_id, order, event.tick)
                self._mark_equity(event.ts_ns)
            elif event.kind == "feed":
                self._visible_ticks[event.instrument_id] = event.tick
                self.strategy.on_tick(self, event.instrument_id, event.tick)
            else:
                raise RuntimeError(f"unknown event kind {event.kind}")

        self._flatten_open_positions()
        self.strategy.on_end(self)
        return MultiBacktestResult(self)

    def _flatten_open_positions(self):
        if not self._latest_books:
            return
        final_ts = max(tick["ts"] for tick in self._latest_books.values())
        for instrument_id, pos in list(self.positions.items()):
            if pos == 0:
                continue
            tick = self._latest_books.get(instrument_id)
            if tick is None:
                continue
            side = -int(np.sign(pos))
            price = tick["ask"] if side > 0 else tick["bid"]
            self._oid += 1
            order = Order(
                self._oid,
                side,
                abs(pos),
                price,
                OrderType.IOC,
                final_ts,
                final_ts,
            )
            self._execute(instrument_id, order, abs(pos), price, final_ts, maker=False)
        self._mark_equity(final_ts)


class MultiBacktestResult:
    def __init__(self, engine: MultiInstrumentEngine):
        self.engine = engine
        self.equity = pd.DataFrame(engine.equity_curve, columns=["ts", "equity"])
        self.fills = pd.DataFrame([fill.__dict__ for fill in engine.fills])

    def report(self) -> str:
        if self.equity.empty:
            return "no data"
        pnl = float(self.equity.iloc[-1]["equity"])
        fill_count = len(self.fills)
        turnover = (
            float((self.fills["qty"] * self.fills["price"]).sum())
            if fill_count
            else 0.0
        )
        maker_share = float(self.fills["maker"].mean()) if fill_count else 0.0
        otr = self.engine.orders_sent / max(fill_count, 1)
        return "\n".join(
            [
                f"Net PnL          : Rs {pnl:,.0f}",
                f"Total costs      : Rs {self.engine.total_costs:,.0f}",
                f"Fills / Orders   : {fill_count} / {self.engine.orders_sent} (OTR {otr:.1f})",
                f"Maker fill share : {100 * maker_share:.1f}%",
                f"Turnover         : Rs {turnover:,.0f}",
                f"Portfolio delta  : {self.engine.portfolio_delta():,.2f}",
                f"Portfolio vega   : {self.engine.portfolio_vega():,.2f}",
            ]
        )
