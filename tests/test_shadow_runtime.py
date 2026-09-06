from datetime import UTC, datetime
from decimal import Decimal

from execution.oms import OMS, OMSState, OrderJournal
from execution.risk_engine import IndependentRiskEngine, RiskLimits
from execution.shadow import ShadowTradingRuntime
from trading.contracts import (
    AlphaForecast,
    EventTimes,
    Instrument,
    InstrumentIdentity,
    OrderIntent,
    OrderType,
    Quote,
    Side,
    TraceContext,
)


def test_shadow_runtime_can_never_call_broker(tmp_path):
    inst = Instrument(InstrumentIdentity("NSE", "CM", "ABC", "ABC"), "1", "ABC.NSE.EQ", 1, Decimal("0.05"))
    now = datetime.now(UTC)
    event = Quote(inst, Decimal("99.95"), Decimal("100.05"), times=EventTimes(exchange_ts=now, receive_ts=now))

    def signal(_):
        return OrderIntent(
            inst,
            Side.BUY,
            1,
            Decimal("100"),
            OrderType.LIMIT,
            EventTimes(signal_ts=now),
            TraceContext("s", "st", "sig", "in", "shadow-1"),
        )

    limits = RiskLimits(
        10,
        Decimal("10000"),
        10,
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        Decimal("1000"),
        Decimal("1000"),
        Decimal("1000"),
        10,
        10,
        100,
        Decimal("1"),
        Decimal("1"),
        Decimal("100"),
        Decimal("100"),
        1000,
        1000,
    )
    oms = OMS(OrderJournal(tmp_path / "oms.jsonl"))
    runtime = ShadowTradingRuntime(IndependentRiskEngine(limits), oms, signal, lambda order, event: Decimal("100"))
    result = runtime.on_market_event(event)
    assert (
        result.hypothetical_fill_price == Decimal("100")
        and runtime.broker_calls == 0
        and oms.states["shadow-1"] == OMSState.FILLED
    )


def test_shadow_runtime_runs_forecast_portfolio_risk_oms_and_records_metrics(tmp_path):
    inst = Instrument(InstrumentIdentity("NSE", "CM", "ABC", "ABC"), "1", "ABC.NSE.EQ", 1, Decimal("0.05"))
    now = datetime.now(UTC)
    event = Quote(inst, Decimal("101"), Decimal("103"), times=EventTimes(exchange_ts=now, receive_ts=now))
    trace = TraceContext("s", "strategy", "signal", "intent", "shadow-forecast-1")

    def forecast(_):
        return AlphaForecast(
            inst,
            1,
            Decimal("20"),
            Decimal("0.8"),
            Decimal("0.01"),
            5000,
            Decimal("0.2"),
            10,
            ("rvol", "ofi"),
            "features-1",
            "model-1",
            EventTimes(feature_ts=now, signal_ts=now),
            trace,
        )

    def portfolio(_, __):
        return OrderIntent(
            inst,
            Side.BUY,
            2,
            Decimal("100"),
            OrderType.LIMIT,
            EventTimes(signal_ts=now),
            trace,
        )

    recorded = []
    oms = OMS(OrderJournal(tmp_path / "forecast-oms.jsonl"))
    runtime = ShadowTradingRuntime(
        IndependentRiskEngine(_limits()),
        oms,
        None,
        lambda order, market_event: Decimal("101"),
        forecast=forecast,
        portfolio=portfolio,
        record=recorded.append,
    )
    result = runtime.on_market_event(event)
    assert result is not None
    assert result.forecast is not None and result.forecast.model_version == "model-1"
    assert result.hypothetical_fill_quantity == 2
    assert result.pnl == Decimal("2")
    assert result.slippage_bps == Decimal("100")
    assert result.markout_bps > 0
    assert result.signal_to_risk_ms >= 0
    assert recorded == [result] and runtime.broker_calls == 0


def _limits():
    return RiskLimits(
        10,
        Decimal("10000"),
        10,
        Decimal("100000"),
        Decimal("100000"),
        Decimal("100000"),
        Decimal("1000"),
        Decimal("1000"),
        Decimal("1000"),
        10,
        10,
        100,
        Decimal("1"),
        Decimal("1"),
        Decimal("100"),
        Decimal("100"),
        1000,
        1000,
    )
