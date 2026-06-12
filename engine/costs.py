from __future__ import annotations

from dataclasses import dataclass

from engine.hft_backtest import Instrument


@dataclass(frozen=True)
class GenericCostModel:
    """Configurable cost model for non-India or broker-specific workflows.

    All fields are explicit inputs so the framework can support US markets
    without freezing time-sensitive exchange, clearing, or broker fee schedules.
    """

    buy_notional_rate: float = 0.0
    sell_notional_rate: float = 0.0
    per_unit_fee: float = 0.0
    per_contract_fee: float = 0.0
    per_order_fee: float = 0.0

    def cost(self, side: int, price: float, qty: int, inst: Instrument) -> float:
        if side not in (-1, 1):
            raise ValueError("side must be +1 buy or -1 sell")
        if qty < 0:
            raise ValueError("qty must be non-negative")
        turnover = price * qty * inst.multiplier
        notional_rate = self.buy_notional_rate if side > 0 else self.sell_notional_rate
        contracts = qty / inst.lot_size if inst.lot_size else 0.0
        return (
            notional_rate * turnover
            + self.per_unit_fee * qty
            + self.per_contract_fee * contracts
            + self.per_order_fee
        )

    def round_trip_bps(self, price: float, inst: Instrument) -> float:
        qty = inst.lot_size
        total = self.cost(+1, price, qty, inst) + self.cost(-1, price, qty, inst)
        notional = price * qty * inst.multiplier
        return 1e4 * total / max(notional, 1e-12)
