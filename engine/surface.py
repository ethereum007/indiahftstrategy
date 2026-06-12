from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black76_price(
    *,
    option_type: str,
    forward: float,
    strike: float,
    tte_years: float,
    vol: float,
    discount: float = 1.0,
) -> float:
    option = option_type.upper()
    if forward <= 0 or strike <= 0:
        raise ValueError("forward and strike must be positive")
    if discount <= 0:
        raise ValueError("discount must be positive")
    if tte_years <= 0 or vol <= 0:
        intrinsic = max(forward - strike, 0.0) if option == "C" else max(strike - forward, 0.0)
        return discount * intrinsic
    sqrt_t = math.sqrt(tte_years)
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * tte_years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    if option == "C":
        return discount * (forward * normal_cdf(d1) - strike * normal_cdf(d2))
    if option == "P":
        return discount * (strike * normal_cdf(-d2) - forward * normal_cdf(-d1))
    raise ValueError("option_type must be 'C' or 'P'")


def implied_vol_black76(
    *,
    option_type: str,
    price: float,
    forward: float,
    strike: float,
    tte_years: float,
    discount: float = 1.0,
    low: float = 1e-6,
    high: float = 5.0,
    tol: float = 1e-8,
    max_iter: int = 100,
) -> float:
    if price < 0:
        raise ValueError("price must be non-negative")
    intrinsic = black76_price(
        option_type=option_type,
        forward=forward,
        strike=strike,
        tte_years=0,
        vol=0,
        discount=discount,
    )
    if price < intrinsic - tol:
        raise ValueError("price is below intrinsic value")
    while black76_price(
        option_type=option_type,
        forward=forward,
        strike=strike,
        tte_years=tte_years,
        vol=high,
        discount=discount,
    ) < price:
        high *= 2.0
        if high > 20:
            raise ValueError("could not bracket implied volatility")
    lo, hi = low, high
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        value = black76_price(
            option_type=option_type,
            forward=forward,
            strike=strike,
            tte_years=tte_years,
            vol=mid,
            discount=discount,
        )
        if abs(value - price) <= tol:
            return mid
        if value < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class FittedVolSurface:
    forward: float
    tte_years: float
    coeffs: np.ndarray
    iv_points: pd.DataFrame
    min_vol: float = 0.01

    def predict_iv(self, strike: float) -> float:
        x = math.log(strike / self.forward)
        return max(float(np.polyval(self.coeffs, x)), self.min_vol)

    def theo_price(self, *, option_type: str, strike: float, discount: float = 1.0) -> float:
        return black76_price(
            option_type=option_type,
            forward=self.forward,
            strike=strike,
            tte_years=self.tte_years,
            vol=self.predict_iv(strike),
            discount=discount,
        )


def fit_quadratic_smile(
    quotes: pd.DataFrame,
    *,
    forward: float,
    tte_years: float,
    discount: float = 1.0,
    min_vol: float = 0.01,
) -> FittedVolSurface:
    required = ["strike", "option_type", "mid"]
    missing = [col for col in required if col not in quotes.columns]
    if missing:
        raise ValueError(f"quotes missing required columns: {missing}")
    rows = []
    for row in quotes.itertuples(index=False):
        iv = implied_vol_black76(
            option_type=row.option_type,
            price=float(row.mid),
            forward=forward,
            strike=float(row.strike),
            tte_years=tte_years,
            discount=discount,
        )
        rows.append(
            {
                "strike": float(row.strike),
                "option_type": str(row.option_type).upper(),
                "mid": float(row.mid),
                "log_moneyness": math.log(float(row.strike) / forward),
                "implied_vol": iv,
            }
        )
    points = pd.DataFrame(rows)
    degree = min(2, len(points) - 1)
    if degree < 0:
        raise ValueError("at least one quote is required")
    coeffs = np.polyfit(points["log_moneyness"], points["implied_vol"], degree)
    if degree < 2:
        coeffs = np.pad(coeffs, (2 - degree, 0), mode="constant")
    return FittedVolSurface(
        forward=forward,
        tte_years=tte_years,
        coeffs=coeffs,
        iv_points=points,
        min_vol=min_vol,
    )
