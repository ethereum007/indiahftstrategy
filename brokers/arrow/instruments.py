from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from brokers.arrow.errors import ArrowInstrumentError
from trading.contracts import Instrument, InstrumentIdentity

REQUIRED_COLUMNS = frozenset(
    {"Id", "LotSize", "TickSize", "Segment", "Exchange", "Expiry", "Name", "Strike", "SecurityType"}
)
SUPPORTED_MARKETS = frozenset({("NSE", "CM"), ("NSE", "NFO"), ("BSE", "CM"), ("BSE", "BFO")})


@dataclass(frozen=True, slots=True)
class InstrumentMasterSnapshot:
    instruments: tuple[Instrument, ...]
    sha256: str
    row_count: int
    loaded_ts: datetime


@dataclass(frozen=True, slots=True)
class InstrumentMasterDiff:
    added_tokens: tuple[str, ...]
    removed_tokens: tuple[str, ...]
    changed_tokens: tuple[str, ...]


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


def load_instrument_master(
    rows: Iterable[Mapping[str, object]],
    *,
    raw_payload: bytes | None = None,
    expected_sha256: str | None = None,
    today: date | None = None,
    loaded_ts: datetime | None = None,
) -> InstrumentMasterSnapshot:
    materialized = list(rows)
    if not materialized:
        raise ArrowInstrumentError("instrument master is empty")
    for row in materialized:
        missing = REQUIRED_COLUMNS - row.keys()
        if missing:
            raise ArrowInstrumentError("instrument master missing columns: " + ", ".join(sorted(missing)))
    evidence = (
        raw_payload
        if raw_payload is not None
        else json.dumps(materialized, sort_keys=True, default=str, separators=(",", ":")).encode()
    )
    digest = hashlib.sha256(evidence).hexdigest()
    if expected_sha256 is not None and digest.lower() != expected_sha256.lower():
        raise ArrowInstrumentError("instrument master checksum mismatch")
    instruments = tuple(instrument_from_arrow(row) for row in materialized)
    for instrument in instruments:
        identity = instrument.identity
        if (identity.exchange, identity.segment) not in SUPPORTED_MARKETS:
            raise ArrowInstrumentError("unsupported exchange/segment")
        if identity.segment == "CM" and (
            identity.expiry is not None
            or identity.strike is not None
            or identity.option_type is not None
            or instrument.lot_size != 1
        ):
            raise ArrowInstrumentError("invalid cash instrument identity")
        if identity.segment in {"NFO", "BFO"} and identity.expiry is None:
            raise ArrowInstrumentError("derivative expiry is required")
        if identity.option_type is not None and (identity.strike is None or identity.strike <= 0):
            raise ArrowInstrumentError("option strike is required")
    InstrumentResolver(instruments, today=today)
    stamp = loaded_ts or datetime.now(UTC)
    if stamp.tzinfo is None:
        raise ArrowInstrumentError("loaded_ts must be timezone-aware")
    return InstrumentMasterSnapshot(instruments, digest, len(instruments), stamp)


def compare_instrument_masters(
    previous: InstrumentMasterSnapshot, current: InstrumentMasterSnapshot
) -> InstrumentMasterDiff:
    old = {item.instrument_token: item for item in previous.instruments}
    new = {item.instrument_token: item for item in current.instruments}
    common = old.keys() & new.keys()
    return InstrumentMasterDiff(
        tuple(sorted(new.keys() - old.keys())),
        tuple(sorted(old.keys() - new.keys())),
        tuple(sorted(token for token in common if old[token] != new[token])),
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
