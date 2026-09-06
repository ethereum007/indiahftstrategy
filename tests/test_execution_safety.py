from datetime import UTC, datetime

import pytest

from execution.kill_switch import KillSwitch
from execution.safety import ExecutionSafetyCoordinator
from trading.contracts import BrokerHealth, EventTimes, KillSwitchState, RiskDecision, TraceContext


def _decision(approved=True, reasons=()):
    return RiskDecision(
        approved,
        reasons,
        {},
        EventTimes(risk_ts=datetime.now(UTC)),
        TraceContext("session", strategy_id="strategy"),
    )


def _health(authenticated=True, market=True, orders=True):
    return BrokerHealth(authenticated, market, orders, 1.0, datetime.now(UTC))


def test_safety_coordinator_requires_health_risk_and_running_kill_switch():
    kill_switch = KillSwitch()
    coordinator = ExecutionSafetyCoordinator(kill_switch)
    assert coordinator.assess(_decision(), _health()).route_allowed

    result = coordinator.assess(
        _decision(False, ("max_feed_age", "max_broker_latency")),
        _health(authenticated=False, orders=False),
    )
    assert not result.route_allowed
    assert result.halt_reasons == (
        "authentication_invalid",
        "order_stream_disconnect",
        "stale_feed",
        "latency_breach",
    )
    assert kill_switch.state == KillSwitchState.HALTING


def test_integrity_failures_halt_and_unknown_reason_fails_closed():
    kill_switch = KillSwitch()
    coordinator = ExecutionSafetyCoordinator(kill_switch)
    coordinator.report_integrity_failure("position_mismatch")
    assert kill_switch.state == KillSwitchState.HALTING
    with pytest.raises(ValueError, match="unsupported"):
        coordinator.report_integrity_failure("ignore-me")


def test_degraded_state_never_allows_routing_and_cannot_be_reentered():
    kill_switch = KillSwitch()
    kill_switch.degrade("rate_budget_low")
    coordinator = ExecutionSafetyCoordinator(kill_switch)
    assert not coordinator.assess(_decision(), _health()).route_allowed
    with pytest.raises(RuntimeError, match="only a running"):
        kill_switch.degrade("again")
