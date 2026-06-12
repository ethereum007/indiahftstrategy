from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from engine.surface import normal_cdf
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class OrderExposureConfig:
    forward: float | None = None
    tte_years: float = 30 / 365
    vol: float | None = None
    contract_multiplier: float = 1.0
    require_greeks: bool = True
    max_abs_net_delta: float | None = None
    max_abs_net_vega: float | None = None
    max_gross_notional: float | None = None
    max_side_imbalance: float | None = None
    max_instrument_concentration: float | None = None
    min_orders: int = 1


@dataclass(frozen=True)
class OrderExposureReport:
    orders: pd.DataFrame
    by_instrument: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_order_exposure(
    orders: pd.DataFrame,
    *,
    config: OrderExposureConfig | None = None,
) -> OrderExposureReport:
    config = config or OrderExposureConfig()
    _validate_config(config)
    normalized = _normalize_orders(orders, config)
    enriched = _attach_exposures(normalized, config)
    by_instrument = _by_instrument(enriched)
    summary = _summary(enriched, by_instrument)
    checks = _checks(summary.iloc[0], config)
    summary["passed"] = bool(checks["passed"].all()) if not checks.empty else False
    return OrderExposureReport(enriched, by_instrument, checks, summary)


def write_order_exposure_report(
    orders_path: str | Path,
    *,
    output_dir: str | Path,
    config: OrderExposureConfig | None = None,
) -> OrderExposureReport:
    orders_file = Path(orders_path)
    if not orders_file.exists():
        raise FileNotFoundError(f"orders file not found: {orders_file}")
    config = config or OrderExposureConfig()
    report = evaluate_order_exposure(pd.read_csv(orders_file), config=config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / "order_exposure.csv", index=False)
    report.by_instrument.to_csv(out / "order_exposure_by_instrument.csv", index=False)
    report.checks.to_csv(out / "order_exposure_checks.csv", index=False)
    report.summary.to_csv(out / "order_exposure_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="order_exposure_report",
        parameters={"config": asdict(config)},
        inputs={"orders": orders_file},
    )
    return OrderExposureReport(report.orders, report.by_instrument, report.checks, report.summary, out)


def _normalize_orders(orders: pd.DataFrame, config: OrderExposureConfig) -> pd.DataFrame:
    _require(orders, ["instrument_id", "side", "qty", "price"], "orders")
    frame = orders.copy().reset_index(drop=True)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side).astype("int64")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    parsed = frame["instrument_id"].map(_parse_instrument_id)
    if "option_type" not in frame.columns:
        frame["option_type"] = [item[0] for item in parsed]
    if "strike" not in frame.columns:
        frame["strike"] = [item[1] for item in parsed]
    frame["option_type"] = frame["option_type"].astype(str).str.upper().replace({"CALL": "C", "PUT": "P"})
    frame["strike"] = pd.to_numeric(frame["strike"], errors="coerce")
    frame["forward"] = _numeric_with_fallback(frame, "forward", config.forward)
    frame["implied_vol"] = _numeric_with_fallback(frame, "implied_vol", config.vol)
    frame["tte_years"] = _numeric_with_fallback(frame, "tte_years", config.tte_years)
    frame["notional"] = frame["qty"] * frame["price"] * config.contract_multiplier
    return frame


def _attach_exposures(frame: pd.DataFrame, config: OrderExposureConfig) -> pd.DataFrame:
    out = frame.copy()
    deltas = []
    vegas = []
    greek_available = []
    for row in out.itertuples(index=False):
        try:
            delta, vega = _black76_delta_vega(
                option_type=str(row.option_type),
                forward=float(row.forward),
                strike=float(row.strike),
                tte_years=float(row.tte_years),
                vol=float(row.implied_vol),
            )
            greek_available.append(True)
        except (TypeError, ValueError, ZeroDivisionError):
            delta, vega = np.nan, np.nan
            greek_available.append(False)
        deltas.append(delta)
        vegas.append(vega)
    out["greek_available"] = greek_available
    out["unit_delta"] = deltas
    out["unit_vega"] = vegas
    signed_qty = out["side"] * out["qty"] * config.contract_multiplier
    out["signed_delta"] = signed_qty * out["unit_delta"]
    out["signed_vega"] = signed_qty * out["unit_vega"]
    out["abs_delta"] = out["signed_delta"].abs()
    out["abs_vega"] = out["signed_vega"].abs()
    return out


def _black76_delta_vega(
    *,
    option_type: str,
    forward: float,
    strike: float,
    tte_years: float,
    vol: float,
) -> tuple[float, float]:
    if option_type not in {"C", "P"}:
        raise ValueError("option_type must be C or P")
    if forward <= 0 or strike <= 0 or tte_years <= 0 or vol <= 0:
        raise ValueError("forward, strike, tte_years, and vol must be positive")
    sqrt_t = math.sqrt(tte_years)
    d1 = (math.log(forward / strike) + 0.5 * vol * vol * tte_years) / (vol * sqrt_t)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    delta = normal_cdf(d1) if option_type == "C" else normal_cdf(d1) - 1.0
    vega = forward * pdf * sqrt_t
    return float(delta), float(vega)


def _by_instrument(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "instrument_id",
                "orders",
                "qty",
                "net_qty",
                "notional",
                "net_delta",
                "abs_delta",
                "net_vega",
                "abs_vega",
            ]
        )
    working = frame.copy()
    working["signed_qty"] = working["side"] * working["qty"]
    return (
        working.groupby("instrument_id", dropna=False)
        .agg(
            orders=("instrument_id", "size"),
            qty=("qty", "sum"),
            net_qty=("signed_qty", "sum"),
            notional=("notional", "sum"),
            net_delta=("signed_delta", "sum"),
            abs_delta=("abs_delta", "sum"),
            net_vega=("signed_vega", "sum"),
            abs_vega=("abs_vega", "sum"),
        )
        .reset_index()
    )


def _summary(frame: pd.DataFrame, by_instrument: pd.DataFrame) -> pd.DataFrame:
    order_count = int(len(frame))
    gross_notional = float(pd.to_numeric(frame["notional"], errors="coerce").sum()) if order_count else 0.0
    buy_notional = float(frame.loc[frame["side"] > 0, "notional"].sum()) if order_count else 0.0
    sell_notional = float(frame.loc[frame["side"] < 0, "notional"].sum()) if order_count else 0.0
    return pd.DataFrame(
        [
            {
                "orders": order_count,
                "instruments": int(frame["instrument_id"].nunique()) if order_count else 0,
                "gross_notional": gross_notional,
                "buy_notional": buy_notional,
                "sell_notional": sell_notional,
                "side_imbalance": abs(buy_notional - sell_notional) / gross_notional if gross_notional else 0.0,
                "net_delta": float(pd.to_numeric(frame["signed_delta"], errors="coerce").sum(skipna=True)),
                "abs_delta": float(pd.to_numeric(frame["abs_delta"], errors="coerce").sum(skipna=True)),
                "net_vega": float(pd.to_numeric(frame["signed_vega"], errors="coerce").sum(skipna=True)),
                "abs_vega": float(pd.to_numeric(frame["abs_vega"], errors="coerce").sum(skipna=True)),
                "greek_coverage": float(frame["greek_available"].mean()) if order_count else 0.0,
                "max_instrument_notional": float(by_instrument["notional"].max(skipna=True))
                if not by_instrument.empty
                else 0.0,
                "instrument_concentration": float(by_instrument["notional"].max(skipna=True) / gross_notional)
                if gross_notional and not by_instrument.empty
                else 0.0,
            }
        ]
    )


def _checks(row: pd.Series, config: OrderExposureConfig) -> pd.DataFrame:
    checks = [_threshold_check("orders", row["orders"], ">=", config.min_orders)]
    checks.append(
        _check(
            "greek_coverage",
            row["greek_coverage"],
            "==",
            1.0,
            (not config.require_greeks) or float(row["greek_coverage"]) >= 1.0,
            "some option greeks could not be calculated",
        )
    )
    if config.max_abs_net_delta is not None:
        checks.append(_threshold_check("abs_net_delta", abs(row["net_delta"]), "<=", config.max_abs_net_delta))
    if config.max_abs_net_vega is not None:
        checks.append(_threshold_check("abs_net_vega", abs(row["net_vega"]), "<=", config.max_abs_net_vega))
    if config.max_gross_notional is not None:
        checks.append(_threshold_check("gross_notional", row["gross_notional"], "<=", config.max_gross_notional))
    if config.max_side_imbalance is not None:
        checks.append(_threshold_check("side_imbalance", row["side_imbalance"], "<=", config.max_side_imbalance))
    if config.max_instrument_concentration is not None:
        checks.append(
            _threshold_check(
                "instrument_concentration",
                row["instrument_concentration"],
                "<=",
                config.max_instrument_concentration,
            )
        )
    return pd.DataFrame(checks)


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return _check(name, value_float, operator, threshold_float, passed, reason)


def _check(
    name: str,
    value: object,
    operator: str,
    threshold: object,
    passed: bool,
    reason: str,
) -> dict[str, object]:
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _validate_config(config: OrderExposureConfig) -> None:
    if config.forward is not None and config.forward <= 0:
        raise ValueError("forward must be positive")
    if config.tte_years <= 0:
        raise ValueError("tte_years must be positive")
    if config.vol is not None and config.vol <= 0:
        raise ValueError("vol must be positive")
    if config.contract_multiplier <= 0:
        raise ValueError("contract_multiplier must be positive")
    if config.min_orders < 0:
        raise ValueError("min_orders must be non-negative")
    for name in (
        "max_abs_net_delta",
        "max_abs_net_vega",
        "max_gross_notional",
        "max_side_imbalance",
        "max_instrument_concentration",
    ):
        value = getattr(config, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")


def _numeric_with_fallback(frame: pd.DataFrame, column: str, fallback: float | None) -> pd.Series:
    if column in frame.columns:
        values = pd.to_numeric(frame[column], errors="coerce")
    else:
        values = pd.Series(np.nan, index=frame.index)
    if fallback is not None:
        values = values.fillna(float(fallback))
    return values


def _parse_instrument_id(instrument_id: str) -> tuple[str | float, float]:
    text = str(instrument_id).upper()
    if text.startswith("CALL_"):
        return "C", float(text.replace("CALL_", "").replace("_", "."))
    if text.startswith("PUT_"):
        return "P", float(text.replace("PUT_", "").replace("_", "."))
    return np.nan, np.nan


def _normalize_side(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return 0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return 0


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")
