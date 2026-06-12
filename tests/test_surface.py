import math

import pandas as pd

from engine.surface import black76_price, fit_quadratic_smile, implied_vol_black76


def test_black76_put_call_parity_on_forward():
    call = black76_price(option_type="C", forward=100.0, strike=95.0, tte_years=0.25, vol=0.2)
    put = black76_price(option_type="P", forward=100.0, strike=95.0, tte_years=0.25, vol=0.2)

    assert math.isclose(call - put, 5.0, abs_tol=1e-10)


def test_implied_vol_recovers_planted_vol():
    price = black76_price(
        option_type="C",
        forward=100.0,
        strike=105.0,
        tte_years=0.5,
        vol=0.35,
    )

    iv = implied_vol_black76(
        option_type="C",
        price=price,
        forward=100.0,
        strike=105.0,
        tte_years=0.5,
    )

    assert math.isclose(iv, 0.35, rel_tol=1e-7)


def test_fit_quadratic_smile_predicts_planted_surface():
    forward = 100.0
    tte = 0.25
    strikes = [85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0]
    rows = []
    for strike in strikes:
        x = math.log(strike / forward)
        vol = 0.22 - 0.05 * x + 0.40 * x * x
        rows.append(
            {
                "strike": strike,
                "option_type": "C",
                "mid": black76_price(
                    option_type="C",
                    forward=forward,
                    strike=strike,
                    tte_years=tte,
                    vol=vol,
                ),
            }
        )

    surface = fit_quadratic_smile(pd.DataFrame(rows), forward=forward, tte_years=tte)

    for strike in [92.0, 100.0, 108.0]:
        x = math.log(strike / forward)
        expected = 0.22 - 0.05 * x + 0.40 * x * x
        assert math.isclose(surface.predict_iv(strike), expected, rel_tol=1e-5)
