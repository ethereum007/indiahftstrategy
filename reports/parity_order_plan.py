from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest


PARITY_BOX_STRATEGY = "parity_box"
PARITY_DIRECTIONS = {"buy_synthetic_sell_future", "sell_synthetic_buy_future"}
BOX_DIRECTIONS = {"buy_box", "sell_box"}
SUPPORTED_DIRECTIONS = PARITY_DIRECTIONS | BOX_DIRECTIONS


@dataclass(frozen=True)
class ParityOrderPlanConfig:
    symbol_prefix: str = "NIFTY"
    future_instrument_id: str = "NIFTY_FUT"
    require_promotion_ready: bool = True
    direction: str | None = None
    expiry: str | None = None
    strike: float | None = None
    low_strike: float | None = None
    high_strike: float | None = None
    qty: int | None = None
    call_price: float | None = None
    put_price: float | None = None
    future_price: float | None = None
    low_call_price: float | None = None
    low_put_price: float | None = None
    high_call_price: float | None = None
    high_put_price: float | None = None
    price_offset_ticks: float = 0.0
    tick_size: float = 0.05
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    output_filename: str = "parity_order_candidates.csv"


@dataclass(frozen=True)
class ParityOrderPlanReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


@dataclass(frozen=True)
class _PlanContext:
    strategy: str
    market: str
    scenario_key: str
    direction: str
    leg_family: str
    expiry: str
    qty: int
    tick_size: float
    strike: float
    low_strike: float
    high_strike: float
    base_prices: dict[str, float]
    ts_signal_ns: float
    quote_edge: float
    theo: float


def build_parity_order_plan(
    promotion_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    *,
    config: ParityOrderPlanConfig | None = None,
) -> ParityOrderPlanReport:
    config = config or ParityOrderPlanConfig()
    _validate_config(config)
    _require(promotion_summary, ["ready", "candidate_scenario_key"], "promotion_summary")
    parameters = _dict(candidate_config.get("parameters"))
    replay_defaults = _dict(candidate_config.get("replay_defaults"))
    metrics = _dict(candidate_config.get("metrics"))
    ctx = _plan_context(promotion_summary.iloc[0], candidate_config, parameters, replay_defaults, metrics, config)
    checks = _checks(promotion_summary.iloc[0], candidate_config, ctx, config)
    orders = _orders(ctx, config) if bool(checks["passed"].all()) else _empty_orders()
    summary = _summary(orders, checks, ctx, config)
    return ParityOrderPlanReport(orders=orders, checks=checks, summary=summary)


def write_parity_order_plan(
    promotion_dir: str | Path,
    *,
    output_dir: str | Path,
    config: ParityOrderPlanConfig | None = None,
) -> ParityOrderPlanReport:
    promotion = Path(promotion_dir)
    summary_path = promotion / "promotion_summary.csv"
    candidate_path = promotion / "candidate_config.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"promotion_summary.csv not found: {summary_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")
    config = config or ParityOrderPlanConfig()
    report = build_parity_order_plan(
        pd.read_csv(summary_path),
        json.loads(candidate_path.read_text(encoding="utf-8")),
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "parity_order_checks.csv", index=False)
    report.summary.to_csv(out / "parity_order_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="parity_order_plan",
        parameters={
            "strategy": str(report.summary.iloc[0].get("strategy", PARITY_BOX_STRATEGY)),
            "market": str(report.summary.iloc[0].get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
            "config": asdict(config),
        },
        inputs={"promotion": promotion, "summary": summary_path, "candidate_config": candidate_path},
    )
    return ParityOrderPlanReport(report.orders, report.checks, report.summary, out)


def _plan_context(
    promotion_row: pd.Series,
    candidate_config: dict[str, Any],
    parameters: dict[str, Any],
    replay_defaults: dict[str, Any],
    metrics: dict[str, Any],
    config: ParityOrderPlanConfig,
) -> _PlanContext:
    strategy = _candidate_strategy(candidate_config, parameters, replay_defaults)
    market = str(
        candidate_config.get("market")
        or parameters.get("market")
        or replay_defaults.get("market")
        or INDIA_NSE_INDEX_DERIVATIVES.name
    )
    scenario_key = str(candidate_config.get("scenario_key") or promotion_row["candidate_scenario_key"])
    direction = str(config.direction or parameters.get("direction") or parameters.get("best_direction") or "").strip()
    leg_family = "box" if direction in BOX_DIRECTIONS else "parity" if direction in PARITY_DIRECTIONS else ""
    expiry = str(config.expiry or parameters.get("expiry") or parameters.get("best_expiry") or "").strip()
    qty = int(config.qty if config.qty is not None else _number(parameters.get("qty", parameters.get("best_qty")), 0))
    strike = _number(config.strike if config.strike is not None else parameters.get("strike"), np.nan)
    low_strike = _number(config.low_strike if config.low_strike is not None else parameters.get("low_strike"), np.nan)
    high_strike = _number(
        config.high_strike if config.high_strike is not None else parameters.get("high_strike"),
        np.nan,
    )
    base_prices = _base_prices(direction, parameters, config)
    ts_signal_ns = _number(parameters.get("ts", parameters.get("best_ts")), np.nan)
    quote_edge = _number(
        parameters.get(
            "net_edge",
            parameters.get("best_net_edge", metrics.get("median_net_pnl", metrics.get("total_net_pnl"))),
        ),
        np.nan,
    )
    theo = _number(parameters.get("theo", parameters.get("fair_value")), np.nan)
    return _PlanContext(
        strategy=strategy,
        market=market,
        scenario_key=scenario_key,
        direction=direction,
        leg_family=leg_family,
        expiry=expiry,
        qty=qty,
        tick_size=float(config.tick_size),
        strike=float(strike),
        low_strike=float(low_strike),
        high_strike=float(high_strike),
        base_prices=base_prices,
        ts_signal_ns=float(ts_signal_ns),
        quote_edge=float(quote_edge),
        theo=float(theo),
    )


def _base_prices(direction: str, parameters: dict[str, Any], config: ParityOrderPlanConfig) -> dict[str, float]:
    if direction in PARITY_DIRECTIONS:
        return {
            "call": _price_value(
                config.call_price,
                parameters,
                "call_price",
                "best_call_price",
                "call_ask" if direction == "buy_synthetic_sell_future" else "call_bid",
            ),
            "put": _price_value(
                config.put_price,
                parameters,
                "put_price",
                "best_put_price",
                "put_bid" if direction == "buy_synthetic_sell_future" else "put_ask",
            ),
            "future": _price_value(
                config.future_price,
                parameters,
                "future_price",
                "best_future_price",
                "future_bid" if direction == "buy_synthetic_sell_future" else "future_ask",
            ),
        }
    return {
        "low_call": _price_value(
            config.low_call_price,
            parameters,
            "low_call_price",
            "low_call_ask" if direction == "buy_box" else "low_call_bid",
        ),
        "low_put": _price_value(
            config.low_put_price,
            parameters,
            "low_put_price",
            "low_put_bid" if direction == "buy_box" else "low_put_ask",
        ),
        "high_call": _price_value(
            config.high_call_price,
            parameters,
            "high_call_price",
            "high_call_bid" if direction == "buy_box" else "high_call_ask",
        ),
        "high_put": _price_value(
            config.high_put_price,
            parameters,
            "high_put_price",
            "high_put_ask" if direction == "buy_box" else "high_put_bid",
        ),
    }


def _orders(ctx: _PlanContext, config: ParityOrderPlanConfig) -> pd.DataFrame:
    return pd.DataFrame([_order_row(ctx, config, leg) for leg in _leg_specs(ctx, config)])


def _leg_specs(ctx: _PlanContext, config: ParityOrderPlanConfig) -> list[dict[str, Any]]:
    if ctx.direction == "buy_synthetic_sell_future":
        return [
            _leg("call", "CALL", ctx.strike, "C", 1, ctx.base_prices["call"], ctx, config),
            _leg("put", "PUT", ctx.strike, "P", -1, ctx.base_prices["put"], ctx, config),
            _future_leg("future", -1, ctx.base_prices["future"], ctx, config),
        ]
    if ctx.direction == "sell_synthetic_buy_future":
        return [
            _leg("call", "CALL", ctx.strike, "C", -1, ctx.base_prices["call"], ctx, config),
            _leg("put", "PUT", ctx.strike, "P", 1, ctx.base_prices["put"], ctx, config),
            _future_leg("future", 1, ctx.base_prices["future"], ctx, config),
        ]
    if ctx.direction == "buy_box":
        return [
            _leg("low_call", "LOW_CALL", ctx.low_strike, "C", 1, ctx.base_prices["low_call"], ctx, config),
            _leg("low_put", "LOW_PUT", ctx.low_strike, "P", -1, ctx.base_prices["low_put"], ctx, config),
            _leg("high_call", "HIGH_CALL", ctx.high_strike, "C", -1, ctx.base_prices["high_call"], ctx, config),
            _leg("high_put", "HIGH_PUT", ctx.high_strike, "P", 1, ctx.base_prices["high_put"], ctx, config),
        ]
    if ctx.direction == "sell_box":
        return [
            _leg("low_call", "LOW_CALL", ctx.low_strike, "C", -1, ctx.base_prices["low_call"], ctx, config),
            _leg("low_put", "LOW_PUT", ctx.low_strike, "P", 1, ctx.base_prices["low_put"], ctx, config),
            _leg("high_call", "HIGH_CALL", ctx.high_strike, "C", 1, ctx.base_prices["high_call"], ctx, config),
            _leg("high_put", "HIGH_PUT", ctx.high_strike, "P", -1, ctx.base_prices["high_put"], ctx, config),
        ]
    return []


def _leg(
    key: str,
    role: str,
    strike: float,
    option_type: str,
    side: int,
    base_price: float,
    ctx: _PlanContext,
    config: ParityOrderPlanConfig,
) -> dict[str, Any]:
    return {
        "key": key,
        "role": role,
        "instrument_id": _option_instrument_id(config.symbol_prefix, ctx.expiry, strike, option_type),
        "side": int(side),
        "base_price": float(base_price),
        "price": _planned_price(base_price, side, config),
        "expiry": ctx.expiry,
        "strike": float(strike),
        "option_type": option_type,
    }


def _future_leg(
    key: str,
    side: int,
    base_price: float,
    ctx: _PlanContext,
    config: ParityOrderPlanConfig,
) -> dict[str, Any]:
    return {
        "key": key,
        "role": "FUTURE",
        "instrument_id": str(config.future_instrument_id),
        "side": int(side),
        "base_price": float(base_price),
        "price": _planned_price(base_price, side, config),
        "expiry": ctx.expiry,
        "strike": np.nan,
        "option_type": "",
    }


def _order_row(ctx: _PlanContext, config: ParityOrderPlanConfig, leg: dict[str, Any]) -> dict[str, Any]:
    leg_group_id = _leg_group_id(ctx)
    leg_count = len(_leg_specs(ctx, config))
    side = int(leg["side"])
    price = float(leg["price"])
    return {
        "client_order_id": _client_order_id(ctx.scenario_key, leg_group_id, str(leg["role"]), side, ctx.qty, price),
        "strategy": PARITY_BOX_STRATEGY,
        "instrument_id": str(leg["instrument_id"]),
        "side": side,
        "side_text": "BUY" if side > 0 else "SELL",
        "qty": int(ctx.qty),
        "price": price,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "ts_signal_ns": _nan_if_missing(ctx.ts_signal_ns),
        "marketable": False,
        "quote_edge": _nan_if_missing(ctx.quote_edge),
        "theo": _nan_if_missing(ctx.theo),
        "expiry": ctx.expiry,
        "strike": leg["strike"],
        "option_type": leg["option_type"],
        "scenario_key": ctx.scenario_key,
        "source": "parity_order_plan",
        "direction": ctx.direction,
        "leg_family": ctx.leg_family,
        "leg_group_id": leg_group_id,
        "leg_role": leg["role"],
        "leg_key": leg["key"],
        "leg_count": int(leg_count),
        "base_price": float(leg["base_price"]),
        "template_only": True,
        "lifecycle_action": "MULTI_LEG_TEMPLATE",
        "lifecycle_action_id": leg_group_id,
        "lifecycle_reason": f"paper_shadow_{ctx.direction}_leg_template",
        "lifecycle_message_count": int(leg_count),
    }


def _checks(
    summary: pd.Series,
    candidate_config: dict[str, Any],
    ctx: _PlanContext,
    config: ParityOrderPlanConfig,
) -> pd.DataFrame:
    promotion_ready = _to_bool(summary.get("ready", False))
    candidate_ready = _to_bool(candidate_config.get("ready", False))
    strategy_ok = _normalize_identity(ctx.strategy) in {"parity", "parity_box"}
    checks = [
        _check(
            "promotion_ready",
            promotion_ready,
            "is",
            True,
            promotion_ready or not config.require_promotion_ready,
            "promotion is not ready",
        ),
        _check(
            "candidate_config_ready",
            candidate_ready,
            "is",
            True,
            candidate_ready or not config.require_promotion_ready,
            "candidate_config.json is not ready",
        ),
        _check(
            "valid_strategy",
            ctx.strategy,
            "in",
            "parity,parity_box",
            strategy_ok,
            "candidate strategy must be parity/parity_box",
        ),
        _check(
            "valid_direction",
            ctx.direction,
            "in",
            ",".join(sorted(SUPPORTED_DIRECTIONS)),
            ctx.direction in SUPPORTED_DIRECTIONS,
            "candidate direction is unavailable or unsupported",
        ),
        _check("expiry_available", ctx.expiry, "not_empty", True, bool(ctx.expiry), "expiry is unavailable"),
        _check(
            "symbol_prefix_available",
            config.symbol_prefix,
            "not_empty",
            True,
            bool(str(config.symbol_prefix).strip()),
            "symbol prefix is unavailable",
        ),
        _check(
            "future_instrument_id_available",
            config.future_instrument_id,
            "not_empty",
            True,
            bool(str(config.future_instrument_id).strip()),
            "future instrument id is unavailable",
        ),
        _threshold_check("positive_qty", float(ctx.qty), ">", 0),
        _threshold_check("positive_tick_size", float(ctx.tick_size), ">", 0),
    ]
    if ctx.direction in PARITY_DIRECTIONS:
        checks.append(_threshold_check("positive_strike", ctx.strike, ">", 0))
    if ctx.direction in BOX_DIRECTIONS:
        checks.extend(
            [
                _threshold_check("positive_low_strike", ctx.low_strike, ">", 0),
                _threshold_check("positive_high_strike", ctx.high_strike, ">", 0),
                _check(
                    "high_strike_above_low_strike",
                    ctx.high_strike - ctx.low_strike,
                    ">",
                    0,
                    (not np.isnan(ctx.high_strike)) and (not np.isnan(ctx.low_strike)) and ctx.high_strike > ctx.low_strike,
                    "high_strike must be greater than low_strike",
                ),
            ]
        )
    legs = _leg_specs(ctx, config)
    for leg in legs:
        checks.append(_threshold_check(f"positive_{leg['key']}_price", float(leg["price"]), ">", 0))
        if config.price_band_pct is not None:
            checks.append(
                _price_band_check(
                    f"{leg['key']}_price_band_pct",
                    float(leg["price"]),
                    float(leg["base_price"]),
                    float(config.price_band_pct),
                )
            )
    if config.max_order_qty is not None:
        checks.append(_threshold_check("max_order_qty", float(ctx.qty), "<=", float(config.max_order_qty)))
    if config.max_notional is not None:
        notionals = [float(ctx.qty) * float(leg["price"]) for leg in legs]
        max_notional = max(notionals) if notionals else np.nan
        checks.append(_threshold_check("max_leg_notional", max_notional, "<=", float(config.max_notional)))
    return pd.DataFrame(checks)


def _summary(
    orders: pd.DataFrame,
    checks: pd.DataFrame,
    ctx: _PlanContext,
    config: ParityOrderPlanConfig,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    total_notional = float((orders["qty"] * orders["price"]).sum()) if not orders.empty else 0.0
    max_order_notional = float((orders["qty"] * orders["price"]).max()) if not orders.empty else 0.0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "scenario_key": ctx.scenario_key,
                "strategy": PARITY_BOX_STRATEGY,
                "market": ctx.market,
                "direction": ctx.direction,
                "leg_family": ctx.leg_family,
                "expiry": ctx.expiry,
                "strike": _jsonable(ctx.strike),
                "low_strike": _jsonable(ctx.low_strike),
                "high_strike": _jsonable(ctx.high_strike),
                "orders": int(len(orders)),
                "buy_orders": int((orders["side"] == 1).sum()) if not orders.empty else 0,
                "sell_orders": int((orders["side"] == -1).sum()) if not orders.empty else 0,
                "qty": int(ctx.qty) if ctx.qty > 0 else 0,
                "total_notional": total_notional,
                "max_order_notional": max_order_notional,
                "failed_checks": failed,
                "output_file": config.output_filename,
                "recommendation": "stage_multi_leg_template_orders" if ready else "keep_in_research",
            }
        ]
    )


def _empty_orders() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "client_order_id",
            "strategy",
            "instrument_id",
            "side",
            "side_text",
            "qty",
            "price",
            "order_type",
            "time_in_force",
            "ts_signal_ns",
            "marketable",
            "quote_edge",
            "theo",
            "expiry",
            "strike",
            "option_type",
            "scenario_key",
            "source",
            "direction",
            "leg_family",
            "leg_group_id",
            "leg_role",
            "leg_key",
            "leg_count",
            "base_price",
            "template_only",
            "lifecycle_action",
            "lifecycle_action_id",
            "lifecycle_reason",
            "lifecycle_message_count",
        ]
    )


def _candidate_strategy(
    candidate_config: dict[str, Any],
    parameters: dict[str, Any],
    replay_defaults: dict[str, Any],
) -> str:
    value = candidate_config.get("strategy") or parameters.get("strategy") or replay_defaults.get("strategy")
    if value is None:
        return PARITY_BOX_STRATEGY
    normalized = _normalize_identity(str(value))
    if normalized in {"parity", "parity_box"}:
        return PARITY_BOX_STRATEGY
    return str(value)


def _option_instrument_id(prefix: str, expiry: str, strike: float, option_type: str) -> str:
    expiry_key = "".join(ch for ch in str(expiry) if ch.isalnum())
    strike_key = str(int(strike)) if float(strike).is_integer() else str(strike).replace(".", "p")
    return f"{prefix.upper()}_{expiry_key}_{strike_key}{option_type.upper()}"


def _planned_price(base_price: float, side: int, config: ParityOrderPlanConfig) -> float:
    if np.isnan(float(base_price)):
        return np.nan
    return float(base_price) + int(side) * float(config.price_offset_ticks) * float(config.tick_size)


def _price_value(config_value: float | None, parameters: dict[str, Any], *keys: str) -> float:
    if config_value is not None:
        return float(config_value)
    for key in keys:
        if key in parameters:
            return _number(parameters.get(key), np.nan)
    return np.nan


def _client_order_id(scenario_key: str, leg_group_id: str, leg_role: str, side: int, qty: int, price: float) -> str:
    payload = f"{scenario_key}|{leg_group_id}|{leg_role}|{side}|{qty}|{price:.8f}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"PAR-{digest}"


def _leg_group_id(ctx: _PlanContext) -> str:
    payload = f"{ctx.scenario_key}|{ctx.direction}|{ctx.expiry}|{ctx.strike}|{ctx.low_strike}|{ctx.high_strike}|{ctx.qty}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"PBOX-{digest}"


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, Any]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">":
        passed = (not missing) and value_float > threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _price_band_check(name: str, price: float, reference_price: float, price_band_pct: float) -> dict[str, Any]:
    if np.isnan(price) or np.isnan(reference_price) or reference_price <= 0:
        return _check(name, np.nan, "<=", price_band_pct, False, f"{name} reference price is unavailable")
    deviation_pct = abs(price - reference_price) / reference_price
    return _check(
        name,
        deviation_pct,
        "<=",
        price_band_pct,
        deviation_pct <= price_band_pct,
        f"{name} {deviation_pct:.6g} exceeded {price_band_pct:.6g}",
    )


def _check(
    name: str,
    value: Any,
    operator: str,
    threshold: Any,
    passed: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_config(config: ParityOrderPlanConfig) -> None:
    if not str(config.symbol_prefix).strip():
        raise ValueError("symbol_prefix must not be blank")
    if not str(config.future_instrument_id).strip():
        raise ValueError("future_instrument_id must not be blank")
    if config.qty is not None and config.qty <= 0:
        raise ValueError("qty must be positive")
    if config.price_offset_ticks < 0:
        raise ValueError("price_offset_ticks must be non-negative")
    if config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if config.max_order_qty is not None and config.max_order_qty <= 0:
        raise ValueError("max_order_qty must be positive")
    if config.max_notional is not None and config.max_notional <= 0:
        raise ValueError("max_notional must be positive")
    if config.price_band_pct is not None and config.price_band_pct < 0:
        raise ValueError("price_band_pct must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: object, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if np.isnan(number) else number


def _to_bool(value: object) -> bool:
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _normalize_identity(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")


def _nan_if_missing(value: float) -> float:
    return np.nan if np.isnan(float(value)) else float(value)


def _jsonable(value: object) -> object:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
