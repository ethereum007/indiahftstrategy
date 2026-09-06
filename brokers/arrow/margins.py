from __future__ import annotations

from typing import Any


class ArrowMarginService:
    def __init__(self, transport: Any, headers: dict[str, str]) -> None:
        self.transport, self.headers = transport, headers

    async def calculate(self, payload: dict[str, Any]) -> Any:
        return await self.transport.request("POST", "/margin", headers=self.headers, json=payload)
