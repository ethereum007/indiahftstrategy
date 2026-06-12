from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.hft_backtest import OrderType
from engine.multi_engine import MultiInstrumentEngine, MultiInstrumentStrategy, RoutedFill


@dataclass(frozen=True)
class ParityLegMap:
    future_id: str
    call_by_strike: dict[float, str]
    put_by_strike: dict[float, str]


@dataclass(frozen=True)
class ParityArbConfig:
    max_signal_age_ns: int = 1_000_000
    max_qty: int | None = None


@dataclass
class SignalExecution:
    signal_index: int
    direction: str
    strike: float
    ts_ns: int
    order_ids: list[int] = field(default_factory=list)
    fill_count: int = 0


class ParityArbTakerStrategy(MultiInstrumentStrategy):
    """Replay scanner parity signals as three IOC legs.

    Supported directions:
    - buy_synthetic_sell_future: buy call, sell put, sell future
    - sell_synthetic_buy_future: sell call, buy put, buy future
    """

    def __init__(
        self,
        signals: pd.DataFrame,
        leg_map: ParityLegMap,
        config: ParityArbConfig | None = None,
    ):
        self.signals = signals.sort_values("ts").reset_index(drop=True)
        self.leg_map = leg_map
        self.config = config or ParityArbConfig()
        self.next_signal = 0
        self.executions: list[SignalExecution] = []
        self.order_to_execution: dict[int, int] = {}

    def on_start(self, engine: MultiInstrumentEngine):
        self.next_signal = 0

    def on_tick(self, engine: MultiInstrumentEngine, instrument_id: str, tick: dict):
        now = int(tick["ts"])
        while self.next_signal < len(self.signals):
            signal = self.signals.iloc[self.next_signal]
            signal_ts = int(signal["ts"])
            if signal_ts > now:
                break
            if now - signal_ts > self.config.max_signal_age_ns:
                self.next_signal += 1
                continue
            routed = self._try_execute(engine, self.next_signal, signal, now)
            if not routed:
                break
            self.next_signal += 1

    def on_fill(self, engine: MultiInstrumentEngine, fill: RoutedFill):
        execution_idx = self.order_to_execution.get(fill.oid)
        if execution_idx is not None:
            self.executions[execution_idx].fill_count += 1

    def on_end(self, engine: MultiInstrumentEngine):
        pass

    def legging_report(self) -> pd.DataFrame:
        rows = []
        for execution in self.executions:
            rows.append(
                {
                    "signal_index": execution.signal_index,
                    "direction": execution.direction,
                    "strike": execution.strike,
                    "order_count": len(execution.order_ids),
                    "fill_count": execution.fill_count,
                    "partial": execution.fill_count != len(execution.order_ids),
                }
            )
        return pd.DataFrame(rows)

    def _try_execute(
        self,
        engine: MultiInstrumentEngine,
        signal_index: int,
        signal: pd.Series,
        now: int,
    ) -> bool:
        strike = float(signal["strike"])
        qty = int(signal["qty"])
        if self.config.max_qty is not None:
            qty = min(qty, self.config.max_qty)
        if qty <= 0:
            return True
        call_id = self.leg_map.call_by_strike.get(strike)
        put_id = self.leg_map.put_by_strike.get(strike)
        future_id = self.leg_map.future_id
        if not call_id or not put_id:
            return False
        call = engine.last_tick(call_id)
        put = engine.last_tick(put_id)
        future = engine.last_tick(future_id)
        if call is None or put is None or future is None:
            return False

        direction = str(signal["direction"])
        if direction == "buy_synthetic_sell_future":
            legs = [
                (call_id, +1, call["ask"]),
                (put_id, -1, put["bid"]),
                (future_id, -1, future["bid"]),
            ]
        elif direction == "sell_synthetic_buy_future":
            legs = [
                (call_id, -1, call["bid"]),
                (put_id, +1, put["ask"]),
                (future_id, +1, future["ask"]),
            ]
        else:
            return True

        execution = SignalExecution(signal_index, direction, strike, now)
        self.executions.append(execution)
        execution_idx = len(self.executions) - 1
        for leg_instrument_id, side, price in legs:
            oid = engine.send(leg_instrument_id, side, qty, price, OrderType.IOC)
            if oid is not None:
                execution.order_ids.append(oid)
                self.order_to_execution[oid] = execution_idx
        if not execution.order_ids:
            self.executions.pop()
            return False
        return True
