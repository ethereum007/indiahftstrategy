from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class SettlementOrderPlanConfig:
    symbol_prefix: str = "NIFTY"
    require_promotion_ready: bool = True
    qty: int | None = None
    price_offset_ticks: float = 0.0
    tick_size: float = 0.05
    output_filename: str = "settlement_order_candidates.csv"


@dataclass(frozen=True)
class SettlementOrderPlanReport:
    orders: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["ready"])


def build_settlement_order_plan(
    promotion_summary: pd.DataFrame,
    candidate_config: dict[str, Any],
    *,
    config: SettlementOrderPlanConfig | None = None,
) -> SettlementOrderPlanReport:
    config = config or SettlementOrderPlanConfig()
    _validate_config(config)
    _require(promotion_summary, ["ready", "candidate_scenario_key"], "promotion_summary")
    parameters = (
        candidate_config.get("parameters", {}) if isinstance(candidate_config.get("parameters", {}), dict) else {}
    )
    scenario_key = str(candidate_config.get("scenario_key") or promotion_summary.iloc[0]["candidate_scenario_key"])
    checks = _checks(promotion_summary.iloc[0], candidate_config, parameters, config)
    orders = (
        _orders(parameters, scenario_key=scenario_key, config=config)
        if bool(checks["passed"].all())
        else _empty_orders()
    )
    summary = _summary(orders, checks, scenario_key, config)
    return SettlementOrderPlanReport(orders=orders, checks=checks, summary=summary)


def write_settlement_order_plan(
    promotion_dir: str | Path,
    *,
    output_dir: str | Path,
    config: SettlementOrderPlanConfig | None = None,
) -> SettlementOrderPlanReport:
    promotion = Path(promotion_dir)
    summary_path = promotion / "promotion_summary.csv"
    candidate_path = promotion / "candidate_config.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"promotion_summary.csv not found: {summary_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate_config.json not found: {candidate_path}")
    config = config or SettlementOrderPlanConfig()
    report = build_settlement_order_plan(
        pd.read_csv(summary_path),
        json.loads(candidate_path.read_text(encoding="utf-8")),
        config=config,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / config.output_filename, index=False)
    report.checks.to_csv(out / "settlement_order_checks.csv", index=False)
    report.summary.to_csv(out / "settlement_order_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="settlement_order_plan",
        parameters={"config": asdict(config)},
        inputs={"promotion": promotion, "summary": summary_path, "candidate_config": candidate_path},
    )
    return SettlementOrderPlanReport(report.orders, report.checks, report.summary, out)


def _orders(
    parameters: dict[str, Any],
    *,
    scenario_key: str,
    config: SettlementOrderPlanConfig,
) -> pd.DataFrame:
    side = _side(parameters)
    qty = int(config.qty if config.qty is not None else _number(parameters.get("best_trade_qty"), 0))
    touch_price = float(_number(parameters.get("best_touch_price"), np.nan))
    price = touch_price + side * float(config.price_offset_ticks) * float(config.tick_size)
    option_type = str(parameters.get("best_option_type", "")).upper()
    expiry = str(parameters.get("best_expiry", ""))
    strike = float(_number(parameters.get("best_strike"), np.nan))
    ts_signal_ns = int(_number(parameters.get("best_ts"), 0))
    instrument_id = _instrument_id(config.symbol_prefix, expiry, strike, option_type)
    client_order_id = _client_order_id(scenario_key, instrument_id, side, qty, price)
    return pd.DataFrame(
        [
            {
                "client_order_id": client_order_id,
                "strategy": "settlement_convergence",
                "instrument_id": instrument_id,
                "side": int(side),
                "side_text": "BUY" if side > 0 else "SELL",
                "qty": int(qty),
                "price": float(price),
                "order_type": "LIMIT",
                "time_in_force": "DAY",
                "ts_signal_ns": ts_signal_ns,
                "marketable": False,
                "quote_edge": _number(parameters.get("best_net_edge"), np.nan),
                "theo": _number(parameters.get("best_projected_intrinsic"), np.nan),
                "expiry": expiry,
                "strike": strike,
                "option_type": option_type,
                "scenario_key": scenario_key,
                "source": "settlement_candidate_promotion",
                "projected_settlement": _number(parameters.get("best_projected_settlement"), np.nan),
                "gross_edge_ticks": _number(parameters.get("best_gross_edge_ticks"), np.nan),
            }
        ]
    )


def _checks(
    summary: pd.Series,
    candidate_config: dict[str, Any],
    parameters: dict[str, Any],
    config: SettlementOrderPlanConfig,
) -> pd.DataFrame:
    promotion_ready = _to_bool(summary.get("ready", False))
    candidate_ready = _to_bool(candidate_config.get("ready", False))
    side = _side(parameters, default=0)
    qty = config.qty if config.qty is not None else _number(parameters.get("best_trade_qty"), 0)
    price = _number(parameters.get("best_touch_price"), np.nan)
    strike = _number(parameters.get("best_strike"), np.nan)
    option_type = str(parameters.get("best_option_type", "")).upper()
    expiry = str(parameters.get("best_expiry", "")).strip()
    return pd.DataFrame(
        [
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
            _check("valid_side", side, "in", "-1,1", side in {-1, 1}, "best settlement side is unavailable"),
            _threshold_check("positive_qty", float(qty), ">", 0),
            _threshold_check("positive_price", float(price), ">", 0),
            _threshold_check("positive_strike", float(strike), ">", 0),
            _check(
                "valid_option_type",
                option_type,
                "in",
                "C,P",
                option_type in {"C", "P"},
                "option type must be C or P",
            ),
            _check("expiry_available", expiry, "not_empty", True, bool(expiry), "expiry is unavailable"),
        ]
    )


def _summary(
    orders: pd.DataFrame,
    checks: pd.DataFrame,
    scenario_key: str,
    config: SettlementOrderPlanConfig,
) -> pd.DataFrame:
    ready = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    total_notional = float((orders["qty"] * orders["price"]).sum()) if not orders.empty else 0.0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "scenario_key": scenario_key,
                "orders": int(len(orders)),
                "buy_orders": int((orders["side"] == 1).sum()) if not orders.empty else 0,
                "sell_orders": int((orders["side"] == -1).sum()) if not orders.empty else 0,
                "total_notional": total_notional,
                "failed_checks": failed,
                "output_file": config.output_filename,
                "recommendation": "stage_orders" if ready else "keep_in_research",
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
            "projected_settlement",
            "gross_edge_ticks",
        ]
    )


def _instrument_id(prefix: str, expiry: str, strike: float, option_type: str) -> str:
    expiry_key = "".join(ch for ch in str(expiry) if ch.isalnum())
    strike_key = str(int(strike)) if float(strike).is_integer() else str(strike).replace(".", "p")
    return f"{prefix.upper()}_{expiry_key}_{strike_key}{option_type.upper()}"


def _client_order_id(scenario_key: str, instrument_id: str, side: int, qty: int, price: float) -> str:
    payload = f"{scenario_key}|{instrument_id}|{side}|{qty}|{price:.8f}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"SETTLE-{digest}"


def _side(parameters: dict[str, Any], *, default: int | None = None) -> int:
    value = parameters.get("best_side")
    try:
        side = int(float(value))
    except (TypeError, ValueError):
        side = 0
    if side in {-1, 1}:
        return side
    direction = str(parameters.get("best_direction", "")).strip().lower()
    if direction == "buy_underpriced":
        return 1
    if direction == "sell_overpriced":
        return -1
    if default is not None:
        return default
    raise ValueError("best settlement direction cannot be mapped to an order side")


def _threshold_check(name: str, value: float, operator: str, threshold: float) -> dict[str, Any]:
    missing = np.isnan(value)
    if operator == ">":
        passed = (not missing) and value > threshold
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value:.6g} failed {operator} {threshold:.6g}"
    return _check(name, value, operator, threshold, passed, reason)


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


def _validate_config(config: SettlementOrderPlanConfig) -> None:
    if not str(config.symbol_prefix).strip():
        raise ValueError("symbol_prefix must not be blank")
    if config.qty is not None and config.qty <= 0:
        raise ValueError("qty must be positive")
    if config.tick_size <= 0:
        raise ValueError("tick_size must be positive")
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


def _to_bool(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ready", "passed"}
    return bool(value)
