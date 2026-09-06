from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from brokers.arrow.errors import ArrowAuthenticationError, ArrowError, ArrowRateLimitError
from brokers.arrow.rate_limiter import ConfigurableRateLimiter


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: Any
    headers: dict[str, str]


class RawHTTPTransport(Protocol):
    async def request(
        self, method: str, path: str, *, headers: dict[str, str], json: dict[str, Any] | None
    ) -> HTTPResponse: ...


class ResilientArrowHTTPClient:
    def __init__(
        self,
        transport: RawHTTPTransport,
        limiter: ConfigurableRateLimiter,
        *,
        max_attempts: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.transport = transport
        self.limiter = limiter
        self.max_attempts = max_attempts
        self.sleep = sleep

    async def call(
        self,
        endpoint_class: str,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | None = None,
    ) -> Any:
        error: Exception | None = None
        for attempt in range(self.max_attempts):
            self.limiter.acquire(endpoint_class)
            try:
                response = await self.transport.request(method, path, headers=headers, json=json)
            except TimeoutError as exc:
                error = exc
                if attempt + 1 < self.max_attempts:
                    await self.sleep(2**attempt)
                continue
            if response.status in {401, 403}:
                raise ArrowAuthenticationError("Arrow authentication rejected")
            if response.status == 429:
                retry_after = float(response.headers.get("Retry-After", "1"))
                self.limiter.observe_429(endpoint_class, retry_after)
                raise ArrowRateLimitError("Arrow returned 429")
            if 500 <= response.status < 600:
                error = ArrowError(f"Arrow server error {response.status}")
                if attempt + 1 < self.max_attempts:
                    await self.sleep(2**attempt)
                continue
            if response.status < 200 or response.status >= 300:
                raise ArrowError(f"Arrow request failed with status {response.status}")
            return response.body
        raise ArrowError("Arrow request retry budget exhausted") from error
