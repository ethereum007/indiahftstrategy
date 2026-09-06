from decimal import Decimal

import pytest

from brokers.arrow.errors import ArrowProtocolError
from brokers.arrow.market_data_binary import ArrowDataStreamV1Decoder


def _put(buf, offset, size, value, signed=True):
    buf[offset : offset + size] = int(value).to_bytes(size, "big", signed=signed)


def test_full_depth_and_cas_fixture():
    payload = bytearray(265)
    _put(payload, 0, 4, 2885)
    _put(payload, 4, 4, 250025)
    _put(payload, 13, 4, 7)
    _put(payload, 53, 8, 1000)
    _put(payload, 65, 4, 1_700_000_000)
    for i in range(10):
        offset = 109 + i * 14
        _put(payload, offset, 8, 100 + i)
        _put(payload, offset + 8, 4, 250000 + i * 5)
        _put(payload, offset + 12, 2, 2 + i)
    _put(payload, 249, 8, -20)
    _put(payload, 257, 4, 250100)
    _put(payload, 261, 4, 250050)
    tick = ArrowDataStreamV1Decoder().decode(bytes(payload))
    assert tick.mode == "full" and tick.ltp == Decimal("2500.25")
    assert len(tick.bids) == len(tick.asks) == 5 and tick.bids[0].quantity == 100 and tick.asks[0].quantity == 105
    assert tick.imbalance_quantity == -20 and tick.indicative_close == Decimal("2501")


def test_decoder_rejects_undocumented_layout():
    with pytest.raises(ArrowProtocolError):
        ArrowDataStreamV1Decoder().decode(b"guess")
