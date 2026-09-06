import asyncio
from datetime import date
from decimal import Decimal

import pytest

from brokers.arrow.errors import ArrowExternalValidationRequired, ArrowProtocolError
from brokers.arrow.instruments import InstrumentResolver
from brokers.arrow.market_data import MarketDataGateway
from brokers.arrow.orders import ArrowOrderService
from brokers.arrow.reconnect import ReconnectPolicy
from trading.contracts import Instrument, InstrumentIdentity


class FakeWebSocket:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.sent = []
        self.urls = []
        self.closed = False

    async def connect(self, url):
        self.urls.append(url)

    async def send(self, payload):
        self.sent.append(payload)

    async def receive(self):
        return self.messages.pop(0)

    async def close(self):
        self.closed = True


class FakeRest:
    async def request(self, method, path, *, headers, json=None):
        return {"method": method, "path": path}


def _instrument():
    return Instrument(
        InstrumentIdentity("NSE", "CM", "ABC", "ABC"),
        "1",
        "ABC.NSE.EQ",
        1,
        Decimal("0.05"),
    )


def _ltp(price=10000):
    packet = bytearray(13)
    packet[0:4] = (1).to_bytes(4, "big", signed=True)
    packet[4:8] = price.to_bytes(4, "big", signed=True)
    return bytes(packet)


def _quote(exchange_time, price=10000):
    packet = bytearray(93)
    packet[0:4] = (1).to_bytes(4, "big", signed=True)
    packet[4:8] = price.to_bytes(4, "big", signed=True)
    packet[13:17] = (1).to_bytes(4, "big", signed=True)
    packet[65:69] = exchange_time.to_bytes(4, "big", signed=True)
    return bytes(packet)


def test_disconnect_reconnect_restores_subscriptions_and_deduplicates():
    async def scenario():
        ws = FakeWebSocket([_ltp(), _ltp()])
        gateway = MarketDataGateway("wss://example", ws, InstrumentResolver([_instrument()], today=date(2026, 1, 1)))
        gateway.registry.subscribe("ltp", [1])
        await gateway.connect()
        assert '"code":"sub"' in ws.sent[0]
        first = await gateway.receive_once()
        duplicate = await gateway.receive_once()
        assert first is not None and duplicate is None

    asyncio.run(scenario())


def test_malformed_market_data_and_routing_separation():
    async def scenario():
        gateway = MarketDataGateway(
            "wss://example",
            FakeWebSocket(["not-binary"]),
            InstrumentResolver([_instrument()], today=date(2026, 1, 1)),
        )
        with pytest.raises(ArrowProtocolError):
            await gateway.receive_once()
        orders = ArrowOrderService(FakeRest(), {"appID": "x", "token": "redacted"})
        with pytest.raises(ArrowExternalValidationRequired):
            await orders.place(None)  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_reconnect_is_bounded_and_deterministic_under_injection():
    policy = ReconnectPolicy(initial_seconds=1, maximum_seconds=4, jitter_fraction=0.5, max_attempts=4)
    assert policy.delay(0, random_value=0.5) == 1
    assert policy.delay(3, random_value=0.5) == 4
    with pytest.raises(ValueError):
        policy.delay(4)


def test_feed_diagnostics_count_duplicate_out_of_order_and_malformed_messages():
    async def scenario():
        ws = FakeWebSocket([_quote(20), _quote(10, 10100), _quote(20), "not-binary"])
        gateway = MarketDataGateway("wss://example", ws, InstrumentResolver([_instrument()], today=date(2026, 1, 1)))
        assert await gateway.receive_once() is not None
        assert await gateway.receive_once() is None
        assert await gateway.receive_once() is None
        with pytest.raises(ArrowProtocolError):
            await gateway.receive_once()
        diagnostics = gateway.diagnostics()
        assert diagnostics.received == 4
        assert diagnostics.published == 1
        assert diagnostics.out_of_order == 1
        assert diagnostics.duplicates == 1
        assert diagnostics.malformed == 1

    asyncio.run(scenario())
