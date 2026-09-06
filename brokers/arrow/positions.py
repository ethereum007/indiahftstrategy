from __future__ import annotations

from typing import Any


class ArrowPortfolioService:
    def __init__(self, transport: Any, headers: dict[str, str]) -> None:
        self.transport, self.headers = transport, headers

    async def positions(self) -> Any:
        return await self.transport.request("GET", "/user/positions", headers=self.headers)

    async def holdings(self) -> Any:
        return await self.transport.request("GET", "/user/holdings", headers=self.headers)

    async def funds(self) -> Any:
        return await self.transport.request("GET", "/user/funds", headers=self.headers)
