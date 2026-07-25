from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from engine.hft_backtest import (
    CANCELLATION_COLUMNS,
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
    OrderCancellation,
    OrderHorizonState,
    ORDER_HORIZON_STATE_COLUMNS,
    OrderRejection,
    ORDER_REJECTION_COLUMNS,
    OrderSubmission,
    ORDER_SUBMISSION_COLUMNS,
    OrderType,
    QueueInitialization,
    QUEUE_INITIALIZATION_COLUMNS,
    PassivePriceThrough,
    PASSIVE_PRICE_THROUGH_COLUMNS,
    RestingTransition,
    RESTING_TRANSITION_COLUMNS,
    TerminalLiquidation,
    TERMINAL_LIQUIDATION_COLUMNS,
    _floor_to_lot,
    _limit_book_relation,
    _nonnegative_qty,
    _quantize_price,
    _validate_venue_order_metadata,
    _venue_order_rejection,
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


@dataclass(frozen=True)
class IOCOrderIntent:
    instrument_id: str
    side: int
    qty: int
    price: float


@dataclass(frozen=True)
class IOCBatchPreflightResult:
    passed: bool
    reason: str
    instrument_id: str = ""
    projected_min: float = float("nan")
    projected_max: float = float("nan")
    limit: float = float("nan")
    conflicting_oid: int | None = None
    visible_capacity_checked: bool = False
    min_visible_fill_ratio: float = float("nan")
    limiting_instrument_id: str = ""
    requested_qty: int = 0
    available_qty: float = float("nan")
    touch_price: float = float("nan")
    limit_price: float = float("nan")


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
            _validate_venue_order_metadata(cfg.instrument)
            cfg.data = self._prep(cfg.data)
            if cfg.costs is None:
                cfg.costs = self._default_costs(cfg.instrument)

        self._oid = 0
        self._now_ns = 0
        self._visible_ticks: Dict[str, dict] = {}
        self._latest_books: Dict[str, dict] = {}
        self._latest_liquidity: Dict[str, EventLiquidity] = {}
        self._order_instrument: Dict[int, str] = {}

        self.open_orders: Dict[int, Order] = {}
        self.fills: List[RoutedFill] = []
        self.order_submissions: List[OrderSubmission] = []
        self.order_rejections: List[OrderRejection] = []
        self.order_cancellations: List[OrderCancellation] = []
        self._cancellation_index_by_oid: Dict[int, int] = {}
        self.order_horizon_states: List[OrderHorizonState] = []
        self.liquidity_shortfalls: List[LiquidityShortfall] = []
        self.queue_initializations: List[QueueInitialization] = []
        self.resting_transitions: List[RestingTransition] = []
        self.passive_price_throughs: List[PassivePriceThrough] = []
        self.terminal_liquidations: List[TerminalLiquidation] = []
        self.shared_event_liquidity_enabled = True
        self.arrival_queue_initialization_enabled = True
        self.venue_order_validation_enabled = True
        self.lot_conserving_fills_enabled = True
        self.causal_event_ordering_enabled = True
        self.order_submission_tracking_enabled = True
        self.cancel_lifecycle_tracking_enabled = True
        self.order_horizon_tracking_enabled = True
        self.passive_price_through_depth_constrained_enabled = True
        self.terminal_liquidation_depth_constrained_enabled = True
        self.limit_orders_sent = 0
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
        if isinstance(qty, bool) or not isinstance(qty, (int, np.integer)):
            raise ValueError("qty must be an integer")
        if qty <= 0:
            raise ValueError("qty must be positive")

        cfg = self.instruments[instrument_id]
        venue = self.venues[cfg.venue]
        inst = cfg.instrument
        try:
            price = float(price)
        except (TypeError, ValueError) as exc:
            raise ValueError("price must be numeric") from exc
        venue_rejection = _venue_order_rejection(inst, qty, price)
        if venue_rejection is not None:
            reason, limit = venue_rejection
            position = self.positions[instrument_id]
            self._reject(
                instrument_id=instrument_id,
                side=side,
                qty=qty,
                price=price,
                otype=otype,
                reason=reason,
                projected_min=position,
                projected_max=position,
                limit=limit,
            )
            return None

        visible = self._visible_ticks.get(instrument_id)
        if visible is None:
            return None

        price = _quantize_price(price, inst.tick)
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
        self.order_submissions.append(
            OrderSubmission(
                ts_sent_ns=self._now_ns,
                ts_active_ns=active_ns,
                order_latency_ns=active_ns - self._now_ns,
                instrument_id=instrument_id,
                oid=order.oid,
                side=side,
                qty=qty,
                price=price,
                order_type=otype.value,
            )
        )
        if otype == OrderType.LIMIT:
            self.limit_orders_sent += 1
            market_ts = int(visible.get("market_ts", visible["ts"]))
            if active_ns <= market_ts:
                self._initialize_limit_queue(
                    instrument_id,
                    order,
                    visible,
                    snapshot_ts=market_ts,
                    mode="send_snapshot",
                )

        self.open_orders[order.oid] = order
        self._order_instrument[order.oid] = instrument_id
        self.orders_sent += 1
        return order.oid

    def preflight_ioc_batch(
        self,
        intents: list[IOCOrderIntent] | tuple[IOCOrderIntent, ...],
    ) -> IOCBatchPreflightResult:
        """Validate a correlated IOC package without mutating engine state."""
        if not intents:
            raise ValueError("intents must not be empty")

        normalized: list[IOCOrderIntent] = []
        for intent in intents:
            if not isinstance(intent, IOCOrderIntent):
                raise TypeError("intents must contain IOCOrderIntent values")
            instrument_id = intent.instrument_id
            side = intent.side
            qty = intent.qty
            if instrument_id not in self.instruments:
                raise KeyError(f"unknown instrument_id {instrument_id}")
            if side not in (-1, 1):
                raise ValueError("side must be +1 buy or -1 sell")
            if isinstance(qty, bool) or not isinstance(
                qty,
                (int, np.integer),
            ):
                raise ValueError("qty must be an integer")
            if qty <= 0:
                raise ValueError("qty must be positive")
            try:
                price = float(intent.price)
            except (TypeError, ValueError) as exc:
                raise ValueError("price must be numeric") from exc

            cfg = self.instruments[instrument_id]
            inst = cfg.instrument
            venue_rejection = _venue_order_rejection(
                inst,
                qty,
                price,
            )
            if venue_rejection is not None:
                reason, limit = venue_rejection
                position = float(self.positions[instrument_id])
                return IOCBatchPreflightResult(
                    passed=False,
                    reason=reason,
                    instrument_id=instrument_id,
                    projected_min=position,
                    projected_max=position,
                    limit=float(limit),
                )
            if self._visible_ticks.get(instrument_id) is None:
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="missing_visible_book",
                    instrument_id=instrument_id,
                )

            price = _quantize_price(price, inst.tick)
            conflict = self._preflight_self_cross_conflict(
                instrument_id=instrument_id,
                side=side,
                price=price,
            )
            if conflict is not None:
                position_min, position_max = (
                    self._instrument_position_envelope(
                        instrument_id,
                        extra=(side, qty),
                    )
                )
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="aggressive_self_cross",
                    instrument_id=instrument_id,
                    projected_min=float(position_min),
                    projected_max=float(position_max),
                    conflicting_oid=conflict.oid,
                )
            normalized.append(
                IOCOrderIntent(
                    instrument_id=instrument_id,
                    side=side,
                    qty=int(qty),
                    price=price,
                )
            )

        risk_rejection = self._ioc_batch_risk_rejection(normalized)
        if risk_rejection is not None:
            return risk_rejection
        return self._ioc_batch_visible_capacity(normalized)

    def _own_queue_tail(
        self,
        *,
        instrument_id: str,
        side: int,
        price: float,
        active_ns: int,
        priority_oid: int,
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
        instrument_id: str,
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
            instrument_id=instrument_id,
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
                instrument_id=instrument_id,
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
        instrument_id: str,
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
                instrument_id=instrument_id,
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
            instrument_id=instrument_id,
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
        instrument_id: str,
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
            instrument_id=instrument_id,
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

    def cancel(self, oid: int):
        order = self.open_orders.get(oid)
        if (
            order is None
            or not order.alive
            or order.filled >= order.qty
            or getattr(order, "_pending_cancel", False)
        ):
            return
        instrument_id = self._order_instrument[oid]
        cfg = self.instruments[instrument_id]
        venue = self.venues[cfg.venue]
        ts_sent_ns = int(self._now_ns)
        ts_effective_ns = ts_sent_ns + venue.latency.order_delay_ns()
        remaining_qty = max(int(order.qty) - int(order.filled), 0)
        order.cancel_sent_ns = ts_sent_ns
        order.cancel_at = ts_effective_ns
        order._pending_cancel = True
        self._cancellation_index_by_oid[order.oid] = len(
            self.order_cancellations
        )
        self.order_cancellations.append(
            OrderCancellation(
                ts_sent_ns=ts_sent_ns,
                ts_effective_ns=ts_effective_ns,
                ts_status_ns=None,
                instrument_id=instrument_id,
                oid=order.oid,
                side=order.side,
                price=float(order.price),
                order_type=order.otype.value,
                requested_qty=remaining_qty,
                filled_while_pending_qty=0,
                remaining_qty=remaining_qty,
                status="pending",
            )
        )
        if ts_effective_ns <= ts_sent_ns:
            self._complete_cancel(instrument_id, order)

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

    def _ioc_batch_risk_rejection(
        self,
        intents: list[IOCOrderIntent],
    ) -> IOCBatchPreflightResult | None:
        if not self.reserve_open_order_risk:
            proposed_positions = dict(self.positions)
            for intent in intents:
                instrument_id = intent.instrument_id
                proposed_positions[instrument_id] += (
                    intent.side * intent.qty
                )
                cfg = self.instruments[instrument_id]
                inst_limit = (
                    cfg.max_position_lots
                    * cfg.instrument.lot_size
                )
                proposed = proposed_positions[instrument_id]
                if abs(proposed) > inst_limit:
                    return IOCBatchPreflightResult(
                        passed=False,
                        reason="instrument_position_limit",
                        instrument_id=instrument_id,
                        projected_min=float(proposed),
                        projected_max=float(proposed),
                        limit=float(inst_limit),
                    )

                limits = self.portfolio_limits
                if limits.max_abs_position is not None:
                    gross = sum(
                        abs(pos)
                        for pos in proposed_positions.values()
                    )
                    if gross > limits.max_abs_position:
                        return IOCBatchPreflightResult(
                            passed=False,
                            reason="portfolio_gross_position_limit",
                            projected_min=float(gross),
                            projected_max=float(gross),
                            limit=float(limits.max_abs_position),
                        )
                if limits.max_abs_delta is not None:
                    delta = sum(
                        proposed_positions[iid]
                        * item.delta_per_unit
                        for iid, item in self.instruments.items()
                    )
                    if abs(delta) > limits.max_abs_delta:
                        return IOCBatchPreflightResult(
                            passed=False,
                            reason="portfolio_delta_limit",
                            projected_min=float(delta),
                            projected_max=float(delta),
                            limit=float(limits.max_abs_delta),
                        )
                if limits.max_abs_vega is not None:
                    vega = sum(
                        proposed_positions[iid]
                        * item.vega_per_unit
                        for iid, item in self.instruments.items()
                    )
                    if abs(vega) > limits.max_abs_vega:
                        return IOCBatchPreflightResult(
                            passed=False,
                            reason="portfolio_vega_limit",
                            projected_min=float(vega),
                            projected_max=float(vega),
                            limit=float(limits.max_abs_vega),
                        )
            return None

        pending = self._pending_quantities(
            extras=[
                (
                    intent.instrument_id,
                    intent.side,
                    intent.qty,
                )
                for intent in intents
            ]
        )
        position_ranges = {
            iid: (
                self.positions[iid] - pending[iid][1],
                self.positions[iid] + pending[iid][0],
            )
            for iid in self.instruments
        }
        checked_instruments: set[str] = set()
        for intent in intents:
            instrument_id = intent.instrument_id
            if instrument_id in checked_instruments:
                continue
            checked_instruments.add(instrument_id)
            cfg = self.instruments[instrument_id]
            inst_limit = (
                cfg.max_position_lots * cfg.instrument.lot_size
            )
            position_min, position_max = position_ranges[instrument_id]
            if (
                position_min < -inst_limit
                or position_max > inst_limit
            ):
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="instrument_position_limit",
                    instrument_id=instrument_id,
                    projected_min=float(position_min),
                    projected_max=float(position_max),
                    limit=float(inst_limit),
                )

        limits = self.portfolio_limits
        if limits.max_abs_position is not None:
            gross = sum(
                max(abs(position_min), abs(position_max))
                for position_min, position_max in position_ranges.values()
            )
            if gross > limits.max_abs_position:
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="portfolio_gross_position_limit",
                    projected_min=0.0,
                    projected_max=float(gross),
                    limit=float(limits.max_abs_position),
                )
        if limits.max_abs_delta is not None:
            delta_min, delta_max = self._portfolio_exposure_envelope(
                pending,
                exposure_name="delta_per_unit",
            )
            if (
                delta_min < -limits.max_abs_delta
                or delta_max > limits.max_abs_delta
            ):
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="portfolio_delta_limit",
                    projected_min=float(delta_min),
                    projected_max=float(delta_max),
                    limit=float(limits.max_abs_delta),
                )
        if limits.max_abs_vega is not None:
            vega_min, vega_max = self._portfolio_exposure_envelope(
                pending,
                exposure_name="vega_per_unit",
            )
            if (
                vega_min < -limits.max_abs_vega
                or vega_max > limits.max_abs_vega
            ):
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="portfolio_vega_limit",
                    projected_min=float(vega_min),
                    projected_max=float(vega_max),
                    limit=float(limits.max_abs_vega),
                )
        return None

    def _ioc_batch_visible_capacity(
        self,
        intents: list[IOCOrderIntent],
    ) -> IOCBatchPreflightResult:
        reserved: dict[tuple[str, int], int] = {}
        limiting_instrument_id = ""
        limiting_requested_qty = 0
        limiting_available_qty = float("nan")
        limiting_touch_price = float("nan")
        limiting_limit_price = float("nan")
        min_fill_ratio = float("inf")

        for intent in intents:
            cfg = self.instruments[intent.instrument_id]
            visible = self._visible_ticks[intent.instrument_id]
            if intent.side > 0:
                touch_price = float(visible["ask"])
                displayed_qty = visible.get("ask_qty", 0)
                marketable = intent.price >= touch_price
            else:
                touch_price = float(visible["bid"])
                displayed_qty = visible.get("bid_qty", 0)
                marketable = intent.price <= touch_price

            key = (intent.instrument_id, intent.side)
            venue_qty = _floor_to_lot(
                _nonnegative_qty(displayed_qty),
                cfg.instrument.lot_size,
            )
            available_qty = max(
                venue_qty - reserved.get(key, 0),
                0,
            )
            fill_ratio = (
                float(available_qty) / intent.qty
                if marketable
                else 0.0
            )
            if fill_ratio < min_fill_ratio:
                min_fill_ratio = fill_ratio
                limiting_instrument_id = intent.instrument_id
                limiting_requested_qty = intent.qty
                limiting_available_qty = float(available_qty)
                limiting_touch_price = touch_price
                limiting_limit_price = intent.price

            if not marketable:
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="visible_ioc_not_marketable",
                    instrument_id=intent.instrument_id,
                    visible_capacity_checked=True,
                    min_visible_fill_ratio=0.0,
                    limiting_instrument_id=intent.instrument_id,
                    requested_qty=intent.qty,
                    available_qty=float(available_qty),
                    touch_price=touch_price,
                    limit_price=intent.price,
                )
            if available_qty < intent.qty:
                return IOCBatchPreflightResult(
                    passed=False,
                    reason="visible_ioc_capacity_shortfall",
                    instrument_id=intent.instrument_id,
                    visible_capacity_checked=True,
                    min_visible_fill_ratio=fill_ratio,
                    limiting_instrument_id=intent.instrument_id,
                    requested_qty=intent.qty,
                    available_qty=float(available_qty),
                    touch_price=touch_price,
                    limit_price=intent.price,
                )
            reserved[key] = reserved.get(key, 0) + intent.qty

        return IOCBatchPreflightResult(
            passed=True,
            reason="passed",
            visible_capacity_checked=True,
            min_visible_fill_ratio=min_fill_ratio,
            limiting_instrument_id=limiting_instrument_id,
            requested_qty=limiting_requested_qty,
            available_qty=limiting_available_qty,
            touch_price=limiting_touch_price,
            limit_price=limiting_limit_price,
        )

    def _pending_quantities(
        self,
        *,
        extra: tuple[str, int, int] | None = None,
        extras: list[tuple[str, int, int]] | None = None,
    ) -> dict[str, list[int]]:
        if extra is not None and extras is not None:
            raise ValueError("provide extra or extras, not both")
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
        if extras is not None:
            for instrument_id, side, qty in extras:
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

    def _preflight_self_cross_conflict(
        self,
        *,
        instrument_id: str,
        side: int,
        price: float,
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
            if (
                getattr(order, "_pending_cancel", False)
                and getattr(order, "cancel_at", np.inf) <= self._now_ns
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

    def _pending_cancellation(
        self,
        order: Order,
    ) -> OrderCancellation | None:
        index = self._cancellation_index_by_oid.get(order.oid)
        if index is None:
            return None
        cancellation = self.order_cancellations[index]
        return cancellation if cancellation.status == "pending" else None

    def _resolve_cancellation(
        self,
        order: Order,
        *,
        status: str,
        ts_status_ns: int,
    ) -> None:
        cancellation = self._pending_cancellation(order)
        if cancellation is None:
            return
        cancellation.ts_status_ns = int(ts_status_ns)
        cancellation.remaining_qty = max(
            int(order.qty) - int(order.filled),
            0,
        )
        cancellation.status = status
        order._pending_cancel = False
        self._cancellation_index_by_oid.pop(order.oid, None)

    def _record_pending_cancel_fill(self, order: Order, qty: int) -> None:
        cancellation = self._pending_cancellation(order)
        if cancellation is None:
            return
        cancellation.filled_while_pending_qty += int(qty)
        cancellation.remaining_qty = max(
            int(order.qty) - int(order.filled),
            0,
        )

    def _complete_cancel(
        self,
        instrument_id: str,
        order: Order,
    ) -> None:
        cancellation = self._pending_cancellation(order)
        if cancellation is None:
            return
        status = (
            "effective_after_partial_fill"
            if cancellation.filled_while_pending_qty > 0
            else "effective"
        )
        self._resolve_cancellation(
            order,
            status=status,
            ts_status_ns=cancellation.ts_effective_ns,
        )
        self._remove_order(
            instrument_id,
            order,
            release_queue=True,
        )

    def _expire_cancels(self, now_ns: int) -> None:
        due = sorted(
            (
                order
                for order in self.open_orders.values()
                if (
                    getattr(order, "_pending_cancel", False)
                    and int(getattr(order, "cancel_at", now_ns + 1))
                    <= int(now_ns)
                )
            ),
            key=lambda order: (int(order.cancel_at), order.oid),
        )
        for order in due:
            instrument_id = self._order_instrument.get(order.oid)
            if instrument_id is not None:
                self._complete_cancel(instrument_id, order)

    def _finalize_pending_cancels(self, replay_end_ns: int) -> None:
        for order in list(self.open_orders.values()):
            if self._pending_cancellation(order) is None:
                continue
            self._resolve_cancellation(
                order,
                status="pending_at_replay_end",
                ts_status_ns=int(replay_end_ns),
            )

    def _capture_order_horizon_states(self, replay_end_ns: int) -> None:
        self.order_horizon_states = []
        for order in sorted(
            self.open_orders.values(),
            key=lambda value: (value.ts_active_ns, value.oid),
        ):
            remaining_qty = max(
                int(order.qty) - int(order.filled),
                0,
            )
            if not order.alive or remaining_qty <= 0:
                continue
            instrument_id = self._order_instrument.get(order.oid)
            if instrument_id is None:
                continue
            active_at_horizon = int(order.ts_active_ns) <= int(
                replay_end_ns
            )
            cancel_pending = bool(
                getattr(order, "_pending_cancel", False)
            )
            if cancel_pending:
                state = "cancel_pending"
            elif not active_at_horizon:
                state = "pending_activation"
            elif order.otype == OrderType.IOC:
                state = "active_ioc"
            else:
                state = "active_limit"
            cancel_effective_ns = (
                int(order.cancel_at)
                if cancel_pending
                else None
            )
            self.order_horizon_states.append(
                OrderHorizonState(
                    ts_horizon_ns=int(replay_end_ns),
                    instrument_id=instrument_id,
                    oid=order.oid,
                    side=order.side,
                    price=float(order.price),
                    order_type=order.otype.value,
                    qty=int(order.qty),
                    filled_qty=int(order.filled),
                    remaining_qty=remaining_qty,
                    ts_sent_ns=int(order.ts_sent_ns),
                    ts_active_ns=int(order.ts_active_ns),
                    active_at_horizon=active_at_horizon,
                    cancel_pending=cancel_pending,
                    cancel_effective_ns=cancel_effective_ns,
                    state=state,
                )
            )

    def _remove_order(
        self,
        instrument_id: str,
        order: Order,
        *,
        release_queue: bool = False,
        close_ts_ns: int | None = None,
    ) -> None:
        cancellation = self._pending_cancellation(order)
        if cancellation is not None:
            remaining_qty = max(int(order.qty) - int(order.filled), 0)
            self._resolve_cancellation(
                order,
                status=(
                    "filled_before_effective"
                    if remaining_qty == 0
                    else "closed_before_effective"
                ),
                ts_status_ns=(
                    int(close_ts_ns)
                    if close_ts_ns is not None
                    else int(self._now_ns)
                ),
            )
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
            lot_size=self.instruments[instrument_id].instrument.lot_size,
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
                maker=maker,
            )
        self._record_liquidity_shortfall(
            instrument_id=instrument_id,
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
        instrument_id: str,
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
            instrument_id=instrument_id,
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
            instrument_id,
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
                instrument_id=instrument_id,
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
            self._complete_cancel(instrument_id, order)
            return

        if order.otype == OrderType.LIMIT:
            if order.resting_transition_index is not None:
                self._initialize_deferred_residual_queue(
                    instrument_id,
                    order,
                    tick,
                    snapshot_ts=int(ts),
                )
            else:
                self._initialize_limit_queue(
                    instrument_id,
                    order,
                    tick,
                    snapshot_ts=int(ts),
                    mode="arrival_snapshot",
                )
            if not order.queue_initialized:
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
            self._remove_order(
                instrument_id,
                order,
                close_ts_ns=int(ts),
            )
            return

        if not order.resting_at_venue:
            self._transition_limit_to_resting(
                instrument_id,
                order,
                tick,
                snapshot_ts=int(ts),
            )
            if not order.queue_initialized:
                return

        if order.resting_at_venue and (
            (order.side > 0 and ask < order.price)
            or (order.side < 0 and bid > order.price)
        ):
            self._fill_resting_from_price_through(
                instrument_id,
                order,
                tick,
                liquidity,
                ts_ns=int(ts),
                requested_qty=remaining,
            )
        elif (
            not order.resting_at_venue
            and order.side > 0
            and order.price >= ask
        ):
            self._fill_from_displayed(
                instrument_id,
                order,
                liquidity=liquidity,
                price=ask,
                ts_ns=ts,
                requested_qty=remaining,
            )
        elif (
            not order.resting_at_venue
            and order.side < 0
            and order.price <= bid
        ):
            self._fill_from_displayed(
                instrument_id,
                order,
                liquidity=liquidity,
                price=bid,
                ts_ns=ts,
                requested_qty=remaining,
            )
        else:
            if (
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
                    _floor_to_lot(
                        available,
                        self.instruments[instrument_id].instrument.lot_size,
                    ),
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
                if available > 0 and fill_qty < remaining:
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
            self._remove_order(
                instrument_id,
                order,
                close_ts_ns=int(ts),
            )

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
        if qty % cfg.instrument.lot_size != 0:
            raise RuntimeError("fill quantity must preserve instrument lot size")
        cost = cfg.costs.cost(order.side, price, qty, cfg.instrument)
        order.filled += qty
        self._record_pending_cancel_fill(order, qty)
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
            self._expire_cancels(event.ts_ns)
            if event.kind == "market":
                self._latest_books[event.instrument_id] = event.tick
                liquidity = self._displayed_liquidity[
                    event.instrument_id
                ].event_liquidity(event.tick)
                self._latest_liquidity[event.instrument_id] = liquidity
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
        self._capture_order_horizon_states(self._now_ns)
        self._finalize_pending_cancels(self._now_ns)
        return MultiBacktestResult(self)

    def _flatten_open_positions(self):
        if not self._latest_books:
            return
        final_ts = max(
            self._now_ns,
            max(tick["ts"] for tick in self._latest_books.values()),
        )
        self._now_ns = int(final_ts)
        for instrument_id, pos in list(self.positions.items()):
            if pos == 0:
                continue
            tick = self._latest_books.get(instrument_id)
            if tick is None:
                continue
            side = -int(np.sign(pos))
            price = tick["ask"] if side > 0 else tick["bid"]
            requested_qty = abs(pos)
            self._oid += 1
            order = Order(
                self._oid,
                side,
                requested_qty,
                price,
                OrderType.IOC,
                final_ts,
                final_ts,
            )
            source = (
                "terminal_ask_display"
                if side > 0
                else "terminal_bid_display"
            )
            liquidity = self._latest_liquidity.get(instrument_id)
            if liquidity is None:
                liquidity = self._displayed_liquidity[
                    instrument_id
                ].event_liquidity(tick)
            (
                available_qty,
                filled_qty,
                observed_qty,
                carried_depletion_qty,
            ) = self._fill_from_displayed(
                instrument_id,
                order,
                liquidity=liquidity,
                price=price,
                ts_ns=final_ts,
                requested_qty=requested_qty,
                liquidity_source=source,
            )
            shortfall_qty = requested_qty - filled_qty
            self.terminal_liquidations.append(
                TerminalLiquidation(
                    ts_ns=int(final_ts),
                    book_ts_ns=int(tick["ts"]),
                    instrument_id=instrument_id,
                    oid=order.oid,
                    side=side,
                    price=float(price),
                    requested_qty=requested_qty,
                    available_qty=float(available_qty),
                    filled_qty=filled_qty,
                    shortfall_qty=shortfall_qty,
                    residual_position=int(self.positions[instrument_id]),
                    liquidity_source=source,
                    observed_qty=float(observed_qty),
                    carried_depletion_qty=float(carried_depletion_qty),
                    complete=(
                        shortfall_qty == 0
                        and self.positions[instrument_id] == 0
                    ),
                )
            )
        self._mark_equity(final_ts)


class MultiBacktestResult:
    def __init__(self, engine: MultiInstrumentEngine):
        self.engine = engine
        self.equity = pd.DataFrame(engine.equity_curve, columns=["ts", "equity"])
        self.fills = pd.DataFrame([fill.__dict__ for fill in engine.fills])
        self.order_submissions = pd.DataFrame(
            [
                submission.__dict__
                for submission in engine.order_submissions
            ],
            columns=ORDER_SUBMISSION_COLUMNS,
        )
        self.order_rejections = pd.DataFrame(
            [rejection.__dict__ for rejection in engine.order_rejections],
            columns=ORDER_REJECTION_COLUMNS,
        )
        self.order_cancellations = pd.DataFrame(
            [
                cancellation.__dict__
                for cancellation in engine.order_cancellations
            ],
            columns=CANCELLATION_COLUMNS,
        )
        self.order_horizon_states = pd.DataFrame(
            [
                horizon_state.__dict__
                for horizon_state in engine.order_horizon_states
            ],
            columns=ORDER_HORIZON_STATE_COLUMNS,
        )
        self.liquidity_shortfalls = pd.DataFrame(
            [shortfall.__dict__ for shortfall in engine.liquidity_shortfalls],
            columns=LIQUIDITY_SHORTFALL_COLUMNS,
        )
        self.queue_initializations = pd.DataFrame(
            [
                initialization.__dict__
                for initialization in engine.queue_initializations
            ],
            columns=QUEUE_INITIALIZATION_COLUMNS,
        )
        self.resting_transitions = pd.DataFrame(
            [
                transition.__dict__
                for transition in engine.resting_transitions
            ],
            columns=RESTING_TRANSITION_COLUMNS,
        )
        self.passive_price_throughs = pd.DataFrame(
            [
                price_through.__dict__
                for price_through in engine.passive_price_throughs
            ],
            columns=PASSIVE_PRICE_THROUGH_COLUMNS,
        )
        self.terminal_liquidations = pd.DataFrame(
            [
                liquidation.__dict__
                for liquidation in engine.terminal_liquidations
            ],
            columns=TERMINAL_LIQUIDATION_COLUMNS,
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
                "Terminal residual: "
                f"{sum(abs(position) for position in self.engine.positions.values())} units",
                f"Maker fill share : {100 * maker_share:.1f}%",
                f"Turnover         : Rs {turnover:,.0f}",
                f"Portfolio delta  : {self.engine.portfolio_delta():,.2f}",
                f"Portfolio vega   : {self.engine.portfolio_vega():,.2f}",
            ]
        )
