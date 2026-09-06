from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from execution.kill_switch import KillSwitch
from trading.contracts import BrokerHealth, KillSwitchState, RiskDecision


@dataclass(frozen=True, slots=True)
class SafetyAssessment:
    route_allowed: bool
    halt_reasons: tuple[str, ...]


class ExecutionSafetyCoordinator:
    """Independent final authority between risk/health signals and routing."""

    _risk_halts: ClassVar[dict[str, str]] = {
        "max_daily_loss": "pnl_limit",
        "max_strategy_loss": "pnl_limit",
        "max_drawdown": "drawdown_limit",
        "max_feed_age": "stale_feed",
        "max_broker_latency": "latency_breach",
        "max_reject_ratio": "reject_storm",
    }

    def __init__(self, kill_switch: KillSwitch) -> None:
        self.kill_switch = kill_switch

    def assess(self, decision: RiskDecision, health: BrokerHealth) -> SafetyAssessment:
        reasons: list[str] = []
        if not health.authenticated:
            reasons.append("authentication_invalid")
        if not health.market_data_connected:
            reasons.append("market_data_disconnect")
        if not health.order_stream_connected:
            reasons.append("order_stream_disconnect")
        reasons.extend(
            halt_reason for risk_reason, halt_reason in self._risk_halts.items() if risk_reason in decision.reason_codes
        )
        unique_reasons = tuple(dict.fromkeys(reasons))
        for reason in unique_reasons:
            self.kill_switch.trigger(reason)
        allowed = decision.approved and not unique_reasons and self.kill_switch.state == KillSwitchState.RUNNING
        return SafetyAssessment(allowed, unique_reasons)

    def report_integrity_failure(self, reason: str) -> None:
        if reason not in {"unexpected_fill", "unknown_order", "position_mismatch", "clock_anomaly"}:
            raise ValueError("unsupported integrity failure")
        self.kill_switch.trigger(reason)
