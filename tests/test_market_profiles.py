import pandas as pd

from data.loaders import normalize_ticks, trading_session_mask
from engine.costs import GenericCostModel
from engine.hft_backtest import Instrument, Kind
from markets.profiles import get_market_profile, session_mask


def ns(value: str, tz: str) -> int:
    return pd.Timestamp(value, tz=tz).value


def test_india_and_us_market_profiles_filter_regular_sessions():
    india_ts = pd.Series(
        [
            ns("2026-06-10 09:14:59", "Asia/Kolkata"),
            ns("2026-06-10 09:15:00", "Asia/Kolkata"),
            ns("2026-06-10 15:30:00", "Asia/Kolkata"),
            ns("2026-06-10 15:30:01", "Asia/Kolkata"),
        ]
    )
    us_ts = pd.Series(
        [
            ns("2026-06-10 09:29:59", "America/New_York"),
            ns("2026-06-10 09:30:00", "America/New_York"),
            ns("2026-06-10 16:00:00", "America/New_York"),
            ns("2026-06-10 16:00:01", "America/New_York"),
        ]
    )

    assert list(trading_session_mask(india_ts)) == [False, True, True, False]
    assert list(session_mask(us_ts, market="us_equities_regular")) == [False, True, True, False]


def test_normalize_ticks_can_use_us_market_session():
    raw = pd.DataFrame(
        [
            {
                "ts": ns("2026-06-10 09:29:59", "America/New_York"),
                "bid": 100.0,
                "ask": 100.01,
                "bid_qty": 100,
                "ask_qty": 100,
            },
            {
                "ts": ns("2026-06-10 09:30:00", "America/New_York"),
                "bid": 100.0,
                "ask": 100.01,
                "bid_qty": 100,
                "ask_qty": 100,
            },
        ]
    )

    normalized = normalize_ticks(raw, market="us_equities_regular")

    assert len(normalized.data) == 1
    assert normalized.quarantine.dropped_out_of_session_rows == 1
    assert normalized.data["regime"].tolist() == ["baseline_market_structure"]


def test_market_profile_lookup_and_generic_cost_model():
    profile = get_market_profile("us_options_regular")
    inst = Instrument("SPY250620C00500000", Kind.OPT, lot_size=100, tick=0.01)
    costs = GenericCostModel(
        buy_notional_rate=0.00001,
        sell_notional_rate=0.00002,
        per_contract_fee=0.10,
        per_order_fee=0.25,
    )

    assert profile.currency == "USD"
    assert profile.default_lot_size == 100
    assert costs.cost(+1, 5.0, 100, inst) == 0.005 + 0.10 + 0.25
    assert costs.cost(-1, 5.0, 100, inst) == 0.010 + 0.10 + 0.25
