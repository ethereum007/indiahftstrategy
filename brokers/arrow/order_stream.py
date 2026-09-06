from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from brokers.arrow.errors import ArrowProtocolError
from brokers.arrow.reconnect import ReconnectPolicy
from trading.contracts import BrokerOrderStatus, EventTimes, OrderUpdate, TraceContext

PING_INTERVAL_SECONDS = 3.0
READ_TIMEOUT_SECONDS = 5.0


def heartbeat_payload() -> str:
    return "PONG"


def _arrow_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ArrowProtocolError("invalid Arrow order timestamp") from exc
    return parsed.replace(tzinfo=ZoneInfo("Asia/Kolkata")) if parsed.tzinfo is None else parsed


def parse_order_update(payload: str, *, session_id: str, receive_ts: datetime | None = None) -> OrderUpdate:
    try:
        row = json.loads(payload)
        if row.get("updateType") != "ORDER_UPDATE":
            raise ValueError("unexpected updateType")
        broker_id = str(row["id"])
        status_map = {
            "PENDING": BrokerOrderStatus.ACKNOWLEDGED,
            "OPEN": BrokerOrderStatus.OPEN,
            "PARTIALLY_FILLED": BrokerOrderStatus.PARTIALLY_FILLED,
            "COMPLETE": BrokerOrderStatus.FILLED,
            "CANCELLED": BrokerOrderStatus.CANCELLED,
            "REJECTED": BrokerOrderStatus.REJECTED,
        }
        status = status_map.get(str(row.get("orderStatus", "")), BrokerOrderStatus.UNKNOWN)
        filled = int(str(row.get("cumulativeFillQty", "0")))
        remaining = int(str(row.get("leavesQuantity", "0")))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ArrowProtocolError("malformed Arrow order update") from exc
    received = receive_ts or datetime.now(UTC)
    exchange_ts = _arrow_time(row.get("exchangeTime") or row.get("exchangeUpdateTime"))
    times = EventTimes(exchange_ts=exchange_ts, provider_ts=_arrow_time(row.get("orderTime")), receive_ts=received)
    trace = TraceContext(
        session_id=session_id,
        client_order_id=str(row.get("remarks", "")),
        broker_order_id=broker_id,
        exchange_order_id=str(row.get("exchangeOrderID", "")),
    )
    return OrderUpdate(
        broker_id,
        trace.exchange_order_id,
        status,
        filled,
        remaining,
        str(row.get("rejectReason", "")),
        times,
        trace,
    )


class OrderUpdateBus:
    def __init__(self, maxsize: int = 10000) -> None:
        self._queue: asyncio.Queue[OrderUpdate] = asyncio.Queue(maxsize=maxsize)

    async def publish(self, update: OrderUpdate) -> None:
        await self._queue.put(update)

    async def stream(self) -> AsyncIterator[OrderUpdate]:
        while True:
            yield await self._queue.get()


class OrderStreamTransport(Protocol):
    async def connect(self, url: str) -> None: ...
    async def send(self, payload: str) -> None: ...
    async def receive(self) -> bytes | str: ...
    async def close(self) -> None: ...


Handshake = Callable[[OrderStreamTransport, str], Awaitable[None]]


async def connect_only_handshake(transport: OrderStreamTransport, url: str) -> None:
    """Default transport handshake; credential injection stays transport-specific."""
    await transport.connect(url)


class ArrowOrderStreamGateway:
    """Order-update transport isolated from parsing, publication, and consumers."""

    def __init__(
        self,
        url: str,
        transport: OrderStreamTransport,
        bus: OrderUpdateBus,
        *,
        session_id: str,
        handshake: Handshake = connect_only_handshake,
        reconnect: ReconnectPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.url = url
        self.transport = transport
        self.bus = bus
        self.session_id = session_id
        self.handshake = handshake
        self.reconnect = reconnect or ReconnectPolicy()
        self.sleep = sleep
        self.connected = False

    async def connect(self) -> None:
        await self.handshake(self.transport, self.url)
        self.connected = True

    async def disconnect(self) -> None:
        await self.transport.close()
        self.connected = False

    async def send_heartbeat(self) -> None:
        if not self.connected:
            raise ConnectionError("order stream is disconnected")
        await self.transport.send(heartbeat_payload())

    async def receive_once(self) -> OrderUpdate:
        payload = await asyncio.wait_for(self.transport.receive(), timeout=READ_TIMEOUT_SECONDS)
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ArrowProtocolError("order update is not UTF-8") from exc
        if not isinstance(payload, str):
            raise ArrowProtocolError("order update must be text")
        update = parse_order_update(payload, session_id=self.session_id)
        await self.bus.publish(update)
        return update

    async def run(self, stop: asyncio.Event) -> None:
        """Run until stopped, reconnecting only within the bounded policy."""
        attempt = 0
        while not stop.is_set():
            heartbeat_task: asyncio.Task[None] | None = None
            try:
                await self.connect()
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(stop))
                while not stop.is_set():
                    await self.receive_once()
                    attempt = 0
            except (ConnectionError, OSError, TimeoutError, ArrowProtocolError):
                attempt += 1
                if attempt >= self.reconnect.max_attempts:
                    raise
                await self.sleep(self.reconnect.delay(attempt - 1))
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)
                if self.connected:
                    await self.disconnect()

    async def _heartbeat_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.send_heartbeat()
            await self.sleep(PING_INTERVAL_SECONDS)
