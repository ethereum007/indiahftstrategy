from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from execution.oms import OMS, OMSState
from execution.risk_engine import IndependentRiskEngine
from trading.contracts import (
    AlphaForecast,
    DepthSnapshot,
    MarketEvent,
    OrderIntent,
    Quote,
    RiskDecision,
    Side,
    TradePrint,
)


@dataclass(frozen=True, slots=True)
class ShadowResult:
    intent: OrderIntent
    decision: RiskDecision
    hypothetical_fill_price: Decimal | None
    reason_codes: tuple[str, ...]
    forecast: AlphaForecast | None = None
    hypothetical_fill_quantity: int = 0
    pnl: Decimal = Decimal(0)
    slippage_bps: Decimal = Decimal(0)
    markout_bps: Decimal = Decimal(0)
    signal_to_risk_ms: float = 0.0


class ShadowTradingRuntime:
    """Runs real decision boundaries while containing every order inside simulation."""

    def __init__(
        self,
        risk: IndependentRiskEngine,
        oms: OMS,
        signal: Callable[[MarketEvent], OrderIntent | None] | None,
        fill: Callable[[OrderIntent, MarketEvent], Decimal | None],
        *,
        forecast: Callable[[MarketEvent], AlphaForecast | None] | None = None,
        portfolio: Callable[[AlphaForecast, MarketEvent], OrderIntent | None] | None = None,
        record: Callable[[ShadowResult], None] | None = None,
    ) -> None:
        if signal is None and (forecast is None or portfolio is None):
            raise ValueError("shadow runtime requires signal or forecast plus portfolio")
        self.risk, self.oms, self.signal, self.fill = risk, oms, signal, fill
        self.forecast = forecast
        self.portfolio = portfolio
        self.record = record
        self.results: list[ShadowResult] = []
        self.broker_calls = 0

    def on_market_event(
        self, event: MarketEvent, *, feed_age_ms: float = 0, broker_latency_ms: float = 0
    ) -> ShadowResult | None:
        forecast = self.forecast(event) if self.forecast is not None else None
        if forecast is not None and self.portfolio is not None:
            intent = self.portfolio(forecast, event)
        elif self.signal is not None:
            intent = self.signal(event)
        else:
            intent = None
        if intent is None:
            return None
        self.oms.create(intent.trace.client_order_id)
        decision = self.risk.evaluate(intent, feed_age_ms=feed_age_ms, broker_latency_ms=broker_latency_ms)
        if not decision.approved:
            self.oms.transition(
                intent.trace.client_order_id,
                OMSState.RISK_REJECTED,
                "risk_rejected",
                {"reasons": list(decision.reason_codes)},
            )
            result = ShadowResult(intent, decision, None, decision.reason_codes, forecast=forecast)
        else:
            oid = intent.trace.client_order_id
            self.oms.transition(oid, OMSState.APPROVED, "risk_approved")
            self.oms.transition(oid, OMSState.QUEUED, "shadow_queued")
            price = self.fill(intent, event)
            if price is not None:
                self.oms.transition(oid, OMSState.SUBMITTING, "simulated_submit")
                self.oms.transition(oid, OMSState.SUBMITTED, "simulated_submitted")
                self.oms.transition(oid, OMSState.FILLED, "simulated_fill", {"price": str(price)})
            mark = _event_mark(event)
            side = Decimal(1) if intent.side == Side.BUY else Decimal(-1)
            if price is not None and intent.limit_price:
                slippage = side * (price - intent.limit_price) / intent.limit_price * Decimal(10000)
                markout = side * (mark - price) / price * Decimal(10000) if mark is not None and price else Decimal(0)
                pnl = side * (mark - price) * intent.quantity if mark is not None else Decimal(0)
                fill_quantity = intent.quantity
            else:
                slippage = markout = pnl = Decimal(0)
                fill_quantity = 0
            signal_ts = intent.times.signal_ts
            risk_ts = decision.times.risk_ts
            latency = (risk_ts - signal_ts).total_seconds() * 1000 if signal_ts and risk_ts else 0.0
            result = ShadowResult(
                intent,
                decision,
                price,
                ("shadow_only_no_broker_route",),
                forecast,
                fill_quantity,
                pnl,
                slippage,
                markout,
                latency,
            )
        self.results.append(result)
        if self.record is not None:
            self.record(result)
        return result


class LegacyStrategyAdapter:
    def __init__(self, converter: Callable[[object, MarketEvent], OrderIntent | None]) -> None:
        self.converter = converter

    def forecast_to_intent(self, legacy_output: object, event: MarketEvent) -> OrderIntent | None:
        return self.converter(legacy_output, event)


def _event_mark(event: MarketEvent) -> Decimal | None:
    if isinstance(event, TradePrint):
        return event.price
    if isinstance(event, Quote) and event.bid is not None and event.ask is not None:
        return (event.bid + event.ask) / Decimal(2)
    if isinstance(event, DepthSnapshot) and event.bids and event.asks:
        return (event.bids[0].price + event.asks[0].price) / Decimal(2)
    return None
