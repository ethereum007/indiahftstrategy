from __future__ import annotations

from typing import Any, Protocol

from brokers.arrow.errors import ArrowExternalValidationRequired
from trading.contracts import OrderAck, ValidatedOrder


class RestTransport(Protocol):
    async def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, Any] | None = None
    ) -> Any: ...


class ArrowOrderService:
    """Order API boundary. Routing is fail-closed until external certification."""

    def __init__(self, transport: RestTransport, headers: dict[str, str], *, routing_enabled: bool = False) -> None:
        self.transport, self.headers, self.routing_enabled = transport, headers, routing_enabled

    async def place(self, order: ValidatedOrder) -> OrderAck:
        if not self.routing_enabled:
            raise ArrowExternalValidationRequired(
                "Arrow order routing disabled; BLOCKED_EXTERNAL certification required"
            )
        raise ArrowExternalValidationRequired("live Arrow order schema requires certified external validation")

    async def modify(self, broker_order_id: str, **changes: Any) -> OrderAck:
        if not self.routing_enabled:
            raise ArrowExternalValidationRequired("Arrow order routing disabled")
        raise ArrowExternalValidationRequired("live Arrow modify schema requires certified external validation")

    async def cancel(self, broker_order_id: str) -> OrderAck:
        if not self.routing_enabled:
            raise ArrowExternalValidationRequired("Arrow order routing disabled")
        raise ArrowExternalValidationRequired("live Arrow cancel schema requires certified external validation")
