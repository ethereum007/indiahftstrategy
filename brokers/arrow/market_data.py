from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from brokers.arrow.errors import ArrowProtocolError
from brokers.arrow.instruments import InstrumentResolver
from brokers.arrow.market_data_binary import ArrowDataStreamV1Decoder
from trading.contracts import DepthLevel, DepthSnapshot, EventTimes, MarketEvent, Quote, TradePrint


class WebSocketTransport(Protocol):
    async def connect(self, url: str) -> None: ...
    async def send(self, payload: str) -> None: ...
    async def receive(self) -> bytes | str: ...
    async def close(self) -> None: ...


class SubscriptionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, set[int]] = {}

    def subscribe(self, mode: str, tokens: Sequence[int]) -> None:
        self._items.setdefault(mode, set()).update(tokens)

    def unsubscribe(self, mode: str, tokens: Sequence[int]) -> None:
        self._items.setdefault(mode, set()).difference_update(tokens)

    def messages(self, code: str = "sub") -> list[str]:
        return [
            json.dumps({"code": code, "mode": mode, mode: sorted(tokens)}, separators=(",", ":"))
            for mode, tokens in sorted(self._items.items())
            if tokens
        ]


@dataclass(frozen=True, slots=True)
class FeedDiagnostics:
    received: int
    published: int
    duplicates: int
    out_of_order: int
    malformed: int


class MarketDataGateway:
    def __init__(
        self,
        url: str,
        transport: WebSocketTransport,
        resolver: InstrumentResolver,
        *,
        decoder: ArrowDataStreamV1Decoder | None = None,
        stale_after_seconds: float = 5.0,
    ) -> None:
        self.url, self.transport, self.resolver = url, transport, resolver
        self.decoder = decoder or ArrowDataStreamV1Decoder()
        self.registry = SubscriptionRegistry()
        self.stale_after_seconds = stale_after_seconds
        self.last_receive_monotonic: float | None = None
        self._queue: asyncio.Queue[MarketEvent] = asyncio.Queue(maxsize=10000)
        self._fingerprints: set[tuple[int, int | None, Decimal, int | None]] = set()
        self._last_exchange_time: dict[int, int] = {}
        self._received = 0
        self._published = 0
        self._duplicates = 0
        self._out_of_order = 0
        self._malformed = 0

    async def connect(self) -> None:
        await self.transport.connect(self.url)
        for message in self.registry.messages():
            await self.transport.send(message)

    async def subscribe(self, mode: str, tokens: Sequence[int]) -> None:
        self.registry.subscribe(mode, tokens)
        await self.transport.send(json.dumps({"code": "sub", "mode": mode, mode: list(tokens)}, separators=(",", ":")))

    async def unsubscribe(self, mode: str, tokens: Sequence[int]) -> None:
        self.registry.unsubscribe(mode, tokens)
        await self.transport.send(
            json.dumps({"code": "unsub", "mode": mode, mode: list(tokens)}, separators=(",", ":"))
        )

    def stale(self, now: float | None = None) -> bool:
        return (
            self.last_receive_monotonic is None
            or (time.monotonic() if now is None else now) - self.last_receive_monotonic > self.stale_after_seconds
        )

    async def receive_once(self) -> MarketEvent | None:
        payload = await self.transport.receive()
        receive_ts = datetime.now(UTC)
        self.last_receive_monotonic = time.monotonic()
        self._received += 1
        if not isinstance(payload, bytes):
            self._malformed += 1
            raise ArrowProtocolError("market data payload must be binary")
        try:
            tick = self.decoder.decode(payload)
        except ArrowProtocolError:
            self._malformed += 1
            raise
        fingerprint = (tick.token, tick.exchange_time, tick.ltp, tick.volume)
        if fingerprint in self._fingerprints:
            self._duplicates += 1
            return None
        self._fingerprints.add(fingerprint)
        if len(self._fingerprints) > 100000:
            self._fingerprints.clear()
        if tick.exchange_time is not None:
            previous_exchange_time = self._last_exchange_time.get(tick.token)
            if previous_exchange_time is not None and tick.exchange_time < previous_exchange_time:
                self._out_of_order += 1
                return None
            self._last_exchange_time[tick.token] = tick.exchange_time
        instrument = self.resolver.by_token(tick.token)
        exchange_ts = datetime.fromtimestamp(tick.exchange_time, tz=UTC) if tick.exchange_time else None
        times = EventTimes(exchange_ts=exchange_ts, receive_ts=receive_ts, normalized_ts=datetime.now(UTC))
        if tick.bids or tick.asks:
            event: MarketEvent = DepthSnapshot(
                instrument,
                tuple(DepthLevel(x.price, x.quantity, x.orders) for x in tick.bids),
                tuple(DepthLevel(x.price, x.quantity, x.orders) for x in tick.asks),
                times,
            )
        elif tick.ltq is not None and tick.ltq > 0:
            event = TradePrint(instrument, tick.ltp, tick.ltq, times)
        else:
            event = Quote(instrument, None, None, times=times)
        await self._queue.put(event)
        self._published += 1
        return event

    async def stream(self) -> AsyncIterator[MarketEvent]:
        while True:
            yield await self._queue.get()

    def diagnostics(self) -> FeedDiagnostics:
        return FeedDiagnostics(
            self._received,
            self._published,
            self._duplicates,
            self._out_of_order,
            self._malformed,
        )
