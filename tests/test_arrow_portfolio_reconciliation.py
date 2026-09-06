import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from brokers.arrow.margins import ArrowMarginService
from brokers.arrow.positions import ArrowPortfolioService
from brokers.arrow.reconciliation import reconcile_orders, reconcile_positions
from trading.contracts import (
    BrokerOrder,
    BrokerOrderStatus,
    EventTimes,
    Instrument,
    InstrumentIdentity,
    PositionSnapshot,
    Side,
    TraceContext,
)


class FakeTransport:
    def __init__(self):
        self.calls = []

    async def request(self, method, path, *, headers, json=None):
        self.calls.append((method, path, headers, json))
        return {"path": path}


class FakeSocket:
    async def connect(self, url):
        return None

    async def send(self, payload):
        return None

    async def receive(self):
        raise ConnectionError

    async def close(self):
        return None


class FakeQueries:
    async def get_orders(self):
        return ()

    async def reconcile(self):
        return {"ready": True, "status": "mock"}


def _instrument(token="1"):
    return Instrument(InstrumentIdentity("NSE", "CM", f"SYM{token}"), token, f"SYM{token}", 1, Decimal("0.05"))


def test_portfolio_and_margin_services_use_isolated_rest_boundaries():
    async def scenario():
        transport = FakeTransport()
        headers = {"appID": "app", "token": "redacted-fixture"}
        portfolio = ArrowPortfolioService(transport, headers)
        margin = ArrowMarginService(transport, headers)
        assert await portfolio.positions() == {"path": "/user/positions"}
        assert await portfolio.holdings() == {"path": "/user/holdings"}
        assert await portfolio.funds() == {"path": "/user/funds"}
        assert await margin.calculate({"orders": []}) == {"path": "/margin"}
        assert [call[1] for call in transport.calls] == [
            "/user/positions",
            "/user/holdings",
            "/user/funds",
            "/margin",
        ]

    asyncio.run(scenario())


def test_order_reconciliation_reports_unknown_and_missing_ids():
    now = datetime.now(UTC)
    instrument = _instrument()
    order = BrokerOrder(
        "unexpected",
        "broker-1",
        "exchange-1",
        BrokerOrderStatus.OPEN,
        instrument,
        Side.BUY,
        1,
        0,
        Decimal("100"),
        EventTimes(receive_ts=now),
        TraceContext("session", client_order_id="unexpected"),
    )
    result = reconcile_orders(["expected"], [order])
    assert not result.matched
    assert result.unknown_order_ids == ("unexpected",)
    assert result.missing_order_ids == ("expected",)


def test_position_reconciliation_detects_missing_extra_and_quantity_drift():
    now = datetime.now(UTC)
    actual = [PositionSnapshot(_instrument("1"), 2, Decimal("100"), Decimal(0), Decimal(0), now)]
    assert reconcile_positions({"1": 1, "2": 3}, actual) == ("1", "2")


def test_adapter_queries_fail_closed_or_delegate_to_typed_provider():
    async def scenario():
        config = ArrowConfig(app_id="app", access_token="opaque-test-token")
        blocked = ArrowBrokerAdapter(config, FakeTransport(), FakeSocket())
        with pytest.raises(ArrowExternalValidationRequired):
            await blocked.get_orders()
        delegated = ArrowBrokerAdapter(config, FakeTransport(), FakeSocket(), queries=FakeQueries())
        assert await delegated.get_orders() == ()
        assert await delegated.reconcile() == {"ready": True, "status": "mock"}

    asyncio.run(scenario())


import pytest

from brokers.arrow.client import ArrowBrokerAdapter
from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowExternalValidationRequired
