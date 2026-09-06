from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ExecutionAction(StrEnum):
    NO_TRADE = "NO_TRADE"
    PASSIVE_LIMIT = "PASSIVE_LIMIT"
    JOIN_TOUCH = "JOIN_TOUCH"
    PRICE_IMPROVEMENT = "PRICE_IMPROVEMENT"
    IOC = "IOC"
    MARKETABLE_LIMIT = "MARKETABLE_LIMIT"


@dataclass(frozen=True, slots=True)
class ExecutionInputs:
    forecast_edge_bps: Decimal
    forecast_decay: Decimal
    spread_bps: Decimal
    depth: int
    volatility: Decimal
    fill_probability: Decimal
    adverse_selection_bps: Decimal
    urgency: Decimal
    remaining_rate_budget: Decimal


def choose_execution(inputs: ExecutionInputs) -> ExecutionAction:
    net = inputs.forecast_edge_bps - inputs.spread_bps - inputs.adverse_selection_bps
    if net <= 0 or inputs.remaining_rate_budget <= 0:
        return ExecutionAction.NO_TRADE
    if inputs.urgency >= Decimal("0.8") and net > inputs.spread_bps * 2:
        return ExecutionAction.MARKETABLE_LIMIT
    if inputs.urgency >= Decimal("0.6"):
        return ExecutionAction.IOC
    if inputs.fill_probability >= Decimal("0.7"):
        return ExecutionAction.JOIN_TOUCH
    if inputs.spread_bps >= Decimal(5) and inputs.depth > 0:
        return ExecutionAction.PRICE_IMPROVEMENT
    return ExecutionAction.PASSIVE_LIMIT
