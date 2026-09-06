from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LiquidityObservation:
    symbol: str
    turnover: Decimal
    spread_bps: Decimal
    depth: int
    trades_per_minute: Decimal
    price: Decimal
    stale_ms: int
    volume: int


@dataclass(frozen=True, slots=True)
class LiquidityFilters:
    min_turnover: Decimal
    max_spread_bps: Decimal
    min_depth: int
    min_trades_per_minute: Decimal
    min_price: Decimal
    max_stale_ms: int
    min_volume: int


def liquid_universe(rows: list[LiquidityObservation], limits: LiquidityFilters) -> tuple[str, ...]:
    return tuple(
        row.symbol
        for row in rows
        if row.turnover >= limits.min_turnover
        and row.spread_bps <= limits.max_spread_bps
        and row.depth >= limits.min_depth
        and row.trades_per_minute >= limits.min_trades_per_minute
        and row.price >= limits.min_price
        and row.stale_ms <= limits.max_stale_ms
        and row.volume >= limits.min_volume
    )
