from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class FillModelCalibrationThresholds:
    tick_size: float = 0.05
    min_orders: int = 1
    min_live_fill_rate: float = 0.0
    max_mismatch_rate: float = 0.0
    max_overfill_rate: float = 0.0
    max_unmatched_fills: int = 0
    max_adverse_slippage_ticks: float | None = None
    latency_quantile: float = 0.95
    fill_ratio_quantile: float = 0.25
    slippage_quantile: float = 0.95
    min_queue_conservatism: float = 1.0
    max_queue_conservatism: float = 10.0
    base_edge_ticks: float = 0.0


@dataclass(frozen=True)
class FillModelCalibrationReport:
    metrics: pd.DataFrame
    recommendations: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    config: dict[str, Any]
    output_dir: Path | None = None

    @property
    def ready(self) -> bool:
        return bool(self.summary.iloc[0]["ready"]) if not self.summary.empty else False


def evaluate_fill_model_calibration(
    reconciliation_orders: pd.DataFrame,
    reconciliation_summary: pd.DataFrame | None = None,
    *,
    thresholds: FillModelCalibrationThresholds | None = None,
) -> FillModelCalibrationReport:
    thresholds = thresholds or FillModelCalibrationThresholds()
    _validate_thresholds(thresholds)
    orders = _normalize_orders(reconciliation_orders)
    summary_input = pd.DataFrame() if reconciliation_summary is None else reconciliation_summary.copy()
    metrics = _metrics(orders, thresholds)
    recommendations = _recommendations(metrics, thresholds)
    checks = _checks(metrics.iloc[0], summary_input, thresholds)
    summary = _summary(metrics.iloc[0], recommendations.iloc[0], checks)
    config = _config(recommendations, summary.iloc[0], checks, thresholds)
    return FillModelCalibrationReport(metrics, recommendations, checks, summary, config)


def write_fill_model_calibration(
    *,
    reconciliation_dir: str | Path,
    output_dir: str | Path,
    thresholds: FillModelCalibrationThresholds | None = None,
) -> FillModelCalibrationReport:
    reconciliation = Path(reconciliation_dir)
    orders_path = reconciliation / "order_reconciliation.csv" if reconciliation.is_dir() else reconciliation
    summary_path = reconciliation / "reconciliation_summary.csv" if reconciliation.is_dir() else None
    if not orders_path.exists():
        raise FileNotFoundError(f"order reconciliation file not found: {orders_path}")
    summary = pd.read_csv(summary_path) if summary_path and summary_path.exists() else None
    thresholds = thresholds or FillModelCalibrationThresholds()
    report = evaluate_fill_model_calibration(
        pd.read_csv(orders_path),
        summary,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.metrics.to_csv(out / "fill_model_metrics.csv", index=False)
    report.recommendations.to_csv(out / "fill_model_recommendations.csv", index=False)
    report.checks.to_csv(out / "fill_model_checks.csv", index=False)
    report.summary.to_csv(out / "fill_model_summary.csv", index=False)
    (out / "fill_model_config.json").write_text(
        json.dumps(report.config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_experiment_manifest(
        out,
        run_type="fill_model_calibration",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"reconciliation": reconciliation},
    )
    return FillModelCalibrationReport(
        report.metrics,
        report.recommendations,
        report.checks,
        report.summary,
        report.config,
        out,
    )


def _normalize_orders(orders: pd.DataFrame) -> pd.DataFrame:
    _require(orders, ["instrument_id", "qty", "live_qty", "filled_live", "fill_status"], "reconciliation_orders")
    frame = orders.copy().reset_index(drop=True)
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce").fillna(0.0)
    frame["live_qty"] = pd.to_numeric(frame["live_qty"], errors="coerce").fillna(0.0)
    frame["filled_live"] = frame["filled_live"].map(_to_bool)
    frame["fill_status"] = frame["fill_status"].astype(str).str.strip().str.lower()
    frame["fill_ratio"] = np.where(frame["qty"] > 0, frame["live_qty"] / frame["qty"], 0.0)
    frame["fill_ratio"] = frame["fill_ratio"].clip(lower=0.0)
    frame["latency_ns"] = _numeric_optional(frame, "latency_ns")
    frame["adverse_slippage"] = _numeric_optional(frame, "adverse_slippage")
    frame["mismatch"] = frame["mismatch"].map(_to_bool) if "mismatch" in frame.columns else False
    return frame


def _metrics(orders: pd.DataFrame, thresholds: FillModelCalibrationThresholds) -> pd.DataFrame:
    rows = [_metric_row("ALL", orders, thresholds)]
    for instrument_id, group in orders.groupby("instrument_id", dropna=False):
        rows.append(_metric_row(str(instrument_id), group, thresholds))
    return pd.DataFrame(rows)


def _metric_row(label: str, group: pd.DataFrame, thresholds: FillModelCalibrationThresholds) -> dict[str, object]:
    orders = int(len(group))
    filled = int(group["filled_live"].sum()) if orders else 0
    partial = int((group["fill_status"] == "partial").sum()) if orders else 0
    overfill = int((group["fill_status"] == "overfill").sum()) if orders else 0
    mismatch = int(group["mismatch"].sum()) if orders else 0
    fill_ratio = pd.to_numeric(group["fill_ratio"], errors="coerce")
    latency = pd.to_numeric(group["latency_ns"], errors="coerce")
    adverse = pd.to_numeric(group["adverse_slippage"], errors="coerce")
    adverse_positive = adverse.clip(lower=0.0)
    return {
        "instrument_id": label,
        "orders": orders,
        "filled_orders": filled,
        "partial_orders": partial,
        "overfilled_orders": overfill,
        "mismatched_orders": mismatch,
        "live_fill_rate": filled / orders if orders else 0.0,
        "partial_rate": partial / orders if orders else 0.0,
        "overfill_rate": overfill / orders if orders else 0.0,
        "mismatch_rate": mismatch / orders if orders else 0.0,
        "requested_qty": float(group["qty"].sum()) if orders else 0.0,
        "live_qty": float(group["live_qty"].sum()) if orders else 0.0,
        "avg_fill_ratio": float(fill_ratio.mean(skipna=True)) if fill_ratio.notna().any() else 0.0,
        "fill_ratio_quantile": _quantile(fill_ratio, thresholds.fill_ratio_quantile, default=0.0),
        "avg_latency_ns": float(latency.mean(skipna=True)) if latency.notna().any() else np.nan,
        "latency_quantile_ns": _quantile(latency, thresholds.latency_quantile, default=np.nan),
        "avg_adverse_slippage": float(adverse.mean(skipna=True)) if adverse.notna().any() else np.nan,
        "adverse_slippage_quantile": _quantile(adverse_positive, thresholds.slippage_quantile, default=0.0),
        "max_adverse_slippage": float(adverse.max(skipna=True)) if adverse.notna().any() else 0.0,
    }


def _recommendations(metrics: pd.DataFrame, thresholds: FillModelCalibrationThresholds) -> pd.DataFrame:
    rows = []
    for row in metrics.to_dict("records"):
        fill_ratio_floor = max(float(row["fill_ratio_quantile"]), 1e-9)
        queue_conservatism = min(
            thresholds.max_queue_conservatism,
            max(thresholds.min_queue_conservatism, 1.0 / fill_ratio_floor),
        )
        latency_ns = float(row["latency_quantile_ns"]) if not pd.isna(row["latency_quantile_ns"]) else 0.0
        adverse_ticks = max(0.0, float(row["adverse_slippage_quantile"])) / thresholds.tick_size
        slippage_ticks = float(np.ceil(adverse_ticks - 1e-12))
        rows.append(
            {
                "instrument_id": row["instrument_id"],
                "recommended_queue_conservatism": float(queue_conservatism),
                "recommended_order_latency_us": float(latency_ns / 1_000.0),
                "recommended_slippage_ticks": slippage_ticks,
                "recommended_min_edge_ticks": float(thresholds.base_edge_ticks + slippage_ticks),
                "basis_live_fill_rate": float(row["live_fill_rate"]),
                "basis_fill_ratio_quantile": float(row["fill_ratio_quantile"]),
                "basis_latency_quantile_ns": latency_ns,
                "basis_adverse_slippage_quantile": float(row["adverse_slippage_quantile"]),
            }
        )
    return pd.DataFrame(rows)


def _checks(
    all_metrics: pd.Series,
    reconciliation_summary: pd.DataFrame,
    thresholds: FillModelCalibrationThresholds,
) -> pd.DataFrame:
    unmatched_fills = _unmatched_fills(reconciliation_summary)
    max_adverse_ticks = float(all_metrics["max_adverse_slippage"]) / thresholds.tick_size
    checks = [
        _threshold_check("orders", all_metrics["orders"], ">=", thresholds.min_orders),
        _threshold_check("live_fill_rate", all_metrics["live_fill_rate"], ">=", thresholds.min_live_fill_rate),
        _threshold_check("mismatch_rate", all_metrics["mismatch_rate"], "<=", thresholds.max_mismatch_rate),
        _threshold_check("overfill_rate", all_metrics["overfill_rate"], "<=", thresholds.max_overfill_rate),
        _threshold_check("unmatched_fills", unmatched_fills, "<=", thresholds.max_unmatched_fills),
    ]
    if thresholds.max_adverse_slippage_ticks is not None:
        checks.append(
            _threshold_check(
                "max_adverse_slippage_ticks",
                max_adverse_ticks,
                "<=",
                thresholds.max_adverse_slippage_ticks,
            )
        )
    return pd.DataFrame(checks)


def _summary(all_metrics: pd.Series, all_recommendation: pd.Series, checks: pd.DataFrame) -> pd.DataFrame:
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 1
    ready = failed == 0
    return pd.DataFrame(
        [
            {
                "ready": ready,
                "orders": int(all_metrics["orders"]),
                "live_fill_rate": float(all_metrics["live_fill_rate"]),
                "avg_fill_ratio": float(all_metrics["avg_fill_ratio"]),
                "recommended_queue_conservatism": float(all_recommendation["recommended_queue_conservatism"]),
                "recommended_order_latency_us": float(all_recommendation["recommended_order_latency_us"]),
                "recommended_slippage_ticks": float(all_recommendation["recommended_slippage_ticks"]),
                "recommended_min_edge_ticks": float(all_recommendation["recommended_min_edge_ticks"]),
                "failed_checks": failed,
                "recommendation": "use_recommended_fill_model" if ready else "collect_more_shadow_data_or_tighten_simulation",
            }
        ]
    )


def _config(
    recommendations: pd.DataFrame,
    summary: pd.Series,
    checks: pd.DataFrame,
    thresholds: FillModelCalibrationThresholds,
) -> dict[str, Any]:
    global_row = recommendations.iloc[0]
    return {
        "schema_version": 1,
        "ready": bool(summary["ready"]),
        "tick_size": float(thresholds.tick_size),
        "global": {
            "queue_conservatism": float(global_row["recommended_queue_conservatism"]),
            "order_latency_us": float(global_row["recommended_order_latency_us"]),
            "slippage_ticks": float(global_row["recommended_slippage_ticks"]),
            "min_edge_ticks": float(global_row["recommended_min_edge_ticks"]),
        },
        "by_instrument": [
            {
                "instrument_id": str(row.instrument_id),
                "queue_conservatism": float(row.recommended_queue_conservatism),
                "order_latency_us": float(row.recommended_order_latency_us),
                "slippage_ticks": float(row.recommended_slippage_ticks),
                "min_edge_ticks": float(row.recommended_min_edge_ticks),
            }
            for row in recommendations.iloc[1:].itertuples(index=False)
        ],
        "thresholds": asdict(thresholds),
        "failed_checks": checks.loc[~checks["passed"].astype(bool), "check"].astype(str).tolist(),
    }


def _unmatched_fills(reconciliation_summary: pd.DataFrame) -> int:
    if reconciliation_summary.empty or "unmatched_fills" not in reconciliation_summary.columns:
        return 0
    value = pd.to_numeric(reconciliation_summary.iloc[0]["unmatched_fills"], errors="coerce")
    return int(value) if not pd.isna(value) else 0


def _threshold_check(name: str, value: float | int, operator: str, threshold: float | int) -> dict[str, object]:
    value_float = float(value)
    threshold_float = float(threshold)
    missing = np.isnan(value_float) or np.isnan(threshold_float)
    if operator == ">=":
        passed = (not missing) and value_float + 1e-12 >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value_float <= threshold_float + 1e-12
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} or threshold is unavailable"
    elif not passed:
        reason = f"{name} {value_float:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "check": name,
        "value": value_float,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": "" if passed else reason,
    }


def _quantile(values: pd.Series, quantile: float, *, default: float) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return float(default)
    return float(clean.quantile(quantile))


def _numeric_optional(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([np.nan] * len(frame), index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _validate_thresholds(thresholds: FillModelCalibrationThresholds) -> None:
    if thresholds.tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if thresholds.min_orders <= 0:
        raise ValueError("min_orders must be positive")
    for name in ("min_live_fill_rate", "max_mismatch_rate", "max_overfill_rate"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    for name in ("latency_quantile", "fill_ratio_quantile", "slippage_quantile"):
        value = getattr(thresholds, name)
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be between 0 and 1")
    if thresholds.max_unmatched_fills < 0:
        raise ValueError("max_unmatched_fills must be non-negative")
    if thresholds.max_adverse_slippage_ticks is not None and thresholds.max_adverse_slippage_ticks < 0:
        raise ValueError("max_adverse_slippage_ticks must be non-negative")
    if thresholds.min_queue_conservatism <= 0:
        raise ValueError("min_queue_conservatism must be positive")
    if thresholds.max_queue_conservatism < thresholds.min_queue_conservatism:
        raise ValueError("max_queue_conservatism must be >= min_queue_conservatism")
    if thresholds.base_edge_ticks < 0:
        raise ValueError("base_edge_ticks must be non-negative")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
