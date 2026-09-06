from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from math import sqrt

from trading.contracts import DepthSnapshot, TradePrint


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    instrument_token: str
    asof_ts: datetime
    values: dict[str, float]


class CausalFeatureEngine:
    """Online-only features: every output uses observations at or before asof_ts."""

    def __init__(
        self,
        window: int = 100,
        *,
        expected_volume_by_minute: dict[int, float] | None = None,
        prior_closes: dict[str, float] | None = None,
    ) -> None:
        if window < 2:
            raise ValueError("feature window must be at least two")
        self.window = window
        self.expected_volume_by_minute = expected_volume_by_minute or {}
        self.prior_closes = prior_closes or {}
        self.trades: dict[str, deque[tuple[datetime, float, int, int]]] = defaultdict(lambda: deque(maxlen=window))
        self.books: dict[str, DepthSnapshot] = {}
        self.previous_books: dict[str, DepthSnapshot] = {}
        self.spreads: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self.references: dict[str, tuple[datetime, float, float]] = {}
        self.opening: dict[str, tuple[float, float, float]] = {}

    def on_trade(self, event: TradePrint) -> FeatureSnapshot:
        ts = event.times.exchange_ts or event.times.receive_ts
        if ts is None:
            raise ValueError("trade requires source timestamp")
        key = event.instrument.instrument_token
        history = self.trades[key]
        if history and ts < history[-1][0]:
            raise ValueError("out-of-order feature input")
        price = float(event.price)
        previous_price = history[-1][1] if history else price
        previous_sign = 1 if not history else (1 if history[-1][3] > 0 else -1 if history[-1][3] < 0 else 0)
        sign = 1 if price > previous_price else -1 if price < previous_price else previous_sign
        history.append((ts, price, event.quantity, sign * event.quantity))
        if key not in self.opening:
            self.opening[key] = (price, price, price)
        else:
            open_price, high, low = self.opening[key]
            self.opening[key] = (open_price, max(high, price), min(low, price))
        return self.snapshot(key, ts)

    def on_book(self, event: DepthSnapshot) -> FeatureSnapshot:
        ts = event.times.exchange_ts or event.times.receive_ts
        if ts is None:
            raise ValueError("book requires source timestamp")
        key = event.instrument.instrument_token
        current = self.books.get(key)
        current_ts = (current.times.exchange_ts or current.times.receive_ts) if current else None
        if current_ts is not None and ts < current_ts:
            raise ValueError("out-of-order feature input")
        if current is not None:
            self.previous_books[key] = current
        self.books[key] = event
        if event.bids and event.asks:
            self.spreads[key].append(float(event.asks[0].price - event.bids[0].price))
        return self.snapshot(key, ts)

    def update_reference(self, key: str, ts: datetime, *, index_return: float, sector_return: float) -> None:
        current = self.references.get(key)
        if current is not None and ts < current[0]:
            raise ValueError("out-of-order reference input")
        self.references[key] = (ts, index_return, sector_return)

    def snapshot(self, key: str, ts: datetime) -> FeatureSnapshot:
        rows = list(self.trades[key])
        prices = [r[1] for r in rows]
        volumes = [r[2] for r in rows]
        signed_volumes = [r[3] for r in rows]
        total = sum(volumes)
        vwap = sum(p * q for p, q in zip(prices, volumes)) / total if total else 0.0
        previous_total = sum(volumes[:-1])
        previous_vwap = (
            sum(p * q for p, q in zip(prices[:-1], volumes[:-1])) / previous_total if previous_total else vwap
        )
        returns = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices)) if prices[i - 1]]
        realized = sqrt(sum(x * x for x in returns)) if returns else 0.0
        recent_realized = sqrt(sum(x * x for x in returns[-5:])) if returns else 0.0
        expected_volume = self.expected_volume_by_minute.get(ts.hour * 60 + ts.minute, 0.0)
        prior_volume = sum(volumes[:-1])
        elapsed = max((rows[-1][0] - rows[0][0]).total_seconds(), 1.0) if len(rows) > 1 else 1.0
        short_return = returns[-1] if returns else 0.0
        reference = self.references.get(key)
        index_return = reference[1] if reference and reference[0] <= ts else 0.0
        sector_return = reference[2] if reference and reference[0] <= ts else 0.0
        opening = self.opening.get(key)
        open_price, high, low = opening if opening else (0.0, 0.0, 0.0)
        opening_range = high - low
        prior_close = self.prior_closes.get(key, 0.0)
        values = {
            "relative_volume": total / expected_volume if expected_volume > 0 else float(total),
            "time_of_day_expected_volume": expected_volume,
            "volume_acceleration": (
                volumes[-1] / (prior_volume / len(volumes[:-1])) - 1 if len(volumes) > 1 and prior_volume > 0 else 0.0
            ),
            "turnover_acceleration": float(prices[-1] * volumes[-1] - prices[-2] * volumes[-2])
            if len(rows) > 1
            else 0.0,
            "trade_intensity": len(rows) * 60.0 / elapsed,
            "signed_trade_volume": float(sum(signed_volumes)),
            "VWAP": vwap,
            "VWAP_distance": prices[-1] - vwap if prices else 0.0,
            "VWAP_slope": vwap - previous_vwap,
            "short_return": short_return,
            "short_term_momentum": sum(returns[-5:]),
            "short_term_reversal": -sum(returns[-3:]),
            "realized_volatility": realized,
            "volatility_shock": recent_realized / realized if realized > 0 else 0.0,
            "index_relative_strength": short_return - index_return,
            "sector_relative_strength": short_return - sector_return,
            "index_residual_return": short_return - index_return,
            "sector_residual_return": short_return - sector_return,
            "opening_gap": (open_price / prior_close - 1) if prior_close else 0.0,
            "opening_range_position": (prices[-1] - low) / opening_range if prices and opening_range > 0 else 0.0,
        }
        book = self.books.get(key)
        if book and book.bids and book.asks:
            bid, ask = book.bids[0], book.asks[0]
            denom = bid.quantity + ask.quantity
            spread = float(ask.price - bid.price)
            spread_rows = list(self.spreads[key])
            spread_mean = sum(spread_rows) / len(spread_rows)
            spread_variance = sum((item - spread_mean) ** 2 for item in spread_rows) / len(spread_rows)
            previous = self.previous_books.get(key)
            previous_bid_qty = previous.bids[0].quantity if previous and previous.bids else bid.quantity
            previous_ask_qty = previous.asks[0].quantity if previous and previous.asks else ask.quantity
            bid_change = bid.quantity - previous_bid_qty
            ask_change = ask.quantity - previous_ask_qty
            flow_denom = max(1, abs(bid_change) + abs(ask_change))
            depletion = max(0, -bid_change) + max(0, -ask_change)
            replenishment = max(0, bid_change) + max(0, ask_change)
            values.update(
                {
                    "spread": spread,
                    "spread_zscore": (spread - spread_mean) / sqrt(spread_variance) if spread_variance else 0.0,
                    "L1_imbalance": (bid.quantity - ask.quantity) / denom if denom else 0.0,
                    "depth_imbalance": (sum(x.quantity for x in book.bids) - sum(x.quantity for x in book.asks))
                    / max(1, sum(x.quantity for x in (*book.bids, *book.asks))),
                    "order_flow_imbalance": (bid_change - ask_change) / flow_denom,
                    "microprice": float((ask.price * bid.quantity + bid.price * ask.quantity) / denom)
                    if denom
                    else 0.0,
                    "liquidity_depletion": float(depletion),
                    "liquidity_replenishment": float(replenishment),
                }
            )
        return FeatureSnapshot(key, ts, values)
