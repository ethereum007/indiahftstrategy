from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal

from brokers.arrow.errors import ArrowInstrumentError
from trading.contracts import Instrument, InstrumentIdentity


def instrument_from_arrow(row: Mapping[str, object]) -> Instrument:
    exchange = str(row.get("Exchange", "")).upper()
    segment = str(row.get("Segment", "")).upper()
    symbol = str(row.get("Name", "")).strip()
    token = str(row.get("Id", "")).strip()
    underlying = str(row.get("Underlying", "")).strip()
    expiry_raw = str(row.get("Expiry", "")).strip()
    expiry = None
    if expiry_raw and expiry_raw != "-1":
        try:
            expiry = datetime.strptime(expiry_raw, "%Y%m%d").replace(tzinfo=UTC).date()
        except ValueError as exc:
            raise ArrowInstrumentError("invalid expiry") from exc
    strike_raw = Decimal(str(row.get("Strike", "-1")))
    strike = None if strike_raw < 0 else strike_raw
    security_type = str(row.get("SecurityType", "")).upper()
    option_type = "CE" if security_type.endswith("CE") else "PE" if security_type.endswith("PE") else None
    return Instrument(
        InstrumentIdentity(exchange, segment, symbol, underlying, expiry, strike, option_type),
        token,
        symbol,
        int(str(row.get("LotSize", 0))),
        Decimal(str(row.get("TickSize", "0"))),
    )


class InstrumentResolver:
    def __init__(self, instruments: Iterable[Instrument], today: date | None = None) -> None:
        self.today = today or datetime.now(UTC).date()
        self._by_token: dict[str, Instrument] = {}
        self._by_identity: dict[InstrumentIdentity, Instrument] = {}
        for instrument in instruments:
            if instrument.instrument_token in self._by_token or instrument.identity in self._by_identity:
                raise ArrowInstrumentError("duplicate instrument mapping")
            if instrument.identity.expiry and instrument.identity.expiry < self.today:
                raise ArrowInstrumentError("expired instrument in active master")
            self._by_token[instrument.instrument_token] = instrument
            self._by_identity[instrument.identity] = instrument

    def by_token(self, token: str | int) -> Instrument:
        try:
            return self._by_token[str(token)]
        except KeyError as exc:
            raise ArrowInstrumentError("missing instrument mapping") from exc

    def resolve(self, identity: InstrumentIdentity) -> Instrument:
        try:
            return self._by_identity[identity]
        except KeyError as exc:
            raise ArrowInstrumentError("missing or incorrect instrument identity") from exc
