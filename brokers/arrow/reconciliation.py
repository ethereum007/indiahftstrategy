from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from trading.contracts import BrokerOrder, PositionSnapshot


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    matched: bool
    unknown_order_ids: tuple[str, ...]
    missing_order_ids: tuple[str, ...]
    position_mismatches: tuple[str, ...]


def reconcile_orders(expected_ids: Iterable[str], broker_orders: Iterable[BrokerOrder]) -> ReconciliationResult:
    expected = set(expected_ids)
    actual = {o.client_order_id for o in broker_orders}
    unknown = tuple(sorted(actual - expected))
    missing = tuple(sorted(expected - actual))
    return ReconciliationResult(not unknown and not missing, unknown, missing, ())


def reconcile_positions(expected: dict[str, int], actual: Iterable[PositionSnapshot]) -> tuple[str, ...]:
    observed = {item.instrument.instrument_token: item.quantity for item in actual}
    keys = set(expected) | set(observed)
    return tuple(sorted(key for key in keys if expected.get(key, 0) != observed.get(key, 0)))
