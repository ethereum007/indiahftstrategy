from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from engine.hft_backtest import (
    DisplayedLiquidityLedger,
    EventLiquidity,
    Fill,
    IndianCostModel,
    Instrument,
    Kind,
    LatencyModel,
    LiquidityShortfall,
    LIQUIDITY_SHORTFALL_COLUMNS,
    Order,
    OrderRejection,
    ORDER_REJECTION_COLUMNS,
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
        reserve_open_order_risk: bool = True,
        ban_aggressive_self_cross: bool = True,
        persist_displayed_liquidity_depletion: bool = True,
    ):
        if not instruments:
            raise ValueError("at least one instrument is required")
        self.instruments = dict(instruments)
        self.venues = dict(venues)
        self.strategy = strategy
        self.portfolio_limits = portfolio_limits or PortfolioLimits()
        self.qcons = queue_conservatism
        self.reserve_open_order_risk = reserve_open_order_risk
        self.ban_aggressive_self_cross = ban_aggressive_self_cross
        self.persist_displayed_liquidity_depletion = (
            persist_displayed_liquidity_depletion
        )

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
        self.order_rejections: List[OrderRejection] = []
        self.liquidity_shortfalls: List[LiquidityShortfall] = []
        self.shared_event_liquidity_enabled = True
        self._displayed_liquidity = {
            instrument_id: DisplayedLiquidityLedger(
                enabled=persist_displayed_liquidity_depletion,
            )
            for instrument_id in self.instruments
        }
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
        visible = self._visible_ticks.get(instrument_id)
        if visible is None:
            return None

        cfg = self.instruments[instrument_id]
        venue = self.venues[cfg.venue]
        inst = cfg.instrument
        price = round(round(price / inst.tick) * inst.tick, 10)
        risk_rejection = self._risk_rejection(instrument_id, side, qty)
        if risk_rejection is not None:
            reason, projected_min, projected_max, limit = risk_rejection
            self._reject(
                instrument_id=instrument_id,
                side=side,
                qty=qty,
                price=price,
                otype=otype,
                reason=reason,
                projected_min=projected_min,
                projected_max=projected_max,
                limit=limit,
            )
            return None

        active_ns = self._now_ns + venue.latency.order_delay_ns()
        conflict = self._self_cross_conflict(
            instrument_id=instrument_id,
            side=side,
            price=price,
            otype=otype,
            active_ns=active_ns,
        )
        if conflict is not None:
            inst_limit = cfg.max_position_lots * inst.lot_size
            position_min, position_max = self._instrument_position_envelope(
                instrument_id,
                extra=(side, qty),
            )
            self._reject(
                instrument_id=instrument_id,
                side=side,
                qty=qty,
                price=price,
                otype=otype,
                reason="aggressive_self_cross",
                projected_min=position_min,
                projected_max=position_max,
                limit=float("nan"),
                conflicting_oid=conflict.oid,
            )
            return None

        self._oid += 1
        order = Order(
            self._oid,
            side,
            qty,
            price,
            otype,
            ts_sent_ns=self._now_ns,
            ts_active_ns=active_ns,
        )
        if otype == OrderType.LIMIT:
            public_queue = 0.0
            if side > 0 and abs(price - visible["bid"]) < 1e-9:
                public_queue = self.qcons * visible["bid_qty"]
            elif side < 0 and abs(price - visible["ask"]) < 1e-9:
                public_queue = self.qcons * visible["ask_qty"]
            order.public_queue_ahead = max(float(public_queue), 0.0)
            order.queue_ahead = max(
                order.public_queue_ahead,
                self._own_queue_tail(
                    instrument_id=instrument_id,
                    side=side,
                    price=price,
                    active_ns=active_ns,
                ),
            )

        self.open_orders[order.oid] = order
        self._order_instrument[order.oid] = instrument_id
        self.orders_sent += 1
        return order.oid

    def _own_queue_tail(
        self,
        *,
        instrument_id: str,
        side: int,
        price: float,
        active_ns: int,
    ) -> float:
        tail = 0.0
        for oid, order in self.open_orders.items():
            if (
                self._order_instrument.get(oid) != instrument_id
                or not order.alive
                or order.otype != OrderType.LIMIT
                or order.side != side
                or abs(order.price - price) >= 1e-9
                or order.filled >= order.qty
                or (order.ts_active_ns, order.oid) > (active_ns, self._oid)
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

    def cancel(self, oid: int):
        order = self.open_orders.get(oid)
        if order is None:
            return
        instrument_id = self._order_instrument[oid]
        cfg = self.instruments[instrument_id]
        venue = self.venues[cfg.venue]
        order.cancel_sent_ns = self._now_ns
        order.cancel_at = self._now_ns + venue.latency.order_delay_ns()
        order._pending_cancel = True
        if order.cancel_at <= self._now_ns:
            self._remove_order(
                instrument_id,
                order,
                release_queue=True,
            )

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

    def _risk_rejection(
        self,
        instrument_id: str,
        side: int,
        qty: int,
    ) -> tuple[str, float, float, float] | None:
        cfg = self.instruments[instrument_id]
        inst_limit = cfg.max_position_lots * cfg.instrument.lot_size
        if not self.reserve_open_order_risk:
            proposed_positions = dict(self.positions)
            proposed_positions[instrument_id] += side * qty
            proposed = proposed_positions[instrument_id]
            if abs(proposed) > inst_limit:
                return (
                    "instrument_position_limit",
                    float(proposed),
                    float(proposed),
                    float(inst_limit),
                )

            limits = self.portfolio_limits
            if limits.max_abs_position is not None:
                gross = sum(abs(pos) for pos in proposed_positions.values())
                if gross > limits.max_abs_position:
                    return (
                        "portfolio_gross_position_limit",
                        float(gross),
                        float(gross),
                        float(limits.max_abs_position),
                    )
            if limits.max_abs_delta is not None:
                delta = sum(
                    proposed_positions[iid] * item.delta_per_unit
                    for iid, item in self.instruments.items()
                )
                if abs(delta) > limits.max_abs_delta:
                    return (
                        "portfolio_delta_limit",
                        float(delta),
                        float(delta),
                        float(limits.max_abs_delta),
                    )
            if limits.max_abs_vega is not None:
                vega = sum(
                    proposed_positions[iid] * item.vega_per_unit
                    for iid, item in self.instruments.items()
                )
                if abs(vega) > limits.max_abs_vega:
                    return (
                        "portfolio_vega_limit",
                        float(vega),
                        float(vega),
                        float(limits.max_abs_vega),
                    )
            return None

        pending = self._pending_quantities(extra=(instrument_id, side, qty))
        position_ranges = {
            iid: (
                self.positions[iid] - pending[iid][1],
                self.positions[iid] + pending[iid][0],
            )
            for iid in self.instruments
        }
        position_min, position_max = position_ranges[instrument_id]
        if position_min < -inst_limit or position_max > inst_limit:
            return (
                "instrument_position_limit",
                float(position_min),
                float(position_max),
                float(inst_limit),
            )

        limits = self.portfolio_limits
        if limits.max_abs_position is not None:
            gross = sum(
                max(abs(position_min), abs(position_max))
                for position_min, position_max in position_ranges.values()
            )
            if gross > limits.max_abs_position:
                return (
                    "portfolio_gross_position_limit",
                    0.0,
                    float(gross),
                    float(limits.max_abs_position),
                )
        if limits.max_abs_delta is not None:
            delta_min, delta_max = self._portfolio_exposure_envelope(
                pending,
                exposure_name="delta_per_unit",
            )
            if delta_min < -limits.max_abs_delta or delta_max > limits.max_abs_delta:
                return (
                    "portfolio_delta_limit",
                    float(delta_min),
                    float(delta_max),
                    float(limits.max_abs_delta),
                )
        if limits.max_abs_vega is not None:
            vega_min, vega_max = self._portfolio_exposure_envelope(
                pending,
                exposure_name="vega_per_unit",
            )
            if vega_min < -limits.max_abs_vega or vega_max > limits.max_abs_vega:
                return (
                    "portfolio_vega_limit",
                    float(vega_min),
                    float(vega_max),
                    float(limits.max_abs_vega),
                )
        return None

    def _pending_quantities(
        self,
        *,
        extra: tuple[str, int, int] | None = None,
    ) -> dict[str, list[int]]:
        pending = {iid: [0, 0] for iid in self.instruments}
        for oid, order in self.open_orders.items():
            if not order.alive:
                continue
            instrument_id = self._order_instrument.get(oid)
            if instrument_id is None:
                continue
            remaining = max(int(order.qty) - int(order.filled), 0)
            pending[instrument_id][0 if order.side > 0 else 1] += remaining
        if extra is not None:
            instrument_id, side, qty = extra
            pending[instrument_id][0 if side > 0 else 1] += qty
        return pending

    def _instrument_position_envelope(
        self,
        instrument_id: str,
        *,
        extra: tuple[int, int] | None = None,
    ) -> tuple[int, int]:
        pending_extra = (
            (instrument_id, extra[0], extra[1])
            if extra is not None
            else None
        )
        pending = self._pending_quantities(extra=pending_extra)
        buys, sells = pending[instrument_id]
        position = self.positions[instrument_id]
        return position - sells, position + buys

    def _portfolio_exposure_envelope(
        self,
        pending: Mapping[str, list[int]],
        *,
        exposure_name: str,
    ) -> tuple[float, float]:
        current = 0.0
        negative_pending = 0.0
        positive_pending = 0.0
        for instrument_id, cfg in self.instruments.items():
            exposure = float(getattr(cfg, exposure_name))
            current += self.positions[instrument_id] * exposure
            buys, sells = pending[instrument_id]
            for contribution in (buys * exposure, -sells * exposure):
                if contribution < 0:
                    negative_pending += contribution
                else:
                    positive_pending += contribution
        return current + negative_pending, current + positive_pending

    def _self_cross_conflict(
        self,
        *,
        instrument_id: str,
        side: int,
        price: float,
        otype: OrderType,
        active_ns: int,
    ) -> Order | None:
        if not self.ban_aggressive_self_cross:
            return None
        for oid, order in self.open_orders.items():
            if (
                self._order_instrument.get(oid) != instrument_id
                or not order.alive
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
        instrument_id: str,
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
                ts_ns=int(self._now_ns),
                instrument_id=instrument_id,
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

    def _advance_later_own_queue(
        self,
        instrument_id: str,
        order: Order,
        qty: int,
        *,
        pending_after_ns: int | None = None,
        exclude_post_cancel_orders: bool = False,
    ) -> None:
        if qty <= 0 or order.otype != OrderType.LIMIT:
            return
        priority = (order.ts_active_ns, order.oid)
        for oid, later in self.open_orders.items():
            if (
                oid == order.oid
                or self._order_instrument.get(oid) != instrument_id
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

    def _release_own_queue(self, instrument_id: str, order: Order) -> None:
        remaining = max(int(order.qty) - int(order.filled), 0)
        self._advance_later_own_queue(
            instrument_id,
            order,
            remaining,
            exclude_post_cancel_orders=True,
        )

    def _remove_order(
        self,
        instrument_id: str,
        order: Order,
        *,
        release_queue: bool = False,
    ) -> None:
        if release_queue:
            self._release_own_queue(instrument_id, order)
        order.alive = False
        self.open_orders.pop(order.oid, None)
        self._order_instrument.pop(order.oid, None)

    def _record_liquidity_shortfall(
        self,
        *,
        instrument_id: str,
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
                instrument_id=instrument_id,
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
        instrument_id: str,
        order: Order,
        *,
        liquidity: EventLiquidity,
        price: float,
        ts_ns: int,
        requested_qty: int,
    ) -> None:
        source = "ask_display" if order.side > 0 else "bid_display"
        observed_qty, carried_depletion_qty = liquidity.displayed_context(
            order.side
        )
        available, fill_qty = liquidity.consume_displayed(
            order.side,
            requested_qty,
        )
        if fill_qty > 0:
            self._advance_later_own_queue(
                instrument_id,
                order,
                fill_qty,
            )
            self._execute(
                instrument_id,
                order,
                fill_qty,
                price,
                ts_ns,
                maker=False,
            )
        self._record_liquidity_shortfall(
            instrument_id=instrument_id,
            order=order,
            ts_ns=ts_ns,
            requested_qty=requested_qty,
            available_qty=available,
            filled_qty=fill_qty,
            liquidity_source=source,
            observed_qty=observed_qty,
            carried_depletion_qty=carried_depletion_qty,
        )

    def _try_fill(
        self,
        instrument_id: str,
        order: Order,
        tick: dict,
        liquidity: EventLiquidity,
    ):
        ts = tick["ts"]
        if ts < order.ts_active_ns:
            return
        if getattr(order, "_pending_cancel", False) and ts >= getattr(order, "cancel_at", np.inf):
            self._remove_order(
                instrument_id,
                order,
                release_queue=True,
            )
            return

        bid, ask = tick["bid"], tick["ask"]
        remaining = order.qty - order.filled
        if remaining <= 0:
            return

        if order.otype == OrderType.IOC:
            if order.side > 0 and order.price >= ask:
                self._fill_from_displayed(
                    instrument_id,
                    order,
                    liquidity=liquidity,
                    price=ask,
                    ts_ns=ts,
                    requested_qty=remaining,
                )
            elif order.side < 0 and order.price <= bid:
                self._fill_from_displayed(
                    instrument_id,
                    order,
                    liquidity=liquidity,
                    price=bid,
                    ts_ns=ts,
                    requested_qty=remaining,
                )
            self._remove_order(instrument_id, order)
            return

        if order.queue_ahead > 0 and (
            (order.side > 0 and ask < order.price)
            or (order.side < 0 and bid > order.price)
        ):
            self._advance_later_own_queue(
                instrument_id,
                order,
                remaining,
            )
            self._execute(instrument_id, order, remaining, order.price, ts, maker=True)
        elif order.side > 0 and order.price >= ask:
            self._fill_from_displayed(
                instrument_id,
                order,
                liquidity=liquidity,
                price=ask,
                ts_ns=ts,
                requested_qty=remaining,
            )
        elif order.side < 0 and order.price <= bid:
            self._fill_from_displayed(
                instrument_id,
                order,
                liquidity=liquidity,
                price=bid,
                ts_ns=ts,
                requested_qty=remaining,
            )
        else:
            if (order.side > 0 and ask < order.price) or (
                order.side < 0 and bid > order.price
            ):
                self._advance_later_own_queue(
                    instrument_id,
                    order,
                    remaining,
                )
                self._execute(instrument_id, order, remaining, order.price, ts, maker=True)
            elif (
                not math.isnan(tick.get("last", np.nan))
                and abs(tick["last"] - order.price) < 1e-9
                and liquidity.last_qty > 0
            ):
                queue_before = max(float(order.queue_ahead), 0.0)
                queue_consumed = min(liquidity.last_qty, queue_before)
                order.queue_ahead = max(
                    queue_before - liquidity.last_qty,
                    0.0,
                )
                order.public_queue_ahead = max(
                    float(order.public_queue_ahead) - liquidity.last_qty,
                    0.0,
                )
                available = max(liquidity.last_qty - queue_before, 0.0)
                fill_qty = min(
                    remaining,
                    max(int(math.floor(available)), 0),
                )
                if fill_qty > 0:
                    self._advance_later_own_queue(
                        instrument_id,
                        order,
                        fill_qty,
                        pending_after_ns=ts,
                    )
                    self._execute(
                        instrument_id,
                        order,
                        fill_qty,
                        order.price,
                        ts,
                        maker=True,
                    )
                if 0 < fill_qty < remaining:
                    self._record_liquidity_shortfall(
                        instrument_id=instrument_id,
                        order=order,
                        ts_ns=ts,
                        requested_qty=remaining,
                        available_qty=available,
                        filled_qty=fill_qty,
                        liquidity_source="trade_print",
                        queue_ahead_before=queue_before,
                        queue_consumed=queue_consumed,
                    )

        if order.filled >= order.qty:
            self._remove_order(instrument_id, order)

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
                liquidity = self._displayed_liquidity[
                    event.instrument_id
                ].event_liquidity(event.tick)
                order_ids = sorted(
                    self.open_orders,
                    key=lambda oid: (
                        self.open_orders[oid].ts_active_ns,
                        oid,
                    ),
                )
                for oid in order_ids:
                    if self._order_instrument.get(oid) != event.instrument_id:
                        continue
                    order = self.open_orders.get(oid)
                    if order is not None:
                        self._try_fill(
                            event.instrument_id,
                            order,
                            event.tick,
                            liquidity,
                        )
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
        self.order_rejections = pd.DataFrame(
            [rejection.__dict__ for rejection in engine.order_rejections],
            columns=ORDER_REJECTION_COLUMNS,
        )
        self.liquidity_shortfalls = pd.DataFrame(
            [shortfall.__dict__ for shortfall in engine.liquidity_shortfalls],
            columns=LIQUIDITY_SHORTFALL_COLUMNS,
        )

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
                f"Pre-trade rejects: {len(self.order_rejections)}",
                f"Liquidity gaps   : {len(self.liquidity_shortfalls)} events",
                f"Maker fill share : {100 * maker_share:.1f}%",
                f"Turnover         : Rs {turnover:,.0f}",
                f"Portfolio delta  : {self.engine.portfolio_delta():,.2f}",
                f"Portfolio vega   : {self.engine.portfolio_vega():,.2f}",
            ]
        )
