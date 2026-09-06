from datetime import date

import pytest

from brokers.arrow.errors import ArrowInstrumentError
from brokers.arrow.instruments import InstrumentResolver, instrument_from_arrow


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
