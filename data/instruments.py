from __future__ import annotations

import re
from dataclasses import dataclass


MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


@dataclass(frozen=True)
class OptionInstrumentSpec:
    instrument_id: str
    underlying: str
    option_type: str
    strike: float
    expiry: str
    symbol_format: str


def parse_option_instrument_id(instrument_id: object) -> OptionInstrumentSpec | None:
    text = str(instrument_id).strip().upper()
    if not text:
        return None
    for parser in (_parse_internal_call_put, _parse_settlement_symbol, _parse_occ_symbol, _parse_nse_compact_symbol):
        parsed = parser(text)
        if parsed is not None:
            return parsed
    return None


def _parse_internal_call_put(text: str) -> OptionInstrumentSpec | None:
    match = re.fullmatch(r"(CALL|PUT)_([0-9]+(?:_[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", text)
    if match is None:
        return None
    option_type = "C" if match.group(1) == "CALL" else "P"
    strike = _decimal(match.group(2))
    return OptionInstrumentSpec(text, "", option_type, strike, "", "internal_call_put")


def _parse_settlement_symbol(text: str) -> OptionInstrumentSpec | None:
    match = re.fullmatch(r"([A-Z0-9]+)_([0-9]{8})_([0-9]+(?:P[0-9]+)?)([CP])", text)
    if match is None:
        return None
    expiry_raw = match.group(2)
    expiry = f"{expiry_raw[:4]}-{expiry_raw[4:6]}-{expiry_raw[6:]}"
    return OptionInstrumentSpec(
        text,
        match.group(1),
        match.group(4),
        _decimal(match.group(3)),
        expiry,
        "settlement_option",
    )


def _parse_occ_symbol(text: str) -> OptionInstrumentSpec | None:
    match = re.fullmatch(r"([A-Z]{1,6})\s*([0-9]{6})([CP])([0-9]{8})", text)
    if match is None:
        return None
    expiry_raw = match.group(2)
    expiry = f"20{expiry_raw[:2]}-{expiry_raw[2:4]}-{expiry_raw[4:]}"
    strike = int(match.group(4)) / 1000.0
    canonical = f"{match.group(1)}{expiry_raw}{match.group(3)}{match.group(4)}"
    return OptionInstrumentSpec(canonical, match.group(1), match.group(3), float(strike), expiry, "occ_option")


def _parse_nse_compact_symbol(text: str) -> OptionInstrumentSpec | None:
    match = re.fullmatch(r"([A-Z]+)([0-9]{2})([A-Z]{3})([0-9]+(?:\.[0-9]+)?)(CE|PE)", text)
    if match is None or match.group(3) not in MONTHS:
        return None
    expiry = f"20{match.group(2)}-{MONTHS[match.group(3)]}"
    option_type = "C" if match.group(5) == "CE" else "P"
    return OptionInstrumentSpec(
        text,
        match.group(1),
        option_type,
        float(match.group(4)),
        expiry,
        "nse_compact_option",
    )


def _decimal(value: str) -> float:
    return float(str(value).replace("P", ".").replace("_", "."))
