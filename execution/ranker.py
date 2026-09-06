from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RankedOpportunity:
    symbol: str
    rank: int
    expected_alpha_bps: Decimal
    expected_cost_bps: Decimal
    expected_slippage_bps: Decimal
    risk_penalty_bps: Decimal
    net_expected_edge_bps: Decimal
    confidence: Decimal
    expected_horizon_ms: int
    capacity: int
    reason_codes: tuple[str, ...]


def rank_opportunities(rows: list[RankedOpportunity]) -> list[RankedOpportunity]:
    calculated = [
        replace(
            row,
            net_expected_edge_bps=row.expected_alpha_bps
            - row.expected_cost_bps
            - row.expected_slippage_bps
            - row.risk_penalty_bps,
        )
        for row in rows
    ]
    ordered = sorted(
        calculated, key=lambda row: (row.net_expected_edge_bps, row.confidence, row.capacity), reverse=True
    )
    return [replace(row, rank=index) for index, row in enumerate(ordered, 1)]
