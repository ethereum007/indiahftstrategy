from datetime import UTC, datetime
from decimal import Decimal

import pytest

from execution.shadow import ShadowResult
from execution.shadow_session import ShadowSessionRecorder
from trading.contracts import (
    EventTimes,
    Instrument,
    InstrumentIdentity,
    OrderIntent,
    OrderType,
    RiskDecision,
    Side,
    TraceContext,
)


def _result(approved=True):
    now = datetime.now(UTC)
    instrument = Instrument(InstrumentIdentity("NSE", "CM", "ABC"), "1", "ABC", 1, Decimal("0.05"))
    trace = TraceContext("session", "strategy", "signal", "intent", "shadow-1")
    intent = OrderIntent(
        instrument,
        Side.BUY,
        1,
        Decimal(100),
        OrderType.LIMIT,
        EventTimes(signal_ts=now),
        trace,
    )
    decision = RiskDecision(approved, () if approved else ("max_feed_age",), {}, EventTimes(risk_ts=now), trace)
    return ShadowResult(
        intent,
        decision,
        Decimal(101) if approved else None,
        ("shadow_only_no_broker_route",),
        hypothetical_fill_quantity=1 if approved else 0,
        pnl=Decimal(5) if approved else Decimal(0),
        slippage_bps=Decimal(1) if approved else Decimal(0),
        markout_bps=Decimal(2) if approved else Decimal(0),
    )


def test_shadow_session_recorder_survives_restart_and_summarizes(tmp_path):
    path = tmp_path / "shadow.jsonl"
    first = ShadowSessionRecorder(path, "session")
    first.record(_result())
    first.record(_result(False))
    assert first.verify()

    restarted = ShadowSessionRecorder(path, "session")
    summary = restarted.summarize()
    assert summary.events == 2
    assert summary.approved == 1 and summary.rejected == 1
    assert summary.hypothetical_fills == 1
    assert summary.total_pnl == Decimal(5)
    assert summary.average_slippage_bps == Decimal(1)
    assert summary.average_markout_bps == Decimal(2)


def test_shadow_session_recorder_detects_tampering(tmp_path):
    path = tmp_path / "shadow.jsonl"
    recorder = ShadowSessionRecorder(path, "session")
    recorder.record(_result())
    path.write_text(path.read_text(encoding="utf-8").replace('"pnl":"5"', '"pnl":"6"'), encoding="utf-8")
    assert not recorder.verify()
    with pytest.raises(ValueError, match="changed"):
        recorder.record(_result())
    with pytest.raises(ValueError, match="integrity"):
        ShadowSessionRecorder(path, "session")


def test_shadow_session_recorder_fails_closed_on_truncated_json(tmp_path):
    path = tmp_path / "shadow.jsonl"
    path.write_text('{"session_id":', encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        ShadowSessionRecorder(path, "session")
