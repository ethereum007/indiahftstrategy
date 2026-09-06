from datetime import datetime, timezone
from decimal import Decimal

import pytest

from trading.contracts import DepthLevel, EventTimes, Instrument, InstrumentIdentity


def test_instrument_and_depth_fail_closed():
    instrument = Instrument(
        InstrumentIdentity("NSE", "CM", "RELIANCE", "RELIANCE"), "2885", "RELIANCE.NSE.EQ", 1, Decimal("0.05")
    )
    assert instrument.lot_size == 1
    with pytest.raises(ValueError):
        DepthLevel(Decimal("100"), -1)
    with pytest.raises(ValueError):
        EventTimes(receive_ts=datetime.now())
    assert EventTimes(receive_ts=datetime.now(timezone.utc)).receive_ts.tzinfo is not None
