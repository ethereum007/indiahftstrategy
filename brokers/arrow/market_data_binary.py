from __future__ import annotations

from decimal import Decimal
from typing import ClassVar, Protocol

from brokers.arrow.errors import ArrowProtocolError
from brokers.arrow.models import ArrowDepthLevel, ArrowTick


class BinaryDecoder(Protocol):
    version: str

    def decode(self, payload: bytes) -> ArrowTick: ...


class ArrowDataStreamV1Decoder:
    """Documented big-endian ds.arrow.trade packet decoder (2026-09 schema)."""

    version = "ds-v1-cas"
    _sizes: ClassVar[dict[int, str]] = {
        13: "ltp",
        17: "ltpc",
        93: "quote",
        249: "full",
        29: "ltp",
        33: "ltpc",
        109: "quote",
        265: "full",
    }

    def __init__(self, price_scale: int = 100) -> None:
        if price_scale <= 0:
            raise ValueError("price_scale must be positive")
        self.price_scale = Decimal(price_scale)

    def _price(self, raw: int) -> Decimal:
        return Decimal(raw) / self.price_scale

    @staticmethod
    def _i(payload: bytes, offset: int, size: int, *, signed: bool = True) -> int:
        return int.from_bytes(payload[offset : offset + size], "big", signed=signed)

    def decode(self, payload: bytes) -> ArrowTick:
        mode = self._sizes.get(len(payload))
        if mode is None:
            raise ArrowProtocolError(f"unsupported Arrow packet length: {len(payload)}")
        token = self._i(payload, 0, 4)
        ltp = self._price(self._i(payload, 4, 4))
        ltq = volume = exchange_time = None
        bids: tuple[ArrowDepthLevel, ...] = ()
        asks: tuple[ArrowDepthLevel, ...] = ()
        if mode in {"quote", "full"}:
            ltq = self._i(payload, 13, 4)
            volume = self._i(payload, 53, 8)
            exchange_time = self._i(payload, 65, 4)
        if mode == "full":
            levels = []
            for index in range(10):
                offset = 109 + index * 14
                levels.append(
                    ArrowDepthLevel(
                        quantity=self._i(payload, offset, 8),
                        price=self._price(self._i(payload, offset + 8, 4)),
                        orders=self._i(payload, offset + 12, 2),
                    )
                )
            bids, asks = tuple(levels[:5]), tuple(levels[5:])
        base = {"ltp": 13, "ltpc": 17, "quote": 93, "full": 249}[mode]
        imbalance = 0
        indicative = reference = Decimal(0)
        if len(payload) == base + 16:
            imbalance = self._i(payload, base, 8)
            indicative = self._price(self._i(payload, base + 8, 4))
            reference = self._price(self._i(payload, base + 12, 4))
        return ArrowTick(token, mode, ltp, exchange_time, ltq, volume, bids, asks, imbalance, indicative, reference)


class VersionedDecoderRegistry:
    def __init__(self) -> None:
        self._decoders: dict[str, BinaryDecoder] = {}

    def register(self, decoder: BinaryDecoder) -> None:
        if decoder.version in self._decoders:
            raise ValueError(f"decoder already registered: {decoder.version}")
        self._decoders[decoder.version] = decoder

    def decode(self, version: str, payload: bytes) -> ArrowTick:
        try:
            return self._decoders[version].decode(payload)
        except KeyError as exc:
            raise ArrowProtocolError(f"unknown decoder version: {version}") from exc
