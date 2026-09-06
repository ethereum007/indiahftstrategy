from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


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


class UniverseTier(StrEnum):
    NIFTY50 = "NIFTY50"
    NIFTY100 = "NIFTY100"
    NIFTY200 = "NIFTY200"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True, slots=True)
class UniverseDefinition:
    tier: UniverseTier
    symbols: tuple[str, ...]
    asof_date: date
    source_sha256: str

    def __post_init__(self) -> None:
        if not self.symbols or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("universe symbols must be non-empty and unique")
        if any(symbol != symbol.strip().upper() for symbol in self.symbols):
            raise ValueError("universe symbols must be canonical uppercase values")
        if len(self.source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_sha256
        ):
            raise ValueError("universe source checksum is required")


@dataclass(frozen=True, slots=True)
class UniverseSelection:
    selected: tuple[str, ...]
    rejected: tuple[str, ...]
    missing_market_data: tuple[str, ...]


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


def select_liquid_universe(
    definition: UniverseDefinition,
    rows: list[LiquidityObservation],
    limits: LiquidityFilters,
    *,
    max_names: int | None = None,
) -> UniverseSelection:
    if max_names is not None and max_names <= 0:
        raise ValueError("max_names must be positive")
    by_symbol: dict[str, LiquidityObservation] = {}
    for row in rows:
        if row.symbol in by_symbol:
            raise ValueError("duplicate liquidity observation")
        by_symbol[row.symbol] = row
    membership = set(definition.symbols)
    eligible = set(liquid_universe([row for row in rows if row.symbol in membership], limits))
    ordered = sorted(
        (by_symbol[symbol] for symbol in eligible),
        key=lambda row: (row.turnover, row.depth, row.volume, row.symbol),
        reverse=True,
    )
    if max_names is not None:
        ordered = ordered[:max_names]
    selected = tuple(row.symbol for row in ordered)
    selected_set = set(selected)
    observed_members = membership & set(by_symbol)
    return UniverseSelection(
        selected,
        tuple(sorted(observed_members - selected_set)),
        tuple(sorted(membership - set(by_symbol))),
    )
