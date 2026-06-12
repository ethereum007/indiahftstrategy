from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.broker import normalize_live_fills
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class ReconciliationThresholds:
    min_order_fill_rate: float = 0.0
    max_unfilled_orders: int | None = None
    max_partial_orders: int | None = None
    max_overfilled_orders: int = 0
    max_mismatched_orders: int = 0
    max_unmatched_fills: int = 0
    max_adverse_slippage: float | None = None


@dataclass(frozen=True)
class ReconciliationReport:
    orders: pd.DataFrame
    unmatched_fills: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        return bool(self.summary.iloc[0]["passed"]) if not self.summary.empty else False


def evaluate_order_reconciliation(
    exported_orders: pd.DataFrame,
    live_fills: pd.DataFrame,
    *,
    thresholds: ReconciliationThresholds | None = None,
) -> ReconciliationReport:
    thresholds = thresholds or ReconciliationThresholds()
    _validate_thresholds(thresholds)
    orders = _normalize_orders(exported_orders)
    fills = _normalize_fills(live_fills)
    matched = _reconcile_orders(orders, fills)
    unmatched = fills.loc[~fills["client_order_id"].isin(orders["client_order_id"])].reset_index(drop=True)
    summary = _summary(matched, unmatched)
    checks = _checks(summary.iloc[0], thresholds)
    summary["passed"] = bool(checks["passed"].all()) if not checks.empty else False
    return ReconciliationReport(orders=matched, unmatched_fills=unmatched, checks=checks, summary=summary)


def write_order_reconciliation(
    *,
    export_dir: str | Path,
    fills_path: str | Path,
    output_dir: str | Path,
    adapter: str = "normalized",
    thresholds: ReconciliationThresholds | None = None,
) -> ReconciliationReport:
    export_path = Path(export_dir)
    orders_path = export_path / "broker_orders.csv"
    if not orders_path.exists():
        raise FileNotFoundError(f"broker_orders.csv not found: {orders_path}")
    fills_file = Path(fills_path)
    if not fills_file.exists():
        raise FileNotFoundError(f"live fills file not found: {fills_file}")
    thresholds = thresholds or ReconciliationThresholds()
    report = evaluate_order_reconciliation(
        pd.read_csv(orders_path),
        normalize_live_fills(fills_file, adapter=adapter),
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.orders.to_csv(out / "order_reconciliation.csv", index=False)
    report.unmatched_fills.to_csv(out / "unmatched_fills.csv", index=False)
    report.checks.to_csv(out / "reconciliation_checks.csv", index=False)
    report.summary.to_csv(out / "reconciliation_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="order_reconciliation",
        parameters={"adapter": adapter, "thresholds": asdict(thresholds)},
        inputs={"export": export_path, "fills": fills_file},
    )
    return ReconciliationReport(report.orders, report.unmatched_fills, report.checks, report.summary, out)


def _normalize_orders(orders: pd.DataFrame) -> pd.DataFrame:
    _require(orders, ["client_order_id", "instrument_id", "side", "qty", "price"], "exported_orders")
    frame = orders.copy().reset_index(drop=True)
    frame["client_order_id"] = frame["client_order_id"].astype(str)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side).astype("int64")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    if "ts_signal_ns" not in frame.columns:
        frame["ts_signal_ns"] = np.nan
    frame["ts_signal_ns"] = pd.to_numeric(frame["ts_signal_ns"], errors="coerce")
    return frame


def _normalize_fills(fills: pd.DataFrame) -> pd.DataFrame:
    _require(fills, ["client_order_id", "instrument_id", "ts_fill_ns", "side", "qty", "price"], "live_fills")
    frame = fills.copy().reset_index(drop=True)
    frame["client_order_id"] = frame["client_order_id"].astype(str)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side).astype("int64")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
    frame["ts_fill_ns"] = pd.to_numeric(frame["ts_fill_ns"], errors="coerce")
    frame["fill_notional"] = frame["qty"] * frame["price"]
    return frame


def _reconcile_orders(orders: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        out = orders.copy()
        return _attach_empty_fill_metrics(out)

    fill_groups = []
    for client_order_id, group in fills.sort_values("ts_fill_ns").groupby("client_order_id", dropna=False):
        live_qty = float(group["qty"].sum())
        live_notional = float(group["fill_notional"].sum())
        avg_price = live_notional / live_qty if live_qty > 0 else np.nan
        instruments = sorted(group["instrument_id"].dropna().astype(str).unique())
        sides = sorted(group["side"].dropna().astype(int).unique())
        fill_groups.append(
            {
                "client_order_id": str(client_order_id),
                "live_qty": live_qty,
                "live_avg_price": avg_price,
                "fill_count": int(len(group)),
                "live_instrument_id": instruments[0] if len(instruments) == 1 else "MULTIPLE",
                "live_side": sides[0] if len(sides) == 1 else 0,
                "first_fill_ts_ns": float(group["ts_fill_ns"].min()),
                "last_fill_ts_ns": float(group["ts_fill_ns"].max()),
                "live_notional": live_notional,
            }
        )
    live = pd.DataFrame(fill_groups)
    out = orders.merge(live, on="client_order_id", how="left")
    out["live_qty"] = out["live_qty"].fillna(0.0)
    out["fill_count"] = out["fill_count"].fillna(0).astype("int64")
    out["filled_live"] = out["live_qty"] > 0
    out["fill_qty_diff"] = out["live_qty"] - out["qty"]
    out["fill_status"] = np.select(
        [
            out["live_qty"] <= 0,
            out["live_qty"] < out["qty"],
            out["live_qty"] == out["qty"],
            out["live_qty"] > out["qty"],
        ],
        ["unfilled", "partial", "full", "overfill"],
        default="unknown",
    )
    out["instrument_match"] = (~out["filled_live"]) | (out["live_instrument_id"] == out["instrument_id"])
    out["side_match"] = (~out["filled_live"]) | (out["live_side"] == out["side"])
    out["mismatch"] = out["filled_live"] & (~out["instrument_match"] | ~out["side_match"])
    out["latency_ns"] = out["first_fill_ts_ns"] - out["ts_signal_ns"]
    out["adverse_slippage"] = out["side"] * (out["live_avg_price"] - out["price"])
    out.loc[~out["filled_live"], ["latency_ns", "adverse_slippage"]] = np.nan
    return out


def _attach_empty_fill_metrics(orders: pd.DataFrame) -> pd.DataFrame:
    out = orders.copy()
    out["live_qty"] = 0.0
    out["live_avg_price"] = np.nan
    out["fill_count"] = 0
    out["live_instrument_id"] = np.nan
    out["live_side"] = np.nan
    out["first_fill_ts_ns"] = np.nan
    out["last_fill_ts_ns"] = np.nan
    out["live_notional"] = 0.0
    out["filled_live"] = False
    out["fill_qty_diff"] = -out["qty"]
    out["fill_status"] = "unfilled"
    out["instrument_match"] = True
    out["side_match"] = True
    out["mismatch"] = False
    out["latency_ns"] = np.nan
    out["adverse_slippage"] = np.nan
    return out


def _summary(orders: pd.DataFrame, unmatched_fills: pd.DataFrame) -> pd.DataFrame:
    order_count = int(len(orders))
    filled_orders = int(orders["filled_live"].sum()) if order_count else 0
    partial_orders = int((orders["fill_status"] == "partial").sum()) if order_count else 0
    overfilled_orders = int((orders["fill_status"] == "overfill").sum()) if order_count else 0
    unfilled_orders = int((orders["fill_status"] == "unfilled").sum()) if order_count else 0
    mismatched_orders = int(orders["mismatch"].sum()) if order_count else 0
    adverse = pd.to_numeric(orders["adverse_slippage"], errors="coerce")
    return pd.DataFrame(
        [
            {
                "orders": order_count,
                "filled_orders": filled_orders,
                "partial_orders": partial_orders,
                "overfilled_orders": overfilled_orders,
                "unfilled_orders": unfilled_orders,
                "mismatched_orders": mismatched_orders,
                "unmatched_fills": int(len(unmatched_fills)),
                "order_fill_rate": filled_orders / order_count if order_count else 0.0,
                "requested_qty": float(pd.to_numeric(orders["qty"], errors="coerce").sum()) if order_count else 0.0,
                "live_qty": float(pd.to_numeric(orders["live_qty"], errors="coerce").sum()) if order_count else 0.0,
                "avg_adverse_slippage": float(adverse.mean(skipna=True)) if adverse.notna().any() else np.nan,
                "max_adverse_slippage": float(adverse.max(skipna=True)) if adverse.notna().any() else np.nan,
                "avg_latency_ns": float(pd.to_numeric(orders["latency_ns"], errors="coerce").mean(skipna=True))
                if pd.to_numeric(orders["latency_ns"], errors="coerce").notna().any()
                else np.nan,
            }
        ]
    )


def _checks(row: pd.Series, thresholds: ReconciliationThresholds) -> pd.DataFrame:
    checks = [
        _threshold_check("order_fill_rate", row["order_fill_rate"], ">=", thresholds.min_order_fill_rate),
        _threshold_check("overfilled_orders", row["overfilled_orders"], "<=", thresholds.max_overfilled_orders),
        _threshold_check("mismatched_orders", row["mismatched_orders"], "<=", thresholds.max_mismatched_orders),
        _threshold_check("unmatched_fills", row["unmatched_fills"], "<=", thresholds.max_unmatched_fills),
    ]
    if thresholds.max_unfilled_orders is not None:
        checks.append(_threshold_check("unfilled_orders", row["unfilled_orders"], "<=", thresholds.max_unfilled_orders))
    if thresholds.max_partial_orders is not None:
        checks.append(_threshold_check("partial_orders", row["partial_orders"], "<=", thresholds.max_partial_orders))
    if thresholds.max_adverse_slippage is not None:
        checks.append(
            _threshold_check("max_adverse_slippage", row["max_adverse_slippage"], "<=", thresholds.max_adverse_slippage)
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
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _validate_thresholds(thresholds: ReconciliationThresholds) -> None:
    if not 0 <= thresholds.min_order_fill_rate <= 1:
        raise ValueError("min_order_fill_rate must be between 0 and 1")
    for name in ("max_unfilled_orders", "max_partial_orders", "max_overfilled_orders", "max_mismatched_orders", "max_unmatched_fills"):
        value = getattr(thresholds, name)
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative")
    if thresholds.max_adverse_slippage is not None and thresholds.max_adverse_slippage < 0:
        raise ValueError("max_adverse_slippage must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


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
