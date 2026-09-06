from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from brokers.arrow.auth import ArrowAuthManager
from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowExternalValidationRequired
from brokers.arrow.instruments import InstrumentResolver
from brokers.arrow.market_data import MarketDataGateway, WebSocketTransport
from brokers.arrow.order_stream import (
    ArrowOrderStreamGateway,
    Handshake,
    OrderStreamTransport,
    OrderUpdateBus,
    connect_only_handshake,
)
from brokers.arrow.orders import ArrowOrderService, RestTransport
from trading.contracts import (
    BrokerHealth,
    BrokerOrder,
    Instrument,
    MarginSnapshot,
    MarketEvent,
    OrderAck,
    OrderUpdate,
    PositionSnapshot,
    TradeFill,
    ValidatedOrder,
)


class BrokerQueryProvider(Protocol):
    async def get_order(self, broker_order_id: str) -> BrokerOrder: ...
    async def get_orders(self) -> Sequence[BrokerOrder]: ...
    async def get_trades(self) -> Sequence[TradeFill]: ...
    async def get_positions(self) -> Sequence[PositionSnapshot]: ...
    async def get_holdings(self) -> Sequence[PositionSnapshot]: ...
    async def get_funds(self) -> MarginSnapshot: ...
    async def calculate_margin(self, orders: Sequence[ValidatedOrder]) -> MarginSnapshot: ...
    async def reconcile(self) -> dict[str, Any]: ...


class ArrowBrokerAdapter:
    def __init__(
        self,
        config: ArrowConfig,
        rest: RestTransport,
        websocket: WebSocketTransport,
        *,
        order_websocket: OrderStreamTransport | None = None,
        order_handshake: Handshake = connect_only_handshake,
        session_id: str = "",
        queries: BrokerQueryProvider | None = None,
        instruments: Sequence[Instrument] = (),
        routing_enabled: bool = False,
    ) -> None:
        self.config, self.rest, self.websocket = config, rest, websocket
        self.auth = ArrowAuthManager(config)
        self.instruments = list(instruments)
        self.resolver = InstrumentResolver(self.instruments)
        self.market_data: MarketDataGateway | None = None
        self.order_bus = OrderUpdateBus()
        self.order_stream = (
            ArrowOrderStreamGateway(
                config.order_stream_url,
                order_websocket,
                self.order_bus,
                session_id=session_id,
                handshake=order_handshake,
            )
            if order_websocket is not None
            else None
        )
        self.orders: ArrowOrderService | None = None
        self.routing_enabled = routing_enabled
        self.queries = queries
        self.connected = False

    async def authenticate(self) -> None:
        token = await self.auth.authenticate()
        headers = {"appID": self.config.app_id, "token": token}
        self.orders = ArrowOrderService(self.rest, headers, routing_enabled=self.routing_enabled)

    async def connect(self) -> None:
        if not self.auth.token:
            await self.authenticate()
        separator = "&" if "?" in self.config.market_data_url else "?"
        url = f"{self.config.market_data_url}{separator}appID={self.config.app_id}&token={self.auth.token}"
        self.market_data = MarketDataGateway(url, self.websocket, self.resolver)
        await self.market_data.connect()
        self.connected = True

    async def disconnect(self) -> None:
        await self.websocket.close()
        if self.order_stream is not None and self.order_stream.connected:
            await self.order_stream.disconnect()
        self.connected = False

    async def connect_order_stream(self) -> None:
        if not self.auth.token:
            await self.authenticate()
        if self.order_stream is None:
            raise RuntimeError("order-stream transport is not configured")
        await self.order_stream.connect()

    async def health(self) -> BrokerHealth:
        return BrokerHealth(
            bool(self.auth.token),
            self.connected,
            bool(self.order_stream and self.order_stream.connected),
            None,
            datetime.now(UTC),
            tuple(
                reason
                for condition, reason in (
                    (self.connected, "market_data_disconnected"),
                    (bool(self.order_stream and self.order_stream.connected), "order_stream_disconnected"),
                )
                if not condition
            ),
        )

    async def load_instruments(self) -> Sequence[Instrument]:
        return tuple(self.instruments)

    async def subscribe_market_data(self, instruments: Sequence[Instrument], mode: str = "full") -> None:
        if self.market_data is None:
            raise RuntimeError("adapter is not connected")
        await self.market_data.subscribe(mode, [int(i.instrument_token) for i in instruments])

    async def unsubscribe_market_data(self, instruments: Sequence[Instrument], mode: str = "full") -> None:
        if self.market_data is None:
            raise RuntimeError("adapter is not connected")
        await self.market_data.unsubscribe(mode, [int(i.instrument_token) for i in instruments])

    async def _market_stream(self) -> AsyncIterator[MarketEvent]:
        if self.market_data is None:
            raise RuntimeError("adapter is not connected")
        async for item in self.market_data.stream():
            yield item

    def stream_market_data(self) -> AsyncIterator[MarketEvent]:
        return self._market_stream()

    def stream_order_updates(self) -> AsyncIterator[OrderUpdate]:
        return self.order_bus.stream()

    async def place_order(self, order: ValidatedOrder) -> OrderAck:
        if self.orders is None:
            raise RuntimeError("adapter is not authenticated")
        return await self.orders.place(order)

    async def modify_order(self, broker_order_id: str, **changes: Any) -> OrderAck:
        if self.orders is None:
            raise RuntimeError("adapter is not authenticated")
        return await self.orders.modify(broker_order_id, **changes)

    async def cancel_order(self, broker_order_id: str) -> OrderAck:
        if self.orders is None:
            raise RuntimeError("adapter is not authenticated")
        return await self.orders.cancel(broker_order_id)

    async def cancel_all(self) -> Sequence[OrderAck]:
        raise ArrowExternalValidationRequired("cancel-all certification BLOCKED_EXTERNAL")

    async def get_order(self, broker_order_id: str) -> BrokerOrder:
        if self.queries is None:
            raise ArrowExternalValidationRequired("order query certification BLOCKED_EXTERNAL")
        return await self.queries.get_order(broker_order_id)

    async def get_orders(self) -> Sequence[BrokerOrder]:
        if self.queries is None:
            raise ArrowExternalValidationRequired("orders response certification BLOCKED_EXTERNAL")
        return await self.queries.get_orders()

    async def get_trades(self) -> Sequence[TradeFill]:
        if self.queries is None:
            raise ArrowExternalValidationRequired("trades response certification BLOCKED_EXTERNAL")
        return await self.queries.get_trades()

    async def get_positions(self) -> Sequence[PositionSnapshot]:
        if self.queries is None:
            raise ArrowExternalValidationRequired("positions response certification BLOCKED_EXTERNAL")
        return await self.queries.get_positions()

    async def get_holdings(self) -> Sequence[PositionSnapshot]:
        if self.queries is None:
            raise ArrowExternalValidationRequired("holdings response certification BLOCKED_EXTERNAL")
        return await self.queries.get_holdings()

    async def get_funds(self) -> MarginSnapshot:
        if self.queries is None:
            raise ArrowExternalValidationRequired("funds response certification BLOCKED_EXTERNAL")
        return await self.queries.get_funds()

    async def calculate_margin(self, orders: Sequence[ValidatedOrder]) -> MarginSnapshot:
        if self.queries is None:
            raise ArrowExternalValidationRequired("margin response certification BLOCKED_EXTERNAL")
        return await self.queries.calculate_margin(orders)

    async def reconcile(self) -> dict[str, Any]:
        if self.queries is None:
            return {"ready": False, "status": "BLOCKED_EXTERNAL", "reason": "live broker state unavailable"}
        return await self.queries.reconcile()
