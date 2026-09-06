from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from trading.contracts import KillSwitchState

HALT_REASONS = {
    "stale_feed",
    "market_data_disconnect",
    "order_stream_disconnect",
    "authentication_invalid",
    "latency_breach",
    "rate_limit_danger",
    "reject_storm",
    "unexpected_fill",
    "unknown_order",
    "position_mismatch",
    "pnl_limit",
    "drawdown_limit",
    "manual_halt",
    "clock_anomaly",
}


@dataclass(frozen=True, slots=True)
class KillSwitchTransition:
    previous: KillSwitchState
    current: KillSwitchState
    reason: str
    ts: datetime


class KillSwitch:
    def __init__(self) -> None:
        self.state = KillSwitchState.RUNNING
        self.history: list[KillSwitchTransition] = []

    def trigger(self, reason: str) -> KillSwitchTransition:
        if reason not in HALT_REASONS:
            raise ValueError("unsupported halt reason")
        return self._move(KillSwitchState.HALTING if self.state != KillSwitchState.HALTED else self.state, reason)

    def complete_halt(self) -> KillSwitchTransition:
        return self._move(KillSwitchState.HALTED, "orders_cancelled_and_routes_disabled")

    def begin_reconciliation(self) -> KillSwitchTransition:
        if self.state != KillSwitchState.HALTED:
            raise RuntimeError("reconciliation requires HALTED")
        return self._move(KillSwitchState.RECONCILING, "operator_started_reconciliation")

    def authorize_resume(self, operator: str) -> KillSwitchTransition:
        if self.state != KillSwitchState.RECONCILING or not operator.strip():
            raise RuntimeError("explicit operator authorization required")
        return self._move(KillSwitchState.RUNNING, f"authorized_by:{operator}")

    def _move(self, target: KillSwitchState, reason: str) -> KillSwitchTransition:
        item = KillSwitchTransition(self.state, target, reason, datetime.now(UTC))
        self.state = target
        self.history.append(item)
        return item
