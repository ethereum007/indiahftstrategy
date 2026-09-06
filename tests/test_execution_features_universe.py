from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from execution.features import CausalFeatureEngine
from execution.universe import (
    LiquidityFilters,
    LiquidityObservation,
    UniverseDefinition,
    UniverseTier,
    liquid_universe,
    select_liquid_universe,
)
from trading.contracts import DepthLevel, DepthSnapshot, EventTimes, Instrument, InstrumentIdentity, TradePrint


def instrument():
    return Instrument(InstrumentIdentity("NSE", "CM", "ABC", "ABC"), "1", "ABC.NSE.EQ", 1, Decimal("0.05"))


def test_online_features_are_causal_and_support_depth():
    inst = instrument()
    now = datetime.now(UTC)
    engine = CausalFeatureEngine()
    book = DepthSnapshot(
        inst,
        (DepthLevel(Decimal(99), 20),),
        (DepthLevel(Decimal(101), 10),),
        EventTimes(exchange_ts=now),
    )
    snapshot = engine.on_book(book)
    assert snapshot.values["microprice"] > 99 and snapshot.values["L1_imbalance"] > 0
    trade = TradePrint(inst, Decimal(100), 5, EventTimes(exchange_ts=now + timedelta(milliseconds=1)))
    assert engine.on_trade(trade).values["VWAP"] == 100
    with pytest.raises(ValueError, match="out-of-order"):
        engine.on_trade(TradePrint(inst, Decimal(99), 1, EventTimes(exchange_ts=now)))


def test_nse_liquidity_universe_fails_illiquid_names():
    limits = LiquidityFilters(Decimal(1000000), Decimal(10), 100, Decimal(5), Decimal(20), 1000, 10000)
    liquid = LiquidityObservation("LIQUID", Decimal(2000000), Decimal(2), 500, Decimal(20), Decimal(100), 10, 50000)
    illiquid = LiquidityObservation("ILLIQUID", Decimal(10), Decimal(100), 1, Decimal(0), Decimal(1), 5000, 1)
    assert liquid_universe([liquid, illiquid], limits) == ("LIQUID",)


def test_online_features_calculate_flow_rvol_opening_and_residuals_without_lookahead():
    inst = instrument()
    start = datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    minute = start.hour * 60 + start.minute
    engine = CausalFeatureEngine(expected_volume_by_minute={minute: 10.0}, prior_closes={inst.instrument_token: 95.0})
    engine.update_reference(inst.instrument_token, start, index_return=0.01, sector_return=0.02)
    engine.on_trade(TradePrint(inst, Decimal(100), 4, EventTimes(exchange_ts=start)))
    trade = engine.on_trade(TradePrint(inst, Decimal(102), 6, EventTimes(exchange_ts=start + timedelta(seconds=1))))
    assert trade.values["relative_volume"] == 1.0
    assert trade.values["signed_trade_volume"] == 10.0
    assert trade.values["VWAP_slope"] > 0
    assert trade.values["opening_gap"] > 0
    assert trade.values["index_residual_return"] == pytest.approx(0.01)
    assert trade.values["opening_range_position"] == 1.0

    first = DepthSnapshot(
        inst,
        (DepthLevel(Decimal(101), 20),),
        (DepthLevel(Decimal(103), 20),),
        EventTimes(exchange_ts=start),
    )
    second = DepthSnapshot(
        inst,
        (DepthLevel(Decimal(101), 30),),
        (DepthLevel(Decimal(104), 10),),
        EventTimes(exchange_ts=start + timedelta(seconds=2)),
    )
    engine.on_book(first)
    book = engine.on_book(second)
    assert book.values["order_flow_imbalance"] == 1.0
    assert book.values["liquidity_depletion"] == 10.0
    assert book.values["liquidity_replenishment"] == 10.0
    assert book.values["spread_zscore"] == 1.0

    with pytest.raises(ValueError, match="out-of-order"):
        engine.update_reference(
            inst.instrument_token,
            start - timedelta(seconds=1),
            index_return=999,
            sector_return=999,
        )


def test_named_nifty_universe_is_versioned_liquidity_filtered_and_capacity_limited():
    definition = UniverseDefinition(
        UniverseTier.NIFTY50,
        ("AAA", "BBB", "MISSING"),
        date(2026, 1, 1),
        "a" * 64,
    )
    limits = LiquidityFilters(Decimal(100), Decimal(10), 10, Decimal(1), Decimal(5), 1000, 100)
    rows = [
        LiquidityObservation("AAA", Decimal(1000), Decimal(2), 100, Decimal(5), Decimal(50), 1, 1000),
        LiquidityObservation("BBB", Decimal(500), Decimal(50), 100, Decimal(5), Decimal(50), 1, 1000),
        LiquidityObservation("OUTSIDE", Decimal(5000), Decimal(1), 100, Decimal(5), Decimal(50), 1, 1000),
    ]
    result = select_liquid_universe(definition, rows, limits, max_names=1)
    assert result.selected == ("AAA",)
    assert result.rejected == ("BBB",)
    assert result.missing_market_data == ("MISSING",)
    with pytest.raises(ValueError, match="unique"):
        UniverseDefinition(UniverseTier.NIFTY50, ("AAA", "AAA"), date(2026, 1, 1), "a" * 64)
    with pytest.raises(ValueError, match="canonical"):
        UniverseDefinition(UniverseTier.NIFTY50, (" AAA",), date(2026, 1, 1), "a" * 64)
    with pytest.raises(ValueError, match="checksum"):
        UniverseDefinition(UniverseTier.NIFTY50, ("AAA",), date(2026, 1, 1), "z" * 64)
