from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from strategies.microprice_features import (
    microprice_entry_side,
    microprice_exit_action,
    microprice_features,
)


REQUIRED_TELEMETRY_COLUMNS = (
    "sequence",
    "ts_ns",
    "source_mode",
    "symbol",
    "bid_price",
    "ask_price",
    "bid_qty",
    "ask_qty",
    "accepted",
    "breach_code",
)
FEATURE_COLUMNS = (
    "sequence",
    "ts_ns",
    "symbol",
    "bid_price",
    "ask_price",
    "bid_qty",
    "ask_qty",
    "spread_ticks",
    "imbalance",
    "microprice",
    "microprice_edge_ticks",
    "signal_action",
    "signal_side",
    "shadow_position_lots",
    "cumulative_shadow_notional",
    "halted",
    "breach_code",
)
INTENT_COLUMNS = (
    "intent_sequence",
    "source_sequence",
    "ts_ns",
    "symbol",
    "action",
    "side",
    "side_name",
    "quantity_lots",
    "quantity_units",
    "limit_price",
    "intent_notional",
    "cumulative_notional_before",
    "prospective_cumulative_notional",
    "cumulative_notional_after",
    "position_before_lots",
    "prospective_position_lots",
    "shadow_position_after_lots",
    "shadow_open_orders",
    "within_limits",
    "breach_code",
    "intent_status",
    "routing_status",
    "submission_status",
    "shadow_fill_assumption",
)


class ShadowMicropriceEvaluationError(ValueError):
    """Raised when a shadow-evaluation contract is invalid."""


@dataclass(frozen=True)
class ShadowMicropriceConfig:
    lot_size: int = 1
    intent_quantity_lots: int = 1
    tick_size: float = 0.05
    entry_imbalance: float = 0.6
    exit_imbalance: float = 0.15
    min_microprice_edge_ticks: float = 0.25
    max_spread_ticks: float = 2.0
    min_depth: int = 1
    hold_ns: int = 500_000_000
    cooloff_ns: int = 0
    terminal_flatten: bool = True


@dataclass(frozen=True)
class ShadowRuntimeLimits:
    max_orders_per_session: int
    max_notional_per_session: float
    max_open_orders: int
    max_position_lots: int


@dataclass(frozen=True)
class ShadowKillSwitch:
    enabled: bool
    trigger_on_limit_breach: bool
    stop_new_orders: bool
    cancel_open_orders: bool


@dataclass(frozen=True)
class ShadowMicropriceEvaluationResult:
    features: pd.DataFrame
    intents: pd.DataFrame
    source_event_count: int
    processed_event_count: int
    observed_intent_count: int
    rejected_intent_count: int
    ending_shadow_position_lots: int
    cumulative_shadow_notional: float
    max_shadow_open_orders: int
    completed: bool
    halted: bool
    halt_reason: str


def evaluate_shadow_microprice_session(
    telemetry: pd.DataFrame,
    *,
    config: ShadowMicropriceConfig,
    limits: ShadowRuntimeLimits,
    kill_switch: ShadowKillSwitch,
) -> ShadowMicropriceEvaluationResult:
    _validate_config(config)
    _validate_limits(limits)
    _validate_kill_switch(kill_switch)
    source = _validated_telemetry(telemetry)

    feature_rows: list[dict[str, Any]] = []
    intent_rows: list[dict[str, Any]] = []
    position_lots = 0
    entry_ts_ns: int | None = None
    last_intent_ts_ns: int | None = None
    cumulative_notional = 0.0
    observed_intents = 0
    rejected_intents = 0
    halt_reason = ""

    for row in source.itertuples(index=False):
        sequence = int(row.sequence)
        now_ns = int(row.ts_ns)
        tick = {
            "bid": float(row.bid_price),
            "ask": float(row.ask_price),
            "bid_qty": float(row.bid_qty),
            "ask_qty": float(row.ask_qty),
        }
        features = microprice_features(tick, config.tick_size)
        if features is None:
            raise ShadowMicropriceEvaluationError(
                f"source event {sequence} has an invalid book"
            )
        action, side, quantity_lots = _candidate(
            features=features,
            tick=tick,
            position_lots=position_lots,
            entry_ts_ns=entry_ts_ns,
            last_intent_ts_ns=last_intent_ts_ns,
            now_ns=now_ns,
            config=config,
        )
        event_breach = ""
        if action:
            intent, event_breach = _intent(
                intent_sequence=len(intent_rows) + 1,
                source_sequence=sequence,
                now_ns=now_ns,
                symbol=str(row.symbol),
                action=action,
                side=side,
                quantity_lots=quantity_lots,
                tick=tick,
                position_lots=position_lots,
                cumulative_notional=cumulative_notional,
                observed_intents=observed_intents,
                config=config,
                limits=limits,
            )
            intent_rows.append(intent)
            if event_breach:
                rejected_intents += 1
                halt_reason = event_breach
            else:
                observed_intents += 1
                position_lots = int(intent["shadow_position_after_lots"])
                cumulative_notional = float(
                    intent["cumulative_notional_after"]
                )
                last_intent_ts_ns = now_ns
                if action == "entry":
                    entry_ts_ns = now_ns
                elif position_lots == 0:
                    entry_ts_ns = None
        feature_rows.append(
            _feature_row(
                row=row,
                features=features,
                action=action,
                side=side,
                position_lots=position_lots,
                cumulative_notional=cumulative_notional,
                breach_code=event_breach,
            )
        )
        if event_breach:
            break

    if not halt_reason and position_lots != 0 and config.terminal_flatten:
        last = source.iloc[len(feature_rows) - 1]
        tick = {
            "bid": float(last["bid_price"]),
            "ask": float(last["ask_price"]),
            "bid_qty": float(last["bid_qty"]),
            "ask_qty": float(last["ask_qty"]),
        }
        side = -1 if position_lots > 0 else 1
        intent, terminal_breach = _intent(
            intent_sequence=len(intent_rows) + 1,
            source_sequence=int(last["sequence"]),
            now_ns=int(last["ts_ns"]),
            symbol=str(last["symbol"]),
            action="terminal_flatten",
            side=side,
            quantity_lots=abs(position_lots),
            tick=tick,
            position_lots=position_lots,
            cumulative_notional=cumulative_notional,
            observed_intents=observed_intents,
            config=config,
            limits=limits,
        )
        intent_rows.append(intent)
        if terminal_breach:
            rejected_intents += 1
            halt_reason = terminal_breach
        else:
            observed_intents += 1
            position_lots = int(intent["shadow_position_after_lots"])
            cumulative_notional = float(intent["cumulative_notional_after"])

    features_frame = pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)
    intents_frame = pd.DataFrame(intent_rows, columns=INTENT_COLUMNS)
    processed = len(features_frame)
    completed = bool(
        not halt_reason
        and processed == len(source)
        and position_lots == 0
    )
    return ShadowMicropriceEvaluationResult(
        features=features_frame,
        intents=intents_frame,
        source_event_count=len(source),
        processed_event_count=processed,
        observed_intent_count=observed_intents,
        rejected_intent_count=rejected_intents,
        ending_shadow_position_lots=position_lots,
        cumulative_shadow_notional=round(cumulative_notional, 10),
        max_shadow_open_orders=0,
        completed=completed,
        halted=bool(halt_reason),
        halt_reason=halt_reason,
    )


def _candidate(
    *,
    features: dict[str, float],
    tick: dict[str, float],
    position_lots: int,
    entry_ts_ns: int | None,
    last_intent_ts_ns: int | None,
    now_ns: int,
    config: ShadowMicropriceConfig,
) -> tuple[str, int, int]:
    if position_lots != 0:
        action = microprice_exit_action(
            features,
            position_lots=position_lots,
            entry_ts_ns=entry_ts_ns,
            now_ns=now_ns,
            hold_ns=config.hold_ns,
            exit_imbalance=config.exit_imbalance,
        )
        if not action:
            return "", 0, 0
        return action, (-1 if position_lots > 0 else 1), abs(position_lots)
    if (
        last_intent_ts_ns is not None
        and now_ns - last_intent_ts_ns < config.cooloff_ns
    ):
        return "", 0, 0
    if features["spread_ticks"] > config.max_spread_ticks:
        return "", 0, 0
    if min(tick["bid_qty"], tick["ask_qty"]) < config.min_depth:
        return "", 0, 0
    side = microprice_entry_side(
        features,
        entry_imbalance=config.entry_imbalance,
        min_microprice_edge_ticks=config.min_microprice_edge_ticks,
    )
    if not side:
        return "", 0, 0
    return "entry", side, config.intent_quantity_lots


def _intent(
    *,
    intent_sequence: int,
    source_sequence: int,
    now_ns: int,
    symbol: str,
    action: str,
    side: int,
    quantity_lots: int,
    tick: dict[str, float],
    position_lots: int,
    cumulative_notional: float,
    observed_intents: int,
    config: ShadowMicropriceConfig,
    limits: ShadowRuntimeLimits,
) -> tuple[dict[str, Any], str]:
    price = float(tick["ask"] if side > 0 else tick["bid"])
    quantity_units = quantity_lots * config.lot_size
    intent_notional = abs(quantity_units * price)
    prospective_notional = cumulative_notional + intent_notional
    prospective_position = position_lots + (side * quantity_lots)
    breach = _limit_breach(
        next_observed_intent_count=observed_intents + 1,
        prospective_notional=prospective_notional,
        prospective_position_lots=prospective_position,
        shadow_open_orders=0,
        limits=limits,
    )
    within_limits = not breach
    return (
        {
            "intent_sequence": intent_sequence,
            "source_sequence": source_sequence,
            "ts_ns": now_ns,
            "symbol": symbol,
            "action": action,
            "side": side,
            "side_name": "buy" if side > 0 else "sell",
            "quantity_lots": quantity_lots,
            "quantity_units": quantity_units,
            "limit_price": price,
            "intent_notional": round(intent_notional, 10),
            "cumulative_notional_before": round(cumulative_notional, 10),
            "prospective_cumulative_notional": round(
                prospective_notional,
                10,
            ),
            "cumulative_notional_after": round(
                prospective_notional if within_limits else cumulative_notional,
                10,
            ),
            "position_before_lots": position_lots,
            "prospective_position_lots": prospective_position,
            "shadow_position_after_lots": (
                prospective_position if within_limits else position_lots
            ),
            "shadow_open_orders": 0,
            "within_limits": within_limits,
            "breach_code": breach,
            "intent_status": (
                "shadow_observed" if within_limits else "rejected_limit"
            ),
            "routing_status": "not_routable",
            "submission_status": "not_submitted",
            "shadow_fill_assumption": "immediate_touch_observation",
        },
        breach,
    )


def _limit_breach(
    *,
    next_observed_intent_count: int,
    prospective_notional: float,
    prospective_position_lots: int,
    shadow_open_orders: int,
    limits: ShadowRuntimeLimits,
) -> str:
    if next_observed_intent_count > limits.max_orders_per_session:
        return "max_orders_per_session"
    if prospective_notional > limits.max_notional_per_session:
        return "max_notional_per_session"
    if shadow_open_orders > limits.max_open_orders:
        return "max_open_orders"
    if abs(prospective_position_lots) > limits.max_position_lots:
        return "max_position_lots"
    return ""


def _feature_row(
    *,
    row: Any,
    features: dict[str, float],
    action: str,
    side: int,
    position_lots: int,
    cumulative_notional: float,
    breach_code: str,
) -> dict[str, Any]:
    return {
        "sequence": int(row.sequence),
        "ts_ns": int(row.ts_ns),
        "symbol": str(row.symbol),
        "bid_price": float(row.bid_price),
        "ask_price": float(row.ask_price),
        "bid_qty": int(row.bid_qty),
        "ask_qty": int(row.ask_qty),
        "spread_ticks": round(features["spread_ticks"], 10),
        "imbalance": round(features["imbalance"], 10),
        "microprice": round(features["microprice"], 10),
        "microprice_edge_ticks": round(
            features["microprice_edge_ticks"],
            10,
        ),
        "signal_action": action,
        "signal_side": side,
        "shadow_position_lots": position_lots,
        "cumulative_shadow_notional": round(cumulative_notional, 10),
        "halted": bool(breach_code),
        "breach_code": breach_code,
    }


def _validated_telemetry(telemetry: pd.DataFrame) -> pd.DataFrame:
    missing = [
        column
        for column in REQUIRED_TELEMETRY_COLUMNS
        if column not in telemetry.columns
    ]
    if missing:
        raise ShadowMicropriceEvaluationError(
            "launcher telemetry missing columns: " + ", ".join(missing)
        )
    if telemetry.empty:
        raise ShadowMicropriceEvaluationError(
            "launcher telemetry must not be empty"
        )
    frame = telemetry.copy().reset_index(drop=True)
    sequences = [_exact_integer(value, "sequence") for value in frame["sequence"]]
    if sequences != list(range(1, len(frame) + 1)):
        raise ShadowMicropriceEvaluationError(
            "launcher telemetry sequence must be contiguous from one"
        )
    timestamps = [_exact_integer(value, "ts_ns") for value in frame["ts_ns"]]
    if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        raise ShadowMicropriceEvaluationError(
            "launcher telemetry timestamps must be strictly increasing"
        )
    if not all(_explicit_true(value) for value in frame["accepted"]):
        raise ShadowMicropriceEvaluationError(
            "shadow evaluation requires accepted launcher events only"
        )
    if any(str(value).strip() for value in frame["breach_code"] if not _missing(value)):
        raise ShadowMicropriceEvaluationError(
            "shadow evaluation source contains a launcher breach"
        )
    if set(frame["source_mode"].astype(str).str.strip()) != {
        "deterministic_simulation"
    }:
        raise ShadowMicropriceEvaluationError(
            "shadow evaluation source mode is not deterministic simulation"
        )
    symbols = set(frame["symbol"].astype(str).str.strip())
    if len(symbols) != 1 or not next(iter(symbols)):
        raise ShadowMicropriceEvaluationError(
            "shadow evaluation requires exactly one symbol"
        )
    frame["sequence"] = sequences
    frame["ts_ns"] = timestamps
    return frame


def _validate_config(config: ShadowMicropriceConfig) -> None:
    for name, value in {
        "lot_size": config.lot_size,
        "intent_quantity_lots": config.intent_quantity_lots,
        "min_depth": config.min_depth,
        "hold_ns": config.hold_ns,
        "cooloff_ns": config.cooloff_ns,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise ShadowMicropriceEvaluationError(f"{name} must be an integer")
    if config.lot_size <= 0 or config.intent_quantity_lots <= 0:
        raise ShadowMicropriceEvaluationError(
            "lot_size and intent_quantity_lots must be positive"
        )
    if config.min_depth <= 0 or config.hold_ns <= 0 or config.cooloff_ns < 0:
        raise ShadowMicropriceEvaluationError(
            "depth and timing settings are invalid"
        )
    for name, value in {
        "tick_size": config.tick_size,
        "entry_imbalance": config.entry_imbalance,
        "exit_imbalance": config.exit_imbalance,
        "min_microprice_edge_ticks": config.min_microprice_edge_ticks,
        "max_spread_ticks": config.max_spread_ticks,
    }.items():
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise ShadowMicropriceEvaluationError(f"{name} must be finite")
    if config.tick_size <= 0 or config.max_spread_ticks <= 0:
        raise ShadowMicropriceEvaluationError(
            "tick_size and max_spread_ticks must be positive"
        )
    if not 0 < config.entry_imbalance < 1:
        raise ShadowMicropriceEvaluationError(
            "entry_imbalance must be between zero and one"
        )
    if not 0 <= config.exit_imbalance < config.entry_imbalance:
        raise ShadowMicropriceEvaluationError(
            "exit_imbalance must be below entry_imbalance"
        )
    if config.min_microprice_edge_ticks < 0:
        raise ShadowMicropriceEvaluationError(
            "min_microprice_edge_ticks must be non-negative"
        )
    if config.terminal_flatten is not True:
        raise ShadowMicropriceEvaluationError(
            "terminal_flatten must remain enabled"
        )


def _validate_limits(limits: ShadowRuntimeLimits) -> None:
    for name, value in {
        "max_orders_per_session": limits.max_orders_per_session,
        "max_open_orders": limits.max_open_orders,
        "max_position_lots": limits.max_position_lots,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ShadowMicropriceEvaluationError(
                f"{name} must be a positive integer"
            )
    if (
        isinstance(limits.max_notional_per_session, bool)
        or not math.isfinite(float(limits.max_notional_per_session))
        or limits.max_notional_per_session <= 0
    ):
        raise ShadowMicropriceEvaluationError(
            "max_notional_per_session must be positive and finite"
        )


def _validate_kill_switch(kill_switch: ShadowKillSwitch) -> None:
    if not all(
        value is True
        for value in (
            kill_switch.enabled,
            kill_switch.trigger_on_limit_breach,
            kill_switch.stop_new_orders,
            kill_switch.cancel_open_orders,
        )
    ):
        raise ShadowMicropriceEvaluationError(
            "shadow evaluation requires the complete armed kill-switch contract"
        )


def _exact_integer(value: Any, name: str) -> int:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ShadowMicropriceEvaluationError(f"{name} must be an integer") from exc
    if not math.isfinite(parsed) or not parsed.is_integer():
        raise ShadowMicropriceEvaluationError(f"{name} must be an integer")
    return int(parsed)


def _explicit_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(math.isfinite(float(value)) and float(value) == 1.0)
    return str(value).strip().lower() in {"1", "true", "yes"}


def _missing(value: Any) -> bool:
    if value is None or (
        isinstance(value, str) and value.strip().lower() in {"", "nan"}
    ):
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
