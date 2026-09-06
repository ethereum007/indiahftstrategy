import hashlib
from datetime import UTC, date, datetime

import pytest

from brokers.arrow.errors import ArrowInstrumentError
from brokers.arrow.instruments import (
    InstrumentResolver,
    compare_instrument_masters,
    instrument_from_arrow,
    load_instrument_master,
)

ROW = {
    "Id": 17140,
    "LotSize": 1,
    "TickSize": 0.05,
    "Segment": "CM",
    "Exchange": "NSE",
    "Underlying": "IDEAFORGE",
    "Expiry": "-1",
    "Name": "IDEAFORGE.NSE.EQ",
    "Strike": -1,
    "SecurityType": "EQ",
}


def test_arrow_instrument_resolution_is_exact_and_fail_closed():
    instrument = instrument_from_arrow(ROW)
    resolver = InstrumentResolver([instrument], today=date(2026, 1, 1))
    assert resolver.by_token(17140) == instrument
    with pytest.raises(ArrowInstrumentError):
        resolver.by_token("missing")
    with pytest.raises(ArrowInstrumentError):
        InstrumentResolver([instrument, instrument])


def test_instrument_master_is_checksum_bound_and_comparable():
    loaded = datetime(2026, 1, 1, tzinfo=UTC)
    first = load_instrument_master([ROW], raw_payload=b"reviewed-master-v1", today=date(2026, 1, 1), loaded_ts=loaded)
    assert first.row_count == 1 and len(first.sha256) == 64
    same = load_instrument_master(
        [ROW],
        raw_payload=b"reviewed-master-v1",
        expected_sha256=first.sha256,
        today=date(2026, 1, 1),
        loaded_ts=loaded,
    )
    assert compare_instrument_masters(first, same).changed_tokens == ()

    empty_payload = load_instrument_master([ROW], raw_payload=b"", today=date(2026, 1, 1), loaded_ts=loaded)
    assert empty_payload.sha256 == hashlib.sha256(b"").hexdigest()

    changed_row = {**ROW, "TickSize": 0.1}
    changed = load_instrument_master([changed_row], today=date(2026, 1, 1), loaded_ts=loaded)
    assert compare_instrument_masters(first, changed).changed_tokens == ("17140",)
    with pytest.raises(ArrowInstrumentError, match="checksum"):
        load_instrument_master([ROW], raw_payload=b"different", expected_sha256=first.sha256)


@pytest.mark.parametrize(
    "row,error",
    [
        ({key: value for key, value in ROW.items() if key != "Id"}, "missing columns"),
        ({**ROW, "Exchange": "UNKNOWN"}, "unsupported exchange"),
        ({**ROW, "LotSize": 50}, "cash instrument"),
        ({**ROW, "Segment": "NFO", "SecurityType": "OPTCE", "Strike": -1}, "derivative expiry"),
    ],
)
def test_instrument_master_fails_closed_on_schema_and_identity(row, error):
    with pytest.raises(ArrowInstrumentError, match=error):
        load_instrument_master([row], today=date(2026, 1, 1))
