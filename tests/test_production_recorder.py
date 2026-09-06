from datetime import datetime, timezone
from decimal import Decimal

from data.production_recorder import AppendOnlyRecorder, DataQualityMonitor
from trading.contracts import DepthLevel, DepthSnapshot, EventTimes, Instrument, InstrumentIdentity


def test_raw_and_partitioned_normalized_recording(tmp_path):
    now = datetime.now(timezone.utc)
    inst = Instrument(InstrumentIdentity("NSE", "CM", "ABC", "ABC"), "1", "ABC.NSE.EQ", 1, Decimal(".05"))
    event = DepthSnapshot(
        inst,
        (DepthLevel(Decimal("101"), 10),),
        (DepthLevel(Decimal("100"), 10),),
        EventTimes(exchange_ts=now, receive_ts=now),
    )
    recorder = AppendOnlyRecorder(tmp_path, "session")
    raw = recorder.record_raw(b"abc", {"mode": "full"}, receive_ts=now, monotonic_ns=1)
    normalized = recorder.record_normalized(event)
    assert raw.exists() and normalized.exists() and "exchange=NSE" in str(normalized)
    monitor = DataQualityMonitor()
    assert "crossed_book" in monitor.inspect(event)
    assert "duplicate_event" in monitor.inspect(event)
    monitor.record_condition("data_gap")
    assert monitor.report()["data_gap"] == 1
    assert set(monitor.report()) == {
        "duplicate_event",
        "timestamp_regression",
        "stale_period",
        "data_gap",
        "crossed_book",
        "invalid_price",
        "zero_depth",
        "session_violation",
        "reconnect_window",
    }
