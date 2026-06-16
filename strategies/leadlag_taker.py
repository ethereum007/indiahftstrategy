from __future__ import annotations

from dataclasses import dataclass

from engine.hft_backtest import OrderType
from engine.multi_engine import MultiInstrumentEngine, MultiInstrumentStrategy, RoutedFill


@dataclass(frozen=True)
class LeadLagTakerConfig:
    leader_id: str
    laggard_id: str
    qty: int
    delta: float
    leader_tick: float
    laggard_tick: float
    trigger_ticks: float = 3.0
    flat_after_ns: int = 500_000_000
    cooloff_ns: int = 0


class LeadLagTakerStrategy(MultiInstrumentStrategy):
    """Takes stale laggard quotes after leader mid-price innovations."""

    def __init__(self, config: LeadLagTakerConfig):
        self.config = config
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self.prev_leader_mid: float | None = None
        self.entry_ts: int | None = None
        self.last_trade_ts: int | None = None
        self.entry_orders: list[int] = []
        self.exit_orders: list[int] = []
        self.fills: list[RoutedFill] = []

    def on_start(self, engine: MultiInstrumentEngine):
        self._reset_run_state()

    def on_tick(self, engine: MultiInstrumentEngine, instrument_id: str, tick: dict):
        now = int(tick["ts"])
        self._maybe_flatten(engine, now)
        if instrument_id != self.config.leader_id:
            return
        leader_mid = 0.5 * (tick["bid"] + tick["ask"])
        if self.prev_leader_mid is None:
            self.prev_leader_mid = leader_mid
            return
        leader_move = leader_mid - self.prev_leader_mid
        self.prev_leader_mid = leader_mid
        if abs(leader_move) < self.config.leader_tick:
            return
        if self.last_trade_ts is not None and now - self.last_trade_ts < self.config.cooloff_ns:
            return
        if engine.positions.get(self.config.laggard_id, 0) != 0:
            return

        expected_ticks = (leader_move * self.config.delta) / self.config.laggard_tick
        if abs(expected_ticks) < self.config.trigger_ticks:
            return
        laggard = engine.last_tick(self.config.laggard_id)
        if laggard is None:
            return
        if expected_ticks > 0:
            oid = engine.send(
                self.config.laggard_id,
                +1,
                self.config.qty,
                laggard["ask"],
                OrderType.IOC,
            )
        else:
            oid = engine.send(
                self.config.laggard_id,
                -1,
                self.config.qty,
                laggard["bid"],
                OrderType.IOC,
            )
        if oid is not None:
            self.entry_orders.append(oid)
            self.entry_ts = now
            self.last_trade_ts = now

    def on_fill(self, engine: MultiInstrumentEngine, fill: RoutedFill):
        self.fills.append(fill)

    def on_end(self, engine: MultiInstrumentEngine):
        pass

    def _maybe_flatten(self, engine: MultiInstrumentEngine, now: int):
        if self.entry_ts is None or now - self.entry_ts < self.config.flat_after_ns:
            return
        pos = engine.positions.get(self.config.laggard_id, 0)
        if pos == 0:
            self.entry_ts = None
            return
        laggard = engine.last_tick(self.config.laggard_id)
        if laggard is None:
            return
        side = -1 if pos > 0 else +1
        price = laggard["bid"] if side < 0 else laggard["ask"]
        oid = engine.send(self.config.laggard_id, side, abs(pos), price, OrderType.IOC)
        if oid is not None:
            self.exit_orders.append(oid)
            self.last_trade_ts = now
            self.entry_ts = None
