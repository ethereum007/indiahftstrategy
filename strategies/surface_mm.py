from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from engine.surface import FittedVolSurface


QUOTE_UNIVERSE_REQUIRED = ["instrument_id", "strike", "option_type"]


@dataclass(frozen=True)
class QuoteBudget:
    max_order_messages: int
    used_order_messages: int = 0

    @property
    def remaining_messages(self) -> int:
        return max(self.max_order_messages - self.used_order_messages, 0)


@dataclass(frozen=True)
class SurfaceQuoteConfig:
    tick_size: float
    lot_size: int
    quote_lots: int = 1
    edge_ticks: float = 2.0
    inventory_skew_ticks_per_lot: float = 0.5
    min_price: float | None = None
    max_market_spread_ticks: float | None = None
    max_quotes: int | None = None


def generate_surface_quotes(
    universe: pd.DataFrame,
    surface: FittedVolSurface,
    *,
    config: SurfaceQuoteConfig,
    positions: Mapping[str, int] | None = None,
    budget: QuoteBudget | None = None,
) -> pd.DataFrame:
    """Generate two-sided option quotes from a fitted surface.

    Inventory skew moves both sides lower when long and higher when short, so
    the desk naturally leans toward reducing inventory.
    """

    _require(universe, QUOTE_UNIVERSE_REQUIRED, "universe")
    if config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if config.lot_size <= 0 or config.quote_lots <= 0:
        raise ValueError("lot_size and quote_lots must be positive")

    rows = []
    positions = positions or {}
    candidates = universe.copy()
    if config.max_market_spread_ticks is not None and {"bid", "ask"}.issubset(candidates.columns):
        spread_ticks = (candidates["ask"] - candidates["bid"]) / config.tick_size
        candidates = candidates.loc[spread_ticks <= config.max_market_spread_ticks].copy()
        candidates["market_spread_ticks"] = spread_ticks.loc[candidates.index]
    else:
        candidates["market_spread_ticks"] = np.nan
    candidates["abs_log_moneyness"] = np.abs(np.log(candidates["strike"] / surface.forward))
    candidates = candidates.sort_values(["market_spread_ticks", "abs_log_moneyness"], na_position="last")

    max_messages = budget.remaining_messages if budget else None
    if config.max_quotes is not None:
        max_messages = config.max_quotes if max_messages is None else min(max_messages, config.max_quotes)
    messages_used = 0

    for row in candidates.itertuples(index=False):
        instrument_id = str(row.instrument_id)
        strike = float(row.strike)
        option_type = str(row.option_type).upper()
        theo = surface.theo_price(option_type=option_type, strike=strike)
        iv = surface.predict_iv(strike)
        inventory_lots = positions.get(instrument_id, 0) / config.lot_size
        skew_ticks = inventory_lots * config.inventory_skew_ticks_per_lot
        bid_px = _round_down(theo - (config.edge_ticks + skew_ticks) * config.tick_size, config.tick_size)
        ask_px = _round_up(theo + (config.edge_ticks - skew_ticks) * config.tick_size, config.tick_size)
        min_price = config.min_price if config.min_price is not None else config.tick_size
        bid_px = max(bid_px, min_price)
        ask_px = max(ask_px, bid_px + config.tick_size)
        qty = config.quote_lots * config.lot_size

        for side, price in ((+1, bid_px), (-1, ask_px)):
            if max_messages is not None and messages_used >= max_messages:
                return pd.DataFrame(rows)
            rows.append(
                {
                    "instrument_id": instrument_id,
                    "strike": strike,
                    "option_type": option_type,
                    "side": side,
                    "price": float(price),
                    "qty": int(qty),
                    "theo": float(theo),
                    "implied_vol": float(iv),
                    "edge_ticks": float(config.edge_ticks),
                    "inventory_lots": float(inventory_lots),
                    "skew_ticks": float(skew_ticks),
                }
            )
            messages_used += 1
    return pd.DataFrame(rows)


def _round_down(value: float, tick: float) -> float:
    return math.floor((value + 1e-12) / tick) * tick


def _round_up(value: float, tick: float) -> float:
    return math.ceil((value - 1e-12) / tick) * tick


def _require(df: pd.DataFrame, columns: list[str], name: str):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
