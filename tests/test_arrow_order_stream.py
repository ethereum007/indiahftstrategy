import asyncio
import json
from datetime import UTC, datetime

import pytest

from brokers.arrow.errors import ArrowProtocolError
from brokers.arrow.client import ArrowBrokerAdapter
from brokers.arrow.config import ArrowConfig
from brokers.arrow.order_stream import ArrowOrderStreamGateway, OrderUpdateBus, heartbeat_payload, parse_order_update
from trading.contracts import BrokerOrderStatus


def test_official_order_update_normalization_and_heartbeat():
    update = parse_order_update(
        '{"updateType":"ORDER_UPDATE","id":"b1","orderStatus":"PARTIALLY_FILLED",'
        '"cumulativeFillQty":"5","leavesQuantity":"5","exchangeOrderID":"e1",'
        '"orderTime":"2026-01-23T13:40:53","exchangeTime":"2026-01-23T13:40:54","remarks":"client-1"}',
        session_id="session",
        receive_ts=datetime.now(UTC),
    )
    assert update.status == BrokerOrderStatus.PARTIALLY_FILLED
    assert update.filled_quantity == 5 and update.remaining_quantity == 5
    assert update.trace.client_order_id == "client-1" and heartbeat_payload() == "PONG"
    assert update.times.exchange_ts.utcoffset().total_seconds() == 19800


def test_malformed_order_update_is_rejected():
    with pytest.raises(ArrowProtocolError):
        parse_order_update("{}", session_id="s")


class FakeOrderSocket:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.connected = []
        self.sent = []
        self.closed = False

    async def connect(self, url):
        self.connected.append(url)

    async def send(self, payload):
        self.sent.append(payload)

    async def receive(self):
        return self.messages.pop(0)

    async def close(self):
        self.closed = True


class FakeRest:
    async def request(self, method, path, *, headers, json=None):
        return {"method": method, "path": path, "headers": headers, "json": json}


def test_order_stream_gateway_separates_transport_parser_and_bus():
    async def scenario():
        payload = json.dumps(
            {
                "updateType": "ORDER_UPDATE",
                "id": "broker-1",
                "orderStatus": "OPEN",
                "cumulativeFillQty": "0",
                "leavesQuantity": "5",
                "remarks": "client-1",
            }
        )
        socket = FakeOrderSocket([payload.encode()])
        bus = OrderUpdateBus()
        gateway = ArrowOrderStreamGateway("wss://order.example", socket, bus, session_id="session-1")
        await gateway.connect()
        await gateway.send_heartbeat()
        update = await gateway.receive_once()
        published = await anext(bus.stream())
        await gateway.disconnect()
        assert update == published
        assert socket.connected == ["wss://order.example"]
        assert socket.sent == ["PONG"]
        assert socket.closed

    asyncio.run(scenario())


def test_order_stream_gateway_uses_injected_handshake():
    async def scenario():
        socket = FakeOrderSocket()
        calls = []

        async def handshake(transport, url):
            calls.append((transport, url, "credential-free-fixture"))
            await transport.connect(url)

        gateway = ArrowOrderStreamGateway(
            "wss://order.example", socket, OrderUpdateBus(), session_id="s", handshake=handshake
        )
        await gateway.connect()
        await gateway.disconnect()
        assert calls == [(socket, "wss://order.example", "credential-free-fixture")]

    asyncio.run(scenario())


def test_arrow_adapter_health_tracks_market_and_order_streams_independently():
    async def scenario():
        market_socket = FakeOrderSocket()
        order_socket = FakeOrderSocket()
        adapter = ArrowBrokerAdapter(
            ArrowConfig(app_id="app", access_token="opaque-test-token"),
            FakeRest(),
            market_socket,
            order_websocket=order_socket,
            session_id="session-1",
        )
        await adapter.connect()
        before = await adapter.health()
        assert before.market_data_connected and not before.order_stream_connected
        assert before.reason_codes == ("order_stream_disconnected",)
        await adapter.connect_order_stream()
        after = await adapter.health()
        assert after.market_data_connected and after.order_stream_connected and not after.reason_codes
        await adapter.disconnect()
        assert market_socket.closed and order_socket.closed

    asyncio.run(scenario())
