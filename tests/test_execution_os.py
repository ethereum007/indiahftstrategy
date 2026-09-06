from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from execution.kill_switch import KillSwitch
from execution.oms import OMS, OMSState, OrderJournal
from execution.policy import ExecutionAction, ExecutionInputs, choose_execution
from execution.ranker import RankedOpportunity, rank_opportunities
from execution.risk_engine import IndependentRiskEngine, RiskLimits
from observability.latency import LatencyObservatory
from trading.contracts import (
    EventTimes,
    Instrument,
    InstrumentIdentity,
    LatencyEvent,
    OrderIntent,
    OrderType,
    Side,
    TraceContext,
)


def instrument():
    return Instrument(InstrumentIdentity("NSE", "CM", "ABC", "ABC"), "1", "ABC.NSE.EQ", 1, Decimal("0.05"))


def limits():
    return RiskLimits(
        100,
        Decimal(100000),
        200,
        Decimal(1000000),
        Decimal(1000000),
        Decimal(5000000),
        Decimal(10000),
        Decimal(5000),
        Decimal(5000),
        10,
        5,
        20,
        Decimal("0.5"),
        Decimal("0.8"),
        Decimal(20),
        Decimal(50),
        1000,
        500,
    )


def intent(qty=10):
    now = datetime.now(UTC)
    trace = TraceContext("s", "strategy", "sig", "intent", "coid")
    return OrderIntent(instrument(), Side.BUY, qty, Decimal(100), OrderType.LIMIT, EventTimes(signal_ts=now), trace)


def test_risk_is_independent_immutable_and_checks_stale_feed():
    risk = IndependentRiskEngine(limits())
    approved = risk.evaluate(intent(), feed_age_ms=1, broker_latency_ms=1)
    assert approved.approved and approved.times.risk_ts is not None
    rejected = risk.evaluate(intent(101), feed_age_ms=2000, broker_latency_ms=1)
    assert not rejected.approved and {"max_order_qty", "max_feed_age"} <= set(rejected.reason_codes)


def test_kill_switch_never_auto_resumes():
    switch = KillSwitch()
    switch.trigger("stale_feed")
    switch.complete_halt()
    with pytest.raises(RuntimeError):
        switch.authorize_resume("operator")
    switch.begin_reconciliation()
    with pytest.raises(RuntimeError):
        switch.authorize_resume("")
    assert switch.authorize_resume("kiran").current.value == "RUNNING"


def test_oms_journal_recovers_and_submission_is_idempotent(tmp_path):
    path = tmp_path / "oms.jsonl"
    oms = OMS(OrderJournal(path))
    oms.create("x")
    oms.transition("x", OMSState.APPROVED, "approved")
    oms.transition("x", OMSState.QUEUED, "queued")
    assert oms.reserve_submission("x") and not oms.reserve_submission("x")
    recovered = OMS(OrderJournal(path))
    assert recovered.states["x"] == OMSState.QUEUED and not recovered.reserve_submission("x")


def test_oms_accepts_documented_network_races(tmp_path):
    oms = OMS(OrderJournal(tmp_path / "races.jsonl"))
    for order_id in ("fill-before-ack", "cancel-fill", "modify-fill"):
        oms.create(order_id)
        oms.transition(order_id, OMSState.APPROVED, "approved")
        oms.transition(order_id, OMSState.QUEUED, "queued")
        oms.transition(order_id, OMSState.SUBMITTING, "submitting")
        oms.transition(order_id, OMSState.SUBMITTED, "submitted")
    oms.transition("fill-before-ack", OMSState.FILLED, "fill")
    oms.transition("cancel-fill", OMSState.ACKNOWLEDGED, "ack")
    oms.transition("cancel-fill", OMSState.OPEN, "open")
    oms.transition("cancel-fill", OMSState.CANCEL_PENDING, "cancel")
    oms.transition("cancel-fill", OMSState.FILLED, "fill")
    oms.transition("modify-fill", OMSState.ACKNOWLEDGED, "ack")
    oms.transition("modify-fill", OMSState.OPEN, "open")
    oms.transition("modify-fill", OMSState.MODIFY_PENDING, "modify")
    oms.transition("modify-fill", OMSState.FILLED, "fill")
    assert all(oms.states[key] == OMSState.FILLED for key in oms.states)


def test_latency_percentiles_and_execution_net_edge():
    now = datetime.now(UTC)
    obs = LatencyObservatory()
    trace = TraceContext("s", strategy_id="a")
    for ms in [1, 2, 3, 10]:
        obs.record(LatencyEvent("send_to_ack", now, now + timedelta(milliseconds=ms), trace, instrument()))
    assert obs.summarize(stage="send_to_ack").p50 == 2.5 and obs.summarize().maximum == 10
    rows = [
        RankedOpportunity(
            "A", 0, Decimal(10), Decimal(2), Decimal(1), Decimal(1), Decimal(0), Decimal(".8"), 1000, 100, ()
        ),
        RankedOpportunity(
            "B", 0, Decimal(9), Decimal(1), Decimal(1), Decimal(0), Decimal(0), Decimal(".8"), 1000, 100, ()
        ),
    ]
    assert rank_opportunities(rows)[0].symbol == "B"
    action = choose_execution(
        ExecutionInputs(
            Decimal(10),
            Decimal(".1"),
            Decimal(1),
            100,
            Decimal(".1"),
            Decimal(".8"),
            Decimal(1),
            Decimal(".2"),
            Decimal(1),
        )
    )
    assert action == ExecutionAction.JOIN_TOUCH


def test_latency_observatory_groups_by_hour_and_dimensions():
    start = datetime(2026, 1, 1, 9, tzinfo=UTC)
    obs = LatencyObservatory()
    trace = TraceContext("s", strategy_id="alpha")
    obs.record(LatencyEvent("receive_to_normalize", start, start + timedelta(milliseconds=2), trace, instrument()))
    later = start + timedelta(hours=1)
    obs.record(LatencyEvent("receive_to_normalize", later, later + timedelta(milliseconds=4), trace, instrument()))
    grouped = obs.group_by("hour", "stage", "symbol")
    assert grouped[("09", "receive_to_normalize", "ABC")].maximum == 2
    assert grouped[("10", "receive_to_normalize", "ABC")].maximum == 4
    assert obs.summarize(hour="09").count == 1
    with pytest.raises(ValueError, match="unsupported"):
        obs.group_by("unknown")
