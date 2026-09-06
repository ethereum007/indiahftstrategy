from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading.contracts import OrderIntent, RiskDecision


@dataclass(frozen=True, slots=True)
class RiskLimits:
    max_order_qty: int
    max_order_notional: Decimal
    max_position_per_instrument: int
    max_gross_exposure: Decimal
    max_net_exposure: Decimal
    max_daily_turnover: Decimal
    max_daily_loss: Decimal
    max_strategy_loss: Decimal
    max_drawdown: Decimal
    max_open_orders: int
    max_orders_per_second: int
    max_orders_per_minute: int
    max_reject_ratio: Decimal
    max_cancel_ratio: Decimal
    max_slippage_bps: Decimal
    max_spread_bps: Decimal
    max_feed_age_ms: int
    max_broker_latency_ms: int


@dataclass
class RiskState:
    positions: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    gross_exposure: Decimal = Decimal(0)
    net_exposure: Decimal = Decimal(0)
    daily_turnover: Decimal = Decimal(0)
    daily_pnl: Decimal = Decimal(0)
    strategy_pnl: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: Decimal(0)))
    drawdown: Decimal = Decimal(0)
    open_orders: int = 0
    rejected: int = 0
    cancelled: int = 0
    total_orders: int = 0
    order_times: deque[datetime] = field(default_factory=deque)


class IndependentRiskEngine:
    def __init__(self, limits: RiskLimits, state: RiskState | None = None) -> None:
        self.limits, self.state = limits, state or RiskState()

    def evaluate(
        self,
        intent: OrderIntent,
        *,
        feed_age_ms: float,
        broker_latency_ms: float,
        spread_bps: Decimal = Decimal(0),
        expected_slippage_bps: Decimal = Decimal(0),
        now: datetime | None = None,
    ) -> RiskDecision:
        now = now or datetime.now(UTC)
        reasons: list[str] = []
        notional = intent.limit_price * intent.quantity
        signed_qty = intent.quantity if intent.side.value == "BUY" else -intent.quantity
        key = intent.instrument.instrument_token
        projected_position = self.state.positions[key] + signed_qty
        checks = {
            "max_order_qty": intent.quantity <= self.limits.max_order_qty,
            "max_order_notional": notional <= self.limits.max_order_notional,
            "max_position_per_instrument": abs(projected_position) <= self.limits.max_position_per_instrument,
            "max_gross_exposure": self.state.gross_exposure + notional <= self.limits.max_gross_exposure,
            "max_net_exposure": abs(self.state.net_exposure + (notional if signed_qty > 0 else -notional))
            <= self.limits.max_net_exposure,
            "max_daily_turnover": self.state.daily_turnover + notional <= self.limits.max_daily_turnover,
            "max_daily_loss": self.state.daily_pnl >= -self.limits.max_daily_loss,
            "max_strategy_loss": self.state.strategy_pnl[intent.trace.strategy_id] >= -self.limits.max_strategy_loss,
            "max_drawdown": self.state.drawdown <= self.limits.max_drawdown,
            "max_open_orders": self.state.open_orders < self.limits.max_open_orders,
            "max_reject_ratio": self._ratio(self.state.rejected) <= self.limits.max_reject_ratio,
            "max_cancel_ratio": self._ratio(self.state.cancelled) <= self.limits.max_cancel_ratio,
            "max_slippage": expected_slippage_bps <= self.limits.max_slippage_bps,
            "max_spread": spread_bps <= self.limits.max_spread_bps,
            "max_feed_age": feed_age_ms <= self.limits.max_feed_age_ms,
            "max_broker_latency": broker_latency_ms <= self.limits.max_broker_latency_ms,
        }
        while self.state.order_times and now - self.state.order_times[0] > timedelta(minutes=1):
            self.state.order_times.popleft()
        per_second = sum(now - item <= timedelta(seconds=1) for item in self.state.order_times)
        checks["max_orders_per_second"] = per_second < self.limits.max_orders_per_second
        checks["max_orders_per_minute"] = len(self.state.order_times) < self.limits.max_orders_per_minute
        reasons.extend(key for key, passed in checks.items() if not passed)
        self.state.total_orders += 1
        self.state.order_times.append(now)
        if reasons:
            self.state.rejected += 1
        times = replace(intent.times, risk_ts=now)
        return RiskDecision(not reasons, tuple(reasons), checks, times, intent.trace)

    def _ratio(self, count: int) -> Decimal:
        return Decimal(count) / Decimal(self.state.total_orders) if self.state.total_orders else Decimal(0)
