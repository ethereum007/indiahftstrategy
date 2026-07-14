from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.hft_backtest import OrderType
from engine.multi_engine import MultiInstrumentEngine, MultiInstrumentStrategy, RoutedFill
from strategies.microprice_features import (
    microprice_entry_side,
    microprice_exit_action,
    microprice_features,
)


@dataclass(frozen=True)
class MicropriceImbalanceConfig:
    instrument_id: str
    qty: int
    tick_size: float
    entry_imbalance: float = 0.6
    exit_imbalance: float = 0.15
    min_microprice_edge_ticks: float = 0.25
    max_spread_ticks: float = 2.0
    min_depth: int = 1
    hold_ns: int = 500_000_000
    cooloff_ns: int = 0


class MicropriceImbalanceStrategy(MultiInstrumentStrategy):
    """Trades short-horizon top-of-book pressure from imbalance and microprice."""

    def __init__(self, config: MicropriceImbalanceConfig):
        _validate_config(config)
        self.config = config
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self.entry_ts: int | None = None
        self.last_order_ts: int | None = None
        self.entry_orders: list[int] = []
        self.exit_orders: list[int] = []
        self.fills: list[RoutedFill] = []
        self.signals: list[dict[str, object]] = []

    def on_start(self, engine: MultiInstrumentEngine):
        self._reset_run_state()

    def on_tick(self, engine: MultiInstrumentEngine, instrument_id: str, tick: dict):
        if instrument_id != self.config.instrument_id:
            return
        now = int(tick["ts"])
        features = microprice_features(tick, self.config.tick_size)
        if features is None:
            return

        pos = engine.positions.get(self.config.instrument_id, 0)
        if pos != 0:
            self._maybe_exit(engine, tick, features, pos, now)
            return
        if self.last_order_ts is not None and now - self.last_order_ts < self.config.cooloff_ns:
            return
        if features["spread_ticks"] > self.config.max_spread_ticks:
            return
        if min(float(tick["bid_qty"]), float(tick["ask_qty"])) < self.config.min_depth:
            return

        side = self._entry_side(features)
        if side == 0:
            return
        price = float(tick["ask"] if side > 0 else tick["bid"])
        oid = engine.send(self.config.instrument_id, side, self.config.qty, price, OrderType.IOC)
        self._record_signal(tick, features, side=side, price=price, action="entry", oid=oid)
        if oid is not None:
            self.entry_orders.append(oid)
            self.last_order_ts = now

    def on_fill(self, engine: MultiInstrumentEngine, fill: RoutedFill):
        self.fills.append(fill)
        if fill.oid in self.entry_orders:
            self.entry_ts = int(fill.ts_ns)
        if fill.oid in self.exit_orders and engine.positions.get(self.config.instrument_id, 0) == 0:
            self.entry_ts = None

    def on_end(self, engine: MultiInstrumentEngine):
        pass

    def _entry_side(self, features: dict[str, float]) -> int:
        return microprice_entry_side(
            features,
            entry_imbalance=self.config.entry_imbalance,
            min_microprice_edge_ticks=(
                self.config.min_microprice_edge_ticks
            ),
        )

    def _maybe_exit(
        self,
        engine: MultiInstrumentEngine,
        tick: dict,
        features: dict[str, float],
        pos: int,
        now: int,
    ) -> None:
        action = microprice_exit_action(
            features,
            position_lots=pos,
            entry_ts_ns=self.entry_ts,
            now_ns=now,
            hold_ns=self.config.hold_ns,
            exit_imbalance=self.config.exit_imbalance,
        )
        if not action:
            return
        side = -1 if pos > 0 else +1
        price = float(tick["bid"] if side < 0 else tick["ask"])
        oid = engine.send(self.config.instrument_id, side, abs(pos), price, OrderType.IOC)
        self._record_signal(
            tick,
            features,
            side=side,
            price=price,
            action=action,
            oid=oid,
        )
        if oid is not None:
            self.exit_orders.append(oid)
            self.last_order_ts = now

    def _record_signal(
        self,
        tick: dict,
        features: dict[str, float],
        *,
        side: int,
        price: float,
        action: str,
        oid: int | None,
    ) -> None:
        self.signals.append(
            {
                "ts": int(tick["ts"]),
                "market_ts": int(tick.get("market_ts", tick["ts"])),
                "action": action,
                "side": int(side),
                "qty": int(self.config.qty),
                "price": float(price),
                "order_id": oid if oid is not None else "",
                "bid": float(tick["bid"]),
                "ask": float(tick["ask"]),
                "bid_qty": int(tick["bid_qty"]),
                "ask_qty": int(tick["ask_qty"]),
                "spread_ticks": features["spread_ticks"],
                "imbalance": features["imbalance"],
                "microprice": features["microprice"],
                "microprice_edge_ticks": features["microprice_edge_ticks"],
            }
        )

def _validate_config(config: MicropriceImbalanceConfig) -> None:
    if not config.instrument_id:
        raise ValueError("instrument_id must not be blank")
    if config.qty <= 0:
        raise ValueError("qty must be positive")
    if config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if not 0 < config.entry_imbalance < 1:
        raise ValueError("entry_imbalance must be between 0 and 1")
    if not 0 <= config.exit_imbalance < config.entry_imbalance:
        raise ValueError("exit_imbalance must be non-negative and below entry_imbalance")
    if config.min_microprice_edge_ticks < 0:
        raise ValueError("min_microprice_edge_ticks must be non-negative")
    if config.max_spread_ticks <= 0 or np.isnan(config.max_spread_ticks):
        raise ValueError("max_spread_ticks must be positive")
    if config.min_depth <= 0:
        raise ValueError("min_depth must be positive")
    if config.hold_ns <= 0:
        raise ValueError("hold_ns must be positive")
    if config.cooloff_ns < 0:
        raise ValueError("cooloff_ns must be non-negative")
