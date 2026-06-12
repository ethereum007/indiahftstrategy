from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class LeadLagEdgeThresholds:
    min_events: int = 1
    min_abs_correlation: float = 0.0
    min_correlation_samples: int = 2
    min_update_rate: float = 0.0
    max_median_update_ns: int | None = None
    min_best_latency_net_pnl: float = 0.0
    min_best_latency_fills: int = 1
    min_profitable_latency_ns: int = 0


@dataclass(frozen=True)
class LeadLagEdgeAudit:
    metrics: pd.DataFrame
    checks: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None

    @property
    def passed(self) -> bool:
        if self.summary.empty:
            return False
        return bool(self.summary.iloc[0]["passed"])


def evaluate_leadlag_edge(
    cross_correlation: pd.DataFrame,
    lag_profile: pd.DataFrame,
    latency_curve: pd.DataFrame,
    *,
    thresholds: LeadLagEdgeThresholds | None = None,
) -> LeadLagEdgeAudit:
    thresholds = thresholds or LeadLagEdgeThresholds()
    _validate_thresholds(thresholds)
    metrics = pd.DataFrame(
        [
            {
                **_correlation_metrics(cross_correlation),
                **_lag_profile_metrics(lag_profile),
                **_latency_metrics(latency_curve, thresholds),
            }
        ]
    )
    checks = _checks(metrics.iloc[0], thresholds)
    summary = _summary(metrics, checks)
    return LeadLagEdgeAudit(metrics=metrics, checks=checks, summary=summary)


def write_leadlag_edge_audit(
    measure_dir: str | Path,
    *,
    output_dir: str | Path,
    thresholds: LeadLagEdgeThresholds | None = None,
) -> LeadLagEdgeAudit:
    source = Path(measure_dir)
    cross_correlation = _read_required(source / "cross_correlation.csv")
    lag_profile = _read_required(source / "lag_profile.csv")
    latency_curve = _read_required(source / "latency_curve.csv")
    thresholds = thresholds or LeadLagEdgeThresholds()
    audit = evaluate_leadlag_edge(
        cross_correlation,
        lag_profile,
        latency_curve,
        thresholds=thresholds,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit.metrics.to_csv(out / "leadlag_edge_metrics.csv", index=False)
    audit.checks.to_csv(out / "leadlag_edge_checks.csv", index=False)
    audit.summary.to_csv(out / "leadlag_edge_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="leadlag_edge_audit",
        parameters={"thresholds": asdict(thresholds)},
        inputs={"measure": source},
    )
    return LeadLagEdgeAudit(audit.metrics, audit.checks, audit.summary, out)


def _correlation_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    _require(frame, ["lag_ns", "correlation", "samples"], "cross_correlation")
    work = frame.copy()
    work["abs_correlation"] = pd.to_numeric(work["correlation"], errors="coerce").abs()
    if work["abs_correlation"].notna().any():
        best = work.sort_values("abs_correlation", ascending=False).iloc[0]
        best_lag_ns = int(best["lag_ns"])
        best_correlation = float(best["correlation"])
        best_abs_correlation = float(best["abs_correlation"])
        best_samples = int(best["samples"])
    else:
        best_lag_ns = np.nan
        best_correlation = np.nan
        best_abs_correlation = np.nan
        best_samples = 0
    return {
        "correlation_rows": int(len(work)),
        "best_lag_ns": best_lag_ns,
        "best_correlation": best_correlation,
        "best_abs_correlation": best_abs_correlation,
        "best_correlation_samples": best_samples,
    }


def _lag_profile_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    _require(frame, ["event_ts", "time_to_update_ns", "updated_within_window"], "lag_profile")
    updated = frame["updated_within_window"].map(_to_bool)
    update_times = pd.to_numeric(frame.loc[updated, "time_to_update_ns"], errors="coerce").dropna()
    event_count = int(len(frame))
    updated_events = int(updated.sum())
    return {
        "event_count": event_count,
        "updated_events": updated_events,
        "update_rate": float(updated_events / event_count) if event_count else 0.0,
        "median_update_ns": float(update_times.median()) if not update_times.empty else np.nan,
        "p90_update_ns": float(update_times.quantile(0.9)) if not update_times.empty else np.nan,
    }


def _latency_metrics(frame: pd.DataFrame, thresholds: LeadLagEdgeThresholds) -> dict[str, Any]:
    _require(frame, ["latency_ns", "fills", "net_pnl"], "latency_curve")
    work = frame.copy()
    work["net_pnl"] = pd.to_numeric(work["net_pnl"], errors="coerce")
    work["fills"] = pd.to_numeric(work["fills"], errors="coerce").fillna(0)
    if work["net_pnl"].notna().any():
        best = work.sort_values(["net_pnl", "fills"], ascending=[False, False]).iloc[0]
        best_latency_ns = int(best["latency_ns"])
        best_net_pnl = float(best["net_pnl"])
        best_fills = int(best["fills"])
        best_win_rate = _float(best, "win_rate")
        best_avg_edge = _float(best, "avg_edge")
    else:
        best_latency_ns = np.nan
        best_net_pnl = np.nan
        best_fills = 0
        best_win_rate = np.nan
        best_avg_edge = np.nan

    viable = work.loc[
        (work["net_pnl"] >= thresholds.min_best_latency_net_pnl)
        & (work["fills"] >= thresholds.min_best_latency_fills)
    ]
    max_profitable_latency_ns = int(viable["latency_ns"].max()) if not viable.empty else np.nan
    return {
        "latency_rows": int(len(work)),
        "best_latency_ns": best_latency_ns,
        "best_latency_net_pnl": best_net_pnl,
        "best_latency_fills": best_fills,
        "best_latency_win_rate": best_win_rate,
        "best_latency_avg_edge": best_avg_edge,
        "viable_latency_rows": int(len(viable)),
        "max_profitable_latency_ns": max_profitable_latency_ns,
    }


def _checks(row: pd.Series, thresholds: LeadLagEdgeThresholds) -> pd.DataFrame:
    checks = [
        _threshold_check(row, "event_count", ">=", thresholds.min_events),
        _threshold_check(row, "best_abs_correlation", ">=", thresholds.min_abs_correlation),
        _threshold_check(row, "best_correlation_samples", ">=", thresholds.min_correlation_samples),
        _threshold_check(row, "update_rate", ">=", thresholds.min_update_rate),
        _threshold_check(row, "best_latency_net_pnl", ">=", thresholds.min_best_latency_net_pnl),
        _threshold_check(row, "best_latency_fills", ">=", thresholds.min_best_latency_fills),
        _threshold_check(row, "max_profitable_latency_ns", ">=", thresholds.min_profitable_latency_ns),
    ]
    if thresholds.max_median_update_ns is not None:
        checks.append(_threshold_check(row, "median_update_ns", "<=", thresholds.max_median_update_ns))
    return pd.DataFrame(checks)


def _summary(metrics: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    passed = bool(checks["passed"].all()) if not checks.empty else False
    failed = int((~checks["passed"].astype(bool)).sum()) if not checks.empty else 0
    metric = metrics.iloc[0]
    return pd.DataFrame(
        [
            {
                "passed": passed,
                "failed_checks": failed,
                "recommendation": "replay_or_sweep_candidate" if passed else "keep_researching",
                "event_count": int(metric["event_count"]),
                "best_lag_ns": metric["best_lag_ns"],
                "best_abs_correlation": metric["best_abs_correlation"],
                "update_rate": metric["update_rate"],
                "best_latency_ns": metric["best_latency_ns"],
                "best_latency_net_pnl": metric["best_latency_net_pnl"],
                "max_profitable_latency_ns": metric["max_profitable_latency_ns"],
            }
        ]
    )


def _threshold_check(row: pd.Series, name: str, operator: str, threshold: float | int) -> dict[str, Any]:
    value = _float(row, name)
    threshold_float = float(threshold)
    missing = np.isnan(value)
    if operator == ">=":
        passed = (not missing) and value >= threshold_float
    elif operator == "<=":
        passed = (not missing) and value <= threshold_float
    else:
        raise ValueError(f"unsupported operator {operator!r}")
    reason = ""
    if missing:
        reason = f"{name} is unavailable"
    elif not passed:
        reason = f"{name} {value:.6g} failed {operator} {threshold_float:.6g}"
    return {
        "check": name,
        "value": value,
        "operator": operator,
        "threshold": threshold_float,
        "passed": bool(passed),
        "reason": reason,
    }


def _validate_thresholds(thresholds: LeadLagEdgeThresholds) -> None:
    if thresholds.min_events < 0:
        raise ValueError("min_events must be non-negative")
    if thresholds.min_correlation_samples < 0:
        raise ValueError("min_correlation_samples must be non-negative")
    if thresholds.min_best_latency_fills < 0:
        raise ValueError("min_best_latency_fills must be non-negative")
    if thresholds.min_profitable_latency_ns < 0:
        raise ValueError("min_profitable_latency_ns must be non-negative")
    if not 0 <= thresholds.min_update_rate <= 1:
        raise ValueError("min_update_rate must be between 0 and 1")
    if thresholds.min_abs_correlation < 0:
        raise ValueError("min_abs_correlation must be non-negative")


def _read_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"required lead-lag measure artifact missing: {path}")
    return pd.read_csv(path)


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _float(row: pd.Series, column: str) -> float:
    return float(row[column]) if column in row and not pd.isna(row[column]) else np.nan


def _to_bool(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)
