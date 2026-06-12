from data.instruments import parse_option_instrument_id


def test_parse_internal_and_settlement_option_symbols():
    internal = parse_option_instrument_id("CALL_1000_0")
    settlement = parse_option_instrument_id("NIFTY_20260610_100C")

    assert internal is not None
    assert internal.option_type == "C"
    assert internal.strike == 1000.0
    assert internal.symbol_format == "internal_call_put"

    assert settlement is not None
    assert settlement.underlying == "NIFTY"
    assert settlement.expiry == "2026-06-10"
    assert settlement.option_type == "C"
    assert settlement.strike == 100.0
    assert settlement.symbol_format == "settlement_option"


def test_parse_nse_compact_option_symbol():
    parsed = parse_option_instrument_id("NIFTY24JUN22500PE")

    assert parsed is not None
    assert parsed.underlying == "NIFTY"
    assert parsed.expiry == "2024-06"
    assert parsed.option_type == "P"
    assert parsed.strike == 22500.0
    assert parsed.symbol_format == "nse_compact_option"


def test_parse_occ_option_symbol():
    parsed = parse_option_instrument_id("SPY250620C00500000")
    padded = parse_option_instrument_id("SPY  250620C00500000")

    assert parsed is not None
    assert parsed.underlying == "SPY"
    assert parsed.expiry == "2025-06-20"
    assert parsed.option_type == "C"
    assert parsed.strike == 500.0
    assert parsed.symbol_format == "occ_option"
    assert padded == parsed


def test_parse_unknown_symbol_returns_none():
    assert parse_option_instrument_id("NOT_AN_OPTION") is None
