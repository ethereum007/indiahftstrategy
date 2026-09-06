from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ArrowDepthLevel:
    quantity: int
    price: Decimal
    orders: int


@dataclass(frozen=True, slots=True)
class ArrowTick:
    token: int
    mode: str
    ltp: Decimal
    exchange_time: int | None = None
    ltq: int | None = None
    volume: int | None = None
    bids: tuple[ArrowDepthLevel, ...] = ()
    asks: tuple[ArrowDepthLevel, ...] = ()
    imbalance_quantity: int = 0
    indicative_close: Decimal = Decimal(0)
    reference_price: Decimal = Decimal(0)
