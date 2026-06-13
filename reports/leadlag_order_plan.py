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
from strategies.run_leadlag_replay import LEAD_LAG_STRATEGY


@dataclass(frozen=True)
class LeadLagOrderPlanConfig:
    laggard_instrument_id: str = "LAGGARD"
    require_promotion_ready: bool = True
    qty: int | None = None
    reference_price: float | None = None
    buy_limit_price: float | None = None
    sell_limit_price: float | None = None
    entry_offset_ticks: float = 0.0
    tick_size: float | None = None
    max_order_qty: int | None = None
    max_notional: float | None = None
    price_band_pct: float | None = None
    output_filename: str = "leadlag_order_candidates.csv"


@dataclass(frozen=True)
class LeadLagOrderPlanReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def build_leadlag_order_plan(
    promotion_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    *,
    config: LeadLagOrderPlanConfig | None = None,
) -> LeadLagOrderPlanReport:
    config = config or LeadLagOrderPlanConfig()
    _validate_config(config)
    _require(promotion_summary, ["ready", "candidate_scenario_key"], "promotion_summary")
    parameters = (
        candidate_config.get("parameters", {}) if isinstance(candidate_config.get("parameters", {}), dict) else {}
    )
    replay_defaults = (
        candidate_config.get("replay_defaults", {})
        if isinstance(candidate_config.get("replay_defaults", {}), dict)
        else {}
    )
    strategy = str(candidate_config.get("strategy") or parameters.get("strategy") or LEAD_LAG_STRATEGY)
    market = str(
        candidate_config.get("market")
        or parameters.get("market")
        or replay_defaults.get("market")
        or INDIA_NSE_INDEX_DERIVATIVES.name
    )
    scenario_key = str(candidate_config.get("scenario_key") or promotion_summary.iloc[0]["candidate_scenario_key"])
    plan = _plan_values(parameters, replay_defaults, config)
    checks = _checks(
        promotion_summary.iloc[0],
        candidate_config,
        parameters,
        replay_defaults,
        plan,
        config,
        strategy=strategy,
    )
    orders = (
        _orders(
            candidate_config,
            parameters,
            replay_defaults,
            plan,
            scenario_key=scenario_key,
            config=config,
            strategy=strategy,
        )
        if bool(checks["passed"].all())
        else _empty_orders()
    )
    summary = _summary(
        orders,
        checks,
        scenario_key,
        config,
        plan,
        strategy=strategy,
        market=market,
    )
    return LeadLagOrderPlanReport(orders=orders, checks=checks, summary=summary)


def write_leadlag_order_plan(
    promotion_dir: str | Path,
    *,
    output_dir: str | Path,
    config: LeadLagOrderPlanConfig | None = None,
) -> LeadLagOrderPlanReport:
    promotion = Path(promotion_dir)
    summary_path = promotion / "promotion_summary.csv"
    candidate_path = promotion / "candidate_config.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"promotion_summary.csv not found: {summary_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")
    config = config or LeadLagOrderPlanConfig()
    report = build_leadlag_order_plan(
        pd.read_csv(summary_path),
        json.loads(candidate_path.read_text(encoding="utf-8")),
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "leadlag_order_checks.csv", index=False)
    report.summary.to_csv(out / "leadlag_order_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="leadlag_order_plan",
        parameters={
            "strategy": str(report.summary.iloc[0].get("strategy", LEAD_LAG_STRATEGY)),
            "market": str(report.summary.iloc[0].get("market", INDIA_NSE_INDEX_DERIVATIVES.name)),
            "config": asdict(config),
        },
        inputs={"promotion": promotion, "summary": summary_path, "candidate_config": candidate_path},
    )
    return LeadLagOrderPlanReport(report.orders, report.checks, report.summary, out)


def _plan_values(
    parameters: dict[str, Any],
    replay_defaults: dict[str, Any],
    config: LeadLagOrderPlanConfig,
) -> dict[str, float | int]:
    qty = int(config.qty if config.qty is not None else _number(parameters.get("qty", replay_defaults.get("qty")), 0))
    tick_size = float(
        config.tick_size
        if config.tick_size is not None
        else _number(parameters.get("laggard_tick", replay_defaults.get("laggard_tick")), 0.0)
    )
    reference_price = _optional_number(config.reference_price)
    if reference_price is None:
        reference_price = _optional_number(parameters.get("reference_price", replay_defaults.get("reference_price")))
    offset = float(config.entry_offset_ticks) * tick_size if tick_size > 0 else np.nan
    buy_price = _optional_number(config.buy_limit_price)
    sell_price = _optional_number(config.sell_limit_price)
    if buy_price is None and reference_price is not None:
        buy_price = reference_price + offset
    if sell_price is None and reference_price is not None:
        sell_price = reference_price - offset
    return {
        "qty": qty,
        "tick_size": tick_size,
        "reference_price": np.nan if reference_price is None else float(reference_price),
        "buy_limit_price": np.nan if buy_price is None else float(buy_price),
        "sell_limit_price": np.nan if sell_price is None else float(sell_price),
    }


def _orders(
    candidate_config: dict[str, Any],
    parameters: dict[str, Any],
    replay_defaults: dict[str, Any],
    plan: dict[str, float | int],
    *,
    scenario_key: str,
    config: LeadLagOrderPlanConfig,
    strategy: str,
) -> pd.DataFrame:
    qty = int(plan["qty"])
    trigger_ticks = _number(parameters.get("trigger_ticks", replay_defaults.get("trigger_ticks")), np.nan)
    delta = _number(parameters.get("delta", replay_defaults.get("delta")), np.nan)
    leader_tick = _number(parameters.get("leader_tick", replay_defaults.get("leader_tick")), np.nan)
    laggard_tick = _number(parameters.get("laggard_tick", replay_defaults.get("laggard_tick")), np.nan)
    flat_after_ns = _number(parameters.get("flat_after_ns", replay_defaults.get("flat_after_ns")), np.nan)
    cooloff_ns = _number(parameters.get("cooloff_ns", replay_defaults.get("cooloff_ns")), np.nan)
    metrics = candidate_config.get("metrics", {}) if isinstance(candidate_config.get("metrics", {}), dict) else {}
    rows = [
        _order_row(
            scenario_key,
            config.laggard_instrument_id,
            side=1,
            qty=qty,
            price=float(plan["buy_limit_price"]),
            trigger="leader_up_buy_laggard",
            strategy=strategy,
            trigger_ticks=trigger_ticks,
            delta=delta,
            leader_tick=leader_tick,
            laggard_tick=laggard_tick,
            flat_after_ns=flat_after_ns,
            cooloff_ns=cooloff_ns,
            expected_markout=_number(metrics.get("median_markout_mean"), np.nan),
        ),
        _order_row(
            scenario_key,
            config.laggard_instrument_id,
            side=-1,
            qty=qty,
            price=float(plan["sell_limit_price"]),
            trigger="leader_down_sell_laggard",
            strategy=strategy,
            trigger_ticks=trigger_ticks,
            delta=delta,
            leader_tick=leader_tick,
            laggard_tick=laggard_tick,
            flat_after_ns=flat_after_ns,
            cooloff_ns=cooloff_ns,
            expected_markout=_number(metrics.get("median_markout_mean"), np.nan),
        ),
    ]
    return pd.DataFrame(rows)


def _order_row(
    scenario_key: str,
    instrument_id: str,
    *,
    side: int,
    qty: int,
    price: float,
    trigger: str,
    strategy: str,
    trigger_ticks: float,
    delta: float,
    leader_tick: float,
    laggard_tick: float,
    flat_after_ns: float,
    cooloff_ns: float,
    expected_markout: float,
) -> dict[str, Any]:
    return {
        "client_order_id": _client_order_id(scenario_key, instrument_id, side, qty, price, trigger),
        "strategy": strategy,
        "instrument_id": instrument_id,
        "side": int(side),
        "side_text": "BUY" if side > 0 else "SELL",
        "qty": int(qty),
        "price": float(price),
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "ts_signal_ns": np.nan,
        "marketable": False,
        "quote_edge": expected_markout,
        "theo": np.nan,
        "scenario_key": scenario_key,
        "source": "leadlag_candidate_promotion",
        "trigger": trigger,
        "signal_direction": int(side),
        "template_only": True,
        "trigger_ticks": trigger_ticks,
        "delta": delta,
        "leader_tick": leader_tick,
        "laggard_tick": laggard_tick,
        "flat_after_ns": flat_after_ns,
        "cooloff_ns": cooloff_ns,
        "lifecycle_action": "SIGNAL_TEMPLATE",
        "lifecycle_action_id": trigger,
        "lifecycle_reason": "paper_shadow_leadlag_trigger_template",
        "lifecycle_message_count": 1,
    }


def _checks(
    summary: pd.Series,
    candidate_config: dict[str, Any],
    parameters: dict[str, Any],
    replay_defaults: dict[str, Any],
    plan: dict[str, float | int],
    config: LeadLagOrderPlanConfig,
    *,
    strategy: str,
) -> pd.DataFrame:
    promotion_ready = _to_bool(summary.get("ready", False))
    candidate_ready = _to_bool(candidate_config.get("ready", False))
    qty = float(plan["qty"])
    buy_price = float(plan["buy_limit_price"])
    sell_price = float(plan["sell_limit_price"])
    tick_size = float(plan["tick_size"])
    reference_price = float(plan["reference_price"])
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
            strategy,
            "==",
            LEAD_LAG_STRATEGY,
            strategy == LEAD_LAG_STRATEGY,
            "candidate strategy must be lead_lag_taker",
        ),
        _check(
            "laggard_instrument_id_available",
            config.laggard_instrument_id,
            "not_empty",
            True,
            bool(str(config.laggard_instrument_id).strip()),
            "laggard instrument id is unavailable",
        ),
        _threshold_check("positive_qty", qty, ">", 0),
        _threshold_check("positive_tick_size", tick_size, ">", 0),
        _threshold_check("positive_buy_limit_price", buy_price, ">", 0),
        _threshold_check("positive_sell_limit_price", sell_price, ">", 0),
        _check(
            "candidate_qty_available",
            _number(parameters.get("qty", replay_defaults.get("qty")), np.nan)
            if config.qty is None
            else config.qty,
            "available",
            True,
            config.qty is not None or not np.isnan(_number(parameters.get("qty", replay_defaults.get("qty")), np.nan)),
            "candidate qty is unavailable",
        ),
    ]
    if config.max_order_qty is not None:
        checks.append(_threshold_check("max_order_qty", qty, "<=", float(config.max_order_qty)))
    if config.max_notional is not None:
        checks.append(_threshold_check("buy_order_notional", qty * buy_price, "<=", float(config.max_notional)))
        checks.append(_threshold_check("sell_order_notional", qty * sell_price, "<=", float(config.max_notional)))
    if config.price_band_pct is not None:
        if np.isnan(reference_price):
            checks.append(
                _check(
                    "reference_price_available_for_band",
                    reference_price,
                    "available",
                    True,
                    False,
                    "reference price is required when price_band_pct is set",
                )
            )
        else:
            max_deviation = abs(float(config.price_band_pct))
            checks.append(_price_band_check("buy_price_band_pct", buy_price, reference_price, max_deviation))
            checks.append(_price_band_check("sell_price_band_pct", sell_price, reference_price, max_deviation))
    return pd.DataFrame(checks)


def _summary(
    orders: pd.DataFrame,
    checks: pd.DataFrame,
    scenario_key: str,
    config: LeadLagOrderPlanConfig,
    plan: dict[str, float | int],
    *,
    strategy: str,
    market: str,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    total_notional = float((orders["qty"] * orders["price"]).sum()) if not orders.empty else 0.0
    max_order_notional = float((orders["qty"] * orders["price"]).max()) if not orders.empty else 0.0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "scenario_key": scenario_key,
                "strategy": strategy,
                "market": market,
                "laggard_instrument_id": config.laggard_instrument_id,
                "orders": int(len(orders)),
                "buy_orders": int((orders["side"] == 1).sum()) if not orders.empty else 0,
                "sell_orders": int((orders["side"] == -1).sum()) if not orders.empty else 0,
                "qty": int(plan["qty"]) if not np.isnan(float(plan["qty"])) else 0,
                "reference_price": _jsonable(plan["reference_price"]),
                "buy_limit_price": _jsonable(plan["buy_limit_price"]),
                "sell_limit_price": _jsonable(plan["sell_limit_price"]),
                "total_notional": total_notional,
                "max_order_notional": max_order_notional,
                "failed_checks": failed,
                "output_file": config.output_filename,
                "recommendation": "stage_for_paper_shadow_runtime" if ready else "keep_in_research",
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
            "scenario_key",
            "source",
            "trigger",
            "signal_direction",
            "template_only",
            "trigger_ticks",
            "delta",
            "leader_tick",
            "laggard_tick",
            "flat_after_ns",
            "cooloff_ns",
            "lifecycle_action",
            "lifecycle_action_id",
            "lifecycle_reason",
            "lifecycle_message_count",
        ]
    )


def _client_order_id(
    scenario_key: str,
    instrument_id: str,
    side: int,
    qty: int,
    price: float,
    trigger: str,
) -> str:
    payload = f"{scenario_key}|{instrument_id}|{side}|{qty}|{price:.8f}|{trigger}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"LLAG-{digest}"


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


def _validate_config(config: LeadLagOrderPlanConfig) -> None:
    if not str(config.laggard_instrument_id).strip():
        raise ValueError("laggard_instrument_id must not be blank")
    if config.qty is not None and config.qty <= 0:
        raise ValueError("qty must be positive")
    if config.reference_price is not None and config.reference_price <= 0:
        raise ValueError("reference_price must be positive")
    if config.buy_limit_price is not None and config.buy_limit_price <= 0:
        raise ValueError("buy_limit_price must be positive")
    if config.sell_limit_price is not None and config.sell_limit_price <= 0:
        raise ValueError("sell_limit_price must be positive")
    if config.entry_offset_ticks < 0:
        raise ValueError("entry_offset_ticks must be non-negative")
    if config.tick_size is not None and config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if config.max_order_qty is not None and config.max_order_qty <= 0:
        raise ValueError("max_order_qty must be positive")
    if config.max_notional is not None and config.max_notional <= 0:
        raise ValueError("max_notional must be positive")
    if config.price_band_pct is not None and config.price_band_pct < 0:
        raise ValueError("price_band_pct must be non-negative")
    output_name = Path(config.output_filename)
    if not config.output_filename or output_name.name != config.output_filename:
        raise ValueError("output_filename must be a file name without directories")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
    if frame.empty:
        raise ValueError(f"{name} must not be empty")


def _number(value: Any, default: float) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
