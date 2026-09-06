import pytest

from brokers.arrow.errors import ArrowRateLimitError
from brokers.arrow.rate_limiter import ConfigurableRateLimiter, RateLimitCircuitBreaker, profile_from_config
from execution.kill_switch import KillSwitch
from trading.contracts import KillSwitchState


def test_configured_limits_and_retry_after():
    now = [0.0]
    limiter = ConfigurableRateLimiter(
        profile_from_config("custom", {"orders": {"per_minute": 2, "burst": 1, "daily": 2}}), clock=lambda: now[0]
    )
    limiter.acquire("orders")
    with pytest.raises(ArrowRateLimitError):
        limiter.acquire("orders")
    now[0] = 1.1
    limiter.acquire("orders")
    limiter.observe_429("orders", 3)
    with pytest.raises(ArrowRateLimitError):
        limiter.acquire("orders")


def test_rate_limit_pressure_triggers_kill_switch_before_exhaustion():
    now = [0.0]
    limiter = ConfigurableRateLimiter(
        profile_from_config("custom", {"orders": {"per_minute": 10, "burst": 2}}), clock=lambda: now[0]
    )
    kill_switch = KillSwitch()
    breaker = RateLimitCircuitBreaker(limiter, kill_switch, danger_threshold=0.5)
    limiter.acquire("orders")
    assert breaker.assess("orders") == 0.5
    assert kill_switch.state == KillSwitchState.HALTING
