import asyncio

import pytest

from brokers.arrow.errors import ArrowAuthenticationError, ArrowError, ArrowRateLimitError
from brokers.arrow.http import HTTPResponse, ResilientArrowHTTPClient
from brokers.arrow.rate_limiter import ConfigurableRateLimiter, profile_from_config


class ScriptedTransport:
    def __init__(self, script):
        self.script = list(script)

    async def request(self, method, path, *, headers, json=None):
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def client(script, clock=None):
    now = clock or [0.0]
    limiter = ConfigurableRateLimiter(
        profile_from_config("test", {"orders": {"per_minute": 10, "burst": 10, "daily": 10}}),
        clock=lambda: now[0],
    )
    return ResilientArrowHTTPClient(ScriptedTransport(script), limiter, sleep=lambda _: asyncio.sleep(0))


def test_timeout_and_5xx_recover_deterministically():
    async def scenario():
        subject = client([TimeoutError(), HTTPResponse(503, {}, {}), HTTPResponse(200, {"ok": True}, {})])
        assert await subject.call("orders", "GET", "/user/orders", headers={}) == {"ok": True}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (HTTPResponse(401, {}, {}), ArrowAuthenticationError),
        (HTTPResponse(429, {}, {"Retry-After": "2"}), ArrowRateLimitError),
    ],
)
def test_auth_and_429_fail_closed(response, error):
    async def scenario():
        with pytest.raises(error):
            await client([response]).call("orders", "GET", "/user/orders", headers={})

    asyncio.run(scenario())


def test_retry_budget_exhaustion():
    async def scenario():
        with pytest.raises(ArrowError, match="retry budget"):
            await client([TimeoutError(), TimeoutError(), TimeoutError()]).call(
                "orders", "GET", "/user/orders", headers={}
            )

    asyncio.run(scenario())
