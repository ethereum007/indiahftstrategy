import numpy as np
import pandas as pd

from engine.surface import FittedVolSurface, black76_price
from strategies.surface_mm import QuoteBudget, SurfaceQuoteConfig, generate_surface_quotes


def flat_surface():
    points = pd.DataFrame(
        [{"strike": 100.0, "option_type": "C", "mid": 2.0, "implied_vol": 0.2}]
    )
    return FittedVolSurface(
        forward=100.0,
        tte_years=0.25,
        coeffs=np.array([0.0, 0.0, 0.2]),
        iv_points=points,
    )


def test_generate_surface_quotes_rounds_prices_and_applies_inventory_skew():
    surface = flat_surface()
    universe = pd.DataFrame(
        [
            {
                "instrument_id": "CALL100",
                "strike": 100.0,
                "option_type": "C",
                "bid": 3.5,
                "ask": 4.5,
            }
        ]
    )
    config = SurfaceQuoteConfig(
        tick_size=0.05,
        lot_size=75,
        quote_lots=2,
        edge_ticks=2.0,
        inventory_skew_ticks_per_lot=1.0,
    )

    quotes = generate_surface_quotes(
        universe,
        surface,
        config=config,
        positions={"CALL100": 150},
    )
    theo = black76_price(option_type="C", forward=100.0, strike=100.0, tte_years=0.25, vol=0.2)
    bid = quotes.loc[quotes["side"] == 1].iloc[0]
    ask = quotes.loc[quotes["side"] == -1].iloc[0]

    assert len(quotes) == 2
    assert bid["qty"] == 150
    assert bid["price"] <= theo - 4 * 0.05
    assert ask["price"] >= theo
    assert bid["skew_ticks"] == 2.0


def test_generate_surface_quotes_respects_budget_and_spread_filter():
    universe = pd.DataFrame(
        [
            {"instrument_id": "ATM", "strike": 100.0, "option_type": "C", "bid": 3.9, "ask": 4.0},
            {"instrument_id": "WIDE", "strike": 120.0, "option_type": "C", "bid": 1.0, "ask": 5.0},
        ]
    )

    quotes = generate_surface_quotes(
        universe,
        flat_surface(),
        config=SurfaceQuoteConfig(
            tick_size=0.05,
            lot_size=75,
            max_market_spread_ticks=10,
        ),
        budget=QuoteBudget(max_order_messages=1),
    )

    assert len(quotes) == 1
    assert set(quotes["instrument_id"]) == {"ATM"}
